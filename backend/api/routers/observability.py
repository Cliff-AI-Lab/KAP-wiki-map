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
    DecisionEvent,
    GroundTruthQuery,
    QueryEvent,
    RecallEvalReport,
    add_ground_truth,
    aggregate_decisions,
    aggregate_queries,
    arecord_query_feedback,
    get_latest_report,
    list_decisions,
    list_ground_truth,
    list_queries,
    list_reports,
    remove_ground_truth,
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
    return event


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


# ════════════════════════════════════════════════════════════════════════
#  M7 #3 · 综合运营仪表盘
# ════════════════════════════════════════════════════════════════════════


@router.get("/dashboard")
async def dashboard(
    project_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> dict[str, Any]:
    """单端点聚合运营三源指标：

    - **decisions**：approve / reject / promote / rollback 计数 + 派生比率
    - **queries**：召回 hit_rate + p95 latency
    - **observations**：当前活跃观察期摘要（status + alerts 数量）

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
    }
