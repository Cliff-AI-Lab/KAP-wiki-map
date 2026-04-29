"""DecisionLog PG 持久化（M7 #1 · 决策书 §5.3）。

write-through 模式：
1. ``initialize_pg_decision_log(dsn, load_limit=N)`` 在 FastAPI 启动时调一次：
   - 建表 + 索引（``decision_events``）
   - 拉最近 N 条事件水化进 ``_events`` 内存（恢复 M6 #3 读路径）
   - 注入异步 sink → 之后 ``record_decision`` / ``arecord_decision`` 自动落 PG

设计（feedback memory · 轻量化）：
- 单连接 + asyncio.Lock 保证并发安全（不引入连接池依赖）
- sink 异常 try/except 吞掉，绝不阻断主业务流
- 关闭走 ``shutdown_pg_decision_log``
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.decision_log import (
    DecisionEvent,
    _events,  # type: ignore[reportPrivateUsage]
    set_pg_sink,
)

log = get_logger("observability.pg_decision_log")


_DDL = """
CREATE TABLE IF NOT EXISTS decision_events (
    id            BIGSERIAL PRIMARY KEY,
    project_id    VARCHAR(64)  NOT NULL,
    decision_type VARCHAR(32)  NOT NULL,
    actor         VARCHAR(64)  NOT NULL DEFAULT '',
    target_id     VARCHAR(128) NOT NULL DEFAULT '',
    note          TEXT         NOT NULL DEFAULT '',
    occurred_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS decision_events_project_idx
ON decision_events(project_id, occurred_at DESC)
"""


# 模块状态
_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_decision_log(
    dsn: str,
    *,
    load_limit: int = 1000,
) -> bool:
    """连接 PG、建表、水化内存、注入 sink。

    Returns:
        True 成功 / False 连接失败（已降级到内存模式）
    """
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("decision_log_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        await cur.execute(_INDEX_DDL)
        await _conn.commit()
        await cur.execute(
            "SELECT project_id, decision_type, actor, target_id, note, occurred_at "
            "FROM decision_events ORDER BY occurred_at DESC LIMIT %s",
            (load_limit,),
        )
        rows = await cur.fetchall()

    # rows 是按时间倒序；_events 内部按追加顺序（旧 → 新），按 reversed(_events) 读
    # 所以这里 reverse 后追加 → 满足"最新在末尾"的内存表示
    for row in reversed(rows):
        _events.append(DecisionEvent(
            project_id=row[0],
            decision_type=row[1],
            actor=row[2] or "",
            target_id=row[3] or "",
            note=row[4] or "",
            occurred_at=row[5],
        ))

    set_pg_sink(_pg_append)
    log.info("decision_log_pg_initialized",
             hydrated=len(rows), load_limit=load_limit)
    return True


async def _pg_append(event: DecisionEvent) -> None:
    """异步 sink：单条 INSERT，asyncio.Lock 串行保护连接。"""
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO decision_events
                  (project_id, decision_type, actor, target_id, note, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    event.project_id, event.decision_type,
                    event.actor, event.target_id, event.note,
                    event.occurred_at,
                ),
            )
            await _conn.commit()


async def shutdown_pg_decision_log() -> None:
    """关闭 PG 连接（FastAPI shutdown event 调）。"""
    global _conn, _lock
    set_pg_sink(None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("decision_log_pg_close_failed", error=str(e))
    _conn = None
    _lock = None


def _reset_pg_state_for_test() -> None:
    """测试用：清掉 PG 模块全局状态。"""
    global _conn, _lock
    set_pg_sink(None)
    _conn = None
    _lock = None
