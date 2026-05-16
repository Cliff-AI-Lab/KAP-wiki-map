"""W6 入库诊断 PG 持久化（M22 #6）。

write-through：record_ingest_metric 完成后异步写 PG（fire-and-forget）。
启动时水化最近 N 条到 _metrics 列表（用于 compute_ingest_trend）。

仿 pg_extraction_quality 模式（M20 #1）。
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.ingest_metrics import (
    IngestMetric,
    _metrics,  # type: ignore[reportPrivateUsage]
    set_ingest_metrics_pg_sink,
)

log = get_logger("observability.pg_ingest_metrics")


_DDL = """
CREATE TABLE IF NOT EXISTS ingest_metrics (
    id                BIGSERIAL    PRIMARY KEY,
    doc_id            VARCHAR(128) NOT NULL,
    project_id        VARCHAR(64)  NOT NULL DEFAULT '',
    parser_name       VARCHAR(128) NOT NULL DEFAULT '',
    source_system     VARCHAR(64)  NOT NULL DEFAULT '',
    doc_size          BIGINT       NOT NULL DEFAULT 0,
    chunk_count       INT          NOT NULL DEFAULT 0,
    parse_ms          INT          NOT NULL DEFAULT 0,
    chunk_ms          INT          NOT NULL DEFAULT 0,
    embed_ms          INT          NOT NULL DEFAULT 0,
    vector_write_ms   INT          NOT NULL DEFAULT 0,
    graph_write_ms    INT          NOT NULL DEFAULT 0,
    total_ms          INT          NOT NULL DEFAULT 0,
    status            VARCHAR(16)  NOT NULL DEFAULT 'success',
    error_kind        VARCHAR(32)  NOT NULL DEFAULT '',
    error_message     TEXT         NOT NULL DEFAULT '',
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS ingest_project_idx "
    "ON ingest_metrics(project_id, ingested_at DESC)",
    "CREATE INDEX IF NOT EXISTS ingest_status_idx "
    "ON ingest_metrics(status, ingested_at DESC)",
    "CREATE INDEX IF NOT EXISTS ingest_error_idx "
    "ON ingest_metrics(error_kind, ingested_at DESC) "
    "WHERE error_kind <> ''",
]


_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_ingest_metrics(
    dsn: str, *, load_limit: int = 1000,
) -> bool:
    """连接 PG → 建表 → 水化 → 注入 sink。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("ingest_metrics_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        for stmt in _INDEX_DDL:
            await cur.execute(stmt)
        await _conn.commit()
        await cur.execute(
            "SELECT doc_id, project_id, parser_name, source_system, "
            "doc_size, chunk_count, parse_ms, chunk_ms, embed_ms, "
            "vector_write_ms, graph_write_ms, total_ms, status, "
            "error_kind, error_message, ingested_at "
            "FROM ingest_metrics ORDER BY ingested_at DESC LIMIT %s",
            (load_limit,),
        )
        rows = await cur.fetchall()

    for row in reversed(rows):
        _metrics.append(IngestMetric(
            doc_id=row[0], project_id=row[1] or "",
            parser_name=row[2] or "", source_system=row[3] or "",
            doc_size=row[4] or 0, chunk_count=row[5] or 0,
            parse_ms=row[6] or 0, chunk_ms=row[7] or 0,
            embed_ms=row[8] or 0, vector_write_ms=row[9] or 0,
            graph_write_ms=row[10] or 0, total_ms=row[11] or 0,
            status=row[12] or "success",  # type: ignore[arg-type]
            error_kind=row[13] or "",  # type: ignore[arg-type]
            error_message=row[14] or "",
            ingested_at=row[15],
        ))

    set_ingest_metrics_pg_sink(_pg_append)
    log.info("ingest_metrics_pg_initialized",
             hydrated=len(rows), load_limit=load_limit)
    return True


async def _pg_append(metric: IngestMetric) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO ingest_metrics
                  (doc_id, project_id, parser_name, source_system,
                   doc_size, chunk_count, parse_ms, chunk_ms, embed_ms,
                   vector_write_ms, graph_write_ms, total_ms,
                   status, error_kind, error_message, ingested_at)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s)
                """,
                (
                    metric.doc_id, metric.project_id, metric.parser_name,
                    metric.source_system,
                    metric.doc_size, metric.chunk_count,
                    metric.parse_ms, metric.chunk_ms, metric.embed_ms,
                    metric.vector_write_ms, metric.graph_write_ms,
                    metric.total_ms,
                    metric.status, metric.error_kind, metric.error_message,
                    metric.ingested_at,
                ),
            )
            await _conn.commit()


async def shutdown_pg_ingest_metrics() -> None:
    global _conn, _lock
    set_ingest_metrics_pg_sink(None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("ingest_metrics_pg_close_failed", error=str(e))
    _conn = None
    _lock = None
