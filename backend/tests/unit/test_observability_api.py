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
    reset_decisions_for_test,
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
    yield
    reset_decisions_for_test()


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
