"""M6 #3 · 可观察性 API 单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.observability import router
from packages.common.auth import UserContext
from packages.observability import (
    record_decision,
    record_query,
    reset_decisions_for_test,
    reset_queries_for_test,
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
    yield
    reset_decisions_for_test()
    reset_queries_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()


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
