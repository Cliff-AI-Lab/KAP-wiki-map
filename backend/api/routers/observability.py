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

from fastapi import APIRouter, Query

from packages.common import get_logger
from packages.observability import (
    DecisionEvent,
    QueryEvent,
    aggregate_decisions,
    aggregate_queries,
    list_decisions,
    list_queries,
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
