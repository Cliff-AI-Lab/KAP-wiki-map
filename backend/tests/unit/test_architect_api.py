"""M2 #4 块① · 批 4 · architect API endpoints 单测（PRD F1.1-F1.7）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.architect import router
from packages.architect.agent import reset_architect_agent_for_test
from packages.common.auth import UserContext


# ════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════


class _UserInjectMiddleware(BaseHTTPMiddleware):
    """测试用：把 X-Test-User 头转为 UserContext + 注入 request.state。"""

    async def dispatch(self, request: Request, call_next):
        roles_header = request.headers.get("X-Test-Roles", "")
        roles = [r.strip() for r in roles_header.split(",") if r.strip()]
        request.state.user = UserContext(
            user_id="test-user",
            roles=roles,
        )
        return await call_next(request)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(_UserInjectMiddleware)
    return app


@pytest.fixture(autouse=True)
def _reset():
    reset_architect_agent_for_test()
    yield
    reset_architect_agent_for_test()


@pytest.fixture
def client():
    app = _build_app()
    return TestClient(app)


# ════════════════════════════════════════════════════════════════════════
#  POST /architect/sessions
# ════════════════════════════════════════════════════════════════════════


class TestCreateSession:
    def test_dg_can_create(self, client) -> None:
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1", "sample_texts": ["设备点检"]},
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["stage"] == "identify"
        assert body["session_id"].startswith("arch_")

    def test_non_dg_blocked(self, client) -> None:
        """决策书 §4.1 锁 DG 主导建体系；READER 应 403。"""
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 403

    def test_anonymous_blocked(self, client) -> None:
        r = client.post("/api/v1/architect/sessions", json={"project_id": "p1"})
        assert r.status_code == 403


# ════════════════════════════════════════════════════════════════════════
#  GET /architect/sessions/{id}
# ════════════════════════════════════════════════════════════════════════


class TestGetSession:
    def test_unknown_returns_404(self, client) -> None:
        r = client.get(
            "/api/v1/architect/sessions/ghost",
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════
#  POST /architect/sessions/{id}/message
# ════════════════════════════════════════════════════════════════════════


class TestPostMessage:
    def test_unknown_session_404(self, client) -> None:
        r = client.post(
            "/api/v1/architect/sessions/ghost/message",
            json={"content": "hi"},
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════
#  POST /architect/sessions/{id}/export
# ════════════════════════════════════════════════════════════════════════


class TestExport:
    def test_export_full_flow(self, client) -> None:
        """端到端：create → mock identify 到 propose → 直接置 draft → export。"""
        # 创建 session
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "DG"},
        )
        session_id = r.json()["session_id"]

        # 直接给 agent 注入 draft（绕过 LLM 调用）
        from packages.architect.agent import get_architect_agent
        from packages.common.types import TaxonomyDraft
        from packages.templates.registry import TaxonomyNode
        agent = get_architect_agent()
        s = agent.get_session(session_id)
        s.draft = TaxonomyDraft(
            industry_code="manufacturing",
            industry_name="制造业",
            confidence=0.85,
            taxonomy=[
                TaxonomyNode(id="production", name="生产管理", level=2),
                TaxonomyNode(id="quality", name="质量管理", level=2),
            ],
        )

        # 导出
        r = client.post(
            f"/api/v1/architect/sessions/{session_id}/export",
            json={"custom_code_suffix": "test", "register_globally": False},
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["industry_code"] == "manufacturing-test"
        assert body["node_count"] == 2
        assert body["stage"] == "export"

    def test_export_without_draft_400(self, client) -> None:
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "DG"},
        )
        session_id = r.json()["session_id"]
        # 没 draft 直接 export
        r = client.post(
            f"/api/v1/architect/sessions/{session_id}/export",
            json={},
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════
#  GET /architect/sessions/{id}/draft (YAML)
# ════════════════════════════════════════════════════════════════════════


class TestGetDraft:
    def test_yaml_response(self, client) -> None:
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "DG"},
        )
        session_id = r.json()["session_id"]

        from packages.architect.agent import get_architect_agent
        from packages.common.types import TaxonomyDraft
        from packages.templates.registry import TaxonomyNode
        agent = get_architect_agent()
        s = agent.get_session(session_id)
        s.draft = TaxonomyDraft(
            industry_code="manufacturing", industry_name="制造业",
            confidence=0.85,
            taxonomy=[TaxonomyNode(id="x", name="X", level=2)],
        )

        r = client.get(
            f"/api/v1/architect/sessions/{session_id}/draft",
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 200
        assert "manufacturing" in r.text
        # YAML 格式（不是 JSON）
        assert "code:" in r.text or "code :" in r.text

    def test_no_draft_400(self, client) -> None:
        r = client.post(
            "/api/v1/architect/sessions",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "DG"},
        )
        session_id = r.json()["session_id"]
        r = client.get(
            f"/api/v1/architect/sessions/{session_id}/draft",
            headers={"X-Test-Roles": "DG"},
        )
        assert r.status_code == 400
