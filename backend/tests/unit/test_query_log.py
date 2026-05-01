"""M7 #2 · 查询召回埋点单测 + M8 #1 · portal 用户反馈（决策书 §5.3）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.observability import (
    aggregate_queries,
    list_queries,
    record_query,
    record_query_feedback,
    reset_queries_for_test,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_queries_for_test()
    yield
    reset_queries_for_test()


class TestRecord:
    def test_basic(self) -> None:
        e = record_query(
            project_id="p1", user_id="u1", query_text="测试问题",
            source_count=5, latency_ms=120,
        )
        assert e.project_id == "p1"
        assert e.source_count == 5
        assert e.hit is True              # 默认 source_count > 0
        assert e.latency_ms == 120
        assert e.query_id.startswith("q_")

    def test_hit_default_when_no_sources(self) -> None:
        e = record_query(query_text="x", source_count=0)
        assert e.hit is False

    def test_hit_explicit_override(self) -> None:
        e = record_query(query_text="x", source_count=5, hit=False)
        assert e.hit is False

    def test_query_text_truncated(self) -> None:
        long = "a" * 500
        e = record_query(query_text=long)
        assert len(e.query_text) == 200

    def test_negative_latency_clamped_to_zero(self) -> None:
        e = record_query(query_text="x", latency_ms=-50)
        assert e.latency_ms == 0

    def test_retrieved_doc_ids_stored(self) -> None:
        e = record_query(
            query_text="x", source_count=3,
            retrieved_doc_ids=["doc_a", "doc_b", "doc_c"],
        )
        assert e.retrieved_doc_ids == ["doc_a", "doc_b", "doc_c"]

    def test_retrieved_doc_ids_capped_at_50(self) -> None:
        ids = [f"d{i}" for i in range(100)]
        e = record_query(query_text="x", retrieved_doc_ids=ids)
        assert len(e.retrieved_doc_ids) == 50

    def test_retrieved_doc_ids_default_empty(self) -> None:
        e = record_query(query_text="x")
        assert e.retrieved_doc_ids == []


class TestList:
    def test_filter_by_project(self) -> None:
        record_query(project_id="p1", query_text="a")
        record_query(project_id="p2", query_text="b")
        out = list_queries(project_id="p1")
        assert len(out) == 1
        assert out[0].project_id == "p1"

    def test_filter_by_user(self) -> None:
        record_query(user_id="u1", query_text="a")
        record_query(user_id="u2", query_text="b")
        out = list_queries(user_id="u2")
        assert len(out) == 1

    def test_orders_newest_first(self) -> None:
        for i in range(5):
            record_query(query_text=f"q{i}")
        out = list_queries(limit=3)
        assert len(out) == 3
        assert out[0].query_text == "q4"

    def test_time_window(self) -> None:
        before_all = datetime.now() - timedelta(hours=1)
        future = datetime.now() + timedelta(hours=1)
        record_query(query_text="x")
        assert len(list_queries(since=before_all)) == 1
        assert list_queries(since=future) == []


class TestAggregate:
    def test_empty_returns_zeros(self) -> None:
        agg = aggregate_queries()
        assert agg["total"] == 0
        assert agg["hits"] == 0
        assert agg["hit_rate"] == 0.0
        assert agg["avg_latency_ms"] == 0.0
        assert agg["p95_latency_ms"] == 0

    def test_hit_rate(self) -> None:
        for i in range(7):
            record_query(query_text=f"q{i}", source_count=3)  # hit=True
        for i in range(3):
            record_query(query_text=f"miss{i}", source_count=0)  # hit=False
        agg = aggregate_queries()
        assert agg["total"] == 10
        assert agg["hits"] == 7
        assert agg["hit_rate"] == 0.7

    def test_avg_and_p95_latency(self) -> None:
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            record_query(query_text="x", source_count=1, latency_ms=ms)
        agg = aggregate_queries()
        assert agg["avg_latency_ms"] == 55.0
        # p95 idx = max(0, 0.95*10 - 1) = 8 → 第 9 个 = 90
        assert agg["p95_latency_ms"] == 90

    def test_filter_by_project(self) -> None:
        record_query(project_id="p1", query_text="a", source_count=1)
        record_query(project_id="p2", query_text="b", source_count=1)
        agg = aggregate_queries(project_id="p1")
        assert agg["total"] == 1


# ════════════════════════════════════════════════════════════════════════
#  M8 #1 · 用户反馈
# ════════════════════════════════════════════════════════════════════════


class TestFeedback:
    def test_record_feedback_updates_event(self) -> None:
        e = record_query(query_text="x", source_count=2)
        updated = record_query_feedback(
            query_id=e.query_id, useful=True, note="精准",
        )
        assert updated is not None
        assert updated.useful is True
        assert updated.feedback_note == "精准"
        assert updated.feedback_at is not None

    def test_unknown_query_id_returns_none(self) -> None:
        result = record_query_feedback(
            query_id="q_nonexistent", useful=True,
        )
        assert result is None

    def test_feedback_note_truncated(self) -> None:
        e = record_query(query_text="x")
        long_note = "a" * 500
        updated = record_query_feedback(
            query_id=e.query_id, useful=False, note=long_note,
        )
        assert len(updated.feedback_note) == 200

    def test_aggregate_useful_rate(self) -> None:
        e1 = record_query(query_text="a", source_count=1)
        e2 = record_query(query_text="b", source_count=1)
        e3 = record_query(query_text="c", source_count=1)
        e4 = record_query(query_text="d", source_count=1)

        # 3 个反馈：2 useful + 1 not useful；e4 未反馈
        record_query_feedback(query_id=e1.query_id, useful=True)
        record_query_feedback(query_id=e2.query_id, useful=True)
        record_query_feedback(query_id=e3.query_id, useful=False)

        agg = aggregate_queries()
        assert agg["feedback_total"] == 3
        assert agg["useful_count"] == 2
        assert agg["useful_rate"] == round(2 / 3, 4)
        assert agg["feedback_coverage"] == 0.75   # 3 of 4

    def test_aggregate_no_feedback(self) -> None:
        record_query(query_text="x", source_count=1)
        agg = aggregate_queries()
        assert agg["feedback_total"] == 0
        assert agg["useful_rate"] == 0.0
        assert agg["feedback_coverage"] == 0.0

    def test_feedback_can_be_overwritten(self) -> None:
        e = record_query(query_text="x", source_count=1)
        record_query_feedback(query_id=e.query_id, useful=True)
        record_query_feedback(query_id=e.query_id, useful=False, note="改主意")
        updated = record_query_feedback(
            query_id=e.query_id, useful=False, note="还是无用",
        )
        assert updated.useful is False
        assert updated.feedback_note == "还是无用"

    # M16 #3 · 反馈细分原因
    def test_feedback_reasons_stored(self) -> None:
        e = record_query(query_text="x", source_count=1)
        updated = record_query_feedback(
            query_id=e.query_id, useful=False,
            reasons=["wrong_answer", "outdated"],
        )
        assert updated.feedback_reasons == ["wrong_answer", "outdated"]

    def test_feedback_reasons_capped_at_8(self) -> None:
        e = record_query(query_text="x", source_count=1)
        many = [f"reason_{i}" for i in range(15)]
        updated = record_query_feedback(
            query_id=e.query_id, useful=False, reasons=many,
        )
        assert len(updated.feedback_reasons) == 8

    def test_feedback_reasons_filters_empty(self) -> None:
        e = record_query(query_text="x", source_count=1)
        updated = record_query_feedback(
            query_id=e.query_id, useful=False,
            reasons=["wrong_answer", "", "  ", "outdated"],
        )
        assert updated.feedback_reasons == ["wrong_answer", "outdated"]

    def test_aggregate_reason_freq(self) -> None:
        # 3 个 useful=False 各带不同 reasons
        for _ in range(3):
            e = record_query(query_text="x", source_count=1)
            record_query_feedback(
                query_id=e.query_id, useful=False,
                reasons=["wrong_answer", "outdated"],
            )
        e = record_query(query_text="x", source_count=1)
        record_query_feedback(
            query_id=e.query_id, useful=False, reasons=["wrong_answer"],
        )
        # useful=True 无 reasons
        e = record_query(query_text="x", source_count=1)
        record_query_feedback(query_id=e.query_id, useful=True)

        agg = aggregate_queries()
        # wrong_answer 4; outdated 3
        assert agg["feedback_reasons"]["wrong_answer"] == 4
        assert agg["feedback_reasons"]["outdated"] == 3
        # top_reasons 按频次降序
        assert agg["top_reasons"][0] == "wrong_answer"


# ════════════════════════════════════════════════════════════════════════
#  M15 #2 · useful_rate 趋势 + 告警
# ════════════════════════════════════════════════════════════════════════


class TestUsefulRateTrend:
    def test_empty_returns_no_alert(self) -> None:
        from packages.observability import compute_useful_rate_trend
        trend = compute_useful_rate_trend()
        assert trend["useful_alert"] is False
        assert trend["alert_messages"] == []
        assert trend["samples_enough"] is False

    def test_below_min_samples_no_alert(self) -> None:
        """有反馈但量不够（< 5）→ 不触发告警。"""
        from packages.observability import compute_useful_rate_trend
        for i in range(3):
            e = record_query(project_id="p1", query_text=f"q{i}", source_count=1)
            record_query_feedback(query_id=e.query_id, useful=True)
        trend = compute_useful_rate_trend(
            project_id="p1", window_size=5, lookback_size=5,
        )
        assert trend["useful_alert"] is False

    def test_stable_no_alert(self) -> None:
        """两窗口 useful_rate 相近 → 不告警。"""
        from packages.observability import compute_useful_rate_trend
        # 共 20 条，全 useful
        for i in range(20):
            e = record_query(project_id="p1", query_text=f"q{i}", source_count=1)
            record_query_feedback(query_id=e.query_id, useful=True)
        trend = compute_useful_rate_trend(
            project_id="p1", window_size=10, lookback_size=10,
        )
        assert trend["useful_alert"] is False

    def test_drop_triggers_alert(self) -> None:
        """前期高 useful，最近一批 useful_rate 跌破 → 告警。"""
        from packages.observability import compute_useful_rate_trend
        # baseline 窗口（先记录的）：10 条 useful=True → useful_rate=1.0
        # 注意 _queries 反向迭代：当前是最新的；最早记录的进 baseline
        for i in range(10):
            e = record_query(project_id="p1", query_text=f"old_q{i}",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=True)
        # 当前窗口（后记录）：10 条 useful=False → useful_rate=0.0
        for i in range(10):
            e = record_query(project_id="p1", query_text=f"new_q{i}",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=False)

        trend = compute_useful_rate_trend(
            project_id="p1", window_size=10, lookback_size=10,
        )
        # current 是最近的（useful_rate=0），baseline 是更早的（useful_rate=1）
        assert trend["current"]["useful_rate"] == 0.0
        assert trend["baseline"]["useful_rate"] == 1.0
        assert trend["useful_rate_delta"] == -1.0
        assert trend["useful_alert"] is True
        assert any("有用率跌破基线" in m for m in trend["alert_messages"])

    def test_propagate_to_active_observation(self) -> None:
        """check_useful_alerts_and_propagate 把告警追加到当前观察期。"""
        from packages.observability import check_useful_alerts_and_propagate
        from packages.rebuild import (
            ShadowGraphStore,
            reset_observations_for_test,
            reset_shadow_store_for_test,
            start_observation,
            get_current_observation,
        )
        reset_observations_for_test()
        reset_shadow_store_for_test()
        try:
            for i in range(10):
                e = record_query(project_id="p1", query_text=f"old_q{i}",
                                 source_count=1)
                record_query_feedback(query_id=e.query_id, useful=True)
            for i in range(10):
                e = record_query(project_id="p1", query_text=f"new_q{i}",
                                 source_count=1)
                record_query_feedback(query_id=e.query_id, useful=False)

            s = ShadowGraphStore()
            for i in range(3):
                s.add_entity("p1", "v1", entity_name=f"E{i}",
                             type_id="equipment", doc_id="d")
            start_observation("p1", "v1", shadow=s)

            result = check_useful_alerts_and_propagate(
                project_id="p1", window_size=10, lookback_size=10,
            )
            assert result["useful_alert"] is True
            assert result["propagated"] is True
            obs = get_current_observation("p1")
            assert obs.status == "alert"
            assert any("有用率跌破基线" in a for a in obs.alerts)
        finally:
            reset_observations_for_test()
            reset_shadow_store_for_test()

    def test_propagate_no_observation_returns_false(self) -> None:
        """无活跃观察期 → propagated=False（不阻断）。"""
        from packages.observability import check_useful_alerts_and_propagate
        from packages.rebuild import reset_observations_for_test
        reset_observations_for_test()
        for i in range(10):
            e = record_query(project_id="p1", query_text=f"old_q{i}",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=True)
        for i in range(10):
            e = record_query(project_id="p1", query_text=f"new_q{i}",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=False)

        result = check_useful_alerts_and_propagate(
            project_id="p1", window_size=10, lookback_size=10,
        )
        assert result["useful_alert"] is True
        assert result["propagated"] is False
