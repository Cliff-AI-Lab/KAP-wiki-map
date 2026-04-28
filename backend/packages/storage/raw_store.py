"""原始文档库 (RawStore) — Layer 0 不可变底座。

Karpathy LLM Wiki 第一原则：原始文档永久保留完整原文，不可修改。
支持重编译 Wiki、溯源追踪、全文重新蒸馏。

V11 新增：知识图鉴双引擎架构的原始层。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import RawDocument

log = get_logger("storage.raw")


class RawStore:
    """原始文档库 — 不可变层。完整原文永久保留，支持重编译。

    设计原则（Karpathy LLM Wiki）:
    - 只写入，不修改，不删除（immutable）
    - 蒸馏流水线和 Wiki 编译器从此读取输入
    - 用于溯源：wiki声明 → 精炼产物 → 原始原文
    """

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._memory: dict[str, dict] = {}  # "{doc_id}:{project_id}" → raw record
        self._conn = None
        self._owns_conn = False  # 是否拥有连接（自建的才 commit/close）

    async def initialize(self, pg_conn=None) -> None:
        """初始化存储。支持外部传入 PG 连接或自行创建。"""
        if self._use_memory:
            log.info("raw_store_memory_mode")
            return

        try:
            if pg_conn:
                self._conn = pg_conn
                self._owns_conn = False
            else:
                import psycopg
                self._conn = await psycopg.AsyncConnection.connect(settings.postgres_dsn)
                self._owns_conn = True
            await self._create_tables()
            # 统计已有文档数
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM raw_documents")
                row = await cur.fetchone()
                count = row[0] if row else 0
            log.info("raw_store_pg_connected", doc_count=count)
        except Exception as e:
            log.warning("raw_store_pg_fallback_to_memory", error=str(e))
            self._use_memory = True

    async def _create_tables(self) -> None:
        """创建原始文档表。"""
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS raw_documents (
                    doc_id          VARCHAR(64) NOT NULL,
                    project_id      VARCHAR(64) NOT NULL DEFAULT 'default',
                    title           VARCHAR(512) NOT NULL,
                    full_content    TEXT NOT NULL,
                    source_system   VARCHAR(32) DEFAULT '',
                    file_hash       VARCHAR(64) DEFAULT '',
                    metadata        JSONB DEFAULT '{}',
                    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (doc_id, project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_raw_project ON raw_documents(project_id);
            """)
            await self._conn.commit()  # DDL 语句始终 commit

    async def _commit(self) -> None:
        """安全 commit: DML 写操作时调用。外部连接也需 commit 以持久化数据。"""
        if self._conn:
            await self._conn.commit()

    async def save_raw(self, doc: RawDocument, project_id: str = "default") -> None:
        """保存原始文档完整原文。只写入不修改（ON CONFLICT DO NOTHING）。"""
        file_hash = hashlib.sha256(doc.content.encode("utf-8")).hexdigest()[:16]

        if self._use_memory:
            mem_key = f"{doc.doc_id}:{project_id}"
            if mem_key not in self._memory:
                self._memory[mem_key] = {
                    "doc_id": doc.doc_id,
                    "project_id": project_id,
                    "title": doc.title,
                    "full_content": doc.content,
                    "source_system": doc.source_system.value if hasattr(doc.source_system, 'value') else str(doc.source_system),
                    "file_hash": file_hash,
                    "metadata": doc.metadata,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO raw_documents (doc_id, project_id, title, full_content, source_system, file_hash, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id, project_id) DO NOTHING
                """,
                (
                    doc.doc_id,
                    project_id,
                    doc.title,
                    doc.content,
                    doc.source_system.value if hasattr(doc.source_system, 'value') else str(doc.source_system),
                    file_hash,
                    json.dumps(doc.metadata, ensure_ascii=False),
                ),
            )
            await self._commit()

    async def get_raw(self, doc_id: str, project_id: str = "default") -> Optional[dict]:
        """获取单个原始文档。"""
        if self._use_memory:
            return self._memory.get(f"{doc_id}:{project_id}") or self._memory.get(doc_id)

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT doc_id, project_id, title, full_content, source_system, file_hash, metadata, ingested_at "
                "FROM raw_documents WHERE doc_id = %s AND project_id = %s",
                (doc_id, project_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "doc_id": row[0], "project_id": row[1], "title": row[2],
                "full_content": row[3], "source_system": row[4], "file_hash": row[5],
                "metadata": row[6] if isinstance(row[6], dict) else json.loads(row[6] or "{}"),
                "ingested_at": row[7],
            }

    async def list_raw_by_project(self, project_id: str = "default") -> list[dict]:
        """列出项目下所有原始文档（不含全文，节省内存）。"""
        if self._use_memory:
            return [
                {k: v for k, v in r.items() if k != "full_content"}
                for r in self._memory.values()
                if r.get("project_id") == project_id
            ]

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT doc_id, project_id, title, source_system, file_hash, ingested_at "
                "FROM raw_documents WHERE project_id = %s ORDER BY ingested_at DESC",
                (project_id,),
            )
            rows = await cur.fetchall()
            return [
                {"doc_id": r[0], "project_id": r[1], "title": r[2],
                 "source_system": r[3], "file_hash": r[4], "ingested_at": r[5]}
                for r in rows
            ]

    @property
    def doc_count(self) -> int:
        """已存储的原始文档总数（内存模式直接返回，PG 模式需调用 async 方法）。"""
        return len(self._memory)

    async def get_doc_count(self, project_id: str = "default") -> int:
        """异步获取文档计数（支持 PG 模式）。"""
        if self._use_memory:
            return sum(1 for r in self._memory.values() if r.get("project_id") == project_id)
        if not self._conn:
            return 0
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM raw_documents WHERE project_id = %s", (project_id,))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def clear_all(self, project_id: str = "default") -> None:
        """清除指定项目的所有原始文档。"""
        if self._use_memory:
            self._memory = {k: v for k, v in self._memory.items() if v.get("project_id") != project_id}
            return
        if not self._conn:
            return
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM raw_documents WHERE project_id = %s", (project_id,))
        await self._commit()
