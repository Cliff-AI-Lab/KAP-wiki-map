"""V15 治理 Agent 模块 — Phase I + K.

四小一大（V15 §3）:
  Curator      无→有: 扫 Raw + 问答缺口 → LLM 起草 Wiki
  Auditor      纵向: Wiki ↔ Raw 溯源一致性 (LLM judge)
  Deduper      横向: Wiki ↔ Wiki 重复/冲突
  Standardizer 归一化: GraphStore 实体别名统一 (借鉴 ai-knowledge-graph)
  Gardener     存量: 访问热度 + 时效 (纯规则)
  Planner      调度: 聚合产单

所有 Agent 产出落入 GovernanceQueueStore（人审工单）。
"""

from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.governance.agents.auditor import AuditorAgent
from packages.governance.agents.standardizer import StandardizerAgent
from packages.governance.agents.curator import CuratorAgent
from packages.governance.agents.deduper import DeduperAgent
from packages.governance.agents.gardener import GardenerAgent

__all__ = [
    "BaseGovernanceAgent",
    "AgentRunResult",
    "AuditorAgent",
    "StandardizerAgent",
    "CuratorAgent",
    "DeduperAgent",
    "GardenerAgent",
]


def get_agent(name: str):
    """按名字返回 Agent 实例 (单例模式可后续优化)。"""
    registry = {
        "auditor": AuditorAgent,
        "standardizer": StandardizerAgent,
        "curator": CuratorAgent,
        "deduper": DeduperAgent,
        "gardener": GardenerAgent,
    }
    cls = registry.get(name.lower())
    if not cls:
        raise ValueError(f"未知治理 Agent: {name}. 可选: {list(registry)}")
    return cls()
