"""可观察性模块（M6 #3 · 决策书 §5.3 监测 → 简单指标聚合）。

decision_log：记录 SME / 系统的关键决策（approve / reject / promote / rollback），
聚合 API 给运营看趋势，不依赖 portal 埋点。

设计（feedback memory · AI native + 轻量化）：
- 函数式 + 内存存储（M7 PG 持久化）
- 不强制接入；调用方自愿调 record_decision
"""

from packages.observability.decision_log import (
    DecisionEvent,
    DecisionType,
    aggregate_decisions,
    list_decisions,
    record_decision,
    reset_decisions_for_test,
)

__all__ = [
    "DecisionEvent",
    "DecisionType",
    "aggregate_decisions",
    "list_decisions",
    "record_decision",
    "reset_decisions_for_test",
]
