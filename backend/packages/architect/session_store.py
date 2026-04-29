"""ArchitectSession PG 持久化（M3 #5）。

M2 #4 ArchitectAgent 是内存 dict；本批加抽象 Store + PG 实现 + 内存 fallback。

设计原则（feedback memory · 轻量化）：
- 协议 + 两实现：``InMemoryArchitectSessionStore`` 与 ``PgArchitectSessionStore``
- ArchitectAgent 接受可选 store，默认 InMemory（向后兼容现有测试）
- PG 模式连接失败时降级 InMemory（参考 M0 metadata_store fallback 模式）
- schema CREATE TABLE IF NOT EXISTS 幂等

存储字段（与 ArchitectSession Pydantic 对齐）：
  session_id PRIMARY KEY / project_id / stage / draft (JSONB) /
  history (JSONB) / created_at / updated_at
"""

from __future__ import annotations

from typing import Protocol

from packages.common import get_logger
from packages.common.types import ArchitectSession

log = get_logger("architect.session_store")


class ArchitectSessionStore(Protocol):
    """ArchitectSession 存储协议。"""

    async def initialize(self) -> None: ...
    async def upsert(self, session: ArchitectSession) -> None: ...
    async def get(self, session_id: str) -> ArchitectSession | None: ...
    async def list_by_project(self, project_id: str) -> list[ArchitectSession]: ...
    async def delete(self, session_id: str) -> bool: ...


class InMemoryArchitectSessionStore:
    """内存 store（默认；测试 / dev 用）。"""

    def __init__(self) -> None:
        self._data: dict[str, ArchitectSession] = {}

    async def initialize(self) -> None:
        log.info("architect_session_store_memory_mode")

    async def upsert(self, session: ArchitectSession) -> None:
        self._data[session.session_id] = session

    async def get(self, session_id: str) -> ArchitectSession | None:
        return self._data.get(session_id)

    async def list_by_project(self, project_id: str) -> list[ArchitectSession]:
        return [s for s in self._data.values() if s.project_id == project_id]

    async def delete(self, session_id: str) -> bool:
        return self._data.pop(session_id, None) is not None


# ════════════════════════════════════════════════════════════════════════
#  PG 实现
# ════════════════════════════════════════════════════════════════════════


class PgArchitectSessionStore:
    """PostgreSQL 持久化 store。

    用法：
        store = PgArchitectSessionStore(dsn=settings.postgres_dsn)
        await store.initialize()
        ...

    连接失败时 ``initialize`` 抛异常；调用方决定是否降级 InMemory。
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    async def initialize(self) -> None:
        import psycopg
        try:
            self._conn = await psycopg.AsyncConnection.connect(self._dsn)
        except Exception as e:
            raise RuntimeError(f"PG connect failed: {e}") from e

        async with self._conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS architect_sessions (
                    session_id   VARCHAR(64) PRIMARY KEY,
                    project_id   VARCHAR(64) NOT NULL,
                    stage        VARCHAR(16) NOT NULL DEFAULT 'identify',
                    draft        JSONB,
                    history      JSONB DEFAULT '[]'::jsonb,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS architect_sessions_project_idx "
                "ON architect_sessions(project_id)"
            )
            await self._conn.commit()
        log.info("architect_session_store_pg_connected")

    async def upsert(self, session: ArchitectSession) -> None:
        assert self._conn is not None
        import json as _json
        draft_json = (
            _json.dumps(session.draft.model_dump(), ensure_ascii=False, default=str)
            if session.draft else None
        )
        history_json = _json.dumps(session.history, ensure_ascii=False, default=str)

        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO architect_sessions
                  (session_id, project_id, stage, draft, history, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    draft = EXCLUDED.draft,
                    history = EXCLUDED.history,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    session.session_id, session.project_id, session.stage,
                    draft_json, history_json,
                    session.created_at, session.updated_at,
                ),
            )
            await self._conn.commit()

    async def get(self, session_id: str) -> ArchitectSession | None:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT session_id, project_id, stage, draft, history, "
                "created_at, updated_at FROM architect_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_session(row)

    async def list_by_project(self, project_id: str) -> list[ArchitectSession]:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT session_id, project_id, stage, draft, history, "
                "created_at, updated_at FROM architect_sessions "
                "WHERE project_id = %s ORDER BY updated_at DESC",
                (project_id,),
            )
            rows = await cur.fetchall()
        return [_row_to_session(r) for r in rows]

    async def delete(self, session_id: str) -> bool:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM architect_sessions WHERE session_id = %s",
                (session_id,),
            )
            deleted = cur.rowcount or 0
            await self._conn.commit()
        return deleted > 0


def _row_to_session(row) -> ArchitectSession:
    """PG row → ArchitectSession Pydantic。"""
    from packages.common.types import TaxonomyDraft
    session_id, project_id, stage, draft_json, history_json, created_at, updated_at = row
    draft = None
    if draft_json:
        if isinstance(draft_json, dict):
            draft = TaxonomyDraft.model_validate(draft_json)
        else:
            import json as _json
            draft = TaxonomyDraft.model_validate(_json.loads(draft_json))
    history: list = []
    if history_json:
        if isinstance(history_json, list):
            history = history_json
        else:
            import json as _json
            history = _json.loads(history_json)
    return ArchitectSession(
        session_id=session_id, project_id=project_id, stage=stage,
        draft=draft, history=history,
        created_at=created_at, updated_at=updated_at,
    )
