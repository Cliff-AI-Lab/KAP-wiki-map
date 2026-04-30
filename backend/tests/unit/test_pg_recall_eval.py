"""M9 #1 · recall_eval PG 持久化单测（mock psycopg）。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from packages.observability import (
    add_ground_truth,
    initialize_pg_recall_eval,
    list_ground_truth,
    list_reports,
    remove_ground_truth,
    reset_recall_eval_for_test,
    run_recall_eval,
    shutdown_pg_recall_eval,
)
from packages.observability import pg_recall_eval as pgmod


# ════════════════════════════════════════════════════════════════════════
#  Fake psycopg
# ════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, params=None):
        sql_norm = " ".join(sql.split())
        op = sql_norm.split()[0].upper()
        self._conn.executed.append((op, sql_norm, params))

        if op == "INSERT" and "ground_truth_queries" in sql_norm:
            (gt_id, project_id, query_text, expected_json, note,
             created_at) = params
            self._conn.gt_rows[gt_id] = {
                "gt_id": gt_id, "project_id": project_id,
                "query_text": query_text,
                "expected_doc_ids": expected_json,
                "note": note, "created_at": created_at,
            }
        elif op == "DELETE" and "ground_truth_queries" in sql_norm:
            gt_id = params[0]
            self._conn.gt_rows.pop(gt_id, None)
        elif op == "INSERT" and "recall_eval_reports" in sql_norm:
            (report_id, project_id, version, k, total_queries,
             avg_recall, avg_precision, avg_f1, details_json,
             created_at) = params
            self._conn.report_rows[report_id] = {
                "report_id": report_id, "project_id": project_id,
                "version": version, "k": k, "total_queries": total_queries,
                "avg_recall": avg_recall, "avg_precision": avg_precision,
                "avg_f1": avg_f1, "details": details_json,
                "created_at": created_at,
            }
        elif op == "SELECT":
            self._conn._last_sql = sql_norm
            self._conn._last_params = params

    async def fetchall(self):
        sql = self._conn._last_sql
        if "FROM ground_truth_queries" in sql:
            return [
                (
                    r["gt_id"], r["project_id"], r["query_text"],
                    r["expected_doc_ids"], r["note"], r["created_at"],
                )
                for r in self._conn.gt_rows.values()
            ]
        elif "FROM recall_eval_reports" in sql:
            rows = sorted(
                self._conn.report_rows.values(),
                key=lambda r: r["created_at"],
                reverse=True,
            )
            limit = (
                self._conn._last_params[-1]
                if self._conn._last_params else None
            )
            if isinstance(limit, int):
                rows = rows[:limit]
            return [
                (
                    r["report_id"], r["project_id"], r["version"],
                    r["k"], r["total_queries"],
                    r["avg_recall"], r["avg_precision"], r["avg_f1"],
                    r["details"], r["created_at"],
                )
                for r in rows
            ]
        return []


class _FakeAsyncConn:
    def __init__(self):
        self.gt_rows: dict = {}
        self.report_rows: dict = {}
        self.executed: list = []
        self.committed = 0
        self.closed = False
        self._last_sql = ""
        self._last_params = None

    def cursor(self):
        return _FakeCursor(self)

    async def commit(self):
        self.committed += 1

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_pg(monkeypatch):
    fake_conn = _FakeAsyncConn()

    class _FakePsycopg:
        class AsyncConnection:
            @staticmethod
            async def connect(dsn):
                return fake_conn

    monkeypatch.setitem(__import__("sys").modules, "psycopg", _FakePsycopg)
    return fake_conn


@pytest.fixture(autouse=True)
def _reset():
    reset_recall_eval_for_test()
    pgmod._reset_pg_state_for_test()
    yield
    reset_recall_eval_for_test()
    pgmod._reset_pg_state_for_test()


# ════════════════════════════════════════════════════════════════════════
#  initialize_pg_recall_eval
# ════════════════════════════════════════════════════════════════════════


class TestInitialize:
    async def test_creates_two_tables_and_indexes(self, fake_pg) -> None:
        ok = await initialize_pg_recall_eval("postgresql://x/y")
        assert ok is True
        ops = [op for op, _, _ in fake_pg.executed]
        # 2 CREATE TABLE + 2 CREATE INDEX
        assert ops.count("CREATE") >= 4

    async def test_hydrates_existing_gt_and_reports(self, fake_pg) -> None:
        # 预置 ground truth
        fake_pg.gt_rows["gt_old1"] = {
            "gt_id": "gt_old1", "project_id": "p1",
            "query_text": "历史问题",
            "expected_doc_ids": ["d1", "d2"],   # list 直接（无需 json）
            "note": "", "created_at": datetime.now() - timedelta(days=1),
        }
        # 预置 report
        fake_pg.report_rows["reval_old1"] = {
            "report_id": "reval_old1", "project_id": "p1",
            "version": "v1", "k": 5, "total_queries": 1,
            "avg_recall": 0.8, "avg_precision": 0.5, "avg_f1": 0.61,
            "details": [],
            "created_at": datetime.now() - timedelta(hours=1),
        }
        await initialize_pg_recall_eval("postgresql://x/y")

        gts = list_ground_truth()
        assert len(gts) == 1
        assert gts[0].gt_id == "gt_old1"
        assert gts[0].expected_doc_ids == ["d1", "d2"]

        reports = list_reports()
        assert len(reports) == 1
        assert reports[0].avg_recall == 0.8

    async def test_connect_failure_returns_false(self, monkeypatch) -> None:
        class _BadPsycopg:
            class AsyncConnection:
                @staticmethod
                async def connect(dsn):
                    raise RuntimeError("PG down")

        monkeypatch.setitem(__import__("sys").modules, "psycopg", _BadPsycopg)
        ok = await initialize_pg_recall_eval("postgresql://x/y")
        assert ok is False
        # sink 没注入 → 内存模式仍可用
        add_ground_truth(query_text="x", expected_doc_ids=[])
        assert len(list_ground_truth()) == 1


# ════════════════════════════════════════════════════════════════════════
#  Write-through
# ════════════════════════════════════════════════════════════════════════


class TestWriteThrough:
    async def test_add_gt_persists_to_pg(self, fake_pg) -> None:
        await initialize_pg_recall_eval("postgresql://x/y")
        gt = add_ground_truth(
            project_id="p1", query_text="问题",
            expected_doc_ids=["d1"], note="测试",
        )
        # fire-and-forget create_task → 让任务跑完
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert gt.gt_id in fake_pg.gt_rows
        # JSON encoded
        stored = fake_pg.gt_rows[gt.gt_id]["expected_doc_ids"]
        assert json.loads(stored) == ["d1"]

    async def test_remove_gt_deletes_from_pg(self, fake_pg) -> None:
        await initialize_pg_recall_eval("postgresql://x/y")
        gt = add_ground_truth(query_text="x", expected_doc_ids=[])
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert gt.gt_id in fake_pg.gt_rows

        remove_ground_truth(gt.gt_id)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert gt.gt_id not in fake_pg.gt_rows

    async def test_run_recall_eval_persists_report(self, fake_pg) -> None:
        await initialize_pg_recall_eval("postgresql://x/y")
        add_ground_truth(project_id="p1", query_text="q",
                         expected_doc_ids=["a"])

        async def qa(query, k):
            return ["a"]

        report = await run_recall_eval(qa_callable=qa, project_id="p1")
        # report sink 是 await 直接调，不需 sleep
        assert report.report_id in fake_pg.report_rows
        stored = fake_pg.report_rows[report.report_id]
        assert stored["avg_recall"] == 1.0
        # details JSON encoded
        details = json.loads(stored["details"])
        assert len(details) == 1


# ════════════════════════════════════════════════════════════════════════
#  shutdown
# ════════════════════════════════════════════════════════════════════════


class TestShutdown:
    async def test_shutdown_closes_conn_and_clears_sinks(self, fake_pg) -> None:
        await initialize_pg_recall_eval("postgresql://x/y")
        await shutdown_pg_recall_eval()
        assert fake_pg.closed is True
        # 关闭后 add 不再写 PG
        add_ground_truth(query_text="x", expected_doc_ids=[])
        await asyncio.sleep(0)
        assert len(fake_pg.gt_rows) == 0
