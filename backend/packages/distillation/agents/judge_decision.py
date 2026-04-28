"""Judge 决策纯函数（M0-tech-debt 坑 3 改造产物）。

把硬编码在 ``judge.py`` 里的 if/elif 决策树拆出来，做成纯函数 ``decide()``。
好处：

- **可单测**：不依赖 LLM、不依赖文档对象、不依赖外部 IO
- **可配置**：阈值通过 ``JudgeThresholds`` dataclass 传入，按行业模板覆盖
- **可观测**：返回的 ``DecisionOutcome`` 含 ``rule_hit`` 字段，便于审计追溯
- **新增 REVIEW 通道**：KPI 居中 + 低置信度时不强行决策，flag ``needs_review``
  让文档进入 W4 SME 复核队列（决策书 §5.2）

决策规则（从严到宽，命中即返回）：

  规则 R1 · 极低 KPI + LLM 也丢 → DISCARD
  规则 R2 · LLM 高置信度 DISCARD → DISCARD
  规则 R3 · KPI 落入 review 带 + 置信度低 → 保留 LLM 决策但 flag needs_review
  规则 R4 · KPI 低于归档线 或 LLM 判归档 → ARCHIVE
  规则 R5 · 默认采用 LLM 原始判定
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.common.types import Decision
from packages.distillation.scoring.judge_thresholds import JudgeThresholds


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """Judge 综合决策结果（决策 + 复核标记 + 命中规则）。"""

    decision: Decision
    needs_review: bool
    rule_hit: str            # "R1" / "R2" / ... 命中的规则编号，便于审计
    reason: str              # 人类可读说明
    thresholds_source: str   # 用了哪个阈值集（来自 JudgeThresholds.source）


def decide(
    kpi: float,
    llm_decision: Decision,
    confidence: float,
    thresholds: JudgeThresholds,
) -> DecisionOutcome:
    """综合 KPI、LLM 决策、置信度，输出最终决策（含 needs_review 标记）。

    Args:
        kpi: ``compute_kpi_retain()`` 计算出的保留指数 ∈ [0, 1]
        llm_decision: LLM 给出的初步决策（KEEP / ARCHIVE / DISCARD）
        confidence: LLM 决策置信度 ∈ [0, 1]
        thresholds: 阈值集，通常来自 ``load_thresholds(industry)``

    Returns:
        ``DecisionOutcome``：含最终决策、needs_review 标记、命中规则编号、文字理由

    Notes:
        - 本函数是纯函数（无 IO、无副作用、无随机），同样输入永远产出同样输出
        - 不修改入参；返回的 ``DecisionOutcome`` 是 frozen 的
        - 边界值用 ``<`` 而非 ``≤``：DISCARD/ARCHIVE 阈值都是"严格小于"才进入更严档位
    """
    # 防御性 clamp：异常输入不应让规则错乱
    kpi = max(0.0, min(kpi, 1.0))
    confidence = max(0.0, min(confidence, 1.0))

    # ── 规则 R1：极低 KPI + LLM 也判 DISCARD → 双信号确认丢弃
    if kpi < thresholds.discard_threshold and llm_decision == Decision.DISCARD:
        return DecisionOutcome(
            decision=Decision.DISCARD,
            needs_review=False,
            rule_hit="R1",
            reason=(
                f"KPI {kpi:.3f} < discard_threshold "
                f"{thresholds.discard_threshold:.3f} 且 LLM 同判 DISCARD"
            ),
            thresholds_source=thresholds.source,
        )

    # ── 规则 R2：LLM 高置信度 DISCARD → 尊重 LLM 判断（移到 ARCHIVE 之前，避免被吞并）
    if llm_decision == Decision.DISCARD and confidence >= thresholds.confidence_floor:
        return DecisionOutcome(
            decision=Decision.DISCARD,
            needs_review=False,
            rule_hit="R2",
            reason=(
                f"LLM 高置信度 ({confidence:.3f} ≥ "
                f"{thresholds.confidence_floor:.3f}) 判定 DISCARD"
            ),
            thresholds_source=thresholds.source,
        )

    # ── 规则 R3：KPI 居中 + 低置信度 → 保留 LLM 决策但触发 SME 复核
    # 这是 V15 没有的新档位：避免 mock LLM 在中间地带"假高分"误丢弃
    in_review_band = thresholds.review_band_low <= kpi <= thresholds.review_band_high
    low_confidence = confidence < thresholds.review_confidence_max
    if in_review_band and low_confidence:
        return DecisionOutcome(
            decision=llm_decision,  # 保留 LLM 原判，但等 SME 复核
            needs_review=True,
            rule_hit="R3",
            reason=(
                f"KPI {kpi:.3f} 落入 review 带 "
                f"[{thresholds.review_band_low:.2f}, {thresholds.review_band_high:.2f}] "
                f"且置信度 {confidence:.3f} < {thresholds.review_confidence_max:.3f}，"
                f"挂起待 SME 复核"
            ),
            thresholds_source=thresholds.source,
        )

    # ── 规则 R4：KPI 低于归档线 或 LLM 判 ARCHIVE → 归档
    if kpi < thresholds.archive_threshold or llm_decision == Decision.ARCHIVE:
        return DecisionOutcome(
            decision=Decision.ARCHIVE,
            needs_review=False,
            rule_hit="R4",
            reason=(
                f"KPI {kpi:.3f} < archive_threshold "
                f"{thresholds.archive_threshold:.3f} 或 LLM 判 ARCHIVE"
            ),
            thresholds_source=thresholds.source,
        )

    # ── 规则 R5：兜底 → LLM 原始判定
    return DecisionOutcome(
        decision=llm_decision,
        needs_review=False,
        rule_hit="R5",
        reason=f"无规则命中，采纳 LLM 原判 {llm_decision.value}",
        thresholds_source=thresholds.source,
    )
