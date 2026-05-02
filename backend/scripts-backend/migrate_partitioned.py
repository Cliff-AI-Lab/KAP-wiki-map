"""DecisionLog / QueryLog 时序分区迁移脚本（M19 #5 部署收口）。

把单表 ``decision_events`` / ``query_events`` 迁移成按月分区的父-子表结构（M14 #3 工具）。

使用方式：
    # dry-run（仅打印 DDL，不执行）
    python -m scripts-backend.migrate_partitioned --dry-run

    # 实际迁移（停写期内执行）
    python -m scripts-backend.migrate_partitioned --apply

    # 仅创建未来一个月的子分区（运行期周度任务）
    python -m scripts-backend.migrate_partitioned --ensure-current

注意：
- 本脚本仅做 DDL 操作，不做数据迁移；老表内容请用 ``INSERT INTO ... SELECT`` 显式补齐
- 必须停写期执行（决策书 §5.3 时序分区为运营期优化）
- 表存在数据时使用 ``ensure_partition_for_month`` 增量加月，无需迁移
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

import psycopg

from packages.observability.partitioning import (
    build_partition_ddl, ensure_partition_for_month, migrate_to_partitioned,
)


_TABLES = ["decision_events", "query_events"]


async def _print_dry_run() -> None:
    print("=" * 72)
    print("DRY RUN — 仅打印 DDL，不执行")
    print("=" * 72)
    for table in _TABLES:
        print(f"\n## {table} 分区迁移 DDL（默认覆盖回看 6 月 + 前看 2 月）")
        from packages.observability.partitioning import build_migration_ddl
        ddls = build_migration_ddl(
            table, months_back=6, months_forward=2,
        )
        for ddl in ddls:
            print(ddl)
            print("---")


async def _apply_full(dsn: str) -> None:
    print(f"connecting to {dsn[:30]}...")
    conn = await psycopg.AsyncConnection.connect(dsn)
    try:
        for table in _TABLES:
            print(f"migrating {table} ...")
            await migrate_to_partitioned(conn, table)
            print(f"  done")
    finally:
        await conn.close()


async def _ensure_current(dsn: str) -> None:
    """周度调用，确保当前月 + 下月子分区已创建。"""
    conn = await psycopg.AsyncConnection.connect(dsn)
    try:
        now = datetime.now()
        next_month = now.month + 1 if now.month < 12 else 1
        next_year = now.year if now.month < 12 else now.year + 1
        for table in _TABLES:
            await ensure_partition_for_month(conn, table, now.year, now.month)
            await ensure_partition_for_month(conn, table, next_year, next_month)
            print(f"ensured {table} partitions for {now.year}-{now.month:02d} + "
                  f"{next_year}-{next_month:02d}")
    finally:
        await conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true",
                     help="仅打印 DDL，不执行")
    grp.add_argument("--apply", action="store_true",
                     help="对 decision_events / query_events 执行完整迁移")
    grp.add_argument("--ensure-current", action="store_true",
                     help="仅确保当前 + 下月分区存在（周度任务）")
    args = ap.parse_args()

    dsn = os.environ.get("KAP_POSTGRES_DSN") or os.environ.get("POSTGRES_DSN")

    if args.dry_run:
        asyncio.run(_print_dry_run())
        return

    if not dsn:
        sys.exit("KAP_POSTGRES_DSN / POSTGRES_DSN 环境变量未设置")

    if args.apply:
        asyncio.run(_apply_full(dsn))
    elif args.ensure_current:
        asyncio.run(_ensure_current(dsn))


if __name__ == "__main__":
    main()
