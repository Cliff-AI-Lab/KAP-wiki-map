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
    arecord_decision,
    list_decisions,
    record_decision,
    reset_decisions_for_test,
    set_pg_sink,
)
from packages.observability.pg_decision_log import (
    initialize_pg_decision_log,
    shutdown_pg_decision_log,
)
from packages.observability.pg_query_log import (
    initialize_pg_query_log,
    shutdown_pg_query_log,
)
from packages.observability.pg_recall_eval import (
    initialize_pg_recall_eval,
    shutdown_pg_recall_eval,
)
from packages.observability.condition_health import (
    ConditionHealth,
    ConditionType,
    analyze_condition_health,
    classify_condition,
)
from packages.observability.prompt_versions import (
    PromptABScore,
    PromptVersion,
    compute_prompt_ab_score,
    create_prompt_version,
    deactivate_prompt_version,
    get_active_version,
    get_version,
    list_prompt_versions,
    reset_prompt_versions_for_test,
    resolve_active_system_prompt,
)
from packages.observability.recall_eval import (
    GroundTruthCandidate,
    GroundTruthQuery,
    MultiKRecallReport,
    RecallEvalDetail,
    RecallEvalReport,
    add_ground_truth,
    auto_construct_ground_truth_candidates,
    check_recall_alerts_and_propagate,
    compute_recall_trend,
    eval_all_projects,
    get_ground_truth,
    get_latest_report,
    list_ground_truth,
    list_projects_with_ground_truth,
    list_reports,
    remove_ground_truth,
    reset_recall_eval_for_test,
    run_multi_k_recall_eval,
    run_recall_eval,
    set_recall_eval_pg_sinks,
)
from packages.observability.query_log import (
    QueryEvent,
    aggregate_queries,
    arecord_query,
    arecord_query_feedback,
    get_query_event,
    list_queries,
    record_query,
    record_query_feedback,
    reset_queries_for_test,
    set_query_feedback_pg_sink,
    set_query_pg_sink,
)

__all__ = [
    "ConditionHealth",
    "ConditionType",
    "DecisionEvent",
    "DecisionType",
    "GroundTruthCandidate",
    "PromptABScore",
    "PromptVersion",
    "GroundTruthQuery",
    "MultiKRecallReport",
    "QueryEvent",
    "RecallEvalDetail",
    "RecallEvalReport",
    "add_ground_truth",
    "analyze_condition_health",
    "auto_construct_ground_truth_candidates",
    "classify_condition",
    "aggregate_decisions",
    "aggregate_queries",
    "arecord_decision",
    "arecord_query",
    "arecord_query_feedback",
    "check_recall_alerts_and_propagate",
    "compute_prompt_ab_score",
    "compute_recall_trend",
    "create_prompt_version",
    "deactivate_prompt_version",
    "eval_all_projects",
    "get_active_version",
    "get_version",
    "list_projects_with_ground_truth",
    "list_prompt_versions",
    "reset_prompt_versions_for_test",
    "resolve_active_system_prompt",
    "get_ground_truth",
    "get_latest_report",
    "get_query_event",
    "initialize_pg_decision_log",
    "initialize_pg_query_log",
    "initialize_pg_recall_eval",
    "list_decisions",
    "list_ground_truth",
    "list_queries",
    "list_reports",
    "record_decision",
    "record_query",
    "record_query_feedback",
    "remove_ground_truth",
    "reset_decisions_for_test",
    "reset_queries_for_test",
    "reset_recall_eval_for_test",
    "run_multi_k_recall_eval",
    "run_recall_eval",
    "set_pg_sink",
    "set_query_feedback_pg_sink",
    "set_query_pg_sink",
    "set_recall_eval_pg_sinks",
    "shutdown_pg_decision_log",
    "shutdown_pg_query_log",
    "shutdown_pg_recall_eval",
]
