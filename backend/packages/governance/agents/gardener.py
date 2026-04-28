"""Gardener Agent — 纯规则存量治理.

扫所有 domain_overview Wiki 页的 compiled_at, 超 30 天产 archive_suggest 工单.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from packages.common import get_logger
from packages.common.types import GovernanceQueueItem
from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.storage.governance_queue_store import GovernanceQueueStore
from packages.storage.wiki_store import WikiStore

log = get_logger("governance.gardener")

STALE_DAYS_LOW = 30
STALE_DAYS_MID = 60
STALE_DAYS_HIGH = 90


def _parse_compiled_at(v: Any) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _priority_from_days(days: int) -> int:
    if days >= STALE_DAYS_HIGH:
        return 60
    if days >= STALE_DAYS_MID:
        return 45
    return 30


class GardenerAgent(BaseGovernanceAgent):
    name = "gardener"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        wiki_store: WikiStore = None,
        **_: Any,
    ) -> AgentRunResult:
        result = AgentRunResult(agent=self.name, ok=True)

        if wiki_store is None:
            result.ok = False
            result.errors.append("缺少 wiki_store 依赖")
            return result

        try:
            pages = await wiki_store.list_pages(project_id, page_type="domain_overview")
        except Exception as e:
            result.ok = False
            result.errors.append(f"拉取 Wiki 页失败: {e}")
            return result

        now = datetime.now(timezone.utc)

        for page in pages:
            result.scanned += 1
            compiled = _parse_compiled_at(getattr(page, "compiled_at", None))
            if compiled is None:
                result.skipped += 1
                continue
            # 容错 naive datetime
            if compiled.tzinfo is None:
                compiled = compiled.replace(tzinfo=timezone.utc)
            days = (now - compiled).days
            if days < STALE_DAYS_LOW:
                continue

            await self._push(queue_store, GovernanceQueueItem(
                id=f"gq_{uuid.uuid4().hex[:10]}",
                project_id=project_id,
                agent="gardener",
                kind="archive_suggest",
                title=f"[冷门] {page.title[:40]} 超 {days} 天未刷新",
                description=f"compiled_at={compiled.isoformat()[:10]}, 建议归档或重新编译",
                target_ref=f"page/{page.page_id}",
                priority=_priority_from_days(days),
                status="pending",
                created_at=now,
            ))
            result.produced += 1

        result.detail["now"] = now.isoformat()
        result.detail["thresholds"] = {"low": STALE_DAYS_LOW, "mid": STALE_DAYS_MID, "high": STALE_DAYS_HIGH}
        log.info("gardener_run_done", project=project_id,
                 scanned=result.scanned, produced=result.produced,
                 skipped=result.skipped)
        return result
