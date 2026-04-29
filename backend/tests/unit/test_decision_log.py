"""M6 #3 · SME 决策日志单测（决策书 §5.3 简单指标聚合）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.observability import (
    aggregate_decisions,
    list_decisions,
    record_decision,
    reset_decisions_for_test,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_decisions_for_test()
    yield
    reset_decisions_for_test()


class TestRecord:
    def test_basic_record(self) -> None:
        e = record_decision(
            project_id="p1", decision_type="approve_proposal",
            actor="sme01", target_id="onto_abc", note="LGTM",
        )
        assert e.project_id == "p1"
        assert e.decision_type == "approve_proposal"
        assert e.occurred_at is not None
        assert list_decisions() == [e]

    def test_multiple_records_keep_order(self) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        record_decision(project_id="p1", decision_type="promote")
        events = list_decisions()
        # list_decisions 按时间倒序
        assert events[0].decision_type == "promote"


class TestList:
    def test_filter_by_project(self) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p2", decision_type="approve_proposal")
        out = list_decisions(project_id="p1")
        assert len(out) == 1
        assert out[0].project_id == "p1"

    def test_filter_by_type(self) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        out = list_decisions(decision_type="reject_proposal")
        assert len(out) == 1
        assert out[0].decision_type == "reject_proposal"

    def test_filter_by_time_window(self) -> None:
        # since 设到过去 → 包含所有事件
        before_all = datetime.now() - timedelta(hours=1)
        record_decision(project_id="p1", decision_type="promote")
        record_decision(project_id="p1", decision_type="rollback")
        out = list_decisions(since=before_all)
        types = {e.decision_type for e in out}
        assert types == {"promote", "rollback"}

        # since 设到未来 → 全过滤掉
        future = datetime.now() + timedelta(hours=1)
        assert list_decisions(since=future) == []

    def test_limit(self) -> None:
        for _ in range(10):
            record_decision(project_id="p1", decision_type="promote")
        assert len(list_decisions(limit=3)) == 3


class TestAggregate:
    def test_empty_returns_zero(self) -> None:
        agg = aggregate_decisions()
        assert agg["total"] == 0
        assert agg["by_type"] == {}
        assert agg["approval_rate"] == 0.0

    def test_approval_rate(self) -> None:
        for _ in range(3):
            record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        agg = aggregate_decisions()
        assert agg["by_type"]["approve_proposal"] == 3
        assert agg["by_type"]["reject_proposal"] == 1
        assert agg["approval_rate"] == 0.75

    def test_promote_rollback_ratio_no_rollback(self) -> None:
        record_decision(project_id="p1", decision_type="promote")
        record_decision(project_id="p1", decision_type="promote")
        agg = aggregate_decisions()
        # 无 rollback → 直接给 promote 数
        assert agg["promote_rollback_ratio"] == 2.0

    def test_promote_rollback_ratio_with_rollback(self) -> None:
        for _ in range(4):
            record_decision(project_id="p1", decision_type="promote")
        record_decision(project_id="p1", decision_type="rollback")
        agg = aggregate_decisions()
        assert agg["promote_rollback_ratio"] == 4.0

    def test_filter_by_project(self) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p2", decision_type="approve_proposal")
        agg = aggregate_decisions(project_id="p2")
        assert agg["total"] == 1
