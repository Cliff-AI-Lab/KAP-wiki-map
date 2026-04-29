"""M3 #1 双层本体 · 批 3 · LLM 演化提议器单测。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.ontology import reset_registry_for_test
from packages.ontology.evolution_proposer import (
    UnmatchedEntityBatch,
    collect_unmatched_entities,
    propose_new_entity_type,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    yield
    reset_registry_for_test()


# ════════════════════════════════════════════════════════════════════════
#  collect_unmatched_entities — 监测器
# ════════════════════════════════════════════════════════════════════════


class TestCollectUnmatchedEntities:
    def test_below_threshold_returns_none(self) -> None:
        result = collect_unmatched_entities(
            industry_code="manufacturing",
            project_id="p1",
            candidate_entity_names=["unknown_a", "unknown_b"],
            threshold=50,
        )
        assert result is None

    def test_above_threshold_returns_batch(self) -> None:
        candidates = [f"unknown_entity_{i}" for i in range(60)]
        result = collect_unmatched_entities(
            industry_code="manufacturing",
            project_id="p1",
            candidate_entity_names=candidates,
            threshold=50,
        )
        assert result is not None
        assert result.total_count == 60
        assert len(result.sample_names) <= 20

    def test_excludes_known_l1_examples(self) -> None:
        """L1 已有 example 的实体不应进 unmatched。"""
        # manufacturing L1 含 "数控车床 CK6140" 等 example
        candidates = ["数控车床 CK6140"] * 60 + [f"truly_new_{i}" for i in range(60)]
        result = collect_unmatched_entities(
            industry_code="manufacturing",
            project_id="p1",
            candidate_entity_names=candidates,
            threshold=50,
        )
        # 只有 truly_new_ 那 60 个能进 unmatched
        assert result is not None
        assert result.total_count == 60
        assert all("truly_new" in n for n in result.sample_names)

    def test_empty_input_returns_none(self) -> None:
        result = collect_unmatched_entities(
            industry_code="manufacturing",
            project_id="p1",
            candidate_entity_names=[],
        )
        assert result is None


# ════════════════════════════════════════════════════════════════════════
#  propose_new_entity_type — LLM
# ════════════════════════════════════════════════════════════════════════


def _make_batch() -> UnmatchedEntityBatch:
    return UnmatchedEntityBatch(
        industry_code="manufacturing",
        project_id="p1",
        sample_names=["控制回路 A", "控制回路 B", "PID 回路", "温度回路 C"],
        total_count=80,
    )


class TestProposeNewEntityType:
    async def test_normal_flow(self) -> None:
        async def fake_llm(system, user):
            return {
                "type_id": "control_loop",
                "type_name": "控制回路",
                "description": "PID/PLC 等闭环控制单元",
                "examples": ["控制回路 A", "PID 回路"],
                "confidence": 0.85,
                "reasoning": "样本均涉及闭环控制",
            }

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            proposal = await propose_new_entity_type(_make_batch())

        assert proposal is not None
        assert proposal.proposal_id.startswith("onto_")
        assert proposal.layer == "L2"
        assert proposal.proposed_entity_type.type_id == "control_loop"
        assert proposal.proposed_entity_type.type_name == "控制回路"
        assert proposal.evidence_count == 80

    async def test_low_confidence_returns_none(self) -> None:
        async def fake_llm(system, user):
            return {
                "type_id": "x", "type_name": "X",
                "confidence": 0.2,  # 低于阈值 0.3
            }

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            proposal = await propose_new_entity_type(_make_batch())

        assert proposal is None

    async def test_llm_failure_returns_none(self) -> None:
        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            proposal = await propose_new_entity_type(_make_batch())
        assert proposal is None

    async def test_missing_type_id_returns_none(self) -> None:
        async def fake_llm(system, user):
            return {"type_name": "缺 id", "confidence": 0.9}

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            proposal = await propose_new_entity_type(_make_batch())
        assert proposal is None

    async def test_examples_fallback_to_sample(self) -> None:
        """LLM 不给 examples 时用 batch.sample_names 兜底。"""
        async def fake_llm(system, user):
            return {
                "type_id": "x", "type_name": "X",
                "confidence": 0.7,
                # 不返回 examples
            }

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            proposal = await propose_new_entity_type(_make_batch())
        assert proposal is not None
        assert len(proposal.proposed_entity_type.examples) > 0

    async def test_confidence_clamp(self) -> None:
        async def fake_llm(system, user):
            return {
                "type_id": "x", "type_name": "X",
                "confidence": 99,  # 超出范围
                "examples": ["a"],
            }

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            proposal = await propose_new_entity_type(_make_batch())
        # 99 → clamp 到 1.0，仍在阈值之上
        assert proposal is not None
