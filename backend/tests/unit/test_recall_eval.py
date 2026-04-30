"""M8 #2 · 召回率评估管线单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.observability import (
    add_ground_truth,
    check_recall_alerts_and_propagate,
    compute_recall_trend,
    get_ground_truth,
    get_latest_report,
    list_ground_truth,
    list_reports,
    remove_ground_truth,
    reset_recall_eval_for_test,
    run_recall_eval,
)
from packages.rebuild import (
    ShadowGraphStore,
    reset_observations_for_test,
    reset_shadow_store_for_test,
    start_observation,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_recall_eval_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    yield
    reset_recall_eval_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()


# ════════════════════════════════════════════════════════════════════════
#  Ground truth CRUD
# ════════════════════════════════════════════════════════════════════════


class TestGroundTruth:
    def test_add_returns_gt_with_id(self) -> None:
        gt = add_ground_truth(
            project_id="p1",
            query_text="电机故障如何处理？",
            expected_doc_ids=["doc1", "doc2", "doc3"],
            note="制造业经典 case",
        )
        assert gt.gt_id.startswith("gt_")
        assert gt.expected_doc_ids == ["doc1", "doc2", "doc3"]
        assert gt.note == "制造业经典 case"

    def test_get_by_id(self) -> None:
        gt = add_ground_truth(
            query_text="x", expected_doc_ids=["d1"],
        )
        assert get_ground_truth(gt.gt_id) is gt
        assert get_ground_truth("gt_nonexistent") is None

    def test_list_filters_by_project(self) -> None:
        add_ground_truth(project_id="p1", query_text="a", expected_doc_ids=[])
        add_ground_truth(project_id="p2", query_text="b", expected_doc_ids=[])
        out = list_ground_truth(project_id="p1")
        assert len(out) == 1
        assert out[0].project_id == "p1"

    def test_remove_existing_returns_true(self) -> None:
        gt = add_ground_truth(query_text="x", expected_doc_ids=[])
        assert remove_ground_truth(gt.gt_id) is True
        assert get_ground_truth(gt.gt_id) is None

    def test_remove_unknown_returns_false(self) -> None:
        assert remove_ground_truth("gt_unknown") is False

    def test_query_text_truncated(self) -> None:
        long = "a" * 800
        gt = add_ground_truth(query_text=long, expected_doc_ids=[])
        assert len(gt.query_text) == 500


# ════════════════════════════════════════════════════════════════════════
#  评估器
# ════════════════════════════════════════════════════════════════════════


class TestRunEval:
    async def test_perfect_recall(self) -> None:
        add_ground_truth(
            project_id="p1", query_text="q1",
            expected_doc_ids=["a", "b"],
        )

        async def perfect_qa(query, k):
            return ["a", "b", "c"]

        report = await run_recall_eval(
            qa_callable=perfect_qa, project_id="p1", k=5,
        )
        assert report.total_queries == 1
        assert report.avg_recall == 1.0
        d = report.details[0]
        assert d.matched_count == 2
        assert d.precision == round(2 / 3, 4)

    async def test_zero_recall(self) -> None:
        add_ground_truth(
            project_id="p1", query_text="q1",
            expected_doc_ids=["a"],
        )

        async def empty_qa(query, k):
            return []

        report = await run_recall_eval(
            qa_callable=empty_qa, project_id="p1",
        )
        assert report.avg_recall == 0.0
        assert report.avg_precision == 0.0
        assert report.avg_f1 == 0.0

    async def test_avg_across_multiple_queries(self) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a", "b"])
        add_ground_truth(project_id="p1", query_text="q2",
                         expected_doc_ids=["c"])

        async def half_qa(query, k):
            if query == "q1":
                return ["a"]                  # recall=0.5
            return ["c"]                       # recall=1.0

        report = await run_recall_eval(
            qa_callable=half_qa, project_id="p1",
        )
        assert report.total_queries == 2
        assert report.avg_recall == 0.75       # (0.5 + 1.0) / 2

    async def test_qa_failure_treats_as_zero_recall(self) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a"])

        async def crashing_qa(query, k):
            raise RuntimeError("qa down")

        report = await run_recall_eval(
            qa_callable=crashing_qa, project_id="p1",
        )
        assert report.total_queries == 1
        assert report.details[0].recall == 0.0

    async def test_top_k_truncation(self) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["x"])

        async def big_qa(query, k):
            # 返回 100 个 doc，前 k 个不含 x
            return [f"doc_{i}" for i in range(100)]

        report = await run_recall_eval(
            qa_callable=big_qa, project_id="p1", k=3,
        )
        # x 不在 top 3 → recall=0
        assert report.details[0].recall == 0.0
        assert report.details[0].retrieved_count == 3

    async def test_empty_ground_truth_returns_zero_avg(self) -> None:
        async def any_qa(query, k):
            return []

        report = await run_recall_eval(qa_callable=any_qa, project_id="p1")
        assert report.total_queries == 0
        assert report.avg_recall == 0.0

    async def test_report_persisted_in_list(self) -> None:
        add_ground_truth(query_text="q1", expected_doc_ids=["a"])

        async def qa(query, k):
            return ["a"]

        r1 = await run_recall_eval(qa_callable=qa, project_id="p1")
        r2 = await run_recall_eval(qa_callable=qa, project_id="p1")

        all_reports = list_reports(project_id="p1")
        assert len(all_reports) == 2
        # 倒序：最新优先
        assert all_reports[0].report_id == r2.report_id
        latest = get_latest_report(project_id="p1")
        assert latest.report_id == r2.report_id

    async def test_f1_formula(self) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a", "b", "c", "d"])

        async def qa(query, k):
            return ["a", "b", "x", "y"]

        report = await run_recall_eval(qa_callable=qa, project_id="p1", k=4)
        d = report.details[0]
        assert d.recall == 0.5
        assert d.precision == 0.5
        assert d.f1 == 0.5


# ════════════════════════════════════════════════════════════════════════
#  M9 #2 · 趋势 + 告警
# ════════════════════════════════════════════════════════════════════════


class TestRecallTrend:
    def test_trend_with_lt_2_samples(self) -> None:
        trend = compute_recall_trend(project_id="p1")
        assert trend["samples"] == 0
        assert trend["recall_alert"] is False
        assert trend["alert_messages"] == []

    async def test_trend_no_alert_when_stable(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def steady_qa(q, k):
            return ["a"]

        await run_recall_eval(qa_callable=steady_qa, project_id="p1")
        await run_recall_eval(qa_callable=steady_qa, project_id="p1")
        trend = compute_recall_trend(project_id="p1")
        assert trend["samples"] == 2
        assert trend["recall_delta"] == 0.0
        assert trend["recall_alert"] is False

    async def test_trend_alert_when_recall_drops(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a", "b", "c", "d"])

        async def good_qa(q, k):
            return ["a", "b", "c", "d"]      # recall=1.0 baseline

        async def bad_qa(q, k):
            return ["a"]                      # recall=0.25 → 跌 0.75

        await run_recall_eval(qa_callable=good_qa, project_id="p1", k=5)
        await run_recall_eval(qa_callable=bad_qa, project_id="p1", k=5)

        trend = compute_recall_trend(project_id="p1")
        assert trend["recall_delta"] == -0.75
        assert trend["recall_alert"] is True
        assert any("召回率跌破基线" in m for m in trend["alert_messages"])

    async def test_alert_propagates_to_active_observation(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a", "b"])

        async def good(q, k):
            return ["a", "b"]

        async def bad(q, k):
            return []

        await run_recall_eval(qa_callable=good, project_id="p1")
        await run_recall_eval(qa_callable=bad, project_id="p1")

        # 启动观察期（M5 #2）
        s = ShadowGraphStore()
        for i in range(3):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        start_observation("p1", "v1", shadow=s)

        result = check_recall_alerts_and_propagate(project_id="p1")
        assert result["recall_alert"] is True
        assert result["propagated"] is True

        from packages.rebuild import get_current_observation
        obs = get_current_observation("p1")
        assert any("召回率跌破基线" in a for a in obs.alerts)
        assert obs.status == "alert"

    async def test_no_propagation_when_no_observation(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a", "b"])

        async def bad(q, k):
            return []

        async def good(q, k):
            return ["a", "b"]

        await run_recall_eval(qa_callable=good, project_id="p1")
        await run_recall_eval(qa_callable=bad, project_id="p1")

        result = check_recall_alerts_and_propagate(project_id="p1")
        assert result["recall_alert"] is True
        assert result["propagated"] is False  # 无活跃观察期

    async def test_lookback_limits_baseline(self) -> None:
        """lookback=3 时 baseline = 最近 3 份的最早 = 第 3 份。"""
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def hit(q, k):
            return ["a"]

        async def miss(q, k):
            return []

        # 5 份 reports：[hit, hit, miss, miss, hit]
        await run_recall_eval(qa_callable=hit, project_id="p1")
        await run_recall_eval(qa_callable=hit, project_id="p1")
        await run_recall_eval(qa_callable=miss, project_id="p1")
        await run_recall_eval(qa_callable=miss, project_id="p1")
        await run_recall_eval(qa_callable=hit, project_id="p1")

        # lookback=3 → 最近 3 份 = [hit, miss, miss]（newest first）
        # baseline = miss (最早即最末) = 0.0
        # current = hit = 1.0
        trend = compute_recall_trend(project_id="p1", lookback=3)
        assert trend["samples"] == 3
        assert trend["current"]["avg_recall"] == 1.0
        assert trend["baseline"]["avg_recall"] == 0.0
