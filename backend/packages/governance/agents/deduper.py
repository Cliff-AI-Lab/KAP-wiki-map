"""Deduper Agent — Wiki ↔ Wiki 重复/冲突检测 (占位).

Phase I-3 接向量相似度; 当前仅骨架.
"""

from __future__ import annotations

from typing import Any

from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.storage.governance_queue_store import GovernanceQueueStore


class DeduperAgent(BaseGovernanceAgent):
    name = "deduper"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        **_: Any,
    ) -> AgentRunResult:
        # TODO Phase I-3: Wiki 页两两 embedding 相似度 → 超阈值产 conflict 工单
        return AgentRunResult(
            agent=self.name,
            ok=True,
            detail={
                "status": "stub",
                "note": "Deduper 真跑待 Phase I-3 实现 (Wiki↔Wiki 向量相似度去重/冲突检测)",
            },
        )
