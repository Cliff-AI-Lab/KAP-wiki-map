"""M8 #2 · 召回率评估管线单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.observability import (
    add_ground_truth,
    auto_construct_ground_truth_candidates,
    check_recall_alerts_and_propagate,
    compute_recall_trend,
    eval_all_projects,
    get_ground_truth,
    get_latest_report,
    list_ground_truth,
    list_projects_with_ground_truth,
    list_reports,
    record_query,
    record_query_feedback,
    remove_ground_truth,
    reset_queries_for_test,
    reset_recall_eval_for_test,
    run_multi_k_recall_eval,
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
    reset_queries_for_test()
    yield
    reset_recall_eval_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    reset_queries_for_test()


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

    async def test_eval_all_processes_multiple_projects(self) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a"])
        add_ground_truth(project_id="p2", query_text="q2",
                         expected_doc_ids=["b"])

        async def qa(query_text, k):
            if query_text == "q1":
                return ["a"]
            return ["b"]

        reports = await eval_all_projects(qa_callable=qa)
        assert len(reports) == 2
        assert {r.project_id for r in reports} == {"p1", "p2"}
        assert all(r.avg_recall == 1.0 for r in reports)

    async def test_eval_all_skips_empty_project_id(self) -> None:
        # gt with project_id="" 不应被列入
        add_ground_truth(query_text="x", expected_doc_ids=["a"])

        async def qa(q, k):
            return ["a"]

        reports = await eval_all_projects(qa_callable=qa)
        assert reports == []

    async def test_eval_all_handles_per_project_failure(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])
        add_ground_truth(project_id="p2", query_text="q",
                         expected_doc_ids=["b"])

        async def qa(q, k):
            return ["a"]  # p1 命中, p2 不命中（recall=0）

        reports = await eval_all_projects(qa_callable=qa)
        # 即使 p2 recall=0 也不算异常
        assert len(reports) == 2

    def test_list_projects_with_ground_truth(self) -> None:
        add_ground_truth(project_id="p1", query_text="x",
                         expected_doc_ids=[])
        add_ground_truth(project_id="p2", query_text="y",
                         expected_doc_ids=[])
        add_ground_truth(query_text="z", expected_doc_ids=[])  # no project
        out = list_projects_with_ground_truth()
        assert out == ["p1", "p2"]

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


# ════════════════════════════════════════════════════════════════════════
#  M10 #1 · 多 K 召回曲线
# ════════════════════════════════════════════════════════════════════════


class TestMultiKRecall:
    async def test_basic_curve(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a", "b"])

        async def qa(query, k):
            return ["a", "x", "b", "y"]   # b 在 top 3

        report = await run_multi_k_recall_eval(
            qa_callable=qa, project_id="p1", ks=[1, 3, 5],
        )
        # k=1: top 1 = ["a"] → recall=0.5
        # k=3: top 3 = ["a", "x", "b"] → recall=1.0
        # k=5: 同 max=4 → recall=1.0
        assert report.by_k[1]["avg_recall"] == 0.5
        assert report.by_k[3]["avg_recall"] == 1.0
        assert report.by_k[5]["avg_recall"] == 1.0
        assert report.total_queries == 1

    async def test_default_ks_when_not_specified(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def qa(query, k):
            return ["a"]

        report = await run_multi_k_recall_eval(
            qa_callable=qa, project_id="p1",
        )
        assert report.ks == [1, 3, 5, 10]

    async def test_qa_failure_zero_across_all_ks(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def crash(q, k):
            raise RuntimeError("down")

        report = await run_multi_k_recall_eval(
            qa_callable=crash, project_id="p1", ks=[1, 5],
        )
        for k in [1, 5]:
            assert report.by_k[k]["avg_recall"] == 0.0

    async def test_dedup_and_sort_ks(self) -> None:
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def qa(query, k):
            return ["a"]

        report = await run_multi_k_recall_eval(
            qa_callable=qa, project_id="p1", ks=[5, 1, 5, 3],
        )
        assert report.ks == [1, 3, 5]


# ════════════════════════════════════════════════════════════════════════
#  M10 #1 · GroundTruth 自动构造候选
# ════════════════════════════════════════════════════════════════════════


class TestAutoConstructGT:
    def test_no_queries_returns_empty(self) -> None:
        assert auto_construct_ground_truth_candidates(project_id="p1") == []

    def test_filters_below_min_samples(self) -> None:
        # 单次查询 + 单次 useful → 不达样本数阈值
        e = record_query(project_id="p1", query_text="孤儿问题",
                         source_count=1)
        record_query_feedback(query_id=e.query_id, useful=True)

        out = auto_construct_ground_truth_candidates(
            project_id="p1", min_samples=2,
        )
        assert out == []

    def test_filters_below_min_useful_rate(self) -> None:
        for _ in range(3):
            e = record_query(project_id="p1", query_text="低评价问题",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=False)

        out = auto_construct_ground_truth_candidates(
            project_id="p1", min_samples=2, min_useful_rate=0.8,
        )
        assert out == []

    def test_returns_high_useful_query(self) -> None:
        # 4 次相同 query：3 useful + 1 not → useful_rate=0.75 < 0.8 不达
        # 加成 4 useful → 1.0
        for _ in range(4):
            e = record_query(project_id="p1", query_text="电机故障",
                             source_count=2)
            record_query_feedback(query_id=e.query_id, useful=True)

        out = auto_construct_ground_truth_candidates(
            project_id="p1", min_samples=3, min_useful_rate=0.8,
        )
        assert len(out) == 1
        c = out[0]
        assert c.query_text == "电机故障"
        assert c.useful_rate == 1.0
        assert c.sample_size == 4
        assert c.candidate_id.startswith("gtc_")

    def test_filter_by_project(self) -> None:
        for _ in range(3):
            e1 = record_query(project_id="p1", query_text="x",
                              source_count=1)
            record_query_feedback(query_id=e1.query_id, useful=True)
            e2 = record_query(project_id="p2", query_text="y",
                              source_count=1)
            record_query_feedback(query_id=e2.query_id, useful=True)

        out = auto_construct_ground_truth_candidates(project_id="p1")
        assert all(c.project_id == "p1" for c in out)
        assert len(out) == 1

    def test_skips_queries_without_feedback(self) -> None:
        for _ in range(3):
            record_query(project_id="p1", query_text="无反馈",
                         source_count=1)
        out = auto_construct_ground_truth_candidates(project_id="p1")
        assert out == []

    def test_sort_by_useful_rate_then_samples(self) -> None:
        # query A: 5 次 + 4 useful → 0.8
        for i in range(5):
            e = record_query(project_id="p1", query_text="A",
                             source_count=1)
            record_query_feedback(
                query_id=e.query_id, useful=(i < 4),
            )
        # query B: 3 次 + 3 useful → 1.0（更高，应排前）
        for i in range(3):
            e = record_query(project_id="p1", query_text="B",
                             source_count=1)
            record_query_feedback(query_id=e.query_id, useful=True)

        out = auto_construct_ground_truth_candidates(
            project_id="p1", min_samples=3,
        )
        assert len(out) == 2
        assert out[0].query_text == "B"  # 1.0 > 0.8
        assert out[1].query_text == "A"
