"""增量哈希（决策书 §5.3 成本控制命门）。

核心逻辑：
- chunk content sha256 哈希
- 上次重抽时记录每个 chunk 的 hash
- 本次重抽：hash 一致 → 跳过 W4 LLM 抽取，仅按新本体重映射类型
- hash 不一致 → 调 W4 entity_extractor 重新抽取

存储模式（M5 #3 加 PG 持久化）：
- ``ChunkHashCache``         — 内存 dict（默认；测试 / 重抽周期内复用）
- ``PgChunkHashCache``       — PG ``chunk_hashes`` 表，跨重抽周期复用
- ``get_chunk_hash_cache()`` — 工厂：环境变量 KAP_CHUNK_HASH_PG=1 时返回 PG，否则内存
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol

from packages.common import get_logger

log = get_logger("rebuild.incremental_hash")


def compute_chunk_hash(content: str) -> str:
    """SHA-256 内容哈希。空内容返回空串。"""
    if not content:
        return ""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ════════════════════════════════════════════════════════════════════════
#  Protocol
# ════════════════════════════════════════════════════════════════════════


class ChunkHashStore(Protocol):
    """ChunkHashCache 抽象（同步接口；PG 实现内部用 await 但 cache 接口同步）。"""

    def get(self, chunk_id: str) -> str | None: ...
    def set(self, chunk_id: str, content_hash: str) -> None: ...
    def clear(self) -> None: ...
    def size(self) -> int: ...


# ════════════════════════════════════════════════════════════════════════
#  内存实现（默认）
# ════════════════════════════════════════════════════════════════════════


class ChunkHashCache:
    """chunk_id → hash 内存缓存（per rebuild job 周期有效）。"""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def get(self, chunk_id: str) -> str | None:
        return self._cache.get(chunk_id)

    def set(self, chunk_id: str, content_hash: str) -> None:
        if not chunk_id:
            return
        self._cache[chunk_id] = content_hash

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# ════════════════════════════════════════════════════════════════════════
#  PG 持久化实现（M5 #3）
# ════════════════════════════════════════════════════════════════════════


_DDL = """
CREATE TABLE IF NOT EXISTS chunk_hashes (
    chunk_id     VARCHAR(128) PRIMARY KEY,
    content_hash VARCHAR(64)  NOT NULL,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""


class PgChunkHashCache:
    """chunk_id → hash PG 持久化（M5 #3 跨重抽周期复用）。

    设计为同步接口（与内存版兼容），但内部用 psycopg.AsyncConnection。
    构造时调 ``initialize()`` 一次（建表 + 加载所有现存 hash 到内存层）；
    后续 ``set`` 同时落 PG + 内存（write-through）。

    Notes:
        - 单连接（M5 lite，符合"轻量化"原则）
        - 启动 load 全表到内存（chunk 数量级 < 1M 时可控）
        - 大规模需要换为 lazy load + LRU；留 M5 后续
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None
        self._cache: dict[str, str] = {}
        self._initialized = False

    async def initialize(self) -> None:
        import psycopg
        try:
            self._conn = await psycopg.AsyncConnection.connect(self._dsn)
        except Exception as e:
            raise RuntimeError(f"PG connect failed: {e}") from e

        async with self._conn.cursor() as cur:
            await cur.execute(_DDL)
            await self._conn.commit()
            await cur.execute(
                "SELECT chunk_id, content_hash FROM chunk_hashes"
            )
            rows = await cur.fetchall()
        for chunk_id, content_hash in rows:
            self._cache[chunk_id] = content_hash
        self._initialized = True
        log.info("chunk_hash_pg_loaded", count=len(self._cache))

    def get(self, chunk_id: str) -> str | None:
        return self._cache.get(chunk_id)

    def set(self, chunk_id: str, content_hash: str) -> None:
        """同步接口：内存即时生效；PG 写在 ``flush()`` 异步收尾。

        重抽编排器跑完一批后调 ``await flush()`` 一次性 upsert。
        """
        if not chunk_id:
            return
        self._cache[chunk_id] = content_hash

    async def flush(self) -> int:
        """把内存 cache 全量 upsert 到 PG（M5 lite 简单实现）。

        Returns:
            写入条数
        """
        if not self._initialized or self._conn is None:
            log.warning("chunk_hash_pg_flush_skipped_uninitialized")
            return 0

        if not self._cache:
            return 0

        rows = list(self._cache.items())
        async with self._conn.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO chunk_hashes (chunk_id, content_hash, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (chunk_id) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW()
                """,
                rows,
            )
            await self._conn.commit()
        log.info("chunk_hash_pg_flushed", count=len(rows))
        return len(rows)

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._initialized = False


# ════════════════════════════════════════════════════════════════════════
#  工厂
# ════════════════════════════════════════════════════════════════════════


async def get_chunk_hash_cache() -> ChunkHashStore:
    """根据 ``KAP_CHUNK_HASH_PG`` 环境变量选实现。

    - ``KAP_CHUNK_HASH_PG=1`` → ``PgChunkHashCache``（自动初始化 + 加载）
    - 其他 / 未设 → ``ChunkHashCache``（内存）
    """
    if os.environ.get("KAP_CHUNK_HASH_PG") == "1":
        try:
            from packages.common.config import settings
            cache = PgChunkHashCache(settings.postgres_dsn)
            await cache.initialize()
            return cache
        except Exception as e:
            log.warning("chunk_hash_pg_fallback_to_memory", error=str(e))
    return ChunkHashCache()


# ════════════════════════════════════════════════════════════════════════
#  helper
# ════════════════════════════════════════════════════════════════════════


def should_reextract(
    chunk_id: str,
    current_hash: str,
    cache: ChunkHashStore,
) -> bool:
    """判断是否需要重新调 W4 LLM 抽取。

    Returns:
        True = 哈希变了或无缓存 → 调 W4 抽取
        False = 哈希一致 → 跳过抽取（仅按新本体重映射类型）
    """
    if not current_hash:
        return True
    cached = cache.get(chunk_id)
    if cached is None:
        return True
    return cached != current_hash
