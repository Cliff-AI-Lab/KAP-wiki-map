"""LLM 演化提议器（决策书 §5.3 LLM 提议 + SME 审批）。

4 种监测条件（M3 #1 + M5 #1 完整版）：

1. **同类未匹配实体累计超阈值** → 提议新实体类型（M3 #1）
2. **SME 自定义关系反复出现** → 提议固化进本体（M5 #1）
3. **关系类型在不同语境语义漂移** → 提议拆分（M5 #1）
4. **行业标准升版** → 提议本体扩展（M5 #1）

设计原则（feedback memory · AI native + 轻量化）：
- 函数式实现，单文件
- LLM 失败静默降级（返回 None，不阻断扫描循环）
- 置信度 < 0.3 视为不可用，让 SME 知道需细分
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from packages.common import get_logger
from packages.common.types import (
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyRelationType,
    OntologyVersion,
)
import os

from packages.distillation.llm_client import acall_llm_json
from packages.observability.prompt_versions import resolve_active_system_prompt


def _current_llm_language() -> str:
    """M15 #3：读 KAP_LLM_LANG 环境变量；默认 zh。"""
    return (os.environ.get("KAP_LLM_LANG") or "zh").strip() or "zh"
from packages.ontology.base import get_current_l1, get_current_l2
from packages.ontology.prompts import (
    ENTITY_TYPE_PROPOSE_SYSTEM,
    ENTITY_TYPE_PROPOSE_USER,
    RELATION_SOLIDIFY_SYSTEM,
    RELATION_SOLIDIFY_USER,
    RELATION_SPLIT_SYSTEM,
    RELATION_SPLIT_USER,
    STANDARD_UPGRADE_SYSTEM,
    STANDARD_UPGRADE_USER,
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
        # M12 #1 · LLM 自学习闭环：active PromptVersion 优先；无则 fallback 硬编码
        # M15 #3 · 按 KAP_LLM_LANG 选语言版本
        sys_prompt = resolve_active_system_prompt(
            "new_entity_type", ENTITY_TYPE_PROPOSE_SYSTEM,
            language=_current_llm_language(),
        )
        data = await acall_llm_json(sys_prompt, user_prompt)
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


def _format_existing_relations(industry_code: str, project_id: str) -> str:
    """组装现有 L1 + L2 已注册关系类型的 prompt 段落（监测条件 2/3 用）。"""
    lines: list[str] = []
    l1 = get_current_l1(industry_code) if industry_code else None
    if l1 and l1.relation_types:
        lines.append(f"### L1 ({industry_code} 行业基础)")
        for rt in l1.relation_types:
            lines.append(f"- {rt.type_id} ({rt.type_name})")
    l2 = get_current_l2(project_id) if project_id else None
    if l2 and l2.relation_types:
        lines.append(f"### L2 ({project_id} 客户私有)")
        for rt in l2.relation_types:
            lines.append(f"- {rt.type_id} ({rt.type_name})")
    return "\n".join(lines) if lines else "（无）"


def _lookup_relation_name(
    industry_code: str, project_id: str, relation_type_id: str
) -> str:
    """L1 + L2 查指定 relation_type_id 的中文名（找不到返回空串）。"""
    for v in (
        get_current_l2(project_id) if project_id else None,
        get_current_l1(industry_code) if industry_code else None,
    ):
        if not v:
            continue
        for rt in v.relation_types:
            if rt.type_id == relation_type_id:
                return rt.type_name
    return ""


# ════════════════════════════════════════════════════════════════════════
#  监测条件 2/3/4 完整 LLM 实现（M5 #1）
# ════════════════════════════════════════════════════════════════════════

_RELATION_SOLIDIFY_THRESHOLD = 20
_RELATION_SPLIT_THRESHOLD = 30


async def propose_relation_solidification(
    usage_records: list[dict],
    *,
    project_id: str,
    industry_code: str = "",
    threshold: int = _RELATION_SOLIDIFY_THRESHOLD,
) -> OntologyEvolutionProposal | None:
    """监测条件 2：自定义关系反复出现 → 提议固化进本体（决策书 §5.3）。

    usage_records 字段约定（来自 SME 在审核台手工标注的"自定义关系"记录）：
    - relation: 关系名（必填）
    - source / target: 源 / 目标实体名（可选）
    - note: 上下文备注（可选）

    Returns:
        Proposal（包含 proposed_relation_type）或 None（数量未达阈值 / LLM 失败 / 置信度过低）
    """
    if len(usage_records) < threshold:
        log.info(
            "evolution_relation_below_threshold",
            count=len(usage_records), threshold=threshold,
        )
        return None

    sample_lines: list[str] = []
    for rec in usage_records[:25]:
        rel = str(rec.get("relation", "")).strip()
        src = str(rec.get("source", "")).strip()
        tgt = str(rec.get("target", "")).strip()
        note = str(rec.get("note", "")).strip()
        line = f"- {rel}"
        if src or tgt:
            line += f": {src} → {tgt}"
        if note:
            line += f"  ({note})"
        sample_lines.append(line)

    user_prompt = RELATION_SOLIDIFY_USER.format(
        existing_relations=_format_existing_relations(industry_code, project_id),
        existing_entities=_format_existing_types(industry_code, project_id),
        evidence_count=len(usage_records),
        usage_samples="\n".join(sample_lines),
    )

    try:
        sys_prompt = resolve_active_system_prompt(
            "relation_solidification", RELATION_SOLIDIFY_SYSTEM,
            language=_current_llm_language(),
        )
        data = await acall_llm_json(sys_prompt, user_prompt)
    except Exception as e:
        log.warning("evolution_relation_llm_failed", error=str(e))
        return None

    type_id = (data.get("type_id") or "").strip()
    type_name = (data.get("type_name") or "").strip()
    if not type_id or not type_name:
        log.warning("evolution_relation_llm_missing_fields", data=str(data)[:120])
        return None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    if confidence < _MIN_LLM_CONFIDENCE:
        log.info(
            "evolution_relation_low_confidence",
            confidence=confidence, threshold=_MIN_LLM_CONFIDENCE,
        )
        return None

    examples = data.get("examples") or []
    if isinstance(examples, list):
        examples = [
            str(e)[:80] for e in examples[:8]
            if isinstance(e, (str, int, float))
        ]
    else:
        examples = []

    source_types = data.get("source_types") or []
    target_types = data.get("target_types") or []
    if not isinstance(source_types, list):
        source_types = []
    if not isinstance(target_types, list):
        target_types = []
    source_types = [str(t)[:40] for t in source_types[:8]]
    target_types = [str(t)[:40] for t in target_types[:8]]

    proposed = OntologyRelationType(
        type_id=type_id,
        type_name=type_name,
        description=str(data.get("description", ""))[:200],
        layer="L2",
        source_types=source_types,
        target_types=target_types,
        examples=examples,
    )

    sample_names = [
        str(rec.get("relation", "")).strip()
        for rec in usage_records[:10]
        if rec.get("relation")
    ]

    return OntologyEvolutionProposal(
        proposal_id=f"onto_{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        layer="L2",
        proposed_relation_type=proposed,
        evidence_count=len(usage_records),
        sample_entities=sample_names,
        reasoning=str(data.get("reasoning", ""))[:200],
        status="pending",
    )


async def propose_relation_split_for_drift(
    samples: list[dict],
    *,
    project_id: str,
    relation_type_id: str,
    industry_code: str = "",
    threshold: int = _RELATION_SPLIT_THRESHOLD,
) -> list[OntologyEvolutionProposal] | None:
    """监测条件 3：现有关系类型在不同语境下语义漂移 → 提议拆分（决策书 §5.3）。

    samples 字段约定：
    - source / target: 实际使用中的实体对（可选）
    - context: 上下文短语（可选，帮 LLM 聚类）

    Returns:
        list[Proposal]（每个对应一个拆分目标关系）或 None（不需拆分 / LLM 失败 / 置信度过低）
    """
    if len(samples) < threshold:
        log.info(
            "evolution_split_below_threshold",
            count=len(samples), threshold=threshold,
        )
        return None
    if not relation_type_id:
        return None

    sample_lines: list[str] = []
    for rec in samples[:30]:
        src = str(rec.get("source", "")).strip()
        tgt = str(rec.get("target", "")).strip()
        ctx = str(rec.get("context", "")).strip()
        line = f"- {src} → {tgt}" if (src or tgt) else "-"
        if ctx:
            line += f"  ::  {ctx}"
        sample_lines.append(line)

    relation_name = _lookup_relation_name(industry_code, project_id, relation_type_id)
    user_prompt = RELATION_SPLIT_USER.format(
        relation_type_id=relation_type_id,
        relation_name=relation_name or relation_type_id,
        existing_relations=_format_existing_relations(industry_code, project_id),
        sample_count=len(samples),
        samples="\n".join(sample_lines),
    )

    try:
        sys_prompt = resolve_active_system_prompt(
            "relation_split", RELATION_SPLIT_SYSTEM,
            language=_current_llm_language(),
        )
        data = await acall_llm_json(sys_prompt, user_prompt)
    except Exception as e:
        log.warning("evolution_split_llm_failed", error=str(e))
        return None

    if not data.get("should_split"):
        log.info(
            "evolution_split_not_needed",
            relation=relation_type_id,
            reasoning=str(data.get("reasoning", ""))[:80],
        )
        return None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    if confidence < _MIN_LLM_CONFIDENCE:
        log.info(
            "evolution_split_low_confidence",
            confidence=confidence, threshold=_MIN_LLM_CONFIDENCE,
        )
        return None

    split_into = data.get("split_into") or []
    if not isinstance(split_into, list) or len(split_into) < 2:
        log.warning("evolution_split_invalid_split_into", data=str(data)[:200])
        return None

    base_reasoning = str(data.get("reasoning", ""))[:160]
    proposals: list[OntologyEvolutionProposal] = []
    for item in split_into:
        if not isinstance(item, dict):
            continue
        new_id = (item.get("type_id") or "").strip()
        new_name = (item.get("type_name") or "").strip()
        if not new_id or not new_name:
            continue

        item_examples = item.get("examples") or []
        if isinstance(item_examples, list):
            item_examples = [
                str(e)[:80] for e in item_examples[:8]
                if isinstance(e, (str, int, float))
            ]
        else:
            item_examples = []

        src_types = item.get("source_types") or []
        tgt_types = item.get("target_types") or []
        if not isinstance(src_types, list):
            src_types = []
        if not isinstance(tgt_types, list):
            tgt_types = []

        proposed = OntologyRelationType(
            type_id=new_id,
            type_name=new_name,
            description=str(item.get("description", ""))[:200],
            layer="L2",
            source_types=[str(t)[:40] for t in src_types[:8]],
            target_types=[str(t)[:40] for t in tgt_types[:8]],
            examples=item_examples,
        )

        proposals.append(OntologyEvolutionProposal(
            proposal_id=f"onto_{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            layer="L2",
            proposed_relation_type=proposed,
            evidence_count=len(samples),
            sample_entities=[relation_type_id],
            reasoning=f"拆分自 {relation_type_id}：{base_reasoning}",
            status="pending",
        ))

    return proposals or None


async def propose_standard_upgrade(
    industry_code: str,
    new_standards: list[str],
    *,
    project_id: str,
) -> OntologyEvolutionProposal | None:
    """监测条件 4：行业标准升版（GB / IEC 新版）→ 提议本体扩展（决策书 §5.3）。

    监测客户文档中引用的标准版本，对比 L1 ``standard`` 实体类型的 examples，
    LLM 判断是否应升版（新版替代旧版，旧版标 [作废] 保留以便溯源）。

    Returns:
        Proposal（proposed_entity_type 含更新后的 examples 列表）或 None
    """
    if not new_standards:
        return None

    l1 = get_current_l1(industry_code) if industry_code else None
    standard_type: OntologyEntityType | None = None
    if l1:
        for et in l1.entity_types:
            if et.type_id == "standard":
                standard_type = et
                break

    if standard_type is None:
        log.warning(
            "evolution_standard_no_type_in_l1",
            industry=industry_code,
            note="L1 未注册 standard 实体类型，跳过升版提议",
        )
        return None

    current_examples_text = (
        "\n".join(f"- {ex}" for ex in standard_type.examples)
        if standard_type.examples else "（空）"
    )
    new_std_text = "\n".join(f"- {s}" for s in new_standards[:50])

    user_prompt = STANDARD_UPGRADE_USER.format(
        industry_code=industry_code,
        industry_name=_industry_name(industry_code),
        current_examples=current_examples_text,
        standard_count=len(new_standards),
        new_standards=new_std_text,
    )

    try:
        sys_prompt = resolve_active_system_prompt(
            "standard_upgrade", STANDARD_UPGRADE_SYSTEM,
            language=_current_llm_language(),
        )
        data = await acall_llm_json(sys_prompt, user_prompt)
    except Exception as e:
        log.warning("evolution_standard_llm_failed", error=str(e))
        return None

    if not data.get("should_upgrade"):
        log.info(
            "evolution_standard_not_needed",
            industry=industry_code,
            reasoning=str(data.get("reasoning", ""))[:80],
        )
        return None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    if confidence < _MIN_LLM_CONFIDENCE:
        log.info(
            "evolution_standard_low_confidence",
            confidence=confidence, threshold=_MIN_LLM_CONFIDENCE,
        )
        return None

    new_examples = data.get("new_examples") or []
    if not isinstance(new_examples, list):
        new_examples = []
    new_examples = [
        str(e)[:80] for e in new_examples[:30]
        if isinstance(e, (str, int, float))
    ]
    if not new_examples:
        # LLM 没给 → 降级：合并旧 examples + 新标准
        new_examples = list(standard_type.examples) + [
            str(s)[:80] for s in new_standards
        ]

    upgrades = data.get("upgrades") or []
    upgrade_summary_parts: list[str] = []
    if isinstance(upgrades, list):
        for u in upgrades[:5]:
            if isinstance(u, dict):
                old = str(u.get("old", "")).strip()
                new = str(u.get("new", "")).strip()
                if old or new:
                    upgrade_summary_parts.append(f"{old} → {new}")

    proposed = OntologyEntityType(
        type_id=standard_type.type_id,
        type_name=standard_type.type_name,
        description=standard_type.description,
        layer="L2",
        parent_type_id=standard_type.type_id,  # L2 继承 L1 standard
        examples=new_examples,
    )

    summary = "; ".join(upgrade_summary_parts)
    base = str(data.get("reasoning", "")).strip()
    reasoning = (f"{summary} | {base}" if summary else base)[:200]

    return OntologyEvolutionProposal(
        proposal_id=f"onto_{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        layer="L2",
        proposed_entity_type=proposed,
        evidence_count=len(new_standards),
        sample_entities=[str(s)[:80] for s in new_standards[:10]],
        reasoning=reasoning,
        status="pending",
    )
