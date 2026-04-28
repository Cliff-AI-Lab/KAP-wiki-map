"""Judge 决策纯函数单测（M0-tech-debt 坑 3 验收）。

覆盖：

- 5 条规则（R1-R5）的命中场景
- 阈值边界条件
- needs_review 标记的触发与清除
- 异常输入的防御性 clamp
- 阈值集 frozen 与一致性校验
- YAML 加载（行业模板覆盖、fallback、解析失败）
"""

from __future__ import annotations

import pytest

from packages.common.types import Decision
from packages.distillation.agents.judge_decision import DecisionOutcome, decide
from packages.distillation.scoring.judge_thresholds import (
    DEFAULT_THRESHOLDS,
    JudgeThresholds,
    load_thresholds,
)


# ───────────── 规则命中 ─────────────


class TestDecisionRules:
    """5 条规则的命中验证。"""

    def test_r1_low_kpi_and_llm_discard(self) -> None:
        """R1：极低 KPI + LLM 也判 DISCARD → 双信号确认 DISCARD。"""
        outcome = decide(
            kpi=0.10,
            llm_decision=Decision.DISCARD,
            confidence=0.7,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.DISCARD
        assert outcome.needs_review is False
        assert outcome.rule_hit == "R1"

    def test_r2_high_confidence_discard(self) -> None:
        """R2：LLM 高置信度 DISCARD → 即使 KPI 高也丢弃。"""
        outcome = decide(
            kpi=0.80,  # 高 KPI
            llm_decision=Decision.DISCARD,
            confidence=0.95,  # 高置信
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.DISCARD
        assert outcome.rule_hit == "R2"

    def test_r2_confidence_floor_boundary(self) -> None:
        """R2 边界：置信度等于 confidence_floor 时仍触发。"""
        outcome = decide(
            kpi=0.80,
            llm_decision=Decision.DISCARD,
            confidence=DEFAULT_THRESHOLDS.confidence_floor,  # 恰好等于
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.rule_hit == "R2"

    def test_r3_review_band_low_confidence(self) -> None:
        """R3：KPI 居中 + 低置信度 → 保留 LLM 决策但 needs_review。"""
        outcome = decide(
            kpi=0.40,  # 居中
            llm_decision=Decision.KEEP,
            confidence=0.50,  # 低置信
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.KEEP  # 保留 LLM 原判
        assert outcome.needs_review is True
        assert outcome.rule_hit == "R3"

    def test_r3_review_band_with_archive_decision(self) -> None:
        """R3：review 带内即使 LLM 判 ARCHIVE 也挂起待复核。"""
        outcome = decide(
            kpi=0.45,
            llm_decision=Decision.ARCHIVE,
            confidence=0.55,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.ARCHIVE
        assert outcome.needs_review is True
        assert outcome.rule_hit == "R3"

    def test_r3_high_confidence_skips_review(self) -> None:
        """R3 反向：KPI 居中但置信度高 → 不进 review。"""
        outcome = decide(
            kpi=0.40,
            llm_decision=Decision.KEEP,
            confidence=0.90,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.needs_review is False
        # 应落到 R4/R5 之一

    def test_r4_kpi_below_archive_threshold(self) -> None:
        """R4：KPI 低于归档线 → ARCHIVE。"""
        outcome = decide(
            kpi=0.25,  # 在 discard(0.20) 和 archive(0.45) 之间
            llm_decision=Decision.KEEP,
            confidence=0.90,  # 高置信，避免命中 R3
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.ARCHIVE
        assert outcome.rule_hit == "R4"

    def test_r4_llm_archive_decision(self) -> None:
        """R4：LLM 判 ARCHIVE → 归档（不论 KPI）。"""
        outcome = decide(
            kpi=0.90,  # 高 KPI
            llm_decision=Decision.ARCHIVE,
            confidence=0.95,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.ARCHIVE
        assert outcome.rule_hit == "R4"

    def test_r5_default_keep(self) -> None:
        """R5：高 KPI + LLM KEEP + 高置信 → 兜底 KEEP。"""
        outcome = decide(
            kpi=0.85,
            llm_decision=Decision.KEEP,
            confidence=0.95,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.KEEP
        assert outcome.rule_hit == "R5"


# ───────────── 边界 / 防御性 ─────────────


class TestBoundaryConditions:
    """边界值与异常输入。"""

    def test_kpi_clamp_negative(self) -> None:
        """KPI 负数应被 clamp 到 0。"""
        outcome = decide(
            kpi=-0.5,
            llm_decision=Decision.DISCARD,
            confidence=0.7,
            thresholds=DEFAULT_THRESHOLDS,
        )
        # KPI=0 < discard_threshold, LLM 也 DISCARD → R1
        assert outcome.rule_hit == "R1"

    def test_kpi_clamp_over_one(self) -> None:
        """KPI 大于 1 应被 clamp 到 1。"""
        outcome = decide(
            kpi=2.0,
            llm_decision=Decision.KEEP,
            confidence=0.95,
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.decision == Decision.KEEP
        assert outcome.rule_hit == "R5"

    def test_confidence_clamp(self) -> None:
        """置信度越界应被 clamp。"""
        outcome = decide(
            kpi=0.85,
            llm_decision=Decision.DISCARD,
            confidence=1.5,  # 超过 1
            thresholds=DEFAULT_THRESHOLDS,
        )
        # clamp 到 1.0 → ≥ confidence_floor → R2
        assert outcome.rule_hit == "R2"

    def test_discard_threshold_strict_less_than(self) -> None:
        """KPI 恰好等于 discard_threshold 时不触发 R1（严格小于）。"""
        outcome = decide(
            kpi=DEFAULT_THRESHOLDS.discard_threshold,
            llm_decision=Decision.DISCARD,
            confidence=0.5,  # 不触发 R2
            thresholds=DEFAULT_THRESHOLDS,
        )
        assert outcome.rule_hit != "R1"


# ───────────── 阈值集 ─────────────


class TestJudgeThresholdsClass:
    """JudgeThresholds dataclass 行为。"""

    def test_frozen(self) -> None:
        """frozen=True，不能修改字段。"""
        with pytest.raises((AttributeError, TypeError)):
            DEFAULT_THRESHOLDS.discard_threshold = 0.5  # type: ignore[misc]

    def test_invalid_threshold_order(self) -> None:
        """discard > archive 应抛错。"""
        with pytest.raises(ValueError, match="discard"):
            JudgeThresholds(discard_threshold=0.6, archive_threshold=0.4)

    def test_invalid_review_band(self) -> None:
        """review_band_low > review_band_high 应抛错。"""
        with pytest.raises(ValueError, match="review"):
            JudgeThresholds(review_band_low=0.7, review_band_high=0.3)

    def test_invalid_confidence_floor(self) -> None:
        """confidence_floor 越界应抛错。"""
        with pytest.raises(ValueError, match="confidence_floor"):
            JudgeThresholds(confidence_floor=1.5)


# ───────────── YAML 加载 ─────────────


class TestLoadThresholds:
    """``load_thresholds`` 加载链路。"""

    def setup_method(self) -> None:
        # 每个测试前清缓存，避免污染
        load_thresholds.cache_clear()

    def test_default_industry(self) -> None:
        """industry=None 应加载 _default 模板（或回到 code-fallback）。"""
        thresholds = load_thresholds(None)
        assert thresholds.industry == "_default"
        # 来源应是 yaml 模板或代码 fallback
        assert thresholds.source in ("code-fallback",) or thresholds.source.startswith("yaml:")

    def test_energy_industry_loaded(self) -> None:
        """加载 energy 模板，应得到能源行业调优后的阈值。"""
        thresholds = load_thresholds("energy")
        assert thresholds.industry == "energy"
        # 能源模板将 discard 调宽到 0.15（V15 经验）
        if thresholds.source.startswith("yaml:"):
            assert thresholds.discard_threshold == 0.15
            assert thresholds.archive_threshold == 0.40

    def test_unknown_industry_fallback(self) -> None:
        """未知行业应回退到 _default 或 code-fallback，不抛错。"""
        thresholds = load_thresholds("non-existent-industry-xyz")
        # 未找到行业模板，应回退；industry 字段保留请求值
        assert thresholds.industry == "non-existent-industry-xyz"
        # 但实际值应来自 _default 或 code-fallback
        assert thresholds.discard_threshold >= 0.0
        assert thresholds.archive_threshold >= 0.0

    def test_lru_cache_works(self) -> None:
        """同一 industry 多次调用应返回同一对象。"""
        a = load_thresholds("energy")
        b = load_thresholds("energy")
        assert a is b  # frozen + cached

    def test_industry_case_insensitive(self) -> None:
        """industry 参数应大小写不敏感。"""
        a = load_thresholds("ENERGY")
        b = load_thresholds("energy")
        # 缓存基于参数，但内部 strip().lower()，所以两次都返回同一缓存项
        assert a.industry == b.industry == "energy"
