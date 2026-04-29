"""M7 #1 · DecisionLog PG 持久化单测（mock psycopg）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from packages.observability import (
    DecisionEvent,
    arecord_decision,
    initialize_pg_decision_log,
    list_decisions,
    record_decision,
    reset_decisions_for_test,
    shutdown_pg_decision_log,
)
from packages.observability import pg_decision_log as pgmod


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
        sql = sql.strip()
        op = sql.split()[0].upper()
        self._conn.executed.append((op, params))
        if op == "INSERT":
            project_id, decision_type, actor, target_id, note, occurred_at = params
            self._conn.rows.append({
                "project_id": project_id,
                "decision_type": decision_type,
                "actor": actor,
                "target_id": target_id,
                "note": note,
                "occurred_at": occurred_at,
            })
        elif op == "SELECT":
            # 简化 SELECT：模拟"按 occurred_at DESC LIMIT N"
            self._conn._select_result = sorted(
                self._conn.rows,
                key=lambda r: r["occurred_at"],
                reverse=True,
            )
            if params and isinstance(params, tuple) and len(params) >= 1:
                limit = params[-1]
                if isinstance(limit, int):
                    self._conn._select_result = self._conn._select_result[:limit]

    async def fetchall(self):
        return [
            (r["project_id"], r["decision_type"], r["actor"],
             r["target_id"], r["note"], r["occurred_at"])
            for r in self._conn._select_result
        ]


class _FakeAsyncConn:
    def __init__(self):
        self.rows: list[dict] = []
        self.executed: list = []
        self.committed = 0
        self.closed = False
        self._select_result: list[dict] = []

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
    reset_decisions_for_test()
    pgmod._reset_pg_state_for_test()
    yield
    reset_decisions_for_test()
    pgmod._reset_pg_state_for_test()


# ════════════════════════════════════════════════════════════════════════
#  initialize_pg_decision_log
# ════════════════════════════════════════════════════════════════════════


class TestInitialize:
    async def test_creates_table_and_index(self, fake_pg) -> None:
        ok = await initialize_pg_decision_log("postgresql://x/y")
        assert ok is True
        ops = [op for op, _ in fake_pg.executed]
        assert "CREATE" in ops  # CREATE TABLE
        # 第二个 CREATE 是 INDEX
        assert ops.count("CREATE") >= 2

    async def test_hydrates_memory_with_existing_rows(self, fake_pg) -> None:
        # 预置历史数据
        fake_pg.rows = [
            {
                "project_id": "p1", "decision_type": "approve_proposal",
                "actor": "sme01", "target_id": "onto_a", "note": "",
                "occurred_at": datetime.now() - timedelta(hours=2),
            },
            {
                "project_id": "p1", "decision_type": "promote",
                "actor": "sme01", "target_id": "v1", "note": "",
                "occurred_at": datetime.now() - timedelta(hours=1),
            },
        ]
        await initialize_pg_decision_log("postgresql://x/y", load_limit=10)
        events = list_decisions()
        assert len(events) == 2
        # 最新事件优先
        assert events[0].decision_type == "promote"

    async def test_connect_failure_returns_false(self, monkeypatch) -> None:
        class _BadPsycopg:
            class AsyncConnection:
                @staticmethod
                async def connect(dsn):
                    raise RuntimeError("connection refused")

        monkeypatch.setitem(__import__("sys").modules, "psycopg", _BadPsycopg)
        ok = await initialize_pg_decision_log("postgresql://x/y")
        assert ok is False
        # sink 没注入 → 内存模式仍可用
        record_decision(project_id="p1", decision_type="approve_proposal")
        assert len(list_decisions()) == 1


# ════════════════════════════════════════════════════════════════════════
#  arecord_decision write-through
# ════════════════════════════════════════════════════════════════════════


class TestWriteThrough:
    async def test_arecord_persists_to_pg(self, fake_pg) -> None:
        await initialize_pg_decision_log("postgresql://x/y")
        await arecord_decision(
            project_id="p1", decision_type="promote",
            actor="sme01", target_id="v2",
        )
        # 内存写入
        assert len(list_decisions()) == 1
        # PG 写入
        assert len(fake_pg.rows) == 1
        assert fake_pg.rows[0]["decision_type"] == "promote"

    async def test_arecord_continues_when_pg_write_fails(
        self, fake_pg, monkeypatch
    ) -> None:
        await initialize_pg_decision_log("postgresql://x/y")

        async def boom(event):
            raise RuntimeError("PG down")

        from packages.observability import set_pg_sink
        set_pg_sink(boom)

        # arecord 异常吞掉，内存仍记
        await arecord_decision(project_id="p1", decision_type="promote")
        assert len(list_decisions()) == 1

    async def test_record_sync_fire_and_forget(self, fake_pg) -> None:
        """sync record 在 running loop 中应触发 create_task；让任务完成后验证 PG。"""
        await initialize_pg_decision_log("postgresql://x/y")
        record_decision(project_id="p1", decision_type="approve_proposal")
        # 让 create_task 完成
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(fake_pg.rows) == 1


# ════════════════════════════════════════════════════════════════════════
#  shutdown
# ════════════════════════════════════════════════════════════════════════


class TestShutdown:
    async def test_shutdown_closes_conn_and_clears_sink(self, fake_pg) -> None:
        await initialize_pg_decision_log("postgresql://x/y")
        await shutdown_pg_decision_log()
        assert fake_pg.closed is True
        # 关闭后 record 不再写 PG
        record_decision(project_id="p1", decision_type="approve_proposal")
        await asyncio.sleep(0)
        assert len(fake_pg.rows) == 0
