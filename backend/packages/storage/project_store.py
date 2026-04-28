"""项目存储 — 管理知识库项目的 CRUD。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from packages.common import get_logger

log = get_logger("storage.project")


class ProjectStore:
    """项目存储，支持 PostgreSQL 和内存模式。"""

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._projects: dict[str, dict] = {}
        self._pg_conn = None

    async def initialize(self, pg_conn=None) -> None:
        self._pg_conn = pg_conn
        if not self._use_memory and self._pg_conn:
            try:
                await self._create_tables()
                await self._load_from_pg()
            except Exception as e:
                log.warning("project_store_pg_failed", error=str(e))
                self._use_memory = True

        log.info("project_store_initialized",
                 mode="memory" if self._use_memory else "pg",
                 count=len(self._projects))

    async def _create_tables(self) -> None:
        assert self._pg_conn is not None
        async with self._pg_conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id              VARCHAR(64) PRIMARY KEY,
                    name            VARCHAR(256) NOT NULL,
                    industry_code   VARCHAR(32) NOT NULL,
                    description     TEXT DEFAULT '',
                    taxonomy_snapshot JSONB,
                    status          VARCHAR(16) DEFAULT 'ACTIVE',
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await self._pg_conn.commit()

    async def _load_from_pg(self) -> None:
        assert self._pg_conn is not None
        async with self._pg_conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, industry_code, description, taxonomy_snapshot, "
                "status, created_at, updated_at FROM projects ORDER BY created_at"
            )
            rows = await cur.fetchall()
            for row in rows:
                proj = {
                    "id": row[0],
                    "name": row[1],
                    "industry_code": row[2],
                    "description": row[3] or "",
                    "taxonomy_snapshot": row[4],
                    "status": row[5] or "ACTIVE",
                    "created_at": row[6].isoformat() if row[6] else None,
                    "updated_at": row[7].isoformat() if row[7] else None,
                }
                self._projects[proj["id"]] = proj

    async def create_project(
        self,
        name: str,
        industry_code: str,
        description: str = "",
        taxonomy_snapshot: Optional[list] = None,
    ) -> dict:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        proj = {
            "id": project_id,
            "name": name,
            "industry_code": industry_code,
            "description": description,
            "taxonomy_snapshot": taxonomy_snapshot,
            "status": "ACTIVE",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._projects[project_id] = proj

        if not self._use_memory and self._pg_conn:
            async with self._pg_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO projects (id, name, industry_code, description,
                                          taxonomy_snapshot, status)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (project_id, name, industry_code, description,
                     json.dumps(taxonomy_snapshot, ensure_ascii=False) if taxonomy_snapshot else None,
                     "ACTIVE"),
                )
                await self._pg_conn.commit()

        log.info("project_created", id=project_id, name=name, industry=industry_code)
        return proj

    async def ensure_default_project(self) -> dict:
        """确保默认项目存在（向后兼容）。"""
        if "default" in self._projects:
            return self._projects["default"]

        now = datetime.now(timezone.utc)
        proj = {
            "id": "default",
            "name": "默认项目",
            "industry_code": "generic",
            "description": "系统默认项目（升级前数据）",
            "taxonomy_snapshot": None,
            "status": "ACTIVE",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._projects["default"] = proj

        if not self._use_memory and self._pg_conn:
            async with self._pg_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO projects (id, name, industry_code, description, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    ("default", proj["name"], proj["industry_code"],
                     proj["description"], "ACTIVE"),
                )
                await self._pg_conn.commit()

        return proj

    def get_project(self, project_id: str) -> dict | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict]:
        return [
            p for p in self._projects.values()
            if p.get("status") == "ACTIVE"
        ]

    async def update_project(self, project_id: str, **kwargs) -> dict | None:
        proj = self._projects.get(project_id)
        if not proj:
            return None

        for key in ("name", "description", "status"):
            if key in kwargs and kwargs[key] is not None:
                proj[key] = kwargs[key]
        proj["updated_at"] = datetime.now(timezone.utc).isoformat()

        if not self._use_memory and self._pg_conn:
            async with self._pg_conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE projects SET name=%s, description=%s, status=%s,
                                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (proj["name"], proj["description"], proj["status"], project_id),
                )
                await self._pg_conn.commit()

        return proj

    async def close(self) -> None:
        pass
