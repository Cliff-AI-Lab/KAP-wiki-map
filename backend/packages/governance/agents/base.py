"""治理 Agent 基类 — V15 Phase I."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.common import get_logger
from packages.common.types import GovernanceQueueItem
from packages.storage.governance_queue_store import GovernanceQueueStore


log = get_logger("governance.base")


@dataclass
class AgentRunResult:
    """Agent 单次运行结果。"""
    agent: str
    ok: bool
    scanned: int = 0        # 扫描了多少个单元 (wiki 页 / 实体 / 域)
    produced: int = 0        # 产出多少条工单
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "ok": self.ok,
            "scanned": self.scanned,
            "produced": self.produced,
            "skipped": self.skipped,
            "errors": self.errors,
            "detail": self.detail,
        }


class BaseGovernanceAgent:
    """治理 Agent 抽象基类。

    子类实现 run(project_id, queue_store, **stores) -> AgentRunResult
    规则:
      - 只读外部 Store, 只写 GovernanceQueueStore
      - 产出的 Item 必须设置 agent / kind / title / target_ref / priority
      - 异常内部捕获, 不抛出 (汇集到 result.errors)
    """

    name: str = "base"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        **kwargs: Any,
    ) -> AgentRunResult:
        raise NotImplementedError

    async def _push(
        self,
        queue_store: GovernanceQueueStore,
        item: GovernanceQueueItem,
    ) -> None:
        """把一个 Item 放进队列。"""
        await queue_store.upsert(item)
        log.info("governance_item_pushed",
                 agent=item.agent, kind=item.kind, id=item.id,
                 project=item.project_id, priority=item.priority)
