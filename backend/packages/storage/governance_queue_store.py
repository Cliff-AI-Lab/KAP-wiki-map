"""治理工单存储 — V15 Phase C.

四 Agent (Curator/Auditor/Deduper/Gardener) 产出工单 → 此 Store 聚合待人工决策。
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
    ) -> list[GovernanceQueueItem]:
        out = [
            it for it in self._items.values()
            if it.project_id == project_id
            and (status is None or it.status == status)
            and (agent is None or it.agent == agent)
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
