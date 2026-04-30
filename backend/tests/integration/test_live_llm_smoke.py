"""真 LLM 集成测试示范（M13 #1 · 用户新约束）。

按 memory feedback_real_llm_in_tests：
- 不 mock ``acall_llm_json``，调真实 LLM
- 弱断言 schema（字段存在 / 类型对 / 长度合理），不精确字符串匹配
- 标 ``@pytest.mark.live_llm`` → CI 默认跳过
- 本地跑：``pytest -m live_llm tests/integration/``
- 需要 ``settings.openai_api_key`` 非空（KAP_OPENAI_API_KEY 环境变量）

设计原则：
- 一份示范 + 一份监测条件 LLM 调用 smoke
- 失败时附 raw 输出方便 debug
- 弱断言：让 prompt 调优不立即破坏测试，只验证 schema 不漂
"""

from __future__ import annotations

import pytest

from packages.distillation.llm_client import acall_llm_json
from packages.ontology.evolution_proposer import (
    UnmatchedEntityBatch, propose_new_entity_type,
)
from packages.ontology.prompts import (
    ENTITY_TYPE_PROPOSE_SYSTEM,
    ENTITY_TYPE_PROPOSE_USER,
)


pytestmark = pytest.mark.live_llm


# ════════════════════════════════════════════════════════════════════════
#  acall_llm_json 直接调用（最小回路）
# ════════════════════════════════════════════════════════════════════════


class TestAcallLlmJsonLive:
    async def test_returns_dict_with_expected_shape(
        self, require_live_llm,
    ) -> None:
        """直接调真实 LLM，验证返回 dict + 含核心字段（schema 弱断言）。"""
        user_prompt = ENTITY_TYPE_PROPOSE_USER.format(
            existing_types="（无）",
            industry_code="manufacturing",
            industry_name="制造业",
            evidence_count=8,
            sample_entities="\n".join([
                "- A 型电机控制回路",
                "- B 型电机控制回路",
                "- C 型电机控制回路",
                "- 锅炉给水控制回路",
                "- 汽轮机调速控制回路",
            ]),
        )

        data = await acall_llm_json(
            ENTITY_TYPE_PROPOSE_SYSTEM, user_prompt,
        )

        # 弱断言：dict + 核心字段存在
        assert isinstance(data, dict), f"期望 dict，实得 {type(data)}: {data!r}"
        assert "type_id" in data, f"返回缺 type_id: {data}"
        assert "type_name" in data, f"返回缺 type_name: {data}"
        # 类型与长度
        type_id = str(data.get("type_id", ""))
        type_name = str(data.get("type_name", ""))
        assert 0 < len(type_id) <= 80, f"type_id 长度不合理: {type_id!r}"
        assert 0 < len(type_name) <= 80, f"type_name 长度不合理: {type_name!r}"
        # confidence 在合理范围
        if "confidence" in data:
            try:
                conf = float(data["confidence"])
                assert 0.0 <= conf <= 1.0, f"confidence 越界: {conf}"
            except (TypeError, ValueError):
                pytest.fail(f"confidence 不是数字: {data['confidence']!r}")


# ════════════════════════════════════════════════════════════════════════
#  evolution_proposer · 端到端真 LLM
# ════════════════════════════════════════════════════════════════════════


class TestProposeNewEntityTypeLive:
    async def test_high_confidence_returns_proposal(
        self, require_live_llm,
    ) -> None:
        """同类样本 → 真 LLM 应返回有效 proposal（弱断言：proposal 非空 + 字段合理）。"""
        batch = UnmatchedEntityBatch(
            industry_code="manufacturing",
            project_id="live_test_p1",
            sample_names=[
                "A 型电机控制回路", "B 型电机控制回路",
                "C 型电机控制回路", "D 型电机控制回路",
                "锅炉给水控制回路", "汽轮机调速控制回路",
                "再热蒸汽温度控制回路", "凝结水压力控制回路",
            ],
            total_count=80,
        )

        proposal = await propose_new_entity_type(batch)

        # 真 LLM 偶尔返回低置信 → propose_new_entity_type 返回 None
        # 我们不强求 proposal 非空；只在非空时验证 schema
        if proposal is None:
            pytest.skip(
                "真 LLM 返回低置信 / schema 缺字段（非测试缺陷；"
                "可重跑或调高 _MIN_LLM_CONFIDENCE 阈值检查）"
            )

        # schema 弱断言
        assert proposal.proposal_id.startswith("onto_")
        assert proposal.project_id == "live_test_p1"
        assert proposal.proposed_entity_type is not None
        et = proposal.proposed_entity_type
        assert 0 < len(et.type_id) <= 80
        assert 0 < len(et.type_name) <= 80
        assert et.layer == "L2"
        assert proposal.evidence_count == 80
        assert proposal.status == "pending"


