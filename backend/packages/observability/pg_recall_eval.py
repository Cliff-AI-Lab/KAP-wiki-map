"""recall_eval PG 持久化（M9 #1 · 决策书 §5.3）。

write-through 模式：
- ``initialize_pg_recall_eval(dsn, load_limit=N)`` 启动时建表 + 索引 + 水化
  最近 N 条 ground truth 和 reports → 注入三个 sink
- 查询 / list 路径仍从内存读，PG 只是持久化副本
- 单连接 + asyncio.Lock 串行（同 pg_decision_log / pg_query_log）

DDL：
- ``ground_truth_queries`` (gt_id PK, project_id, query_text, expected_doc_ids JSONB,
                            note, created_at)
- ``recall_eval_reports`` (report_id PK, project_id, version, k, total_queries,
                          avg_recall, avg_precision, avg_f1, details JSONB,
                          created_at)
"""

from __future__ import annotations

import asyncio
import json

from packages.common import get_logger
from packages.observability.recall_eval import (
    GroundTruthQuery,
    RecallEvalDetail,
    RecallEvalReport,
    _ground_truth,  # type: ignore[reportPrivateUsage]
    _reports,       # type: ignore[reportPrivateUsage]
    set_recall_eval_pg_sinks,
)

log = get_logger("observability.pg_recall_eval")


_GT_DDL = """
CREATE TABLE IF NOT EXISTS ground_truth_queries (
    gt_id            VARCHAR(32)  PRIMARY KEY,
    project_id       VARCHAR(64)  NOT NULL DEFAULT '',
    query_text       TEXT         NOT NULL DEFAULT '',
    expected_doc_ids JSONB        NOT NULL DEFAULT '[]'::jsonb,
    note             TEXT         NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_GT_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS ground_truth_queries_project_idx
ON ground_truth_queries(project_id, created_at DESC)
"""

_REPORT_DDL = """
CREATE TABLE IF NOT EXISTS recall_eval_reports (
    report_id      VARCHAR(32)  PRIMARY KEY,
    project_id     VARCHAR(64)  NOT NULL DEFAULT '',
    version        VARCHAR(64)  NOT NULL DEFAULT '',
    k              INT          NOT NULL DEFAULT 5,
    total_queries  INT          NOT NULL DEFAULT 0,
    avg_recall     DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_precision  DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_f1         DOUBLE PRECISION NOT NULL DEFAULT 0,
    details        JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

_REPORT_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS recall_eval_reports_project_idx
ON recall_eval_reports(project_id, created_at DESC)
"""


# 模块状态
_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_recall_eval(
    dsn: str, *, load_limit: int = 500,
) -> bool:
    """连接 PG → 建表 → 水化 → 注入 sinks。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("recall_eval_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_GT_DDL)
        await cur.execute(_GT_INDEX_DDL)
        await cur.execute(_REPORT_DDL)
        await cur.execute(_REPORT_INDEX_DDL)
        await _conn.commit()

        # 水化 ground truth（全量；通常 < 1000）
        await cur.execute(
            "SELECT gt_id, project_id, query_text, expected_doc_ids, note, "
            "created_at FROM ground_truth_queries"
        )
        gt_rows = await cur.fetchall()

        # 水化 reports（最近 N）
        await cur.execute(
            "SELECT report_id, project_id, version, k, total_queries, "
            "avg_recall, avg_precision, avg_f1, details, created_at "
            "FROM recall_eval_reports ORDER BY created_at DESC LIMIT %s",
            (load_limit,),
        )
        report_rows = await cur.fetchall()

    for row in gt_rows:
        expected = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
        _ground_truth[row[0]] = GroundTruthQuery(
            gt_id=row[0], project_id=row[1] or "",
            query_text=row[2] or "",
            expected_doc_ids=[str(x) for x in expected],
            note=row[4] or "", created_at=row[5],
        )

    # reports 倒序入 _list（旧 → 新）保持插入顺序语义
    for row in reversed(report_rows):
        details_raw = row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]")
        details = [RecallEvalDetail(**d) for d in details_raw]
        _reports.append(RecallEvalReport(
            report_id=row[0], project_id=row[1] or "", version=row[2] or "",
            k=row[3] or 5, total_queries=row[4] or 0,
            avg_recall=float(row[5] or 0),
            avg_precision=float(row[6] or 0),
            avg_f1=float(row[7] or 0),
            details=details,
            created_at=row[9],
        ))

    set_recall_eval_pg_sinks(
        gt_sink=_pg_upsert_gt,
        gt_remove_sink=_pg_delete_gt,
        report_sink=_pg_insert_report,
    )
    log.info("recall_eval_pg_initialized",
             gt_hydrated=len(gt_rows),
             reports_hydrated=len(report_rows))
    return True


async def _pg_upsert_gt(gt: GroundTruthQuery) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO ground_truth_queries
                  (gt_id, project_id, query_text, expected_doc_ids, note, created_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (gt_id) DO UPDATE SET
                  project_id = EXCLUDED.project_id,
                  query_text = EXCLUDED.query_text,
                  expected_doc_ids = EXCLUDED.expected_doc_ids,
                  note = EXCLUDED.note
                """,
                (
                    gt.gt_id, gt.project_id, gt.query_text,
                    json.dumps(gt.expected_doc_ids, ensure_ascii=False),
                    gt.note, gt.created_at,
                ),
            )
            await _conn.commit()


async def _pg_delete_gt(gt_id: str) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM ground_truth_queries WHERE gt_id = %s",
                (gt_id,),
            )
            await _conn.commit()


async def _pg_insert_report(report: RecallEvalReport) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO recall_eval_reports
                  (report_id, project_id, version, k, total_queries,
                   avg_recall, avg_precision, avg_f1, details, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (report_id) DO NOTHING
                """,
                (
                    report.report_id, report.project_id, report.version,
                    report.k, report.total_queries,
                    report.avg_recall, report.avg_precision, report.avg_f1,
                    json.dumps([d.model_dump() for d in report.details],
                               ensure_ascii=False, default=str),
                    report.created_at,
                ),
            )
            await _conn.commit()


async def shutdown_pg_recall_eval() -> None:
    global _conn, _lock
    set_recall_eval_pg_sinks(
        gt_sink=None, gt_remove_sink=None, report_sink=None,
    )
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("recall_eval_pg_close_failed", error=str(e))
    _conn = None
    _lock = None


def _reset_pg_state_for_test() -> None:
    global _conn, _lock
    set_recall_eval_pg_sinks(
        gt_sink=None, gt_remove_sink=None, report_sink=None,
    )
    _conn = None
    _lock = None
