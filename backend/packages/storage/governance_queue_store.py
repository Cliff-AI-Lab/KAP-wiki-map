"""治理工单存储 — V15 Phase C + M1 4×6 矩阵审核台扩展。

V15: 四 Agent (Curator/Auditor/Deduper/Gardener) 产出工单 → 此 Store 聚合。
M1: 加 4×6 矩阵 (claim/escalate/list_matrix/find_overdue) 支撑决策书 §5.2 D6 + D12。

PoC 仅 memory 模式；后续可照 wiki_store 样式加 PG 表。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from packages.common import get_logger
from packages.common.types import (
    GovernanceAgent,
    GovernanceDecision,
    GovernanceQueueItem,
    ReviewerRole,
)

log = get_logger("storage.governance_queue")


class GovernanceQueueStore:
    def __init__(self, use_memory: bool = True) -> None:
        self._use_memory = use_memory
        self._items: dict[str, GovernanceQueueItem] = {}  # id -> item

    async def initialize(self, pg_conn: object = None) -> None:
        if self._use_memory:
            log.info("governance_queue_store_memory_mode")

    async def list(
        self,
        project_id: str,
        status: str | None = None,
        agent: str | None = None,
        workstation: str | None = None,
        assigned_role: str | None = None,
    ) -> list[GovernanceQueueItem]:
        """列出工单。M1 加 workstation / assigned_role 过滤参数（决策书 §5.2 矩阵看板）。"""
        out = [
            it for it in self._items.values()
            if it.project_id == project_id
            and (status is None or it.status == status)
            and (agent is None or it.agent == agent)
            and (workstation is None or it.workstation == workstation)
            and (assigned_role is None or it.assigned_role == assigned_role)
        ]
        out.sort(key=lambda x: (-x.priority, x.created_at))
        return out

    async def get(self, item_id: str) -> GovernanceQueueItem | None:
        return self._items.get(item_id)

    async def upsert(self, item: GovernanceQueueItem) -> None:
        self._items[item.id] = item

    async def decide(
        self,
        item_id: str,
        decision: GovernanceDecision,
        resolver: str,
    ) -> GovernanceQueueItem | None:
        item = self._items.get(item_id)
        if not item:
            return None
        status_map = {"approve": "approved", "reject": "rejected", "edit": "edited"}
        item.status = status_map[decision]  # type: ignore[assignment]
        item.resolved_at = datetime.now(timezone.utc)
        item.resolver = resolver
        return item

    # ════════════════════════════════════════════════════════════════════
    #  M1 4×6 矩阵审核台扩展（决策书 §5.2 D6 + §5.5 D12）
    # ════════════════════════════════════════════════════════════════════

    async def claim(
        self, item_id: str, claimer: str
    ) -> GovernanceQueueItem | None:
        """角色认领工单：状态 pending → reviewing。

        重复认领（reviewing 状态再 claim）允许：覆盖 claimer + claimed_at（交接场景）。
        已 approved/rejected/edited/escalated 工单不能 claim。
        """
        item = self._items.get(item_id)
        if not item:
            return None
        if item.status not in ("pending", "reviewing"):
            return None
        item.status = "reviewing"
        item.claimed_by = claimer
        item.claimed_at = datetime.now(timezone.utc)
        return item

    async def escalate(
        self, item_id: str, reason: str, target_role: ReviewerRole
    ) -> GovernanceQueueItem | None:
        """SLA 超时升级：把 assigned_role 提升到 target_role，状态 → escalated。

        Args:
            item_id: 工单 ID
            reason: 升级原因（D12 必填，回流训练 + 审计）
            target_role: 升级目标角色（由 packages.governance.matrix.next_role_in_chain 决定）

        - DG 顶级再升级时，target_role 仍为 DG，但 reason 拼接"积压告警"
        - reset claimed_by/claimed_at（升级后由新角色重新认领）
        - reset sla_due_at 留给上层决定（store 不假设 SLA 时长）
        """
        item = self._items.get(item_id)
        if not item:
            return None
        item.status = "escalated"
        item.escalated_to = target_role
        item.assigned_role = target_role
        item.escalation_reason = (
            (item.escalation_reason + " | " if item.escalation_reason else "") + reason
        )
        item.claimed_by = None
        item.claimed_at = None
        item.sla_due_at = None
        return item

    async def list_matrix(
        self, project_id: str
    ) -> dict[tuple[str, str], int]:
        """4×6 矩阵看板：返回 (workstation, assigned_role) → 待办计数。

        计入 pending + reviewing + escalated（escalated 仍占着新主审角色的格子）；
        approved/rejected/edited 不计。

        无 workstation 或无 assigned_role 的工单（V15 既有 demo）落入
        ``("uncategorized", "uncategorized")`` 桶。
        """
        counts: dict[tuple[str, str], int] = {}
        for it in self._items.values():
            if it.project_id != project_id:
                continue
            if it.status not in ("pending", "reviewing", "escalated"):
                continue
            ws = it.workstation or "uncategorized"
            role = it.assigned_role or "uncategorized"
            counts[(ws, role)] = counts.get((ws, role), 0) + 1
        return counts

    async def find_overdue(
        self, now: datetime | None = None
    ) -> list[GovernanceQueueItem]:
        """找 sla_due_at < now 的 pending/reviewing 工单（escalated 已经升过不再扫）。

        Args:
            now: 比较时刻；默认当前 UTC 时间（测试用）
        """
        cutoff = now or datetime.now(timezone.utc)
        out = []
        for it in self._items.values():
            if it.status not in ("pending", "reviewing"):
                continue
            if it.sla_due_at is None:
                continue
            if it.sla_due_at < cutoff:
                out.append(it)
        return out

    async def seed_demo(self, project_id: str) -> int:
        """种入 25 条 demo 工单。"""
        existing = await self.list(project_id)
        if existing:
            return 0

        seeds: list[tuple[GovernanceAgent, str, str, str, int]] = []
        # 3 条 Curator draft_pending
        seeds.extend([
            ("curator", "draft_pending", f"编译域 Wiki 初稿: {d}", f"wiki/{d}", 80)
            for d in ("energy/safety/hazard", "energy/production/equipment/maintenance", "energy/safety/permit/hot_work")
        ])
        # 12 条 Auditor unverified
        seeds.extend([
            ("auditor", "unverified", f"断言 #{i+1} 无 Raw 引用", f"page/energy_fs_{i+1:03d}", 60)
            for i in range(12)
        ])
        # 2 条 Deduper conflict
        seeds.extend([
            ("deduper", "conflict", "重大隐患分级与 AQ/T 3034-2022 冲突", "page/hazard_level", 90),
            ("deduper", "conflict", "动火作业审批层级描述不一", "page/hot_work", 85),
        ])
        # 8 条 Gardener archive_suggest
        seeds.extend([
            ("gardener", "archive_suggest", f"冷门页建议归档: {t}", f"page/{t}", 30)
            for t in (
                "energy/logistics/warehouse/general",
                "energy/env/monitoring/weekly",
                "energy/procurement/supplier",
                "energy/emergency/historical",
                "energy/safety/drill_old",
                "energy/production/archive_2019",
                "energy/environmental/old",
                "energy/logistics/transport_old",
            )
        ])

        count = 0
        for agent, kind, title, ref, prio in seeds:
            item = GovernanceQueueItem(
                id=f"gq_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                agent=agent,
                kind=kind,  # type: ignore[arg-type]
                title=title,
                description=f"由 {agent} Agent 自动产出，待人工决策",
                target_ref=ref,
                priority=prio,
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
            await self.upsert(item)
            count += 1
        log.info("governance_queue_seeded", project_id=project_id, count=count)
        return count
