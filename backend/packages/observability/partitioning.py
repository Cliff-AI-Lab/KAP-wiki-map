"""DecisionLog / QueryLog 时序分区迁移工具（M14 #3 · 决策书 §5.3 大表性能）。

M6/M7 lite：单表存所有事件，> 100M 行 时 INSERT/SELECT 慢 + VACUUM 影响。
M14 #3：把 ``decision_events`` / ``query_events`` 改为按 ``occurred_at`` 月度分区。

设计原则（feedback memory · 轻量化）：
- 不在启动时自动迁移（破坏性 + 可能很慢，需要 ops 显式触发）
- 提供函数式工具 ``migrate_to_partitioned`` + ``ensure_partition_for_month``
- 提供 dry_run 模式打印 DDL 不实际执行
- 调用方（运维脚本 / ISS-Job 月度任务）按需调

使用流程：
  1. 停写后调 ``migrate_to_partitioned("decision_events")`` 一次性迁移老表
  2. 月度任务调 ``ensure_partition_for_month("decision_events", year, month)``
     提前创建下月分区（避免月初 INSERT 失败）
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from packages.common import get_logger

log = get_logger("observability.partitioning")


# 迁移目标表 → (主键, 必有索引列)
SUPPORTED_TABLES = {
    "decision_events": ("id", "occurred_at"),
    "query_events": ("query_id", "occurred_at"),
}


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return (year + 1, 1)
    return (year, month + 1)


def _partition_name(table: str, year: int, month: int) -> str:
    return f"{table}_y{year}m{month:02d}"


def _partition_range(year: int, month: int) -> tuple[date, date]:
    """返回该月分区的 [start, end_exclusive) 时间区间。"""
    start = date(year, month, 1)
    ny, nm = _next_month(year, month)
    end = date(ny, nm, 1)
    return start, end


def build_partition_ddl(
    table: str, year: int, month: int,
) -> list[str]:
    """生成创建单个月度分区的 DDL（不执行）。"""
    if table not in SUPPORTED_TABLES:
        raise ValueError(f"不支持的表: {table}; 仅 {sorted(SUPPORTED_TABLES)}")
    name = _partition_name(table, year, month)
    start, end = _partition_range(year, month)
    return [
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {table} "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')",
    ]


def build_migration_ddl(
    table: str,
    *,
    months_back: int = 6,
    months_forward: int = 2,
    today: date | None = None,
) -> list[str]:
    """生成把单表改成 PARTITION BY RANGE (occurred_at) 的完整 DDL 序列。

    步骤：
    1. RENAME 老表 → ``<table>_legacy``
    2. CREATE 新分区主表（同 schema + PARTITION BY RANGE）
    3. CREATE 月度分区（覆盖 [today - months_back, today + months_forward]）
    4. INSERT INTO new SELECT FROM legacy（迁数据）
    5. DROP legacy（可选；调用方决定）

    Returns:
        DDL 列表（顺序执行）
    """
    if table not in SUPPORTED_TABLES:
        raise ValueError(f"不支持的表: {table}; 仅 {sorted(SUPPORTED_TABLES)}")
    today = today or date.today()
    pk, _ = SUPPORTED_TABLES[table]

    # 月度范围
    months: list[tuple[int, int]] = []
    cur_year, cur_month = today.year, today.month
    # 回看 months_back
    for _ in range(months_back):
        # 回退一个月
        if cur_month == 1:
            cur_year -= 1
            cur_month = 12
        else:
            cur_month -= 1
        months.insert(0, (cur_year, cur_month))
    # 当月
    months.append((today.year, today.month))
    # 前看 months_forward
    fy, fm = today.year, today.month
    for _ in range(months_forward):
        fy, fm = _next_month(fy, fm)
        months.append((fy, fm))

    ddl: list[str] = []
    legacy = f"{table}_legacy_m14"
    ddl.append(f"ALTER TABLE {table} RENAME TO {legacy}")

    # 新分区主表（DDL 简化，按 SUPPORTED_TABLES 分别拼）
    if table == "decision_events":
        ddl.append(
            "CREATE TABLE decision_events ("
            "id BIGSERIAL,"
            "project_id VARCHAR(64) NOT NULL,"
            "decision_type VARCHAR(32) NOT NULL,"
            "actor VARCHAR(64) NOT NULL DEFAULT '',"
            "target_id VARCHAR(128) NOT NULL DEFAULT '',"
            "note TEXT NOT NULL DEFAULT '',"
            "occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            "PRIMARY KEY (id, occurred_at)"      # 分区表 PK 必含分区键
            ") PARTITION BY RANGE (occurred_at)"
        )
    elif table == "query_events":
        ddl.append(
            "CREATE TABLE query_events ("
            "query_id VARCHAR(32),"
            "project_id VARCHAR(64) NOT NULL DEFAULT '',"
            "user_id VARCHAR(64) NOT NULL DEFAULT '',"
            "query_text TEXT NOT NULL DEFAULT '',"
            "source_count INT NOT NULL DEFAULT 0,"
            "retrieved_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,"
            "hit BOOLEAN NOT NULL DEFAULT TRUE,"
            "latency_ms INT NOT NULL DEFAULT 0,"
            "useful BOOLEAN,"
            "feedback_note TEXT NOT NULL DEFAULT '',"
            "feedback_at TIMESTAMPTZ,"
            "occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
            "PRIMARY KEY (query_id, occurred_at)"
            ") PARTITION BY RANGE (occurred_at)"
        )

    # 月度分区
    for y, m in months:
        ddl.extend(build_partition_ddl(table, y, m))

    # 重建索引
    ddl.append(
        f"CREATE INDEX IF NOT EXISTS {table}_project_idx "
        f"ON {table}(project_id, occurred_at DESC)"
    )

    # 迁数据
    ddl.append(f"INSERT INTO {table} SELECT * FROM {legacy}")

    # 注：DROP legacy 不自动包含；调用方自行评估后再调
    return ddl


async def migrate_to_partitioned(
    conn,
    table: str,
    *,
    months_back: int = 6,
    months_forward: int = 2,
    drop_legacy: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """执行迁移（或 dry_run 仅返回 DDL）。

    Args:
        conn: psycopg.AsyncConnection
        drop_legacy: True 才在最后 DROP <table>_legacy_m14
        dry_run: True 仅返回 DDL，不执行

    Returns:
        实际执行（或将执行）的 DDL 列表
    """
    ddls = build_migration_ddl(
        table, months_back=months_back, months_forward=months_forward,
    )
    if drop_legacy:
        ddls.append(f"DROP TABLE {table}_legacy_m14")

    if dry_run:
        log.info("partitioning_dry_run", table=table, ddl_count=len(ddls))
        return ddls

    async with conn.cursor() as cur:
        for stmt in ddls:
            await cur.execute(stmt)
        await conn.commit()
    log.info("partitioning_migrated", table=table, ddl_count=len(ddls))
    return ddls


async def ensure_partition_for_month(
    conn, table: str, year: int, month: int,
    *,
    dry_run: bool = False,
) -> list[str]:
    """月度任务调用：确保指定月份的分区存在（若已存在 IF NOT EXISTS 跳过）。"""
    ddls = build_partition_ddl(table, year, month)
    if dry_run:
        return ddls
    async with conn.cursor() as cur:
        for stmt in ddls:
            await cur.execute(stmt)
        await conn.commit()
    log.info("partition_ensured",
             table=table, partition=_partition_name(table, year, month))
    return ddls


def list_recommended_months(
    *,
    months_back: int = 6,
    months_forward: int = 2,
    today: date | None = None,
) -> Iterable[tuple[int, int]]:
    """返回推荐的月度分区时间窗口。"""
    today = today or date.today()
    months: list[tuple[int, int]] = []
    cy, cm = today.year, today.month
    for _ in range(months_back):
        if cm == 1:
            cy -= 1
            cm = 12
        else:
            cm -= 1
        months.insert(0, (cy, cm))
    months.append((today.year, today.month))
    fy, fm = today.year, today.month
    for _ in range(months_forward):
        fy, fm = _next_month(fy, fm)
        months.append((fy, fm))
    return months
