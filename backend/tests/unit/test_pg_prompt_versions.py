"""M12 #2 · PromptVersion PG 持久化单测（mock psycopg）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from packages.observability import (
    create_prompt_version,
    deactivate_prompt_version,
    initialize_pg_prompt_versions,
    list_prompt_versions,
    reset_prompt_versions_for_test,
    shutdown_pg_prompt_versions,
)
from packages.observability import pg_prompt_versions as pgmod


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
        if op == "INSERT":
            (vid, ct, excerpt, sysprompt, by_user,
             act, deact, note) = params
            self._conn.rows[vid] = {
                "version_id": vid, "condition_type": ct,
                "prompt_text_excerpt": excerpt, "system_prompt": sysprompt,
                "created_by": by_user, "activated_at": act,
                "deactivated_at": deact, "note": note,
            }
        elif op == "UPDATE":
            deact, vid = params
            if vid in self._conn.rows:
                self._conn.rows[vid]["deactivated_at"] = deact
        # SELECT 触发 fetchall 时再返回

    async def fetchall(self):
        return [
            (
                r["version_id"], r["condition_type"],
                r["prompt_text_excerpt"], r["system_prompt"],
                r["created_by"], r["activated_at"],
                r["deactivated_at"], r["note"],
            )
            for r in self._conn.rows.values()
        ]


class _FakeAsyncConn:
    def __init__(self):
        self.rows: dict = {}
        self.executed: list = []
        self.committed = 0
        self.closed = False

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
    reset_prompt_versions_for_test()
    pgmod._reset_pg_state_for_test()
    yield
    reset_prompt_versions_for_test()
    pgmod._reset_pg_state_for_test()


# ════════════════════════════════════════════════════════════════════════
#  initialize
# ════════════════════════════════════════════════════════════════════════


class TestInitialize:
    async def test_creates_table_and_index(self, fake_pg) -> None:
        ok = await initialize_pg_prompt_versions("postgresql://x/y")
        assert ok is True
        ops = [op for op, _, _ in fake_pg.executed]
        assert ops.count("CREATE") >= 2

    async def test_hydrates_existing_rows(self, fake_pg) -> None:
        fake_pg.rows["pver_old"] = {
            "version_id": "pver_old", "condition_type": "new_entity_type",
            "prompt_text_excerpt": "v1", "system_prompt": "old override",
            "created_by": "sme01",
            "activated_at": datetime.now() - timedelta(hours=2),
            "deactivated_at": None, "note": "",
        }
        await initialize_pg_prompt_versions("postgresql://x/y")
        out = list_prompt_versions()
        assert len(out) == 1
        assert out[0].system_prompt == "old override"

    async def test_connect_failure_returns_false(self, monkeypatch) -> None:
        class _BadPsycopg:
            class AsyncConnection:
                @staticmethod
                async def connect(dsn):
                    raise RuntimeError("PG down")

        monkeypatch.setitem(__import__("sys").modules, "psycopg", _BadPsycopg)
        ok = await initialize_pg_prompt_versions("postgresql://x/y")
        assert ok is False
        # 仍可内存模式建版本
        v = create_prompt_version(condition_type="new_entity_type")
        assert v is not None


# ════════════════════════════════════════════════════════════════════════
#  Write-through
# ════════════════════════════════════════════════════════════════════════


class TestWriteThrough:
    async def test_create_persists(self, fake_pg) -> None:
        await initialize_pg_prompt_versions("postgresql://x/y")
        v = create_prompt_version(
            condition_type="standard_upgrade",
            system_prompt="OVERRIDE",
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert v.version_id in fake_pg.rows
        assert fake_pg.rows[v.version_id]["system_prompt"] == "OVERRIDE"

    async def test_create_updates_old_active(self, fake_pg) -> None:
        await initialize_pg_prompt_versions("postgresql://x/y")
        v1 = create_prompt_version(condition_type="new_entity_type")
        await asyncio.sleep(0); await asyncio.sleep(0)
        v2 = create_prompt_version(condition_type="new_entity_type")
        await asyncio.sleep(0); await asyncio.sleep(0)

        # v1 在 PG 中应被更新为 deactivated（upsert）
        assert fake_pg.rows[v1.version_id]["deactivated_at"] is not None
        assert fake_pg.rows[v2.version_id]["deactivated_at"] is None

    async def test_deactivate_updates(self, fake_pg) -> None:
        await initialize_pg_prompt_versions("postgresql://x/y")
        v = create_prompt_version(condition_type="relation_split")
        await asyncio.sleep(0); await asyncio.sleep(0)

        deactivate_prompt_version(v.version_id)
        await asyncio.sleep(0); await asyncio.sleep(0)

        assert fake_pg.rows[v.version_id]["deactivated_at"] is not None


# ════════════════════════════════════════════════════════════════════════
#  Shutdown
# ════════════════════════════════════════════════════════════════════════


class TestShutdown:
    async def test_shutdown_closes_and_clears_sinks(self, fake_pg) -> None:
        await initialize_pg_prompt_versions("postgresql://x/y")
        await shutdown_pg_prompt_versions()
        assert fake_pg.closed is True
        # 关闭后 create 不再写 PG
        v = create_prompt_version(condition_type="new_entity_type")
        await asyncio.sleep(0)
        assert v.version_id not in fake_pg.rows
