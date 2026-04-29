"""M4 批 4 · 全量重抽影子库 API 单测（决策书 §5.3）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.rebuild import router
from packages.common.auth import UserContext
from packages.common.types import ExtractionResult
from packages.rebuild import (
    reset_jobs_for_test,
    reset_shadow_store_for_test,
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
    reset_jobs_for_test()
    reset_shadow_store_for_test()
    yield
    reset_jobs_for_test()
    reset_shadow_store_for_test()


@pytest.fixture
def client():
    return TestClient(_build_app())


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/jobs
# ════════════════════════════════════════════════════════════════════════


class TestStartJob:
    def test_sme_can_start(self, client) -> None:
        async def fake_extract(*, doc_id, content, industry_code, project_id):
            return ExtractionResult(doc_id=doc_id)

        with patch(
            "packages.extraction.entity_extractor.extract_entities_and_relations",
            side_effect=fake_extract,
        ):
            r = client.post(
                "/api/v1/rebuild/jobs",
                json={
                    "project_id": "p1",
                    "source_version": "v1",
                    "target_version": "v2",
                    "industry_code": "manufacturing",
                    "chunks": [{"chunk_id": "c1", "doc_id": "d1", "content": "x"}],
                },
                headers={"X-Test-Roles": "SME"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["chunks_total"] == 1

    def test_non_sme_blocked(self, client) -> None:
        r = client.post(
            "/api/v1/rebuild/jobs",
            json={
                "project_id": "p", "source_version": "v1",
                "target_version": "v2", "industry_code": "manufacturing",
                "chunks": [],
            },
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 403


# ════════════════════════════════════════════════════════════════════════
#  GET /rebuild/jobs / GET /rebuild/jobs/{id}
# ════════════════════════════════════════════════════════════════════════


class TestListAndGetJob:
    def test_list_empty(self, client) -> None:
        r = client.get("/api/v1/rebuild/jobs")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_unknown_returns_404(self, client) -> None:
        r = client.get("/api/v1/rebuild/jobs/ghost")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════
#  GET /rebuild/diff
# ════════════════════════════════════════════════════════════════════════


class TestDiffEndpoint:
    def test_diff_returns_report(self, client) -> None:
        # 注入数据
        from packages.rebuild import get_shadow_store
        s = get_shadow_store()
        s.add_entity("p1", "v1", entity_name="A",
                     type_id="equipment", doc_id="d")
        s.add_entity("p1", "v2", entity_name="A",
                     type_id="equipment", doc_id="d")
        s.add_entity("p1", "v2", entity_name="B",
                     type_id="process", doc_id="d")

        r = client.get(
            "/api/v1/rebuild/diff?project_id=p1&source=v1&target=v2",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["source_node_count"] == 1
        assert body["target_node_count"] == 2
        assert "process" in body["added_entity_types"]


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/promote
# ════════════════════════════════════════════════════════════════════════


class TestPromoteEndpoint:
    def test_safe_promote_succeeds(self, client) -> None:
        from packages.rebuild import get_shadow_store
        s = get_shadow_store()
        s.begin_shadow("p1", "v2")
        # 准备相似规模的 source / target
        for i in range(10):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")

        r = client.post(
            "/api/v1/rebuild/promote",
            json={
                "project_id": "p1", "source_version": "v1",
                "target_version": "v2", "force": False,
            },
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert r.json()["safe_to_promote"] is True

    def test_unsafe_without_force_400(self, client) -> None:
        from packages.rebuild import get_shadow_store
        s = get_shadow_store()
        s.begin_shadow("p1", "v2")
        # 巨大变化
        for i in range(100):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(20):
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")

        r = client.post(
            "/api/v1/rebuild/promote",
            json={
                "project_id": "p1", "source_version": "v1",
                "target_version": "v2", "force": False,
            },
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 400

    def test_force_overrides(self, client) -> None:
        from packages.rebuild import get_shadow_store
        s = get_shadow_store()
        s.begin_shadow("p1", "v2")
        for i in range(100):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(20):
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")

        r = client.post(
            "/api/v1/rebuild/promote",
            json={
                "project_id": "p1", "source_version": "v1",
                "target_version": "v2", "force": True,
            },
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert r.json()["safe_to_promote"] is False  # 强制切换但报告仍为 unsafe


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/rollback
# ════════════════════════════════════════════════════════════════════════


class TestRollbackEndpoint:
    def test_rollback_to_previous(self, client) -> None:
        from packages.rebuild import get_shadow_store
        s = get_shadow_store()
        s._previous_main["p1"] = "v1.0.0"

        r = client.post(
            "/api/v1/rebuild/rollback",
            json={"project_id": "p1"},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert r.json()["rolled_back_to"] == "v1.0.0"

    def test_no_previous_returns_400(self, client) -> None:
        r = client.post(
            "/api/v1/rebuild/rollback",
            json={"project_id": "p_no"},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 400
