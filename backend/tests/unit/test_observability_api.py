"""M6 #3 · 可观察性 API 单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.observability import router
from packages.common.auth import UserContext
from packages.observability import (
    add_ground_truth,
    record_decision,
    record_query,
    reset_decisions_for_test,
    reset_queries_for_test,
    reset_recall_eval_for_test,
)
from packages.rebuild import (
    ShadowGraphStore,
    reset_observations_for_test,
    reset_shadow_store_for_test,
    start_observation,
)


class _UserInjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        roles_header = request.headers.get("X-Test-Roles", "")
        roles = [r.strip() for r in roles_header.split(",") if r.strip()]
        request.state.user = UserContext(user_id="test-user", roles=roles)
        return await call_next(request)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(_UserInjectMiddleware)
    return app


@pytest.fixture(autouse=True)
def _reset():
    reset_decisions_for_test()
    reset_queries_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    reset_recall_eval_for_test()
    yield
    reset_decisions_for_test()
    reset_queries_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    reset_recall_eval_for_test()


@pytest.fixture
def client():
    return TestClient(_build_app())


class TestListEndpoint:
    def test_empty(self, client) -> None:
        r = client.get("/api/v1/observability/decisions")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_recent(self, client) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal",
                        actor="sme01", target_id="onto_a")
        r = client.get("/api/v1/observability/decisions?project_id=p1")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["decision_type"] == "approve_proposal"

    def test_filter_by_type(self, client) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        r = client.get(
            "/api/v1/observability/decisions?decision_type=reject_proposal"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1


class TestAggregateEndpoint:
    def test_empty(self, client) -> None:
        r = client.get("/api/v1/observability/decisions/aggregate")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["approval_rate"] == 0.0

    def test_aggregate_with_data(self, client) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        record_decision(project_id="p1", decision_type="promote")

        r = client.get(
            "/api/v1/observability/decisions/aggregate?project_id=p1"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 4
        assert body["by_type"]["approve_proposal"] == 2
        assert body["approval_rate"] == round(2 / 3, 4)
        assert body["promote_rollback_ratio"] == 1.0


# ════════════════════════════════════════════════════════════════════════
#  M7 #2 · 查询埋点端点
# ════════════════════════════════════════════════════════════════════════


class TestQueryEndpoints:
    def test_list_queries_empty(self, client) -> None:
        r = client.get("/api/v1/observability/queries")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_queries_filter_by_project(self, client) -> None:
        record_query(project_id="p1", query_text="a", source_count=2)
        record_query(project_id="p2", query_text="b", source_count=2)
        r = client.get("/api/v1/observability/queries?project_id=p1")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["project_id"] == "p1"

    def test_aggregate_queries(self, client) -> None:
        for ms in [10, 20, 30]:
            record_query(project_id="p1", query_text="x",
                         source_count=1, latency_ms=ms)
        record_query(project_id="p1", query_text="miss", source_count=0)

        r = client.get(
            "/api/v1/observability/queries/aggregate?project_id=p1"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 4
        assert body["hits"] == 3
        assert body["hit_rate"] == 0.75
        assert body["avg_latency_ms"] > 0


# ════════════════════════════════════════════════════════════════════════
#  M7 #3 · 综合运营仪表盘
# ════════════════════════════════════════════════════════════════════════


class TestDashboard:
    def test_empty_dashboard(self, client) -> None:
        r = client.get("/api/v1/observability/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["decisions"]["total"] == 0
        assert body["queries"]["total"] == 0
        assert body["observations"]["total"] == 0
        assert body["observations"]["active"] == 0
        assert body["observations"]["alerting"] == 0

    def test_dashboard_aggregates_three_sources(self, client) -> None:
        # 决策事件
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p1", decision_type="reject_proposal")
        record_decision(project_id="p1", decision_type="promote")
        # 查询事件
        record_query(project_id="p1", query_text="a", source_count=2,
                     latency_ms=50)
        record_query(project_id="p1", query_text="b", source_count=0,
                     latency_ms=80)
        # 观察期
        s = ShadowGraphStore()
        for i in range(5):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        start_observation("p1", "v1", shadow=s)

        r = client.get(
            "/api/v1/observability/dashboard?project_id=p1"
        )
        assert r.status_code == 200
        body = r.json()

        assert body["decisions"]["total"] == 3
        assert body["decisions"]["by_type"]["approve_proposal"] == 1
        assert body["decisions"]["promote_rollback_ratio"] == 1.0

        assert body["queries"]["total"] == 2
        assert body["queries"]["hit_rate"] == 0.5

        assert body["observations"]["total"] == 1
        assert body["observations"]["active"] == 1
        assert body["observations"]["alerting"] == 0
        assert body["observations"]["items"][0]["project_id"] == "p1"
        assert "snapshots" not in body["observations"]["items"][0]
        # 摘要不返回 snapshots 全量
        assert body["observations"]["items"][0]["snapshots_count"] == 0

    def test_dashboard_filters_by_project(self, client) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_decision(project_id="p2", decision_type="approve_proposal")

        r = client.get(
            "/api/v1/observability/dashboard?project_id=p1"
        )
        body = r.json()
        assert body["decisions"]["total"] == 1

    def test_dashboard_includes_feedback_and_recall(self, client) -> None:
        # query feedback (M8 #1)
        e = record_query(project_id="p1", query_text="x", source_count=2)
        client.post(
            f"/api/v1/observability/queries/{e.query_id}/feedback",
            json={"useful": True},
        )

        # ground truth + recall report (M8 #2)
        from packages.observability import (
            add_ground_truth,
            run_recall_eval,
        )
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a", "b"])

        async def fake_qa(q, k):
            return ["a"]  # recall=0.5

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            run_recall_eval(qa_callable=fake_qa, project_id="p1")
        )

        r = client.get(
            "/api/v1/observability/dashboard?project_id=p1"
        )
        assert r.status_code == 200
        body = r.json()
        # query feedback in dashboard
        assert body["queries"]["useful_rate"] == 1.0
        # recall_eval 维度
        assert body["recall_eval"]["ground_truth_count"] == 1
        latest = body["recall_eval"]["latest"]
        assert latest is not None
        assert latest["avg_recall"] == 0.5
        assert latest["total_queries"] == 1

    def test_dashboard_recall_eval_empty(self, client) -> None:
        r = client.get("/api/v1/observability/dashboard")
        body = r.json()
        assert body["recall_eval"]["ground_truth_count"] == 0
        assert body["recall_eval"]["latest"] is None


# ════════════════════════════════════════════════════════════════════════
#  M8 #1 · portal 用户反馈端点
# ════════════════════════════════════════════════════════════════════════


class TestFeedbackEndpoint:
    def test_submit_feedback_marks_useful(self, client) -> None:
        e = record_query(query_text="测试", source_count=3)
        r = client.post(
            f"/api/v1/observability/queries/{e.query_id}/feedback",
            json={"useful": True, "note": "精准"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["useful"] is True
        assert body["feedback_note"] == "精准"
        assert body["feedback_at"] is not None

    def test_submit_feedback_unknown_id_404(self, client) -> None:
        r = client.post(
            "/api/v1/observability/queries/q_no/feedback",
            json={"useful": False},
        )
        assert r.status_code == 404

    def test_aggregate_includes_useful_rate(self, client) -> None:
        e1 = record_query(query_text="a", source_count=1)
        e2 = record_query(query_text="b", source_count=1)
        client.post(
            f"/api/v1/observability/queries/{e1.query_id}/feedback",
            json={"useful": True},
        )
        client.post(
            f"/api/v1/observability/queries/{e2.query_id}/feedback",
            json={"useful": False},
        )
        r = client.get("/api/v1/observability/queries/aggregate")
        body = r.json()
        assert body["feedback_total"] == 2
        assert body["useful_rate"] == 0.5


# ════════════════════════════════════════════════════════════════════════
#  M8 #2 · 召回率评估端点
# ════════════════════════════════════════════════════════════════════════


class TestGroundTruthEndpoint:
    def test_list_empty(self, client) -> None:
        r = client.get("/api/v1/observability/ground-truth")
        assert r.status_code == 200
        assert r.json() == []

    def test_add_requires_sme(self, client) -> None:
        r = client.post(
            "/api/v1/observability/ground-truth",
            json={"project_id": "p1", "query_text": "q",
                  "expected_doc_ids": ["d1"]},
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 403

    def test_add_succeeds_for_sme(self, client) -> None:
        r = client.post(
            "/api/v1/observability/ground-truth",
            json={"project_id": "p1", "query_text": "电机故障",
                  "expected_doc_ids": ["d1", "d2"], "note": "demo"},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["gt_id"].startswith("gt_")
        assert body["expected_doc_ids"] == ["d1", "d2"]

    def test_delete(self, client) -> None:
        gt = add_ground_truth(query_text="x", expected_doc_ids=[])
        r = client.delete(
            f"/api/v1/observability/ground-truth/{gt.gt_id}",
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        r2 = client.delete(
            f"/api/v1/observability/ground-truth/{gt.gt_id}",
            headers={"X-Test-Roles": "SME"},
        )
        assert r2.status_code == 404


class TestRecallEvalEndpoint:
    def test_run_eval_with_mocked_qa(self, client, monkeypatch) -> None:
        add_ground_truth(project_id="p1", query_text="q1",
                         expected_doc_ids=["a"])

        # mock get_qa_engine 返回的 engine.ask
        from api import deps

        class FakeSource:
            def __init__(self, doc_id):
                self.doc_id = doc_id

        class FakeResult:
            def __init__(self, doc_ids):
                self.sources = [FakeSource(d) for d in doc_ids]

        class FakeEngine:
            async def ask(self, *, question, top_k, **kwargs):
                return FakeResult(["a"])  # 完全命中

        monkeypatch.setattr(deps, "get_qa_engine", lambda: FakeEngine())

        r = client.post(
            "/api/v1/observability/recall-eval",
            json={"project_id": "p1", "k": 5},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total_queries"] == 1
        assert body["avg_recall"] == 1.0

    def test_latest_404_when_no_reports(self, client) -> None:
        r = client.get("/api/v1/observability/recall-eval/latest")
        assert r.status_code == 404

    def test_list_reports_empty(self, client) -> None:
        r = client.get("/api/v1/observability/recall-eval/reports")
        assert r.status_code == 200
        assert r.json() == []


class TestRecallTrendEndpoint:
    def test_trend_empty(self, client) -> None:
        r = client.get(
            "/api/v1/observability/recall-eval/trend?project_id=p1"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["samples"] == 0
        assert body["recall_alert"] is False

    def test_trend_with_drop(self, client) -> None:
        from packages.observability import (
            add_ground_truth as _add,
            run_recall_eval as _run,
        )
        import asyncio
        _add(project_id="p1", query_text="q", expected_doc_ids=["a", "b"])

        async def good(q, k):
            return ["a", "b"]

        async def bad(q, k):
            return []

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_run(qa_callable=good, project_id="p1"))
        loop.run_until_complete(_run(qa_callable=bad, project_id="p1"))

        r = client.get(
            "/api/v1/observability/recall-eval/trend?project_id=p1"
        )
        body = r.json()
        assert body["samples"] == 2
        assert body["recall_delta"] == -1.0
        assert body["recall_alert"] is True


class TestEvalAllEndpoint:
    def test_eval_all_empty(self, client) -> None:
        r = client.post(
            "/api/v1/observability/recall-eval/eval-all",
            json={"k": 5},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_eval_all_non_sme_blocked(self, client) -> None:
        r = client.post(
            "/api/v1/observability/recall-eval/eval-all",
            json={"k": 5},
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 403

    def test_multi_k_endpoint(self, client, monkeypatch) -> None:
        from packages.observability import add_ground_truth as _add
        _add(project_id="p1", query_text="q",
             expected_doc_ids=["a"])

        from api import deps

        class FakeSource:
            def __init__(self, doc_id):
                self.doc_id = doc_id

        class FakeResult:
            def __init__(self, doc_ids):
                self.sources = [FakeSource(d) for d in doc_ids]

        class FakeEngine:
            async def ask(self, *, question, top_k, **kwargs):
                return FakeResult(["a"] * top_k)

        monkeypatch.setattr(deps, "get_qa_engine", lambda: FakeEngine())

        r = client.post(
            "/api/v1/observability/recall-eval/multi-k",
            json={"project_id": "p1", "ks": [1, 5]},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ks"] == [1, 5]
        # by_k 序列化为 dict[str, dict]（pydantic dict[int, ...] → str key）
        for k_str in ["1", "5"]:
            assert body["by_k"][k_str]["avg_recall"] == 1.0

    def test_condition_health_endpoint(self, client) -> None:
        """端点直接读 ontology._proposal_store；测试通过 monkey injection 模拟。"""
        from api.routers import ontology
        from packages.common.types import (
            OntologyEntityType,
            OntologyEvolutionProposal,
        )
        ontology._proposal_store["t_approve"] = OntologyEvolutionProposal(
            proposal_id="t_approve", project_id="p1",
            proposed_entity_type=OntologyEntityType(
                type_id="control_loop", type_name="控制回路",
            ),
            status="approved",
        )
        ontology._proposal_store["t_reject"] = OntologyEvolutionProposal(
            proposal_id="t_reject", project_id="p1",
            proposed_entity_type=OntologyEntityType(
                type_id="too_narrow", type_name="太窄",
            ),
            reasoning="r | SME 驳回: 类型粒度太窄",
            status="rejected",
        )

        try:
            r = client.get(
                "/api/v1/observability/condition-health?project_id=p1"
            )
            assert r.status_code == 200
            body = r.json()
            assert "new_entity_type" in body
            assert body["new_entity_type"]["total"] == 2
            assert body["new_entity_type"]["approve_rate"] == 0.5
            assert "类型粒度太窄" in body["new_entity_type"]["common_reject_reasons"]
        finally:
            ontology._proposal_store.pop("t_approve", None)
            ontology._proposal_store.pop("t_reject", None)

    def test_auto_construct_endpoint(self, client) -> None:
        from packages.observability import (
            record_query as _q,
            record_query_feedback as _fb,
        )
        for _ in range(3):
            e = _q(project_id="p1", query_text="高分查询", source_count=2)
            _fb(query_id=e.query_id, useful=True)

        r = client.get(
            "/api/v1/observability/ground-truth/auto-construct"
            "?project_id=p1&min_samples=3"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["query_text"] == "高分查询"
        assert body[0]["useful_rate"] == 1.0

    def test_eval_all_runs_for_all_projects(self, client, monkeypatch) -> None:
        from packages.observability import add_ground_truth as _add
        _add(project_id="p1", query_text="q1", expected_doc_ids=["a"])
        _add(project_id="p2", query_text="q2", expected_doc_ids=["b"])

        from api import deps

        class FakeSource:
            def __init__(self, doc_id):
                self.doc_id = doc_id

        class FakeResult:
            def __init__(self, doc_ids):
                self.sources = [FakeSource(d) for d in doc_ids]

        class FakeEngine:
            async def ask(self, *, question, top_k, **kwargs):
                if question == "q1":
                    return FakeResult(["a"])
                return FakeResult(["b"])

        monkeypatch.setattr(deps, "get_qa_engine", lambda: FakeEngine())

        r = client.post(
            "/api/v1/observability/recall-eval/eval-all",
            json={"k": 5},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        assert {b["project_id"] for b in body} == {"p1", "p2"}
