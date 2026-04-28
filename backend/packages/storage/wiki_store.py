"""Wiki 页存储 (WikiStore) — Layer 0 编译产物库。

存储 WikiCompiler 编译的多层 Wiki 页（Markdown + 元数据）。
V11.2: 三层 Wiki 体系 — index / domain_overview / source_summary。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import WikiPage

log = get_logger("storage.wiki")


class WikiStore:
    """Wiki 页存储 — 编译产物层。

    设计原则（Karpathy LLM Wiki + 知识图鉴）:
    - 三层 Wiki: index → domain_overview → source_summary
    - Wiki 页是人可阅读的 Markdown 格式
    - 支持版本管理(version+1) 和状态标记(published/stale)
    - 交叉引用和溯源信息以 JSONB 存储
    """

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._memory: dict[str, dict] = {}  # "{page_id}:{project_id}" → wiki record
        self._conn = None
        self._owns_conn = False

    async def initialize(self, pg_conn=None) -> None:
        """初始化存储。"""
        if self._use_memory:
            log.info("wiki_store_memory_mode")
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
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM wiki_pages")
                row = await cur.fetchone()
                count = row[0] if row else 0
            log.info("wiki_store_pg_connected", page_count=count)
        except Exception as e:
            log.warning("wiki_store_pg_fallback_to_memory", error=str(e))
            self._use_memory = True

    async def _create_tables(self) -> None:
        """创建 Wiki 页表 (V11.2 完整 schema)。"""
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS wiki_pages (
                    page_id         VARCHAR(128) NOT NULL,
                    project_id      VARCHAR(64) NOT NULL DEFAULT 'default',
                    title           VARCHAR(256) NOT NULL,
                    content         TEXT NOT NULL,
                    summary         TEXT DEFAULT '',
                    page_type       VARCHAR(32) DEFAULT 'domain_overview',
                    parent_page_id  VARCHAR(128) DEFAULT '',
                    source_doc_ids  JSONB DEFAULT '[]',
                    cross_refs      JSONB DEFAULT '[]',
                    compiled_at     TIMESTAMPTZ DEFAULT NOW(),
                    version         INT DEFAULT 1,
                    status          VARCHAR(16) DEFAULT 'published',
                    PRIMARY KEY (page_id, project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_wiki_project ON wiki_pages(project_id);
                CREATE INDEX IF NOT EXISTS idx_wiki_status ON wiki_pages(status);
                CREATE INDEX IF NOT EXISTS idx_wiki_page_type ON wiki_pages(page_type);
            """)
            await self._conn.commit()
            # V11.2 migration: 逐列安全添加，每列独立 try/except
            for col_def in [
                ("page_type", "VARCHAR(32) DEFAULT 'domain_overview'"),
                ("parent_page_id", "VARCHAR(128) DEFAULT ''"),
                ("source_doc_ids", "JSONB DEFAULT '[]'"),
                ("cross_refs", "JSONB DEFAULT '[]'"),
                ("version", "INT DEFAULT 1"),
                ("status", "VARCHAR(16) DEFAULT 'published'"),
                ("summary", "TEXT DEFAULT ''"),
            ]:
                try:
                    await cur.execute(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='wiki_pages' AND column_name=%s",
                        (col_def[0],),
                    )
                    if not await cur.fetchone():
                        await cur.execute(
                            f"ALTER TABLE wiki_pages ADD COLUMN {col_def[0]} {col_def[1]}"
                        )
                        await self._conn.commit()
                except Exception as e:
                    log.warning("wiki_migration_column_skip", column=col_def[0], error=str(e))

    def _mem_key(self, page_id: str, project_id: str) -> str:
        return f"{page_id}:{project_id}"

    async def upsert_page(self, page: WikiPage, project_id: str = "default") -> None:
        """插入或更新 Wiki 页。更新时 version+1。"""
        now = datetime.now(timezone.utc)

        if self._use_memory:
            key = self._mem_key(page.page_id, project_id)
            existing = self._memory.get(key)
            new_version = (existing.get("version", 0) + 1) if existing else 1
            self._memory[key] = {
                "page_id": page.page_id,
                "project_id": project_id,
                "title": page.title,
                "content": page.content,
                "summary": page.summary,
                "page_type": page.page_type,
                "parent_page_id": page.parent_page_id,
                "source_doc_ids": page.source_doc_ids,
                "cross_refs": page.cross_refs,
                "compiled_at": now.isoformat(),
                "version": new_version,
                "status": page.status,
            }
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO wiki_pages (page_id, project_id, title, content, summary,
                    page_type, parent_page_id,
                    source_doc_ids, cross_refs, compiled_at, version, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
                ON CONFLICT (page_id, project_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    summary = EXCLUDED.summary,
                    page_type = EXCLUDED.page_type,
                    parent_page_id = EXCLUDED.parent_page_id,
                    source_doc_ids = EXCLUDED.source_doc_ids,
                    cross_refs = EXCLUDED.cross_refs,
                    compiled_at = EXCLUDED.compiled_at,
                    version = wiki_pages.version + 1,
                    status = EXCLUDED.status
                """,
                (
                    page.page_id, project_id, page.title, page.content, page.summary,
                    page.page_type, page.parent_page_id,
                    json.dumps(page.source_doc_ids, ensure_ascii=False),
                    json.dumps(page.cross_refs, ensure_ascii=False),
                    now, page.status,
                ),
            )
            await self._conn.commit()

    async def get_page(self, page_id: str, project_id: str = "default") -> Optional[WikiPage]:
        """获取单个 Wiki 页。"""
        if self._use_memory:
            key = self._mem_key(page_id, project_id)
            rec = self._memory.get(key)
            if not rec:
                return None
            return WikiPage(**{k: v for k, v in rec.items() if k != "project_id"})

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT page_id, title, content, summary, page_type, parent_page_id, "
                "source_doc_ids, cross_refs, compiled_at, version, status "
                "FROM wiki_pages WHERE page_id = %s AND project_id = %s",
                (page_id, project_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return WikiPage(
                page_id=row[0], title=row[1], content=row[2], summary=row[3],
                page_type=row[4] or "domain_overview",
                parent_page_id=row[5] or "",
                source_doc_ids=row[6] if isinstance(row[6], list) else json.loads(row[6] or "[]"),
                cross_refs=row[7] if isinstance(row[7], list) else json.loads(row[7] or "[]"),
                compiled_at=row[8], version=row[9], status=row[10],
            )

    async def list_pages(
        self, project_id: str = "default", page_type: str | None = None,
        status: str | None = None,
    ) -> list[WikiPage]:
        """列出项目下所有 Wiki 页（不含全文内容，节省传输）。"""
        if self._use_memory:
            results = []
            for key, rec in self._memory.items():
                if rec.get("project_id") != project_id:
                    continue
                if page_type and rec.get("page_type", "domain_overview") != page_type:
                    continue
                if status and rec.get("status", "published") != status:
                    continue
                results.append(WikiPage(
                    page_id=rec["page_id"], title=rec["title"],
                    content="",
                    summary=rec.get("summary", ""),
                    page_type=rec.get("page_type", "domain_overview"),
                    parent_page_id=rec.get("parent_page_id", ""),
                    source_doc_ids=rec.get("source_doc_ids", []),
                    cross_refs=rec.get("cross_refs", []),
                    compiled_at=rec.get("compiled_at"),
                    version=rec.get("version", 1),
                    status=rec.get("status", "published"),
                ))
            return results

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            sql = (
                "SELECT page_id, title, summary, page_type, parent_page_id, "
                "source_doc_ids, cross_refs, compiled_at, version, status "
                "FROM wiki_pages WHERE project_id = %s"
            )
            params: list = [project_id]
            if page_type:
                sql += " AND page_type = %s"
                params.append(page_type)
            if status:
                sql += " AND status = %s"
                params.append(status)
            sql += " ORDER BY page_type, page_id"
            await cur.execute(sql, tuple(params))
            rows = await cur.fetchall()
            return [
                WikiPage(
                    page_id=r[0], title=r[1], content="", summary=r[2],
                    page_type=r[3] or "domain_overview",
                    parent_page_id=r[4] or "",
                    source_doc_ids=r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                    cross_refs=r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                    compiled_at=r[7], version=r[8], status=r[9],
                )
                for r in rows
            ]

    async def mark_stale(self, page_id: str, project_id: str = "default") -> None:
        """标记 Wiki 页为过时（新文档灌入后需重编译）。"""
        if self._use_memory:
            key = self._mem_key(page_id, project_id)
            if key in self._memory:
                self._memory[key]["status"] = "stale"
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE wiki_pages SET status = 'stale' WHERE page_id = %s AND project_id = %s",
                (page_id, project_id),
            )
            await self._conn.commit()

    async def restore_published(self, page_id: str, project_id: str = "default") -> None:
        """将 stale 页恢复为 published（编译批次未覆盖的页面）。"""
        if self._use_memory:
            key = self._mem_key(page_id, project_id)
            if key in self._memory and self._memory[key].get("status") == "stale":
                self._memory[key]["status"] = "published"
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE wiki_pages SET status = 'published' WHERE page_id = %s AND project_id = %s AND status = 'stale'",
                (page_id, project_id),
            )
            await self._conn.commit()

    @property
    def page_count(self) -> int:
        """已存储的 Wiki 页总数（内存模式）。"""
        return len(self._memory)

    async def get_page_count(self, project_id: str = "default") -> int:
        """异步获取页面计数（支持 PG 模式）。"""
        if self._use_memory:
            return sum(1 for r in self._memory.values() if r.get("project_id") == project_id)
        if not self._conn:
            return 0
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM wiki_pages WHERE project_id = %s", (project_id,))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def clear_all(self, project_id: str = "default") -> None:
        """清除指定项目的所有 Wiki 页面。"""
        if self._use_memory:
            self._memory = {k: v for k, v in self._memory.items() if v.get("project_id") != project_id}
            return
        if not self._conn:
            return
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM wiki_pages WHERE project_id = %s", (project_id,))
        await self._conn.commit()
