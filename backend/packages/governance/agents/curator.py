"""Curator Agent — 扫 Raw + 问答缺口 LLM 起草 Wiki (占位).

Phase I-1 只做骨架；Phase I-2 接真 LLM 起草。
"""

from __future__ import annotations

from typing import Any

from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.storage.governance_queue_store import GovernanceQueueStore


class CuratorAgent(BaseGovernanceAgent):
    name = "curator"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        **_: Any,
    ) -> AgentRunResult:
        # TODO Phase I-2: 从 query_log + raw_store 找"未被 Wiki 覆盖的问题" → LLM 起草 draft
        return AgentRunResult(
            agent=self.name,
            ok=True,
            detail={
                "status": "stub",
                "note": "Curator 真跑待 Phase I-2 实现 (Raw 新增扫描 + 问答缺口 → LLM 起草)",
            },
        )
