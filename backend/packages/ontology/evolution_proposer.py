"""LLM 演化提议器（决策书 §5.3 LLM 提议 + SME 审批）。

监测条件 1（M3 lite 仅做最简）：
  **同类未匹配实体累计超阈值 → 提议新实体类型**

实现：
1. ``monitor_unmatched_entities``：扫 graph_store 找未挂 entity_type 或 type 不在
   L1+L2 注册集合的实体，按数量阈值触发
2. ``propose_new_entity_type``：调 LLM 归纳新类型 → 返回 OntologyEvolutionProposal
3. LLM 失败 / 置信度低（< 0.3）→ 返回 None 不入审核台

监测条件 2/3/4（M4 后续）：
- 自定义关系反复出现 → 提议固化进本体
- 关系语义漂移 → 提议拆分
- 行业标准升版 → 提议本体扩展

设计原则（feedback memory · AI native + 轻量化）：
- 函数式实现，单文件
- LLM 失败静默降级（不阻断扫描循环）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from packages.common import get_logger
from packages.common.types import (
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyVersion,
)
from packages.distillation.llm_client import acall_llm_json
from packages.ontology.base import get_current_l1, get_current_l2
from packages.ontology.prompts import (
    ENTITY_TYPE_PROPOSE_SYSTEM,
    ENTITY_TYPE_PROPOSE_USER,
)

log = get_logger("ontology.evolution_proposer")


# ════════════════════════════════════════════════════════════════════════
#  监测器
# ════════════════════════════════════════════════════════════════════════


@dataclass
class UnmatchedEntityBatch:
    """未匹配实体批次（监测器输出）。"""
    industry_code: str
    project_id: str
    sample_names: list[str]
    total_count: int


def collect_unmatched_entities(
    *,
    industry_code: str,
    project_id: str,
    candidate_entity_names: list[str],
    threshold: int = 50,
    sample_limit: int = 20,
) -> UnmatchedEntityBatch | None:
    """根据已注册的 L1+L2 类型，过滤出未匹配的实体。

    M3 lite：调用方传入 candidate_entity_names（如从 graph_store 提取的实体名列表，
    或从蒸馏管线累计的"无类型"实体）。监测器只判断 count >= threshold。

    Args:
        industry_code: 客户行业 code（用于查 L1）
        project_id: 用于查 L2
        candidate_entity_names: 候选实体名列表（已经从 graph_store 提取）
        threshold: 触发阈值（决策书 §5.3 默认 50）
        sample_limit: 入提议器的样本数

    Returns:
        UnmatchedEntityBatch 或 None（未达阈值）
    """
    if not candidate_entity_names:
        return None

    # 收集已注册类型的所有 example 名（L1 + L2）
    known_examples: set[str] = set()
    l1 = get_current_l1(industry_code)
    if l1:
        for et in l1.entity_types:
            known_examples.update(et.examples)
    l2 = get_current_l2(project_id)
    if l2:
        for et in l2.entity_types:
            known_examples.update(et.examples)

    # 过滤出未匹配的（即不在任何已注册类型 example 集合内）
    # 实际生产中实体应该有显式 type；M3 lite 用 example 字符串匹配近似
    unmatched = [
        name for name in candidate_entity_names
        if name and name not in known_examples
    ]

    if len(unmatched) < threshold:
        log.info(
            "ontology_unmatched_below_threshold",
            count=len(unmatched), threshold=threshold,
        )
        return None

    return UnmatchedEntityBatch(
        industry_code=industry_code,
        project_id=project_id,
        sample_names=unmatched[:sample_limit],
        total_count=len(unmatched),
    )


# ════════════════════════════════════════════════════════════════════════
#  LLM 提议器
# ════════════════════════════════════════════════════════════════════════


_MIN_LLM_CONFIDENCE = 0.3


async def propose_new_entity_type(
    batch: UnmatchedEntityBatch,
) -> OntologyEvolutionProposal | None:
    """调 LLM 归纳新实体类型 → OntologyEvolutionProposal（待 SME 审批）。

    Returns:
        Proposal 或 None（LLM 失败 / 置信度过低）
    """
    # 构造 prompt
    existing_types = _format_existing_types(batch.industry_code, batch.project_id)
    industry_name = _industry_name(batch.industry_code)
    sample_text = "\n".join(f"- {name}" for name in batch.sample_names)

    user_prompt = ENTITY_TYPE_PROPOSE_USER.format(
        existing_types=existing_types,
        industry_code=batch.industry_code,
        industry_name=industry_name,
        evidence_count=batch.total_count,
        sample_entities=sample_text,
    )

    try:
        data = await acall_llm_json(ENTITY_TYPE_PROPOSE_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("ontology_propose_llm_failed", error=str(e))
        return None

    type_id = (data.get("type_id") or "").strip()
    type_name = (data.get("type_name") or "").strip()
    if not type_id or not type_name:
        log.warning("ontology_propose_llm_missing_fields", data=str(data)[:120])
        return None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    if confidence < _MIN_LLM_CONFIDENCE:
        log.info(
            "ontology_propose_low_confidence_skipped",
            confidence=confidence, threshold=_MIN_LLM_CONFIDENCE,
        )
        return None

    examples = data.get("examples") or []
    if isinstance(examples, list):
        examples = [str(e)[:40] for e in examples[:8] if isinstance(e, (str, int, float))]
    else:
        examples = []
    if not examples:
        examples = batch.sample_names[:5]

    proposed = OntologyEntityType(
        type_id=type_id,
        type_name=type_name,
        description=str(data.get("description", ""))[:200],
        layer="L2",
        parent_type_id=str(data.get("parent_type_id", "") or ""),
        examples=examples,
    )

    return OntologyEvolutionProposal(
        proposal_id=f"onto_{uuid.uuid4().hex[:10]}",
        project_id=batch.project_id,
        layer="L2",
        proposed_entity_type=proposed,
        evidence_count=batch.total_count,
        sample_entities=batch.sample_names[:10],
        reasoning=str(data.get("reasoning", ""))[:200],
        status="pending",
    )


# ════════════════════════════════════════════════════════════════════════
#  辅助
# ════════════════════════════════════════════════════════════════════════


def _format_existing_types(industry_code: str, project_id: str) -> str:
    """组装现有 L1 + L2 已注册类型的 prompt 段落。"""
    lines: list[str] = []
    l1 = get_current_l1(industry_code)
    if l1:
        lines.append(f"### L1 ({industry_code} 行业基础)")
        for et in l1.entity_types:
            lines.append(f"- {et.type_id} ({et.type_name})")
    l2 = get_current_l2(project_id)
    if l2 and l2.entity_types:
        lines.append(f"### L2 ({project_id} 客户私有)")
        for et in l2.entity_types:
            lines.append(f"- {et.type_id} ({et.type_name})")
    return "\n".join(lines) if lines else "（无）"


_INDUSTRY_NAME_MAP = {
    "manufacturing": "制造业",
    "energy": "能源",
    "finance": "金融",
    "healthcare": "医疗",
    "it": "IT",
}


def _industry_name(code: str) -> str:
    return _INDUSTRY_NAME_MAP.get(code, code)
