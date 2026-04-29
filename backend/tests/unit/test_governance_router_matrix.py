"""M1 矩阵审核台 · 批 3 · governance router 新端点单测。

覆盖：
- /governance/matrix 4×6 矩阵看板
- /governance/queue/{id}/claim 认领
- /governance/queue/{id}/escalate 主动升级
- /governance/queue 加 workstation/assigned_role filter
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.governance import router
from api.deps import get_governance_queue_store
from packages.common.types import GovernanceQueueItem
from packages.storage.governance_queue_store import GovernanceQueueStore


def _make_item(
    project_id: str = "p1",
    status: str = "pending",
    workstation: str | None = None,
    assigned_role: str | None = None,
    agent: str = "auditor",
) -> GovernanceQueueItem:
    return GovernanceQueueItem(
        id=f"gq_{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        agent=agent,  # type: ignore[arg-type]
        kind="unverified",
        title="t",
        priority=50,
        status=status,  # type: ignore[arg-type]
        created_at=datetime.now(timezone.utc),
        workstation=workstation,  # type: ignore[arg-type]
        assigned_role=assigned_role,  # type: ignore[arg-type]
    )


@pytest.fixture
async def app_with_store():
    """构造带 GovernanceQueueStore override 的测试 app。"""
    store = GovernanceQueueStore()
    await store.initialize()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_governance_queue_store] = lambda: store
    return app, store


# ──────── /governance/matrix ────────


class TestMatrixEndpoint:
    async def test_empty_returns_zero(self, app_with_store) -> None:
        app, _ = app_with_store
        client = TestClient(app)
        r = client.get("/api/v1/governance/matrix?project_id=p1")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["cells"] == []
        assert body["uncategorized"] == 0

    async def test_aggregates_cells(self, app_with_store) -> None:
        app, store = app_with_store
        await store.upsert(_make_item(workstation="W4", assigned_role="SME"))
        await store.upsert(_make_item(workstation="W4", assigned_role="SME"))
        await store.upsert(_make_item(workstation="W1", assigned_role="DG"))

        client = TestClient(app)
        r = client.get("/api/v1/governance/matrix?project_id=p1")
        body = r.json()
        cells = {(c["workstation"], c["assigned_role"]): c["count"] for c in body["cells"]}
        assert cells[("W4", "SME")] == 2
        assert cells[("W1", "DG")] == 1
        assert body["total"] == 3

    async def test_uncategorized_bucket(self, app_with_store) -> None:
        """V15 既有 demo 工单无 workstation → uncategorized。"""
        app, store = app_with_store
        await store.upsert(_make_item(workstation=None, assigned_role=None))

        client = TestClient(app)
        r = client.get("/api/v1/governance/matrix?project_id=p1")
        body = r.json()
        assert body["uncategorized"] == 1
        assert body["cells"] == []  # 没有 workstation，不进 cells


# ──────── /governance/queue/{id}/claim ────────


class TestClaimEndpoint:
    async def test_claim_pending_succeeds(self, app_with_store) -> None:
        app, store = app_with_store
        item = _make_item(workstation="W4", assigned_role="SME")
        await store.upsert(item)

        client = TestClient(app)
        r = client.post(
            f"/api/v1/governance/queue/{item.id}/claim",
            json={"claimer": "alice"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "reviewing"
        assert r.json()["claimed_by"] == "alice"

    async def test_claim_nonexistent_returns_404(self, app_with_store) -> None:
        app, _ = app_with_store
        client = TestClient(app)
        r = client.post(
            "/api/v1/governance/queue/ghost/claim",
            json={"claimer": "alice"},
        )
        assert r.status_code == 404

    async def test_claim_resolved_item_returns_404(self, app_with_store) -> None:
        app, store = app_with_store
        item = _make_item(status="approved")
        await store.upsert(item)

        client = TestClient(app)
        r = client.post(
            f"/api/v1/governance/queue/{item.id}/claim",
            json={"claimer": "alice"},
        )
        assert r.status_code == 404


# ──────── /governance/queue/{id}/escalate ────────


class TestEscalateEndpoint:
    async def test_escalate_aiops_to_sme(self, app_with_store) -> None:
        app, store = app_with_store
        item = _make_item(workstation="W6", assigned_role="AIOps")
        await store.upsert(item)

        client = TestClient(app)
        r = client.post(
            f"/api/v1/governance/queue/{item.id}/escalate",
            json={"reason": "manual escalate"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "escalated"
        assert r.json()["assigned_role"] == "SME"
        assert "manual escalate" in r.json()["escalation_reason"]

    async def test_escalate_without_role_returns_400(self, app_with_store) -> None:
        """V15 既有工单无 assigned_role 不能升级。"""
        app, store = app_with_store
        item = _make_item(assigned_role=None)
        await store.upsert(item)

        client = TestClient(app)
        r = client.post(
            f"/api/v1/governance/queue/{item.id}/escalate",
            json={"reason": "x"},
        )
        assert r.status_code == 400


# ──────── /governance/queue 过滤参数扩展 ────────


class TestQueueFilterExtension:
    async def test_filter_by_workstation(self, app_with_store) -> None:
        app, store = app_with_store
        await store.upsert(_make_item(workstation="W4", assigned_role="SME"))
        await store.upsert(_make_item(workstation="W1", assigned_role="DG"))

        client = TestClient(app)
        r = client.get("/api/v1/governance/queue?project_id=p1&workstation=W4")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["workstation"] == "W4"

    async def test_filter_by_assigned_role(self, app_with_store) -> None:
        app, store = app_with_store
        await store.upsert(_make_item(workstation="W4", assigned_role="SME"))
        await store.upsert(_make_item(workstation="W4", assigned_role="DG"))

        client = TestClient(app)
        r = client.get("/api/v1/governance/queue?project_id=p1&assigned_role=SME")
        body = r.json()
        assert len(body) == 1
        assert body[0]["assigned_role"] == "SME"
