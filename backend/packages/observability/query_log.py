"""查询召回事件日志（M7 #2 · 决策书 §5.3 简单运营观察）。

记录 portal / qa 端点的每次查询，含命中数 / 延时 / 用户。聚合输出
hit_rate / avg_latency_ms / p95_latency_ms 三项基础指标，给运营看趋势。

不做（M8 / 接 portal）：
- 准确率（依赖标注 ground truth）
- 用户主动反馈（依赖 portal "有用 / 无用" 按钮埋点）
- 召回率 (recall@k)（依赖完整 ground truth set）

设计（feedback memory · 轻量化）：
- 内存 list 是读路径；PG sink 是 write-through 副本
- record_query (sync) → fire-and-forget；arecord_query (async) → 等待持久化
- hit 默认为 source_count > 0（启发式，可被 portal 显式覆盖）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from packages.common import get_logger

log = get_logger("observability.query_log")


class QueryEvent(BaseModel):
    query_id: str
    project_id: str = ""
    user_id: str = ""
    query_text: str = ""        # 已截断（前 200 字）
    source_count: int = 0       # 召回 sources 数量
    hit: bool = True            # 默认 source_count > 0；portal 可显式覆盖
    latency_ms: int = 0
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# 内存 + sink
_queries: list[QueryEvent] = []
_pg_sink: Callable[[QueryEvent], Awaitable[None]] | None = None


def reset_queries_for_test() -> None:
    global _pg_sink
    _queries.clear()
    _pg_sink = None


def set_query_pg_sink(
    sink: Callable[[QueryEvent], Awaitable[None]] | None,
) -> None:
    global _pg_sink
    _pg_sink = sink


def _build_event(
    *, project_id: str, user_id: str, query_text: str,
    source_count: int, hit: bool | None, latency_ms: int,
) -> QueryEvent:
    if hit is None:
        hit = source_count > 0
    event = QueryEvent(
        query_id=f"q_{uuid.uuid4().hex[:10]}",
        project_id=project_id, user_id=user_id,
        query_text=query_text[:200],
        source_count=source_count, hit=hit,
        latency_ms=max(0, int(latency_ms)),
    )
    _queries.append(event)
    log.info(
        "query_recorded",
        query_id=event.query_id, project_id=project_id,
        user_id=user_id or "anon",
        sources=source_count, hit=hit, latency_ms=event.latency_ms,
    )
    return event


def record_query(
    *,
    project_id: str = "",
    user_id: str = "",
    query_text: str = "",
    source_count: int = 0,
    hit: bool | None = None,
    latency_ms: int = 0,
) -> QueryEvent:
    """同步记录（fire-and-forget PG 写入）。"""
    event = _build_event(
        project_id=project_id, user_id=user_id, query_text=query_text,
        source_count=source_count, hit=hit, latency_ms=latency_ms,
    )
    if _pg_sink is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_pg_sink(event))
        except RuntimeError:
            pass
    return event


async def arecord_query(
    *,
    project_id: str = "",
    user_id: str = "",
    query_text: str = "",
    source_count: int = 0,
    hit: bool | None = None,
    latency_ms: int = 0,
) -> QueryEvent:
    """异步记录（await PG 写入）。"""
    event = _build_event(
        project_id=project_id, user_id=user_id, query_text=query_text,
        source_count=source_count, hit=hit, latency_ms=latency_ms,
    )
    if _pg_sink is not None:
        try:
            await _pg_sink(event)
        except Exception as e:
            log.warning("query_log_pg_write_failed", error=str(e))
    return event


def list_queries(
    *,
    project_id: str | None = None,
    user_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[QueryEvent]:
    out: list[QueryEvent] = []
    for q in reversed(_queries):
        if project_id is not None and q.project_id != project_id:
            continue
        if user_id is not None and q.user_id != user_id:
            continue
        if since is not None and q.occurred_at < since:
            continue
        if until is not None and q.occurred_at > until:
            continue
        out.append(q)
        if len(out) >= limit:
            break
    return out


def aggregate_queries(
    *,
    project_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """聚合查询事件 → hit_rate / avg_latency / p95_latency。"""
    events = list_queries(
        project_id=project_id, since=since, until=until, limit=10**9,
    )
    total = len(events)
    if total == 0:
        return {
            "total": 0, "hits": 0, "hit_rate": 0.0,
            "avg_latency_ms": 0.0, "p95_latency_ms": 0,
            "window": {
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
                "project_id": project_id,
            },
        }

    hits = sum(1 for q in events if q.hit)
    latencies = sorted(q.latency_ms for q in events)
    avg = sum(latencies) / total
    p95_idx = max(0, int(0.95 * total) - 1)
    p95 = latencies[p95_idx]

    return {
        "total": total,
        "hits": hits,
        "hit_rate": round(hits / total, 4),
        "avg_latency_ms": round(avg, 2),
        "p95_latency_ms": p95,
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "project_id": project_id,
        },
    }
