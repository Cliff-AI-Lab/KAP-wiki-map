"""M8 #2 · 召回率评估管线单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.observability import (
    add_ground_truth,
    get_ground_truth,
    get_latest_report,
    list_ground_truth,
    list_reports,
    remove_ground_truth,
    reset_recall_eval_for_test,
    run_recall_eval,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_recall_eval_for_test()
    yield
    reset_recall_eval_for_test()


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
