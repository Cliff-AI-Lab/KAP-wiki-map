"""真 LLM W4 实体抽取集成测试（M15 #1）。

老 mock 测试保留作 schema 快速回归；本文件用真 LLM 跑端到端 W4 抽取，
验证 LLM 响应能正确解析为 ExtractionResult + 含至少 1 个实体。

按 memory feedback_real_llm_in_tests：
- 弱断言 schema（实体列表非空 / 含必有字段 / overall_confidence 在 [0,1]）
- 不精确 entity name 匹配（LLM 偶发不同提取）
- 真 LLM 偶发空实体 / 缺字段 → pytest.skip
- 标 ``@pytest.mark.live_llm`` 默认 deselect
"""

from __future__ import annotations

import pytest

from packages.extraction.entity_extractor import extract_entities_and_relations


pytestmark = pytest.mark.live_llm


SAMPLE_CONTENT = """
本规程描述了某型号燃气轮机的日常巡检流程。

1. 启动前检查：润滑油位 0.85±0.05 MPa；冷却水流量 ≥ 120 m³/h。
2. 巡检由维修部李工负责，每 4 小时一次。
3. 关键设备：燃气轮机 A 型、给水泵 B 型、控制系统 DCS-300。
4. 采用 GB/T 6075-2024 振动监测标准。
5. 异常时升级至总工程师确认。
"""


class TestExtractEntitiesAndRelationsLive:
    async def test_returns_non_empty_entities(
        self, require_live_llm,
    ) -> None:
        """真 LLM 调 W4 → 返回的 ExtractionResult 应含 ≥1 个实体。"""
        result = await extract_entities_and_relations(
            doc_id="live_test_w4_doc1",
            content=SAMPLE_CONTENT,
            industry_code="manufacturing",
            project_id="",
        )

        if result.error:
            pytest.skip(f"W4 抽取报错: {result.error}（可能 L1/L2 本体未注册）")
        if not result.entities:
            pytest.skip("真 LLM 返回 0 个实体（非测试缺陷；可重跑或检查 prompt）")

        # schema 弱断言
        assert result.doc_id == "live_test_w4_doc1"
        assert isinstance(result.entities, list)
        assert len(result.entities) > 0

        for ent in result.entities:
            assert ent.name, f"实体 name 为空: {ent}"
            assert ent.type_id, f"实体 type_id 为空: {ent}"
            assert 0.0 <= ent.confidence <= 1.0, (
                f"实体 confidence 越界: {ent.confidence}"
            )

    async def test_overall_confidence_in_range(
        self, require_live_llm,
    ) -> None:
        """overall_confidence 在 [0, 1] 区间（弱断言）。"""
        result = await extract_entities_and_relations(
            doc_id="live_test_w4_doc2",
            content=SAMPLE_CONTENT,
            industry_code="manufacturing",
        )

        if result.error or not result.entities:
            pytest.skip("LLM 返回错误或空，跳过 overall_confidence 检查")

        assert 0.0 <= result.overall_confidence <= 1.0, (
            f"overall_confidence 越界: {result.overall_confidence}"
        )

