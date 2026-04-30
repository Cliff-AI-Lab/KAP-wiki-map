"""真 LLM 监测条件 2/3/4 集成测试（M14 #1）。

老 mock 测试 ``test_m5_evolution_full.py`` 保留作为 schema 快速回归；本文件
新增真 LLM 版（弱断言）覆盖：
- 监测条件 2 · propose_relation_solidification（自定义关系反复出现）
- 监测条件 3 · propose_relation_split_for_drift（语义漂移拆分）
- 监测条件 4 · propose_standard_upgrade（行业标准升版）

按 memory feedback_real_llm_in_tests：
- 弱断言 schema（字段存在 / 类型对 / 长度合理），不精确字符串匹配
- LLM 偶发低置信 / 缺字段 → pytest.skip 而非 fail（非测试缺陷）
- 默认 ``addopts = "-m 'not live_llm'"`` skip；显式 ``pytest -m live_llm`` 跑
"""

from __future__ import annotations

import pytest

from packages.ontology.evolution_proposer import (
    propose_relation_solidification,
    propose_relation_split_for_drift,
    propose_standard_upgrade,
)


pytestmark = pytest.mark.live_llm


# ════════════════════════════════════════════════════════════════════════
#  监测条件 2 · 自定义关系固化
# ════════════════════════════════════════════════════════════════════════


class TestRelationSolidificationLive:
    async def test_high_freq_relation_returns_proposal(
        self, require_live_llm,
    ) -> None:
        """20+ 次相同自定义关系 → 真 LLM 应归纳出新关系类型。"""
        records = [
            {"relation": "由谁维护", "source": f"机组_{i}",
             "target": "李工", "note": "巡检"}
            for i in range(25)
        ]

        proposal = await propose_relation_solidification(
            records, project_id="live_test_p2", industry_code="manufacturing",
        )

        if proposal is None:
            pytest.skip(
                "真 LLM 返回低置信 / 缺字段（非测试缺陷；可重跑）"
            )

        # schema 弱断言
        assert proposal.proposal_id.startswith("onto_")
        assert proposal.project_id == "live_test_p2"
        assert proposal.proposed_relation_type is not None
        rt = proposal.proposed_relation_type
        assert 0 < len(rt.type_id) <= 80, f"type_id: {rt.type_id!r}"
        assert 0 < len(rt.type_name) <= 80, f"type_name: {rt.type_name!r}"
        assert rt.layer == "L2"
        assert proposal.evidence_count == 25
        assert proposal.status == "pending"


# ════════════════════════════════════════════════════════════════════════
#  监测条件 3 · 语义漂移拆分
# ════════════════════════════════════════════════════════════════════════


class TestRelationSplitForDriftLive:
    async def test_two_clusters_returns_split_proposals(
        self, require_live_llm,
    ) -> None:
        """30+ 样本明显两簇语义 → 真 LLM 应建议拆分（≥2 个新关系）。"""
        samples = []
        # 簇 1：标准约束语境
        for i in range(18):
            samples.append({
                "source": f"GB/T 6075-201{i % 5}",
                "target": f"机组_{i}",
                "context": "标准条款约束设备振动参数",
            })
        # 簇 2：行政规范语境
        for i in range(18):
            samples.append({
                "source": f"质量管理办法_{i}",
                "target": "维修部",
                "context": "行政流程规范部门职能",
            })

        proposals = await propose_relation_split_for_drift(
            samples, project_id="live_test_p3",
            relation_type_id="governs", industry_code="manufacturing",
        )

        if proposals is None:
            pytest.skip(
                "真 LLM 判断 should_split=false / 低置信 / split_into < 2"
            )

        # schema 弱断言
        assert isinstance(proposals, list)
        assert len(proposals) >= 2, f"期望 ≥2 拆分提议，实得 {len(proposals)}"
        for p in proposals:
            assert p.proposal_id.startswith("onto_")
            assert p.project_id == "live_test_p3"
            assert p.proposed_relation_type is not None
            assert "拆分自 governs" in p.reasoning
            assert p.status == "pending"


# ════════════════════════════════════════════════════════════════════════
#  监测条件 4 · 行业标准升版
# ════════════════════════════════════════════════════════════════════════


class TestStandardUpgradeLive:
    async def test_new_version_returns_upgrade_proposal(
        self, require_live_llm,
    ) -> None:
        """客户引用 GB/T 6075-2024（新版）→ 真 LLM 应建议升版。"""
        proposal = await propose_standard_upgrade(
            "manufacturing",
            new_standards=["GB/T 6075-2024", "GB/T 6075.3-2024"],
            project_id="live_test_p4",
        )

        if proposal is None:
            pytest.skip(
                "真 LLM 判断 should_upgrade=false / 低置信 / L1 无 standard 类型"
            )

        # schema 弱断言
        assert proposal.proposal_id.startswith("onto_")
        assert proposal.project_id == "live_test_p4"
        assert proposal.proposed_entity_type is not None
        et = proposal.proposed_entity_type
        assert et.type_id == "standard"
        assert len(et.examples) > 0, "升版后 examples 不应为空"
        # 至少一个 example 含新版字符串（弱）
        joined = " ".join(et.examples)
        assert "2024" in joined or "GB/T 6075" in joined, (
            f"examples 看不出升版痕迹: {et.examples}"
        )
        assert proposal.status == "pending"
