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
from collections import OrderedDict
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


_DEFAULT_LRU_LIMIT = 100_000   # M14 #2 默认 10 万条；可在工厂传入覆盖


class ChunkHashCache:
    """chunk_id → hash 内存缓存（per rebuild job 周期有效）。

    M14 #2：用 ``OrderedDict`` 实现 LRU；超过 ``size_limit`` 时驱逐最久未用条目。
    默认 limit=100k 适用单进程一次重抽；> 1M chunks 场景建议用 PG 模式 + lazy load。
    """

    def __init__(self, size_limit: int = _DEFAULT_LRU_LIMIT) -> None:
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._size_limit = max(1, int(size_limit))

    def get(self, chunk_id: str) -> str | None:
        if chunk_id not in self._cache:
            return None
        # LRU: 命中后移到末尾
        self._cache.move_to_end(chunk_id)
        return self._cache[chunk_id]

    def set(self, chunk_id: str, content_hash: str) -> None:
        if not chunk_id:
            return
        if chunk_id in self._cache:
            self._cache.move_to_end(chunk_id)
            self._cache[chunk_id] = content_hash
            return
        self._cache[chunk_id] = content_hash
        if len(self._cache) > self._size_limit:
            evicted_id, _ = self._cache.popitem(last=False)
            log.debug("chunk_hash_lru_evicted", chunk_id=evicted_id)

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
    """chunk_id → hash PG 持久化（M5 #3 + M14 #2 LRU 分片）。

    M5 #3 模式：``initialize`` 时全量水化所有 chunk hash 到内存。
    M14 #2 改造：可选 ``lazy=True`` + ``size_limit`` LRU；不再启动加载全量，
    只在 ``get`` miss 时按 chunk_id 单查 PG，命中放进 LRU 内存。
    > 1M chunks 时显著降低内存（O(N) → O(limit)）+ 启动延迟。

    向后兼容：默认 ``lazy=False`` 走 M5 #3 老行为；
    ``get_chunk_hash_cache()`` 工厂可通过 KAP_CHUNK_HASH_LAZY=1 切换。
    """

    def __init__(
        self,
        dsn: str,
        *,
        lazy: bool = False,
        size_limit: int = _DEFAULT_LRU_LIMIT,
    ) -> None:
        self._dsn = dsn
        self._conn = None
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        # 暂存待 flush 到 PG 的条目（与 LRU 内存分开，确保 evict 不丢未落盘数据）
        self._pending: dict[str, str] = {}
        self._initialized = False
        self._lazy = bool(lazy)
        self._size_limit = max(1, int(size_limit))

    async def initialize(self) -> None:
        import psycopg
        try:
            self._conn = await psycopg.AsyncConnection.connect(self._dsn)
        except Exception as e:
            raise RuntimeError(f"PG connect failed: {e}") from e

        async with self._conn.cursor() as cur:
            await cur.execute(_DDL)
            await self._conn.commit()
            if not self._lazy:
                # M5 #3 老行为：全量加载
                await cur.execute(
                    "SELECT chunk_id, content_hash FROM chunk_hashes"
                )
                rows = await cur.fetchall()
                for chunk_id, content_hash in rows:
                    self._cache[chunk_id] = content_hash
                log.info("chunk_hash_pg_loaded", count=len(self._cache))
            else:
                log.info("chunk_hash_pg_lazy_mode_enabled",
                         size_limit=self._size_limit)
        self._initialized = True

    def get(self, chunk_id: str) -> str | None:
        if chunk_id in self._cache:
            self._cache.move_to_end(chunk_id)
            return self._cache[chunk_id]
        # lazy 模式：miss 时不查 PG（同步接口；调用方需用 ``await aget``）
        return None

    async def aget(self, chunk_id: str) -> str | None:
        """异步 get：lazy 模式下 miss 时按 chunk_id 单查 PG（M14 #2）。"""
        if chunk_id in self._cache:
            self._cache.move_to_end(chunk_id)
            return self._cache[chunk_id]
        if not self._lazy or self._conn is None:
            return None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT content_hash FROM chunk_hashes WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        content_hash = row[0]
        self._put_lru(chunk_id, content_hash)
        return content_hash

    def _put_lru(self, chunk_id: str, content_hash: str) -> None:
        if chunk_id in self._cache:
            self._cache.move_to_end(chunk_id)
            self._cache[chunk_id] = content_hash
            return
        self._cache[chunk_id] = content_hash
        if len(self._cache) > self._size_limit:
            evicted_id, _ = self._cache.popitem(last=False)
            log.debug("chunk_hash_pg_lru_evicted", chunk_id=evicted_id)

    def set(self, chunk_id: str, content_hash: str) -> None:
        """同步接口：内存即时生效 + 进 pending 队列；
        ``flush()`` 时把 pending 一次性 upsert 到 PG。"""
        if not chunk_id:
            return
        self._put_lru(chunk_id, content_hash)
        self._pending[chunk_id] = content_hash

    async def flush(self) -> int:
        """把 pending 队列 upsert 到 PG（M14 #2：仅写本批新增/更新的）。

        旧 M5 #3 行为是把全量 _cache 写一次（在 LRU 模式下浪费 + 错误）；
        改为只写 set() 后累计的 _pending 队列。flush 完清空 pending（已落盘）。

        Returns:
            写入条数
        """
        if not self._initialized or self._conn is None:
            log.warning("chunk_hash_pg_flush_skipped_uninitialized")
            return 0

        if not self._pending:
            return 0

        rows = list(self._pending.items())
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
        self._pending.clear()
        log.info("chunk_hash_pg_flushed", count=len(rows))
        return len(rows)

    def clear(self) -> None:
        self._cache.clear()
        self._pending.clear()

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
    """根据环境变量选实现：

    - ``KAP_CHUNK_HASH_PG=1`` → ``PgChunkHashCache``
      - ``KAP_CHUNK_HASH_LAZY=1`` 时启用 lazy + LRU（M14 #2，> 1M chunks 推荐）
      - ``KAP_CHUNK_HASH_LIMIT=N`` 自定义 LRU size 上限（默认 100k）
    - 其他 / 未设 → ``ChunkHashCache``（内存 + LRU 默认 100k）
    """
    limit_raw = os.environ.get("KAP_CHUNK_HASH_LIMIT", "")
    try:
        size_limit = int(limit_raw) if limit_raw else _DEFAULT_LRU_LIMIT
    except ValueError:
        size_limit = _DEFAULT_LRU_LIMIT

    if os.environ.get("KAP_CHUNK_HASH_PG") == "1":
        lazy = os.environ.get("KAP_CHUNK_HASH_LAZY") == "1"
        try:
            from packages.common.config import settings
            cache = PgChunkHashCache(
                settings.postgres_dsn, lazy=lazy, size_limit=size_limit,
            )
            await cache.initialize()
            return cache
        except Exception as e:
            log.warning("chunk_hash_pg_fallback_to_memory", error=str(e))
    return ChunkHashCache(size_limit=size_limit)


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
