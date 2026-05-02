"""W4 抽取质量诊断 PG 持久化（M20 #1）。

write-through：record_extraction_metric 完成后异步写 PG（fire-and-forget）。
启动时水化最近 N 条到 _metrics 列表（用于 aggregate / trend）。

仿 pg_wiki_quality 模式（M19 #1）。
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.extraction_quality import (
    ExtractionMetric,
    _metrics,    # type: ignore[reportPrivateUsage]
    set_extraction_quality_pg_sink,
)

log = get_logger("observability.pg_extraction_quality")


_DDL = """
CREATE TABLE IF NOT EXISTS extraction_metrics (
    id                       BIGSERIAL    PRIMARY KEY,
    doc_id                   VARCHAR(128) NOT NULL,
    project_id               VARCHAR(64)  NOT NULL DEFAULT '',
    industry_code            VARCHAR(32)  NOT NULL DEFAULT '',
    content_chars            INT          NOT NULL DEFAULT 0,
    entity_count             INT          NOT NULL DEFAULT 0,
    relation_count           INT          NOT NULL DEFAULT 0,
    sensitive_count          INT          NOT NULL DEFAULT 0,
    entity_density           DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence_avg           DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_entity_density     DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_relation_validity  DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_confidence_avg     DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_sensitive_handled  DOUBLE PRECISION NOT NULL DEFAULT 0,
    overall                  DOUBLE PRECISION NOT NULL DEFAULT 0,
    quality_alert            BOOLEAN      NOT NULL DEFAULT FALSE,
    error                    TEXT         NOT NULL DEFAULT '',
    extracted_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS extr_project_idx "
    "ON extraction_metrics(project_id, extracted_at DESC)",
    "CREATE INDEX IF NOT EXISTS extr_doc_idx "
    "ON extraction_metrics(doc_id, extracted_at DESC)",
]


_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_extraction_quality(
    dsn: str, *, load_limit: int = 1000,
) -> bool:
    """连接 PG → 建表 → 水化 → 注入 sink。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("extraction_quality_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        for stmt in _INDEX_DDL:
            await cur.execute(stmt)
        await _conn.commit()
        await cur.execute(
            "SELECT doc_id, project_id, industry_code, content_chars, "
            "entity_count, relation_count, sensitive_count, "
            "entity_density, confidence_avg, "
            "score_entity_density, score_relation_validity, "
            "score_confidence_avg, score_sensitive_handled, "
            "overall, quality_alert, error, extracted_at "
            "FROM extraction_metrics ORDER BY extracted_at DESC LIMIT %s",
            (load_limit,),
        )
        rows = await cur.fetchall()

    for row in reversed(rows):
        _metrics.append(ExtractionMetric(
            doc_id=row[0], project_id=row[1] or "",
            industry_code=row[2] or "",
            content_chars=row[3] or 0,
            entity_count=row[4] or 0,
            relation_count=row[5] or 0,
            sensitive_count=row[6] or 0,
            entity_density_per_kchars=float(row[7] or 0.0),
            confidence_avg=float(row[8] or 0.0),
            score_entity_density=float(row[9] or 0.0),
            score_relation_validity=float(row[10] or 0.0),
            score_confidence_avg=float(row[11] or 0.0),
            score_sensitive_handled=float(row[12] or 0.0),
            overall=float(row[13] or 0.0),
            quality_alert=bool(row[14]),
            error=row[15] or "",
            extracted_at=row[16],
        ))

    set_extraction_quality_pg_sink(_pg_append)
    log.info("extraction_quality_pg_initialized",
             hydrated=len(rows), load_limit=load_limit)
    return True


async def _pg_append(metric: ExtractionMetric) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO extraction_metrics
                  (doc_id, project_id, industry_code, content_chars,
                   entity_count, relation_count, sensitive_count,
                   entity_density, confidence_avg,
                   score_entity_density, score_relation_validity,
                   score_confidence_avg, score_sensitive_handled,
                   overall, quality_alert, error, extracted_at)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s)
                """,
                (
                    metric.doc_id, metric.project_id, metric.industry_code,
                    metric.content_chars,
                    metric.entity_count, metric.relation_count,
                    metric.sensitive_count,
                    metric.entity_density_per_kchars, metric.confidence_avg,
                    metric.score_entity_density, metric.score_relation_validity,
                    metric.score_confidence_avg, metric.score_sensitive_handled,
                    metric.overall, metric.quality_alert,
                    metric.error, metric.extracted_at,
                ),
            )
            await _conn.commit()


async def shutdown_pg_extraction_quality() -> None:
    global _conn, _lock
    set_extraction_quality_pg_sink(None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("extraction_quality_pg_close_failed", error=str(e))
    _conn = None
    _lock = None
