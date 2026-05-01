"""WikiQualityScore PG 持久化（M19 #1）。

write-through：score_wiki_page 完成后内存命中 _scores + _history 同时
异步写 PG（fire-and-forget）。

启动时水化最近 N 条到 _history（用于趋势图）；_scores 取每 page_id 最新一条。
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.wiki_quality import (
    WikiQualityScore, DimensionScore,
    _history,    # type: ignore[reportPrivateUsage]
    _scores,     # type: ignore[reportPrivateUsage]
    set_wiki_quality_pg_sink,
)

log = get_logger("observability.pg_wiki_quality")


_DDL = """
CREATE TABLE IF NOT EXISTS wiki_quality_scores (
    id              BIGSERIAL    PRIMARY KEY,
    page_id         VARCHAR(128) NOT NULL,
    page_type       VARCHAR(32)  NOT NULL DEFAULT '',
    project_id      VARCHAR(64)  NOT NULL DEFAULT '',
    consistency     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    completeness    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    evidence        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    repetition      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    freshness       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    cross_domain    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    overall         DOUBLE PRECISION NOT NULL DEFAULT 0,
    quality_alert   BOOLEAN      NOT NULL DEFAULT FALSE,
    error           TEXT         NOT NULL DEFAULT '',
    scored_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS wq_project_idx "
    "ON wiki_quality_scores(project_id, scored_at DESC)",
    "CREATE INDEX IF NOT EXISTS wq_page_idx "
    "ON wiki_quality_scores(page_id, scored_at DESC)",
]


_conn = None
_lock: asyncio.Lock | None = None


def _dim_to_dict(d: DimensionScore) -> dict:
    return {"score": d.score, "reason": d.reason}


async def initialize_pg_wiki_quality(
    dsn: str, *, load_limit: int = 1000,
) -> bool:
    """连接 PG → 建表 → 水化 → 注入 sink。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("wiki_quality_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        for stmt in _INDEX_DDL:
            await cur.execute(stmt)
        await _conn.commit()
        await cur.execute(
            "SELECT page_id, page_type, project_id, consistency, completeness, "
            "evidence, repetition, freshness, cross_domain, overall, "
            "quality_alert, error, scored_at "
            "FROM wiki_quality_scores ORDER BY scored_at DESC LIMIT %s",
            (load_limit,),
        )
        rows = await cur.fetchall()

    import json as _json

    def _parse_dim(blob) -> DimensionScore:
        data = blob if isinstance(blob, dict) else _json.loads(blob or "{}")
        return DimensionScore(
            score=float(data.get("score", 0.0)),
            reason=str(data.get("reason", "")),
        )

    for row in reversed(rows):
        score = WikiQualityScore(
            page_id=row[0], page_type=row[1] or "", project_id=row[2] or "",
            consistency=_parse_dim(row[3]),
            completeness=_parse_dim(row[4]),
            evidence=_parse_dim(row[5]),
            repetition=_parse_dim(row[6]),
            freshness=_parse_dim(row[7]),
            cross_domain=_parse_dim(row[8]),
            overall=float(row[9] or 0.0),
            quality_alert=bool(row[10]),
            error=row[11] or "",
            scored_at=row[12],
        )
        _history.append(score)
        if not score.error:
            _scores[score.page_id] = score

    set_wiki_quality_pg_sink(_pg_append)
    log.info("wiki_quality_pg_initialized",
             hydrated=len(rows), load_limit=load_limit)
    return True


async def _pg_append(score: WikiQualityScore) -> None:
    if _conn is None or _lock is None:
        return
    import json as _json
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO wiki_quality_scores
                  (page_id, page_type, project_id,
                   consistency, completeness, evidence,
                   repetition, freshness, cross_domain,
                   overall, quality_alert, error, scored_at)
                VALUES (%s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s)
                """,
                (
                    score.page_id, score.page_type, score.project_id,
                    _json.dumps(_dim_to_dict(score.consistency), ensure_ascii=False),
                    _json.dumps(_dim_to_dict(score.completeness), ensure_ascii=False),
                    _json.dumps(_dim_to_dict(score.evidence), ensure_ascii=False),
                    _json.dumps(_dim_to_dict(score.repetition), ensure_ascii=False),
                    _json.dumps(_dim_to_dict(score.freshness), ensure_ascii=False),
                    _json.dumps(_dim_to_dict(score.cross_domain), ensure_ascii=False),
                    score.overall, score.quality_alert,
                    score.error, score.scored_at,
                ),
            )
            await _conn.commit()


async def shutdown_pg_wiki_quality() -> None:
    global _conn, _lock
    set_wiki_quality_pg_sink(None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("wiki_quality_pg_close_failed", error=str(e))
    _conn = None
    _lock = None
