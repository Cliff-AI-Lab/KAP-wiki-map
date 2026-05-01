"""PromptVersion PG 持久化（M12 #2 · 决策书 §5.3 跨重启不丢 prompt 配置）。

write-through 模式（同 pg_decision_log / pg_query_log / pg_recall_eval）：
- ``initialize_pg_prompt_versions(dsn)`` 启动建表 + 全量水化 + 注入双 sink
- create_prompt_version → 触发 upsert sink
- deactivate_prompt_version → 触发 update_deactivated sink
- 单连接 + asyncio.Lock 串行
"""

from __future__ import annotations

import asyncio

from packages.common import get_logger
from packages.observability.prompt_versions import (
    PromptVersion,
    _versions,  # type: ignore[reportPrivateUsage]
    set_prompt_version_pg_sinks,
)

log = get_logger("observability.pg_prompt_versions")


_DDL = """
CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id           VARCHAR(32)  PRIMARY KEY,
    condition_type       VARCHAR(32)  NOT NULL,
    language             VARCHAR(8)   NOT NULL DEFAULT 'zh',
    prompt_text_excerpt  TEXT         NOT NULL DEFAULT '',
    system_prompt        TEXT         NOT NULL DEFAULT '',
    created_by           VARCHAR(64)  NOT NULL DEFAULT '',
    activated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deactivated_at       TIMESTAMPTZ,
    note                 TEXT         NOT NULL DEFAULT ''
)
"""

# 兼容老库：ALTER 加 M15 #3 language 字段
_ALTER_DDL = [
    "ALTER TABLE prompt_versions ADD COLUMN IF NOT EXISTS language VARCHAR(8) NOT NULL DEFAULT 'zh'",
]

_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS prompt_versions_condition_idx
ON prompt_versions(condition_type, language, activated_at DESC)
"""


_conn = None
_lock: asyncio.Lock | None = None


async def initialize_pg_prompt_versions(dsn: str) -> bool:
    """连接 PG → 建表 → 全量水化 → 注入 sinks。"""
    global _conn, _lock
    import psycopg

    try:
        _conn = await psycopg.AsyncConnection.connect(dsn)
    except Exception as e:
        log.warning("prompt_versions_pg_connect_failed", error=str(e))
        return False

    _lock = asyncio.Lock()

    async with _conn.cursor() as cur:
        await cur.execute(_DDL)
        for stmt in _ALTER_DDL:
            await cur.execute(stmt)
        await cur.execute(_INDEX_DDL)
        await _conn.commit()
        await cur.execute(
            "SELECT version_id, condition_type, language, prompt_text_excerpt, "
            "system_prompt, created_by, activated_at, deactivated_at, note "
            "FROM prompt_versions"
        )
        rows = await cur.fetchall()

    for row in rows:
        _versions[row[0]] = PromptVersion(
            version_id=row[0],
            condition_type=row[1],         # type: ignore[arg-type]
            language=row[2] or "zh",
            prompt_text_excerpt=row[3] or "",
            system_prompt=row[4] or "",
            created_by=row[5] or "",
            activated_at=row[6],
            deactivated_at=row[7],
            note=row[8] or "",
        )

    set_prompt_version_pg_sinks(
        upsert_sink=_pg_upsert,
        deactivate_sink=_pg_deactivate,
    )
    log.info("prompt_versions_pg_initialized", hydrated=len(rows))
    return True


async def _pg_upsert(version: PromptVersion) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO prompt_versions
                  (version_id, condition_type, language, prompt_text_excerpt,
                   system_prompt, created_by, activated_at, deactivated_at, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (version_id) DO UPDATE SET
                    condition_type = EXCLUDED.condition_type,
                    language = EXCLUDED.language,
                    prompt_text_excerpt = EXCLUDED.prompt_text_excerpt,
                    system_prompt = EXCLUDED.system_prompt,
                    created_by = EXCLUDED.created_by,
                    activated_at = EXCLUDED.activated_at,
                    deactivated_at = EXCLUDED.deactivated_at,
                    note = EXCLUDED.note
                """,
                (
                    version.version_id, version.condition_type,
                    version.language,
                    version.prompt_text_excerpt, version.system_prompt,
                    version.created_by, version.activated_at,
                    version.deactivated_at, version.note,
                ),
            )
            await _conn.commit()


async def _pg_deactivate(version_id: str, deactivated_at) -> None:
    if _conn is None or _lock is None:
        return
    async with _lock:
        async with _conn.cursor() as cur:
            await cur.execute(
                "UPDATE prompt_versions SET deactivated_at = %s "
                "WHERE version_id = %s",
                (deactivated_at, version_id),
            )
            await _conn.commit()


async def shutdown_pg_prompt_versions() -> None:
    global _conn, _lock
    set_prompt_version_pg_sinks(upsert_sink=None, deactivate_sink=None)
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            log.warning("prompt_versions_pg_close_failed", error=str(e))
    _conn = None
    _lock = None


def _reset_pg_state_for_test() -> None:
    global _conn, _lock
    set_prompt_version_pg_sinks(upsert_sink=None, deactivate_sink=None)
    _conn = None
    _lock = None
