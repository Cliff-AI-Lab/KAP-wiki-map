"""可观察性 API（M6 #3 + M7 · 决策书 §5.3 简单指标聚合）。

端点：
  GET /api/v1/observability/decisions[/aggregate]   决策事件 + 聚合（M6 #3）
  GET /api/v1/observability/queries[/aggregate]     查询事件 + 聚合（M7 #2）
  GET /api/v1/observability/dashboard               综合运营仪表盘（M7 #3）

权限：开放给所有登录角色（只读运营视图，决策书 §5.3 不限制）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.roles import ROLE_SME, RequireRole
from packages.observability import (
    AutoTuneResult,
    ConditionHealth,
    ConditionType,
    DecisionEvent,
    GroundTruthCandidate,
    GroundTruthQuery,
    MultiKRecallReport,
    PromptABScore,
    PromptVersion,
    QueryEvent,
    RecallEvalReport,
    add_ground_truth,
    auto_promote_best_prompt,
    auto_rollback_alerting_prompt,
    aggregate_decisions,
    aggregate_queries,
    analyze_condition_health,
    arecord_query_feedback,
    auto_construct_ground_truth_candidates,
    check_recall_alerts_and_propagate,
    check_useful_alerts_and_propagate,
    compute_prompt_ab_score,
    compute_recall_trend,
    compute_useful_rate_trend,
    create_prompt_version,
    deactivate_prompt_version,
    eval_all_projects,
    get_latest_report,
    list_decisions,
    list_ground_truth,
    list_prompt_versions,
    list_queries,
    list_reports,
    remove_ground_truth,
    run_multi_k_recall_eval,
    run_recall_eval,
)
from packages.rebuild import list_observations

log = get_logger("api.observability")

router = APIRouter(prefix="/observability", tags=["可观察性"])


@router.get("/decisions", response_model=list[DecisionEvent])
async def list_decision_events(
    project_id: str | None = Query(default=None),
    decision_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[DecisionEvent]:
    return list_decisions(
        project_id=project_id,
        decision_type=decision_type,  # type: ignore[arg-type]
        since=since, until=until, limit=limit,
    )


@router.get("/decisions/aggregate")
async def aggregate_decision_events(
    project_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict[str, Any]:
    return aggregate_decisions(
        project_id=project_id, since=since, until=until,
    )


# ════════════════════════════════════════════════════════════════════════
#  M7 #2 · 查询召回埋点
# ════════════════════════════════════════════════════════════════════════


@router.get("/queries", response_model=list[QueryEvent])
async def list_query_events(
    project_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[QueryEvent]:
    return list_queries(
        project_id=project_id, user_id=user_id,
        since=since, until=until, limit=limit,
    )


@router.get("/queries/aggregate")
async def aggregate_query_events(
    project_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict[str, Any]:
    return aggregate_queries(
        project_id=project_id, since=since, until=until,
    )


# ════════════════════════════════════════════════════════════════════════
#  M8 #1 · portal 用户反馈
# ════════════════════════════════════════════════════════════════════════


class QueryFeedbackBody(BaseModel):
    useful: bool
    note: str = Field(default="", max_length=200)


@router.post("/queries/{query_id}/feedback", response_model=QueryEvent)
async def submit_query_feedback(
    query_id: str, body: QueryFeedbackBody,
) -> QueryEvent:
    """portal "有用 / 无用" 按钮入口。

    任何登录用户可调；M9 加 RequireRole(USER) 走鉴权。
    """
    event = await arecord_query_feedback(
        query_id=query_id, useful=body.useful, note=body.note,
    )
    if event is None:
        raise HTTPException(status_code=404, detail=f"query_id={query_id} 不存在")
    # M15 #2 · 反馈后跑趋势检查；跌破阈值 propagate 到观察期 alerts
    if event.project_id:
        try:
            check_useful_alerts_and_propagate(project_id=event.project_id)
        except Exception:
            log.exception("useful_alert_check_failed")
    return event


@router.get("/queries/useful-trend")
async def useful_rate_trend(
    project_id: str | None = Query(default=None),
    window_size: int = Query(default=50, ge=1, le=500),
    lookback_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """useful_rate 时间窗对比（M9 #2 模式应用到用户反馈维度）。

    跌破阈值（默认 10pp）→ useful_alert=True；alert_messages 列出文字。
    """
    return compute_useful_rate_trend(
        project_id=project_id,
        window_size=window_size, lookback_size=lookback_size,
    )


# ════════════════════════════════════════════════════════════════════════
#  M8 #2 · 召回率评估管线
# ════════════════════════════════════════════════════════════════════════


class GroundTruthBody(BaseModel):
    project_id: str = ""
    query_text: str = Field(min_length=1, max_length=500)
    expected_doc_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=200)


@router.get("/ground-truth", response_model=list[GroundTruthQuery])
async def list_ground_truth_endpoint(
    project_id: str | None = Query(default=None),
) -> list[GroundTruthQuery]:
    return list_ground_truth(project_id=project_id)


@router.post("/ground-truth", response_model=GroundTruthQuery)
async def add_ground_truth_endpoint(
    body: GroundTruthBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> GroundTruthQuery:
    """SME 上传 ground truth 查询条目。"""
    gt = add_ground_truth(
        project_id=body.project_id,
        query_text=body.query_text,
        expected_doc_ids=body.expected_doc_ids,
        note=body.note,
    )
    log.info("ground_truth_added_via_api",
             gt_id=gt.gt_id, user=getattr(user, "user_id", "?"))
    return gt


@router.delete("/ground-truth/{gt_id}")
async def delete_ground_truth_endpoint(
    gt_id: str,
    user=Depends(RequireRole(ROLE_SME)),
) -> dict[str, Any]:
    if not remove_ground_truth(gt_id):
        raise HTTPException(status_code=404, detail="gt_id 不存在")
    return {"gt_id": gt_id, "removed": True}


class RunRecallEvalBody(BaseModel):
    project_id: str = ""
    version: str = ""
    k: int = Field(default=5, ge=1, le=50)


@router.post("/recall-eval", response_model=RecallEvalReport)
async def run_recall_eval_endpoint(
    body: RunRecallEvalBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> RecallEvalReport:
    """SME 触发召回率评估（对该 project 全部 ground truth 跑一遍）。

    M8 lite 用 qa_engine 包装为 ``QaCallable``。M9 加 trend / 自动定时跑。
    """
    # qa 包装：注入 qa_engine.ask（运行时）
    from api.deps import get_qa_engine

    async def qa_callable(query_text: str, k: int) -> list[str]:
        try:
            engine = get_qa_engine()
            result = await engine.ask(question=query_text, top_k=k)
            return [s.doc_id for s in result.sources]
        except Exception as e:
            log.warning("recall_eval_qa_engine_failed", error=str(e))
            return []

    report = await run_recall_eval(
        qa_callable=qa_callable,
        project_id=body.project_id, version=body.version, k=body.k,
    )
    # M9 #2 · 评估完跑趋势检查；跌破阈值自动告警观察期
    if body.project_id:
        try:
            check_recall_alerts_and_propagate(project_id=body.project_id)
        except Exception as e:
            log.warning("recall_alert_check_failed", error=str(e))
    log.info("recall_eval_completed",
             report_id=report.report_id,
             user=getattr(user, "user_id", "?"))
    return report


@router.get("/recall-eval/reports", response_model=list[RecallEvalReport])
async def list_recall_reports(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RecallEvalReport]:
    return list_reports(project_id=project_id, limit=limit)


@router.get("/recall-eval/latest", response_model=RecallEvalReport)
async def latest_recall_report(
    project_id: str | None = Query(default=None),
) -> RecallEvalReport:
    report = get_latest_report(project_id=project_id)
    if report is None:
        raise HTTPException(status_code=404, detail="尚无评估报告")
    return report


@router.get("/recall-eval/trend")
async def recall_trend(
    project_id: str | None = Query(default=None),
    lookback: int = Query(default=10, ge=2, le=100),
) -> dict[str, Any]:
    """召回率 / 精确率 趋势（current 对比 baseline = 最早一份）。

    跌破阈值（默认 -10pp）→ recall_alert / precision_alert = True；
    alert_messages 列出文字。前端直接渲染。
    """
    return compute_recall_trend(project_id=project_id, lookback=lookback)


class EvalAllBody(BaseModel):
    version: str = ""
    k: int = Field(default=5, ge=1, le=50)


@router.post("/recall-eval/eval-all", response_model=list[RecallEvalReport])
async def eval_all_endpoint(
    body: EvalAllBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> list[RecallEvalReport]:
    """批量评估所有有 ground truth 的 project（M9 #3 · 外部 cron / ISS-Job 入口）。

    给定时器 / Quartz 调度器一次性触发的端点；遍历每个 project 跑 recall_eval
    并自动 check_recall_alerts_and_propagate。返回每个 project 最新报告。
    """
    from api.deps import get_qa_engine

    async def qa_callable(query_text: str, k: int) -> list[str]:
        try:
            engine = get_qa_engine()
            result = await engine.ask(question=query_text, top_k=k)
            return [s.doc_id for s in result.sources]
        except Exception as e:
            log.warning("eval_all_qa_engine_failed", error=str(e))
            return []

    reports = await eval_all_projects(
        qa_callable=qa_callable, version=body.version, k=body.k,
    )
    log.info("eval_all_completed_via_api",
             reports=len(reports), user=getattr(user, "user_id", "?"))
    return reports


# ════════════════════════════════════════════════════════════════════════
#  M10 #1 · 多 K 召回曲线 + GT 自动构造
# ════════════════════════════════════════════════════════════════════════


class RunMultiKBody(BaseModel):
    project_id: str = ""
    version: str = ""
    ks: list[int] = Field(default_factory=lambda: [1, 3, 5, 10])


@router.post("/recall-eval/multi-k", response_model=MultiKRecallReport)
async def run_multi_k_recall_endpoint(
    body: RunMultiKBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> MultiKRecallReport:
    """一次跑多 K 评估，输出召回曲线（同 ground truth 集 + 同 qa）。"""
    from api.deps import get_qa_engine

    async def qa_callable(query_text: str, k: int) -> list[str]:
        try:
            engine = get_qa_engine()
            result = await engine.ask(question=query_text, top_k=k)
            return [s.doc_id for s in result.sources]
        except Exception as e:
            log.warning("multi_k_recall_qa_engine_failed", error=str(e))
            return []

    report = await run_multi_k_recall_eval(
        qa_callable=qa_callable,
        project_id=body.project_id, version=body.version, ks=body.ks,
    )
    log.info("multi_k_recall_completed",
             report_id=report.report_id,
             user=getattr(user, "user_id", "?"))
    return report


# ════════════════════════════════════════════════════════════════════════
#  M10 #2 · 监测条件 LLM 自学习
# ════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════
#  M11 #4 · LLM 自学习闭环（prompt versioning + AB 比较）
# ════════════════════════════════════════════════════════════════════════


class CreatePromptVersionBody(BaseModel):
    condition_type: str
    prompt_text_excerpt: str = Field(default="", max_length=200)
    system_prompt: str = Field(default="", max_length=8000)   # M12 #1
    language: str = Field(default="zh", max_length=8)         # M15 #3
    note: str = Field(default="", max_length=200)


_VALID_CONDITIONS = {
    "new_entity_type",
    "relation_solidification",
    "relation_split",
    "standard_upgrade",
}


@router.get("/prompt-versions", response_model=list[PromptVersion])
async def list_prompt_versions_endpoint(
    condition_type: str | None = Query(default=None),
    language: str | None = Query(default=None),
    only_active: bool = Query(default=False),
) -> list[PromptVersion]:
    if condition_type and condition_type not in _VALID_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"非法 condition_type；合法：{sorted(_VALID_CONDITIONS)}",
        )
    return list_prompt_versions(
        condition_type=condition_type,    # type: ignore[arg-type]
        language=language,
        only_active=only_active,
    )


@router.post("/prompt-versions", response_model=PromptVersion)
async def create_prompt_version_endpoint(
    body: CreatePromptVersionBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> PromptVersion:
    if body.condition_type not in _VALID_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"非法 condition_type；合法：{sorted(_VALID_CONDITIONS)}",
        )
    version = create_prompt_version(
        condition_type=body.condition_type,    # type: ignore[arg-type]
        prompt_text_excerpt=body.prompt_text_excerpt,
        system_prompt=body.system_prompt,
        language=body.language,
        created_by=getattr(user, "user_id", "") or "",
        note=body.note,
    )
    log.info("prompt_version_created_via_api",
             version_id=version.version_id,
             user=getattr(user, "user_id", "?"))
    return version


@router.post("/prompt-versions/{version_id}/deactivate")
async def deactivate_prompt_version_endpoint(
    version_id: str,
    user=Depends(RequireRole(ROLE_SME)),
) -> dict[str, Any]:
    if not deactivate_prompt_version(version_id):
        raise HTTPException(
            status_code=404, detail="version 不存在或已停用",
        )
    return {"version_id": version_id, "deactivated": True}


class AutoTuneBody(BaseModel):
    condition_type: str
    language: str = Field(default="zh", max_length=8)
    project_id: str = ""
    min_samples: int = Field(default=10, ge=1, le=1000)


@router.post("/prompt-versions/auto-tune", response_model=AutoTuneResult)
async def prompt_auto_tune_endpoint(
    body: AutoTuneBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> AutoTuneResult:
    """M16 #2 · LLM 自学习自动 promote / rollback。

    流程：
    1. 先调 auto_rollback_alerting_prompt（active 跌破阈值则 rollback）
    2. 再调 auto_promote_best_prompt（候选高于当前则 promote）
    3. 取最终结果（rollback 优先；都不动则返回最后一个 noop）
    """
    if body.condition_type not in _VALID_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"非法 condition_type；合法：{sorted(_VALID_CONDITIONS)}",
        )
    from api.routers.ontology import _proposal_store
    proposals = list(_proposal_store.values())
    if body.project_id:
        proposals = [p for p in proposals if p.project_id == body.project_id]

    rollback_result = auto_rollback_alerting_prompt(
        proposals,
        condition_type=body.condition_type,    # type: ignore[arg-type]
        language=body.language,
        min_samples=body.min_samples,
    )
    if rollback_result.action == "rollback":
        log.warning("prompt_auto_rollback_via_api",
                    user=getattr(user, "user_id", "?"),
                    result=rollback_result.model_dump(),
                    project_id=body.project_id)
        return rollback_result

    promote_result = auto_promote_best_prompt(
        proposals,
        condition_type=body.condition_type,    # type: ignore[arg-type]
        language=body.language,
        min_samples=body.min_samples,
    )
    log.info("prompt_auto_tune_via_api",
             user=getattr(user, "user_id", "?"),
             result=promote_result.model_dump(),
             project_id=body.project_id)
    return promote_result


@router.get("/prompt-versions/ab", response_model=list[PromptABScore])
async def prompt_ab_score_endpoint(
    condition_type: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
) -> list[PromptABScore]:
    """每个 prompt 版本在其活跃期内的 SME approve_rate（AB 比较）。"""
    if condition_type and condition_type not in _VALID_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"非法 condition_type；合法：{sorted(_VALID_CONDITIONS)}",
        )
    from api.routers.ontology import _proposal_store
    proposals = list(_proposal_store.values())
    if project_id:
        proposals = [p for p in proposals if p.project_id == project_id]
    return compute_prompt_ab_score(
        proposals,
        condition_type=condition_type,    # type: ignore[arg-type]
    )


@router.get("/condition-health", response_model=dict[str, ConditionHealth])
async def condition_health_endpoint(
    project_id: str | None = Query(default=None),
) -> dict[str, ConditionHealth]:
    """统计 4 监测条件的 SME approve/reject 比例 + 调优建议。

    分类规则（启发式）：
    - relation_split: proposed_relation_type + reasoning startswith "拆分自"
    - relation_solidification: proposed_relation_type 其他
    - standard_upgrade: proposed_entity_type.type_id == "standard"
    - new_entity_type: proposed_entity_type 其他

    返回 4 类强制 key + 可选 unknown 类。
    """
    from api.routers.ontology import _proposal_store

    proposals = list(_proposal_store.values())
    if project_id:
        proposals = [p for p in proposals if p.project_id == project_id]
    return analyze_condition_health(proposals)


@router.get(
    "/ground-truth/auto-construct",
    response_model=list[GroundTruthCandidate],
)
async def auto_construct_gt_endpoint(
    project_id: str = Query(default=""),
    min_useful_rate: float = Query(default=0.8, ge=0.0, le=1.0),
    min_samples: int = Query(default=2, ge=1, le=100),
    max_results: int = Query(default=50, ge=1, le=500),
) -> list[GroundTruthCandidate]:
    """从 query_log 反向构造 gt 候选；返回候选列表（待 SME 调 add ground-truth 入库）。"""
    return auto_construct_ground_truth_candidates(
        project_id=project_id,
        min_useful_rate=min_useful_rate,
        min_samples=min_samples,
        max_doc_ids=max_results,
    )


# ════════════════════════════════════════════════════════════════════════
#  M7 #3 · 综合运营仪表盘
# ════════════════════════════════════════════════════════════════════════


@router.get("/dashboard/multi")
async def dashboard_multi(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    project_ids: str | None = Query(
        default=None,
        description="逗号分隔；不填则自动从 list_observations + list_decisions 推断有数据的 project",
    ),
) -> dict[str, Any]:
    """M13 #3 · 多 project 横评仪表盘。

    一次拉所有指定 project 的 dashboard 摘要，前端并排展示做横评。
    project_ids 不填时，自动推断有数据的 project（来自 decisions / queries /
    observations / recall_eval 任一 project_id 集合的并集）。
    """
    explicit_ids: list[str] | None = None
    if project_ids:
        explicit_ids = [p.strip() for p in project_ids.split(",") if p.strip()]

    if explicit_ids:
        targets = explicit_ids
    else:
        # 自动推断：扫描各源的 project_id 集合
        from packages.observability import (
            list_decisions as _list_d,
            list_queries as _list_q,
        )
        seen: set[str] = set()
        for d in _list_d(limit=10000):
            if d.project_id:
                seen.add(d.project_id)
        for q in _list_q(limit=10000):
            if q.project_id:
                seen.add(q.project_id)
        for o in list_observations():
            if o.project_id:
                seen.add(o.project_id)
        targets = sorted(seen)

    rows = []
    for pid in targets:
        decisions = aggregate_decisions(
            project_id=pid, since=since, until=until,
        )
        queries = aggregate_queries(
            project_id=pid, since=since, until=until,
        )
        obs_list = list_observations(project_id=pid)
        latest = get_latest_report(project_id=pid)
        rows.append({
            "project_id": pid,
            "decisions": decisions,
            "queries": queries,
            "observations": {
                "total": len(obs_list),
                "active": sum(1 for o in obs_list if o.status == "watching"),
                "alerting": sum(1 for o in obs_list if o.status == "alert"),
            },
            "recall_eval": {
                "ground_truth_count": len(list_ground_truth(project_id=pid)),
                "latest": (
                    {
                        "report_id": latest.report_id,
                        "k": latest.k,
                        "avg_recall": latest.avg_recall,
                        "avg_precision": latest.avg_precision,
                        "avg_f1": latest.avg_f1,
                        "created_at": latest.created_at.isoformat(),
                    }
                    if latest else None
                ),
            },
        })
    return {
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "project_ids": targets,
        "rows": rows,
    }


@router.get("/dashboard")
async def dashboard(
    project_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict[str, Any]:
    """单端点聚合运营全维度指标：

    - **decisions**：approve / reject / promote / rollback 计数 + 派生比率
    - **queries**：召回 hit_rate + p95 latency + useful_rate (M8 #1 用户反馈)
    - **observations**：当前活跃观察期摘要（status + alerts 数量）
    - **recall_eval**：最近一份评估报告摘要（M8 #2）+ ground truth 集大小

    给前端运营看板一次拉全。
    """
    decisions = aggregate_decisions(
        project_id=project_id, since=since, until=until,
    )
    queries = aggregate_queries(
        project_id=project_id, since=since, until=until,
    )

    obs_list = list_observations(project_id=project_id)
    # 观察期摘要：保持精简（不返回历史 snapshots 全量，仅状态 + 告警数）
    obs_summary = [
        {
            "observation_id": o.observation_id,
            "project_id": o.project_id,
            "version": o.version,
            "status": o.status,
            "alerts_count": len(o.alerts),
            "snapshots_count": len(o.snapshots),
            "promoted_at": o.promoted_at.isoformat(),
            "expires_at": o.expires_at.isoformat(),
        }
        for o in obs_list
    ]
    obs_active = sum(1 for o in obs_list if o.status == "watching")
    obs_alerting = sum(1 for o in obs_list if o.status == "alert")

    # M8 #2 召回评估摘要（精简：仅 avg 指标 + report_id，明细走 /reports/{id}）
    latest = get_latest_report(project_id=project_id)
    if latest is not None:
        recall_summary = {
            "report_id": latest.report_id,
            "version": latest.version,
            "k": latest.k,
            "total_queries": latest.total_queries,
            "avg_recall": latest.avg_recall,
            "avg_precision": latest.avg_precision,
            "avg_f1": latest.avg_f1,
            "created_at": latest.created_at.isoformat(),
        }
    else:
        recall_summary = None
    gt_count = len(list_ground_truth(project_id=project_id))

    return {
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "project_id": project_id,
        },
        "decisions": decisions,
        "queries": queries,
        "observations": {
            "total": len(obs_list),
            "active": obs_active,
            "alerting": obs_alerting,
            "items": obs_summary,
        },
        "recall_eval": {
            "ground_truth_count": gt_count,
            "latest": recall_summary,
        },
    }
