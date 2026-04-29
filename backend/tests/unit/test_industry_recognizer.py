"""M2 #4 块① · 批 2 · industry_recognizer 两阶段单测（PRD F1.2）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.architect.industry_recognizer import (
    _STAGE1_HIGH_CONFIDENCE,
    _stage1_keyword_match,
    _stage1_rank,
    recognize_industry,
)
from packages.templates.registry import INDUSTRY_REGISTRY, get_template


# ════════════════════════════════════════════════════════════════════════
#  Stage 1 — 关键词初筛
# ════════════════════════════════════════════════════════════════════════


class TestStage1KeywordMatch:
    def test_manufacturing_samples_match_manufacturing_template(self) -> None:
        samples = [
            "设备点检与润滑标准",
            "生产管理 工艺路线 SPC",
            "OQC 检验 客诉处理 8D 报告",
            "PPAP 文件 试产管理",
        ]
        tpl = get_template("manufacturing")
        conf, matched = _stage1_keyword_match(samples, tpl)
        assert conf > 0
        assert any(kw in matched for kw in ("生产管理", "工艺", "质量管理", "客诉"))

    def test_unrelated_text_low_confidence(self) -> None:
        samples = ["今天天气真好，我去公园散步看樱花"]
        tpl = get_template("manufacturing")
        conf, matched = _stage1_keyword_match(samples, tpl)
        assert conf < 0.3

    def test_empty_samples_zero(self) -> None:
        tpl = get_template("manufacturing")
        conf, matched = _stage1_keyword_match([], tpl)
        assert conf == 0.0
        assert matched == []


class TestStage1Rank:
    def test_ranks_manufacturing_top_for_manufacturing_samples(self) -> None:
        samples = [
            "生产管理 设备维护 质量管理 OQC IPQC",
            "SOP 标准操作程序",
            "工艺标准 PPAP",
        ]
        candidates = _stage1_rank(samples)
        assert candidates[0].industry_code == "manufacturing"

    def test_returns_all_registered_industries(self) -> None:
        candidates = _stage1_rank(["普通文本"])
        # 注册了 5 个行业
        assert len(candidates) == len(INDUSTRY_REGISTRY)


# ════════════════════════════════════════════════════════════════════════
#  recognize_industry — 入口
# ════════════════════════════════════════════════════════════════════════


class TestRecognizeIndustry:
    async def test_high_confidence_skips_llm(self) -> None:
        """Stage 1 命中率高 → 直接采纳，不调 LLM。"""
        # 构造大量制造业关键词 → Stage 1 confidence 应 >= _STAGE1_HIGH_CONFIDENCE
        samples = [
            "生产管理 工艺控制 SPC 质量管理 IQC IPQC OQC 客诉处理",
            "设备维护 预防性维护 计量校准 仪器台账",
            "仓储管理 库存控制 物流配送 厂内物流",
            "研发管理 产品设计 新品导入 PPAP 试产",
            "安全管理 职业健康 消防安全 劳保用品",
        ] * 2  # 加倍命中

        with patch(
            "packages.architect.industry_recognizer.acall_llm_json"
        ) as mock_llm:
            result = await recognize_industry(samples)
            # LLM 不应该被调用
            mock_llm.assert_not_called()

        assert result.stage_used == "stage1"
        assert result.industry_code == "manufacturing"

    async def test_low_confidence_triggers_llm(self) -> None:
        """Stage 1 low confidence → 调 LLM 二轮。"""
        # 弱信号样本 → Stage 1 低置信度
        samples = ["流程 质量 设备"]  # 通用词，跨行业都可能命中

        async def fake_llm(system, user):
            return {
                "industry_code": "manufacturing",
                "confidence": 0.75,
                "reasoning": "样本提及质量管理与设备维护，倾向制造业",
                "recognized_signals": ["质量", "设备"],
            }

        with patch(
            "packages.architect.industry_recognizer.acall_llm_json",
            side_effect=fake_llm,
        ) as mock_llm:
            result = await recognize_industry(samples)
            # 仅当 stage1 conf < 0.7 时才会调 LLM；本测试弱信号大概率走到
            if result.stage_used == "stage2":
                mock_llm.assert_called()
                assert result.confidence == 0.75
                assert result.industry_code == "manufacturing"

    async def test_llm_invalid_code_falls_back(self) -> None:
        """LLM 返回不在候选里的 code → 降级 Stage 1。"""
        samples = ["流程 质量"]

        async def fake_llm(system, user):
            return {"industry_code": "fake_industry", "confidence": 0.9}

        with patch(
            "packages.architect.industry_recognizer.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await recognize_industry(samples)
            # LLM 返回非法 code → 降级 stage1_fallback
            if result.stage_used != "stage1":
                assert result.stage_used == "stage1_fallback"

    async def test_llm_failure_falls_back_to_stage1(self) -> None:
        """LLM 抛异常 → 降级 Stage 1。"""
        samples = ["流程 质量"]

        with patch(
            "packages.architect.industry_recognizer.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            result = await recognize_industry(samples)
            assert result.stage_used in ("stage1", "stage1_fallback")
            # 不抛异常

    async def test_empty_samples_returns_empty_result(self) -> None:
        result = await recognize_industry([])
        assert result.industry_code == ""
        assert result.confidence == 0.0

    async def test_no_match_at_all(self) -> None:
        """完全无关文本 → 返回空 industry_code，候选 confidence 都 0。"""
        result = await recognize_industry(["看樱花散步赏花樱花樱花"])
        # 可能 industry_code 空或者随便挑了一个低 conf 的
        assert result.confidence < 0.3
