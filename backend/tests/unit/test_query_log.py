"""M7 #2 · 查询召回埋点单测（决策书 §5.3 简单运营观察）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.observability import (
    aggregate_queries,
    list_queries,
    record_query,
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
