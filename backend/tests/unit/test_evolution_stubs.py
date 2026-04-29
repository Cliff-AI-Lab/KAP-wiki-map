"""M4 批 5 · 监测条件 2-4 stub 单测（决策书 §5.3）。

M4 lite stub 验证：函数存在 + 返回 None + 不抛异常。
M5 加完整 LLM 实现后扩充正向场景测试。
"""

from __future__ import annotations

import pytest

from packages.ontology.evolution_proposer import (
    propose_relation_solidification,
    propose_relation_split_for_drift,
    propose_standard_upgrade,
)


class TestStub:
    async def test_relation_solidification_stub_returns_none(self) -> None:
        result = await propose_relation_solidification(
            usage_records=[{"relation": "x"}], project_id="p1",
        )
        assert result is None

    async def test_relation_split_stub_returns_none(self) -> None:
        result = await propose_relation_split_for_drift(
            samples=[{"text": "x"}],
            project_id="p1",
            relation_type_id="governs",
        )
        assert result is None

    async def test_standard_upgrade_stub_returns_none(self) -> None:
        result = await propose_standard_upgrade(
            industry_code="manufacturing",
            new_standards=["GB/T 6075-2024"],
            project_id="p1",
        )
        assert result is None

    async def test_stubs_handle_empty_inputs(self) -> None:
        """空输入也不抛异常。"""
        assert await propose_relation_solidification(
            usage_records=[], project_id="",
        ) is None
        assert await propose_relation_split_for_drift(
            samples=[], project_id="", relation_type_id="",
        ) is None
        assert await propose_standard_upgrade(
            industry_code="", new_standards=[], project_id="",
        ) is None
