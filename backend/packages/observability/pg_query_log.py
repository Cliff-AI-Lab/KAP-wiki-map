"""QueryEvent PG 持久化（M7 #2）。

write-through 模式（同 pg_decision_log）：
- ``initialize_pg_query_log`` 启动时建表 + 水化最近 N 条 + 注入 sink
- 查询 / 聚合从内存读，PG 仅作为持久化副本
- 单连接 + asyncio.Lock
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.query_log import (
    QueryEvent,
    _queries,  # type: ignore[reportPrivateUsage]
    set_query_feedback_pg_sink,
    set_query_pg_sink,
)

log = get_logger("observability.pg_query_log")


_DDL = """
CREATE TABLE IF NOT EXISTS query_events (
    query_id      VARCHAR(32)  PRIMARY KEY,
    project_id    VARCHAR(64)  NOT NULL DEFAULT '',
    user_id       VARCHAR(64)  NOT NULL DEFAULT '',
    query_text    TEXT         NOT NULL DEFAULT '',
    source_count  INT          NOT NULL DEFAULT 0,
    hit           BOOLEAN      NOT NULL DEFAULT TRUE,
    latency_ms    INT          NOT NULL DEFAULT 0,
    useful        BOOLEAN,                         -- M8 #1 用户反馈
    feedback_note TEXT         NOT NULL DEFAULT '',
    feedback_at   TIMESTAMPTZ,
    occurred_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

# 兼容老库：尝试 ALTER 加 M8 字段（已存在则忽略）
_ALTER_DDL = [
    "ALTER TABLE query_events ADD COLUMN IF NOT EXISTS useful BOOLEAN",
    "ALTER TABLE query_events ADD COLUMN IF NOT EXISTS feedback_note TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE query_events ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ",
]

_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS query_events_project_idx
ON query_events(project_id, occurred_at DESC)
"""


_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_query_log(
    dsn: str, *, load_limit: int = 1000,
) -> bool:
    """连接 PG → 建表 → 水化 → 注入 sink。返回 True 成功，False 降级内存。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("query_log_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        for stmt in _ALTER_DDL:
            await cur.execute(stmt)
        await cur.execute(_INDEX_DDL)
        await _conn.commit()
        await cur.execute(
            "SELECT query_id, project_id, user_id, query_text, source_count, "
            "hit, latency_ms, useful, feedback_note, feedback_at, occurred_at "
            "FROM query_events ORDER BY occurred_at DESC LIMIT %s",
            (load_limit,),
        )
        rows = await cur.fetchall()

    for row in reversed(rows):
        _queries.append(QueryEvent(
            query_id=row[0], project_id=row[1] or "", user_id=row[2] or "",
            query_text=row[3] or "", source_count=row[4] or 0,
            hit=bool(row[5]), latency_ms=row[6] or 0,
            useful=row[7],  # 可能 None
            feedback_note=row[8] or "",
            feedback_at=row[9],
            occurred_at=row[10],
        ))

    set_query_pg_sink(_pg_append)
    set_query_feedback_pg_sink(_pg_update_feedback)
    log.info("query_log_pg_initialized",
             hydrated=len(rows), load_limit=load_limit)
    return True


async def _pg_append(event: QueryEvent) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO query_events
                  (query_id, project_id, user_id, query_text,
                   source_count, hit, latency_ms, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (query_id) DO NOTHING
                """,
                (
                    event.query_id, event.project_id, event.user_id,
                    event.query_text, event.source_count, event.hit,
                    event.latency_ms, event.occurred_at,
                ),
            )
            await _conn.commit()


async def _pg_update_feedback(event: QueryEvent) -> None:
    """更新已存在 query_events 行的 feedback 字段（M8 #1）。"""
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE query_events
                SET useful = %s,
                    feedback_note = %s,
                    feedback_at = %s
                WHERE query_id = %s
                """,
                (
                    event.useful, event.feedback_note,
                    event.feedback_at, event.query_id,
                ),
            )
            await _conn.commit()


async def shutdown_pg_query_log() -> None:
    global _conn, _lock
    set_query_pg_sink(None)
    set_query_feedback_pg_sink(None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("query_log_pg_close_failed", error=str(e))
    _conn = None
    _lock = None


def _reset_pg_state_for_test() -> None:
    global _conn, _lock
    set_query_pg_sink(None)
    set_query_feedback_pg_sink(None)
    _conn = None
    _lock = None
