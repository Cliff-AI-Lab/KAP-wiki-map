"""M14 #3 · DecisionLog / QueryLog 时序分区单测（mock psycopg）。"""

from __future__ import annotations

from datetime import date

import pytest

from packages.observability import (
    build_migration_ddl,
    build_partition_ddl,
    ensure_partition_for_month,
    list_recommended_months,
    migrate_to_partitioned,
)


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
        self._conn.executed.append(sql.strip())


class _FakeAsyncConn:
    def __init__(self):
        self.executed: list[str] = []
        self.committed = 0

    def cursor(self):
        return _FakeCursor(self)

    async def commit(self):
        self.committed += 1


@pytest.fixture
def fake_conn():
    return _FakeAsyncConn()


# ════════════════════════════════════════════════════════════════════════
#  build_partition_ddl
# ════════════════════════════════════════════════════════════════════════


class TestBuildPartitionDDL:
    def test_basic(self) -> None:
        ddl = build_partition_ddl("decision_events", 2026, 4)
        assert len(ddl) == 1
        assert "decision_events_y2026m04" in ddl[0]
        assert "PARTITION OF decision_events" in ddl[0]
        assert "'2026-04-01'" in ddl[0]
        assert "'2026-05-01'" in ddl[0]

    def test_year_boundary_december(self) -> None:
        ddl = build_partition_ddl("query_events", 2026, 12)
        assert "'2026-12-01'" in ddl[0]
        assert "'2027-01-01'" in ddl[0]

    def test_unsupported_table_raises(self) -> None:
        with pytest.raises(ValueError, match="不支持的表"):
            build_partition_ddl("random_table", 2026, 1)


# ════════════════════════════════════════════════════════════════════════
#  build_migration_ddl
# ════════════════════════════════════════════════════════════════════════


class TestBuildMigrationDDL:
    def test_decision_events_full_sequence(self) -> None:
        ddls = build_migration_ddl(
            "decision_events",
            months_back=2, months_forward=1,
            today=date(2026, 4, 30),
        )
        # 至少含 RENAME / CREATE 主表 / 4 个月分区 (2 back + 当月 + 1 forward) /
        # CREATE INDEX / INSERT
        assert any("RENAME TO decision_events_legacy_m14" in d for d in ddls)
        assert any(
            "CREATE TABLE decision_events" in d and "PARTITION BY RANGE" in d
            for d in ddls
        )
        assert any("decision_events_y2026m02" in d for d in ddls)  # back-2
        assert any("decision_events_y2026m03" in d for d in ddls)  # back-1
        assert any("decision_events_y2026m04" in d for d in ddls)  # 当月
        assert any("decision_events_y2026m05" in d for d in ddls)  # forward-1
        assert any("INSERT INTO decision_events SELECT" in d for d in ddls)

    def test_query_events_includes_jsonb_field(self) -> None:
        ddls = build_migration_ddl(
            "query_events", months_back=0, months_forward=0,
            today=date(2026, 4, 30),
        )
        # 主表 DDL 含 retrieved_doc_ids JSONB
        assert any(
            "retrieved_doc_ids JSONB" in d
            for d in ddls
        )

    def test_unsupported_table_raises(self) -> None:
        with pytest.raises(ValueError):
            build_migration_ddl("random_table")


# ════════════════════════════════════════════════════════════════════════
#  migrate_to_partitioned
# ════════════════════════════════════════════════════════════════════════


class TestMigrateToPartitioned:
    async def test_dry_run_does_not_execute(self, fake_conn) -> None:
        ddls = await migrate_to_partitioned(
            fake_conn, "decision_events",
            months_back=1, months_forward=1, dry_run=True,
        )
        assert len(ddls) > 0
        assert fake_conn.executed == []
        assert fake_conn.committed == 0

    async def test_actual_run_executes_all_ddls(self, fake_conn) -> None:
        ddls = await migrate_to_partitioned(
            fake_conn, "query_events",
            months_back=0, months_forward=0,
        )
        # 全部执行（顺序）
        assert len(fake_conn.executed) == len(ddls)
        assert fake_conn.committed == 1

    async def test_drop_legacy_appends_drop(self, fake_conn) -> None:
        ddls = await migrate_to_partitioned(
            fake_conn, "decision_events",
            months_back=0, months_forward=0,
            drop_legacy=True, dry_run=True,
        )
        assert any("DROP TABLE decision_events_legacy_m14" in d for d in ddls)


# ════════════════════════════════════════════════════════════════════════
#  ensure_partition_for_month
# ════════════════════════════════════════════════════════════════════════


class TestEnsurePartition:
    async def test_dry_run_returns_ddl_no_execute(self, fake_conn) -> None:
        ddls = await ensure_partition_for_month(
            fake_conn, "query_events", 2026, 5, dry_run=True,
        )
        assert len(ddls) == 1
        assert "query_events_y2026m05" in ddls[0]
        assert fake_conn.executed == []

    async def test_actual_run_creates_partition(self, fake_conn) -> None:
        await ensure_partition_for_month(
            fake_conn, "decision_events", 2026, 6,
        )
        assert any(
            "decision_events_y2026m06" in stmt for stmt in fake_conn.executed
        )
        assert fake_conn.committed == 1


# ════════════════════════════════════════════════════════════════════════
#  list_recommended_months
# ════════════════════════════════════════════════════════════════════════


class TestRecommendedMonths:
    def test_basic_window(self) -> None:
        months = list(list_recommended_months(
            months_back=2, months_forward=1, today=date(2026, 4, 30),
        ))
        # 2 back + 当月 + 1 forward = 4
        assert len(months) == 4
        assert months == [(2026, 2), (2026, 3), (2026, 4), (2026, 5)]

    def test_year_rollover(self) -> None:
        months = list(list_recommended_months(
            months_back=2, months_forward=1, today=date(2026, 1, 15),
        ))
        # back: 2025-11, 2025-12; current: 2026-01; forward: 2026-02
        assert (2025, 11) in months
        assert (2025, 12) in months
        assert (2026, 1) in months
        assert (2026, 2) in months
