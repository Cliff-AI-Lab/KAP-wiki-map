"""M1 矩阵审核台 · 批 2 · GovernanceQueueStore 扩展 + SLA sweep 单测。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from packages.common.types import GovernanceQueueItem
from packages.governance.sla import sweep_overdue_tasks
from packages.storage.governance_queue_store import GovernanceQueueStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_item(
    *,
    project_id: str = "test_proj",
    status: str = "pending",
    workstation: str | None = None,
    assigned_role: str | None = None,
    sla_due_at: datetime | None = None,
    confidence: float | None = None,
) -> GovernanceQueueItem:
    return GovernanceQueueItem(
        id=f"gq_{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        agent="curator",
        kind="draft_pending",
        title="test",
        priority=50,
        status=status,  # type: ignore[arg-type]
        created_at=_now(),
        workstation=workstation,  # type: ignore[arg-type]
        assigned_role=assigned_role,  # type: ignore[arg-type]
        sla_due_at=sla_due_at,
        confidence=confidence,
    )


@pytest.fixture
async def store():
    s = GovernanceQueueStore()
    await s.initialize()
    return s


# ──────── claim ────────


class TestClaim:
    async def test_pending_to_reviewing(self, store) -> None:
        item = _make_item(workstation="W4", assigned_role="SME")
        await store.upsert(item)

        result = await store.claim(item.id, "alice")
        assert result is not None
        assert result.status == "reviewing"
        assert result.claimed_by == "alice"
        assert result.claimed_at is not None

    async def test_already_reviewing_can_be_reclaimed(self, store) -> None:
        """交接场景：已 reviewing 的可重新 claim（覆盖 claimer）。"""
        item = _make_item(status="reviewing", assigned_role="SME")
        item.claimed_by = "old"
        await store.upsert(item)

        result = await store.claim(item.id, "new")
        assert result.claimed_by == "new"

    async def test_approved_cannot_be_claimed(self, store) -> None:
        item = _make_item(status="approved")
        await store.upsert(item)
        result = await store.claim(item.id, "alice")
        assert result is None

    async def test_nonexistent_returns_none(self, store) -> None:
        result = await store.claim("ghost-id", "alice")
        assert result is None


# ──────── escalate ────────


class TestEscalate:
    async def test_escalate_resets_claim_and_sla(self, store) -> None:
        item = _make_item(
            status="reviewing", assigned_role="SME",
            sla_due_at=_now() - timedelta(minutes=5),
        )
        item.claimed_by = "alice"
        await store.upsert(item)

        result = await store.escalate(item.id, "SLA 超时", "DG")
        assert result.status == "escalated"
        assert result.assigned_role == "DG"
        assert result.escalated_to == "DG"
        assert "SLA 超时" in result.escalation_reason
        assert result.claimed_by is None
        assert result.claimed_at is None
        assert result.sla_due_at is None

    async def test_escalation_reason_appended(self, store) -> None:
        """多次升级 reason 累加（用 ' | ' 分隔）。"""
        item = _make_item(assigned_role="AIOps")
        await store.upsert(item)
        await store.escalate(item.id, "first", "SME")
        result = await store.escalate(item.id, "second", "DG")
        assert "first" in result.escalation_reason
        assert "second" in result.escalation_reason


# ──────── list_matrix ────────


class TestListMatrix:
    async def test_pending_reviewing_escalated_counted(self, store) -> None:
        await store.upsert(_make_item(workstation="W4", assigned_role="SME", status="pending"))
        await store.upsert(_make_item(workstation="W4", assigned_role="SME", status="reviewing"))
        await store.upsert(_make_item(workstation="W4", assigned_role="SME", status="escalated"))
        await store.upsert(_make_item(workstation="W4", assigned_role="SME", status="approved"))

        matrix = await store.list_matrix("test_proj")
        assert matrix.get(("W4", "SME")) == 3  # approved 不计

    async def test_uncategorized_bucket_for_old_v15(self, store) -> None:
        """V15 既有 demo 工单无 workstation/role → uncategorized 桶。"""
        await store.upsert(_make_item(workstation=None, assigned_role=None))
        matrix = await store.list_matrix("test_proj")
        assert matrix.get(("uncategorized", "uncategorized")) == 1

    async def test_only_target_project(self, store) -> None:
        await store.upsert(_make_item(project_id="A", workstation="W1", assigned_role="DG"))
        await store.upsert(_make_item(project_id="B", workstation="W1", assigned_role="DG"))
        matrix = await store.list_matrix("A")
        assert sum(matrix.values()) == 1


# ──────── find_overdue ────────


class TestFindOverdue:
    async def test_returns_only_due_items(self, store) -> None:
        past = _now() - timedelta(hours=1)
        future = _now() + timedelta(hours=1)
        await store.upsert(_make_item(sla_due_at=past, assigned_role="SME"))
        await store.upsert(_make_item(sla_due_at=future, assigned_role="SME"))
        await store.upsert(_make_item(sla_due_at=None, assigned_role="SME"))

        overdue = await store.find_overdue()
        assert len(overdue) == 1

    async def test_skip_already_escalated(self, store) -> None:
        """已 escalated 的不再扫（已经升过一次，不重复升级）。"""
        past = _now() - timedelta(hours=1)
        await store.upsert(_make_item(status="escalated", sla_due_at=past, assigned_role="DG"))
        overdue = await store.find_overdue()
        assert overdue == []

    async def test_skip_resolved(self, store) -> None:
        past = _now() - timedelta(hours=1)
        await store.upsert(_make_item(status="approved", sla_due_at=past))
        overdue = await store.find_overdue()
        assert overdue == []


# ──────── sweep_overdue_tasks ────────


class TestSlaSweep:
    async def test_aiops_overdue_escalates_to_sme(self, store) -> None:
        past = _now() - timedelta(hours=1)
        item = _make_item(
            workstation="W6", assigned_role="AIOps",
            status="pending", sla_due_at=past,
        )
        await store.upsert(item)

        upgraded = await sweep_overdue_tasks(store)
        assert upgraded == 1
        result = await store.get(item.id)
        assert result.status == "escalated"
        assert result.assigned_role == "SME"

    async def test_dg_top_role_marks_backlog_alert(self, store) -> None:
        """DG 已是顶级，再超时仍 escalate 但 reason 含'积压告警'。"""
        past = _now() - timedelta(hours=1)
        item = _make_item(
            workstation="W5", assigned_role="DG",
            status="pending", sla_due_at=past,
        )
        await store.upsert(item)

        await sweep_overdue_tasks(store)
        result = await store.get(item.id)
        assert result.assigned_role == "DG"
        assert "积压告警" in result.escalation_reason

    async def test_skip_v15_items_without_role(self, store) -> None:
        """V15 既有 demo 工单无 assigned_role，跳过不报错。"""
        past = _now() - timedelta(hours=1)
        await store.upsert(_make_item(
            assigned_role=None, status="pending", sla_due_at=past,
        ))
        upgraded = await sweep_overdue_tasks(store)
        assert upgraded == 0

    async def test_no_overdue_returns_zero(self, store) -> None:
        future = _now() + timedelta(hours=1)
        await store.upsert(_make_item(
            assigned_role="SME", status="pending", sla_due_at=future,
        ))
        upgraded = await sweep_overdue_tasks(store)
        assert upgraded == 0
