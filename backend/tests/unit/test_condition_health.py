"""M10 #2 · 监测条件健康度 + 自学习单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.common.types import (
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyRelationType,
)
from packages.observability import (
    analyze_condition_health,
    classify_condition,
)


def _entity_proposal(
    *, type_id: str = "control_loop", status: str = "pending",
    reasoning: str = "",
) -> OntologyEvolutionProposal:
    return OntologyEvolutionProposal(
        proposal_id=f"p_{type_id}_{status}",
        project_id="p1",
        proposed_entity_type=OntologyEntityType(
            type_id=type_id, type_name=type_id,
        ),
        evidence_count=10,
        reasoning=reasoning,
        status=status,    # type: ignore[arg-type]
    )


def _relation_proposal(
    *, status: str = "pending", reasoning: str = "",
) -> OntologyEvolutionProposal:
    return OntologyEvolutionProposal(
        proposal_id=f"r_{status}",
        project_id="p1",
        proposed_relation_type=OntologyRelationType(
            type_id="maintained_by", type_name="维护人员",
        ),
        evidence_count=10,
        reasoning=reasoning,
        status=status,    # type: ignore[arg-type]
    )


# ════════════════════════════════════════════════════════════════════════
#  classify_condition
# ════════════════════════════════════════════════════════════════════════


class TestClassify:
    def test_new_entity_type(self) -> None:
        p = _entity_proposal(type_id="control_loop")
        assert classify_condition(p) == "new_entity_type"

    def test_standard_upgrade(self) -> None:
        p = _entity_proposal(type_id="standard")
        assert classify_condition(p) == "standard_upgrade"

    def test_relation_solidification(self) -> None:
        p = _relation_proposal(reasoning="频次足，语义清晰")
        assert classify_condition(p) == "relation_solidification"

    def test_relation_split(self) -> None:
        p = _relation_proposal(reasoning="拆分自 governs：两簇语义")
        assert classify_condition(p) == "relation_split"

    def test_empty_proposal_unknown(self) -> None:
        p = OntologyEvolutionProposal(
            proposal_id="x", project_id="p1",
        )
        assert classify_condition(p) == "unknown"


# ════════════════════════════════════════════════════════════════════════
#  analyze_condition_health
# ════════════════════════════════════════════════════════════════════════


class TestAnalyze:
    def test_empty_returns_4_baseline_keys(self) -> None:
        out = analyze_condition_health([])
        assert set(out.keys()) == {
            "new_entity_type", "relation_solidification",
            "relation_split", "standard_upgrade",
        }
        for ct, h in out.items():
            assert h.total == 0
            assert h.approve_rate == 0.0
            assert "样本不足" in h.tuning_suggestion

    def test_high_approve_rate_healthy(self) -> None:
        proposals = [
            _entity_proposal(type_id=f"t{i}", status="approved")
            for i in range(8)
        ] + [
            _entity_proposal(type_id="bad", status="rejected"),
        ]
        out = analyze_condition_health(proposals)
        new_et = out["new_entity_type"]
        assert new_et.total == 9
        assert new_et.approved == 8
        assert new_et.rejected == 1
        assert new_et.approve_rate == round(8 / 9, 4)
        assert "接受率高" in new_et.tuning_suggestion

    def test_low_approve_rate_warns(self) -> None:
        proposals = [
            _entity_proposal(type_id=f"t{i}", status="rejected",
                             reasoning="原 reasoning | SME 驳回: 类型粒度太宽")
            for i in range(8)
        ] + [
            _entity_proposal(type_id="ok", status="approved"),
        ]
        out = analyze_condition_health(proposals)
        new_et = out["new_entity_type"]
        assert new_et.approve_rate < 0.3
        assert "接受率偏低" in new_et.tuning_suggestion
        assert "类型粒度太宽" in new_et.common_reject_reasons

    def test_medium_approve_rate(self) -> None:
        proposals = [
            _entity_proposal(type_id=f"a{i}", status="approved")
            for i in range(5)
        ] + [
            _entity_proposal(type_id=f"r{i}", status="rejected")
            for i in range(5)
        ]
        out = analyze_condition_health(proposals)
        new_et = out["new_entity_type"]
        assert new_et.approve_rate == 0.5
        assert "中等接受率" in new_et.tuning_suggestion

    def test_split_classified_separately(self) -> None:
        proposals = [
            _relation_proposal(status="approved",
                               reasoning="频次足"),
            _relation_proposal(status="approved",
                               reasoning="拆分自 governs：分簇"),
            _relation_proposal(status="rejected",
                               reasoning="拆分自 owns：太勉强 | SME 驳回: 语义不足"),
        ]
        out = analyze_condition_health(proposals)
        assert out["relation_solidification"].total == 1
        assert out["relation_split"].total == 2
        # split 的驳回理由提取
        assert "语义不足" in out["relation_split"].common_reject_reasons

    def test_top_3_reject_reasons(self) -> None:
        # 5 个不同理由 → 取 top 3
        reasons = ["A", "A", "A", "B", "B", "C", "D", "E"]
        proposals = []
        for i, r in enumerate(reasons):
            proposals.append(_entity_proposal(
                type_id=f"e{i}", status="rejected",
                reasoning=f"reasoning | SME 驳回: {r}",
            ))
        out = analyze_condition_health(proposals)
        top = out["new_entity_type"].common_reject_reasons
        assert top == ["A", "B", "C"]   # 频次降序

    def test_pending_does_not_count_toward_approve_rate(self) -> None:
        proposals = [
            _entity_proposal(type_id="a", status="approved"),
            _entity_proposal(type_id="p1", status="pending"),
            _entity_proposal(type_id="p2", status="pending"),
        ]
        out = analyze_condition_health(proposals)
        new_et = out["new_entity_type"]
        assert new_et.total == 3
        assert new_et.pending == 2
        assert new_et.approve_rate == 1.0   # 1 approved / 1 decided

    def test_skips_无理由_marker(self) -> None:
        proposals = [
            _entity_proposal(
                type_id="x", status="rejected",
                reasoning="orig | SME 驳回: 无理由",
            ),
            _entity_proposal(
                type_id="y", status="rejected",
                reasoning="orig | SME 驳回: 类型粒度太宽",
            ),
        ]
        out = analyze_condition_health(proposals)
        # "无理由" 不进 top
        assert "无理由" not in out["new_entity_type"].common_reject_reasons
        assert "类型粒度太宽" in out["new_entity_type"].common_reject_reasons
