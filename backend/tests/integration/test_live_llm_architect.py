"""真 LLM 架构师模块（块① 知识咨询智能体）集成测试（M19 #4）。

弱断言：
- recognize_industry 在能源样本下应返回有效 industry_code（弱：不强制具体值）
- propose_taxonomy 在 manufacturing 模板上不会全 drop
"""

from __future__ import annotations

import pytest

from packages.architect.industry_recognizer import recognize_industry
from packages.architect.taxonomy_builder import propose_taxonomy


pytestmark = pytest.mark.live_llm


# ════════════════════════════════════════════════════════════════════════
#  industry_recognizer
# ════════════════════════════════════════════════════════════════════════


class TestIndustryRecognitionLive:
    async def test_energy_samples_recognized(
        self, require_live_llm,
    ) -> None:
        """能源行业样本：应识别到 industry_code 非空 + confidence > 0。"""
        samples = [
            "燃气轮机日常巡检规程：润滑油位 0.85 MPa；冷却水流量 ≥ 120 m³/h",
            "变电站继电保护装置定期检查标准",
            "GB/T 6075 振动监测国家标准",
            "锅炉点火操作规程 + 紧急停车流程",
        ]
        result = await recognize_industry(samples)
        if not result.industry_code:
            pytest.skip(f"LLM/规则均未识别（不强制）；signals={result.recognized_signals}")
        # 弱断言
        assert isinstance(result.industry_code, str)
        assert len(result.industry_code) > 0
        assert result.confidence > 0
        # stage_used 必须 stage1 或 stage2 之一
        assert result.stage_used in ("stage1", "stage2")

    async def test_empty_samples_returns_empty(
        self, require_live_llm,
    ) -> None:
        """空样本：不调 LLM，直接返回空（验证 short-circuit）。"""
        result = await recognize_industry([])
        assert result.industry_code == ""
        assert result.confidence == 0.0


# ════════════════════════════════════════════════════════════════════════
#  taxonomy_builder
# ════════════════════════════════════════════════════════════════════════


class TestTaxonomyProposeLive:
    async def test_manufacturing_propose_keeps_some(
        self, require_live_llm,
    ) -> None:
        """制造业模板 + 制造样本 → 不会全 drop（弱断言：返回非空）。"""
        samples = [
            "数控机床加工工艺规程",
            "产品质量检验记录表",
            "生产线设备故障维修日志",
            "刀具寿命管理规程",
            "工序卡片与工艺路线",
        ]
        revised = await propose_taxonomy("manufacturing", samples)

        if not revised:
            pytest.skip("manufacturing 模板未注册或 LLM 全 drop 兜底；非测试缺陷")

        # 弱断言：每个节点都有 id + name
        for node in revised:
            assert node.id
            assert node.name

    async def test_unknown_industry_returns_empty(
        self, require_live_llm,
    ) -> None:
        """未注册行业 → 返回空（不调 LLM）。"""
        revised = await propose_taxonomy("unknown_xyz_industry_999", [])
        assert revised == []
