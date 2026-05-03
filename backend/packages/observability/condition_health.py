"""监测条件 LLM 自学习（M10 #2 · 决策书 §5.3）。

把 SME 历史 approve / reject 决策按 4 监测条件分组，反哺 prompt 调优建议。
不实际改 prompt（prompt 改动需 SME 审），仅生成调优报告。

4 监测条件（同 evolution_proposer.py）：
1. **new_entity_type** — 未匹配实体累计超阈值 → 新实体类型
2. **relation_solidification** — 自定义关系反复出现 → 固化进本体
3. **relation_split** — 关系语义漂移 → 拆分（reasoning 以 "拆分自" 开头）
4. **standard_upgrade** — 行业标准升版（proposed_entity_type.type_id == "standard"）

判定规则（启发式）：
- proposed_relation_type 非空 + reasoning startswith "拆分自" → relation_split
- proposed_relation_type 非空                              → relation_solidification
- proposed_entity_type.type_id == "standard"             → standard_upgrade
- proposed_entity_type 非空                                → new_entity_type
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.types import OntologyEvolutionProposal

log = get_logger("observability.condition_health")


ConditionType = Literal[
    "new_entity_type",
    "relation_solidification",
    "relation_split",
    "standard_upgrade",
    "unknown",
]


class ConditionHealth(BaseModel):
    """单监测条件的健康度统计（M10 #2）。"""
    condition_type: ConditionType
    total: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    approve_rate: float = 0.0       # approved / (approved + rejected)
    common_reject_reasons: list[str] = Field(default_factory=list)  # top 3
    tuning_suggestion: str = ""           # 已国际化中文（zh fallback）
    suggestion_code: str = ""              # M21 i18n · 前端按 code 渲染（low_samples / all_pending / low_approve / high_approve / mid_approve / unclassified）
    suggestion_params: dict = Field(default_factory=dict)   # 渲染参数（如 approve_rate, sample_count）


# 启发式阈值（可后续按运行数据校准）
_LOW_APPROVE_RATE = 0.3
_HIGH_APPROVE_RATE = 0.7
_MIN_SAMPLES_FOR_JUDGMENT = 5
_TOP_REJECT_REASONS = 3


def classify_condition(proposal: OntologyEvolutionProposal) -> ConditionType:
    """按 proposal 内容推断监测条件类型。"""
    if proposal.proposed_relation_type is not None:
        if (proposal.reasoning or "").startswith("拆分自"):
            return "relation_split"
        return "relation_solidification"
    if proposal.proposed_entity_type is not None:
        if proposal.proposed_entity_type.type_id == "standard":
            return "standard_upgrade"
        return "new_entity_type"
    return "unknown"


def _extract_reject_reason(reasoning: str) -> str:
    """从 reasoning 中提取 SME 驳回理由（ontology.reject_proposal 用 ' | SME 驳回: ...' 拼接）。"""
    marker = "SME 驳回:"
    idx = reasoning.find(marker)
    if idx < 0:
        return ""
    reason = reasoning[idx + len(marker):].strip().strip("|").strip()
    if reason in ("无理由", ""):
        return ""
    return reason[:80]


def _top_reject_reasons(rejected: list[OntologyEvolutionProposal]) -> list[str]:
    """提取 top N 高频驳回理由（精确串相同视为同类；未来可加聚类）。"""
    freq: dict[str, int] = {}
    for p in rejected:
        reason = _extract_reject_reason(p.reasoning)
        if reason:
            freq[reason] = freq.get(reason, 0) + 1
    sorted_reasons = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [r for r, _ in sorted_reasons[:_TOP_REJECT_REASONS]]


def _make_suggestion(
    *, condition_type: ConditionType, total: int,
    approved: int, rejected: int, approve_rate: float,
) -> tuple[str, str, dict]:
    """返回 (中文文案 fallback, suggestion_code, suggestion_params)。

    code 列表（前端 i18n 字典 condhealth.suggest.* 渲染）：
    - low_samples       样本不足
    - all_pending       全部 pending
    - low_approve       接受率偏低
    - mid_approve       中等接受率
    - high_approve      接受率高（健康）
    """
    if total < _MIN_SAMPLES_FOR_JUDGMENT:
        return (
            f"样本不足 ({total} < {_MIN_SAMPLES_FOR_JUDGMENT})，暂无法评估 prompt 健康度",
            "low_samples",
            {"total": total, "min_samples": _MIN_SAMPLES_FOR_JUDGMENT},
        )
    decided = approved + rejected
    if decided == 0:
        return (
            "全部 pending，等 SME 审批后再评估",
            "all_pending",
            {},
        )
    pct = f"{approve_rate:.0%}"
    if approve_rate < _LOW_APPROVE_RATE:
        return (
            f"接受率偏低 ({pct})，建议收紧触发阈值或细化 prompt 例子；"
            f"可参考 common_reject_reasons 调优",
            "low_approve",
            {"approve_rate_pct": pct},
        )
    if approve_rate >= _HIGH_APPROVE_RATE:
        return (
            f"接受率高 ({pct})，prompt 健康",
            "high_approve",
            {"approve_rate_pct": pct},
        )
    return (
        f"中等接受率 ({pct})，建议样本扩大后再评估；可关注 common_reject_reasons",
        "mid_approve",
        {"approve_rate_pct": pct},
    )


def analyze_condition_health(
    proposals: list[OntologyEvolutionProposal],
) -> dict[str, ConditionHealth]:
    """按监测条件分组聚合 proposals，返回 {condition_type: ConditionHealth}。

    Args:
        proposals: 当前所有提议（含 pending / approved / rejected）

    Returns:
        固定 4 个 condition_type key（unknown 类不返回，除非有该类样本）
    """
    by_type: dict[str, list[OntologyEvolutionProposal]] = {}
    for p in proposals:
        ct = classify_condition(p)
        by_type.setdefault(ct, []).append(p)

    out: dict[str, ConditionHealth] = {}
    # 4 个核心条件强制返回（即使无样本，前端能稳定渲染）
    for ct in [
        "new_entity_type", "relation_solidification",
        "relation_split", "standard_upgrade",
    ]:
        items = by_type.get(ct, [])
        approved = [p for p in items if p.status == "approved"]
        rejected = [p for p in items if p.status == "rejected"]
        pending = [p for p in items if p.status == "pending"]
        decided = len(approved) + len(rejected)
        approve_rate = round(
            len(approved) / decided, 4,
        ) if decided > 0 else 0.0

        suggestion_text, suggestion_code, suggestion_params = _make_suggestion(
            condition_type=ct,                # type: ignore[arg-type]
            total=len(items),
            approved=len(approved),
            rejected=len(rejected),
            approve_rate=approve_rate,
        )
        out[ct] = ConditionHealth(
            condition_type=ct,                   # type: ignore[arg-type]
            total=len(items),
            approved=len(approved),
            rejected=len(rejected),
            pending=len(pending),
            approve_rate=approve_rate,
            common_reject_reasons=_top_reject_reasons(rejected),
            tuning_suggestion=suggestion_text,
            suggestion_code=suggestion_code,
            suggestion_params=suggestion_params,
        )

    # unknown 类型有样本时也返回
    if "unknown" in by_type:
        items = by_type["unknown"]
        out["unknown"] = ConditionHealth(
            condition_type="unknown",
            total=len(items),
            approved=sum(1 for p in items if p.status == "approved"),
            rejected=sum(1 for p in items if p.status == "rejected"),
            pending=sum(1 for p in items if p.status == "pending"),
            tuning_suggestion="无法分类的提议（缺 entity_type 和 relation_type）",
            suggestion_code="unclassified",
        )

    log.info("condition_health_analyzed",
             total_proposals=len(proposals),
             condition_count=len(out))
    return out
