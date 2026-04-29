"""可观察性 API（M6 #3 · 决策书 §5.3 简单指标聚合）。

端点：
  GET  /api/v1/observability/decisions             列出 decision 事件（过滤 + 分页）
  GET  /api/v1/observability/decisions/aggregate   聚合 by_type + 派生指标

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
