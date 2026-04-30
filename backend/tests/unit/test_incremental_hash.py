"""M4 批 1 · 增量哈希单测（决策书 §5.3 成本控制命门）。

M5 #3 扩展：PgChunkHashCache 持久化（mock psycopg.AsyncConnection）。
"""

from __future__ import annotations

import pytest

from packages.rebuild import (
    ChunkHashCache,
    PgChunkHashCache,
    compute_chunk_hash,
    get_chunk_hash_cache,
    should_reextract,
)


# ════════════════════════════════════════════════════════════════════════
#  compute_chunk_hash
# ════════════════════════════════════════════════════════════════════════


class TestComputeChunkHash:
    def test_same_content_same_hash(self) -> None:
        h1 = compute_chunk_hash("这是一段测试内容")
        h2 = compute_chunk_hash("这是一段测试内容")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_chunk_hash("内容 A")
        h2 = compute_chunk_hash("内容 B")
        assert h1 != h2

    def test_empty_returns_empty_string(self) -> None:
        assert compute_chunk_hash("") == ""

    def test_hash_is_hex_64(self) -> None:
        h = compute_chunk_hash("x")
        # SHA-256 hex 64 字符
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ════════════════════════════════════════════════════════════════════════
#  ChunkHashCache
# ════════════════════════════════════════════════════════════════════════


class TestChunkHashCache:
    def test_set_and_get(self) -> None:
        cache = ChunkHashCache()
        cache.set("c1", "hash_abc")
        assert cache.get("c1") == "hash_abc"

    def test_missing_key_returns_none(self) -> None:
        cache = ChunkHashCache()
        assert cache.get("missing") is None

    def test_empty_chunk_id_silently_skipped(self) -> None:
        cache = ChunkHashCache()
        cache.set("", "hash")
        assert cache.size() == 0

    def test_clear(self) -> None:
        cache = ChunkHashCache()
        cache.set("a", "h1")
        cache.set("b", "h2")
        assert cache.size() == 2
        cache.clear()
        assert cache.size() == 0


# ════════════════════════════════════════════════════════════════════════
#  M14 #2 · ChunkHashCache LRU
# ════════════════════════════════════════════════════════════════════════


class TestChunkHashCacheLRU:
    def test_lru_evicts_oldest_when_over_limit(self) -> None:
        cache = ChunkHashCache(size_limit=3)
        cache.set("a", "h1")
        cache.set("b", "h2")
        cache.set("c", "h3")
        cache.set("d", "h4")    # 触发 evict a
        assert cache.size() == 3
        assert cache.get("a") is None
        assert cache.get("b") == "h2"

    def test_lru_get_promotes_recent(self) -> None:
        cache = ChunkHashCache(size_limit=3)
        cache.set("a", "h1")
        cache.set("b", "h2")
        cache.set("c", "h3")
        # 访问 a 让它变 most-recent
        cache.get("a")
        cache.set("d", "h4")    # 应该 evict b（不是 a）
        assert cache.get("a") == "h1"
        assert cache.get("b") is None
        assert cache.get("c") == "h3"
        assert cache.get("d") == "h4"

    def test_lru_default_limit_used(self) -> None:
        cache = ChunkHashCache()
        # 默认 100k 上限；只检查实例化不爆
        cache.set("a", "h1")
        assert cache.get("a") == "h1"

    def test_set_existing_key_updates_no_evict(self) -> None:
        cache = ChunkHashCache(size_limit=2)
        cache.set("a", "h1")
        cache.set("b", "h2")
        cache.set("a", "h1_new")
        assert cache.size() == 2
        assert cache.get("a") == "h1_new"


# ════════════════════════════════════════════════════════════════════════
#  should_reextract
# ════════════════════════════════════════════════════════════════════════


class TestShouldReextract:
    def test_no_cache_means_reextract(self) -> None:
        cache = ChunkHashCache()
        assert should_reextract("c1", "hash_x", cache) is True

    def test_cache_hit_means_skip(self) -> None:
        cache = ChunkHashCache()
        cache.set("c1", "hash_x")
        assert should_reextract("c1", "hash_x", cache) is False

    def test_cache_miss_means_reextract(self) -> None:
        cache = ChunkHashCache()
        cache.set("c1", "hash_old")
        assert should_reextract("c1", "hash_new", cache) is True

    def test_empty_current_hash_means_reextract(self) -> None:
        cache = ChunkHashCache()
        cache.set("c1", "hash_x")
        # current_hash 空 → 保守抽取
        assert should_reextract("c1", "", cache) is True


# ════════════════════════════════════════════════════════════════════════
#  M5 #3 · PgChunkHashCache（mock psycopg）
# ════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, params=None):
        sql_up = sql.strip().split()[0].upper()
        self._conn.executed.append((sql_up, params))
        self._conn._last_sql = sql.strip()
        self._conn._last_params = params

    async def executemany(self, sql, rows):
        self._conn.executemany_calls.append((sql.strip().split()[0], list(rows)))
        for chunk_id, content_hash in rows:
            self._conn.table[chunk_id] = content_hash

    async def fetchall(self):
        return [(k, v) for k, v in self._conn.table.items()]

    async def fetchone(self):
        # M14 #2 · 支持 SELECT content_hash WHERE chunk_id=%s（lazy 模式）
        sql = self._conn._last_sql or ""
        params = self._conn._last_params
        if "WHERE chunk_id" in sql and params:
            chunk_id = params[0]
            v = self._conn.table.get(chunk_id)
            return (v,) if v is not None else None
        return None


class _FakeAsyncConn:
    def __init__(self):
        self.table: dict[str, str] = {}
        self.executed: list = []
        self.executemany_calls: list = []
        self.committed = 0
        self.closed = False
        self._last_sql = ""
        self._last_params = None

    def cursor(self):
        return _FakeCursor(self)

    async def commit(self):
        self.committed += 1

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_pg(monkeypatch):
    """替换 psycopg.AsyncConnection.connect → 返回 FakeAsyncConn。"""
    fake_conn = _FakeAsyncConn()

    class _FakePsycopg:
        class AsyncConnection:
            @staticmethod
            async def connect(dsn):
                return fake_conn

    monkeypatch.setitem(
        __import__("sys").modules, "psycopg", _FakePsycopg,
    )
    return fake_conn


class TestPgChunkHashCache:
    async def test_initialize_creates_table_and_loads(self, fake_pg) -> None:
        # 预置已有数据
        fake_pg.table["c_existing"] = "hash_old"
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        await cache.initialize()
        # CREATE TABLE 被执行
        assert any("CREATE" in op for op, _ in fake_pg.executed)
        # 加载到内存
        assert cache.get("c_existing") == "hash_old"
        assert cache.size() == 1

    async def test_set_in_memory_then_flush_to_pg(self, fake_pg) -> None:
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        await cache.initialize()
        cache.set("c1", "h1")
        cache.set("c2", "h2")
        assert cache.size() == 2
        # 还没 flush，PG 表为空
        assert "c1" not in fake_pg.table
        # flush
        written = await cache.flush()
        assert written == 2
        assert fake_pg.table["c1"] == "h1"
        assert fake_pg.table["c2"] == "h2"

    async def test_set_empty_chunk_id_skipped(self, fake_pg) -> None:
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        await cache.initialize()
        cache.set("", "h")
        assert cache.size() == 0

    async def test_flush_uninitialized_returns_zero(self) -> None:
        # 未 initialize 的 cache → flush 不爆，返回 0
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        cache.set("c1", "h1")
        written = await cache.flush()
        assert written == 0

    async def test_close_closes_pg_connection(self, fake_pg) -> None:
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        await cache.initialize()
        await cache.close()
        assert fake_pg.closed is True

    async def test_should_reextract_works_with_pg_cache(self, fake_pg) -> None:
        cache = PgChunkHashCache(dsn="postgresql://x/y")
        await cache.initialize()
        cache.set("c1", "h_old")
        assert should_reextract("c1", "h_old", cache) is False
        assert should_reextract("c1", "h_new", cache) is True


# ════════════════════════════════════════════════════════════════════════
#  get_chunk_hash_cache 工厂
# ════════════════════════════════════════════════════════════════════════


class TestFactory:
    async def test_default_returns_memory(self, monkeypatch) -> None:
        monkeypatch.delenv("KAP_CHUNK_HASH_PG", raising=False)
        cache = await get_chunk_hash_cache()
        assert isinstance(cache, ChunkHashCache)

    async def test_pg_env_returns_pg(self, fake_pg, monkeypatch) -> None:
        monkeypatch.setenv("KAP_CHUNK_HASH_PG", "1")
        cache = await get_chunk_hash_cache()
        assert isinstance(cache, PgChunkHashCache)

    async def test_pg_failure_falls_back_to_memory(self, monkeypatch) -> None:
        """psycopg 连不上 → 静默降级内存模式。"""
        monkeypatch.setenv("KAP_CHUNK_HASH_PG", "1")

        class _BadPsycopg:
            class AsyncConnection:
                @staticmethod
                async def connect(dsn):
                    raise RuntimeError("connection refused")

        monkeypatch.setitem(
            __import__("sys").modules, "psycopg", _BadPsycopg,
        )
        cache = await get_chunk_hash_cache()
        assert isinstance(cache, ChunkHashCache)


# ════════════════════════════════════════════════════════════════════════
#  M14 #2 · PgChunkHashCache lazy 模式
# ════════════════════════════════════════════════════════════════════════


class TestPgLazyMode:
    async def test_lazy_does_not_load_all_at_init(self, fake_pg) -> None:
        # 预置 PG 已有数据
        fake_pg.table["c_existing"] = "hash_old"
        cache = PgChunkHashCache(
            dsn="postgresql://x/y", lazy=True, size_limit=10,
        )
        await cache.initialize()
        # lazy 模式 → 内存仍为空
        assert cache.size() == 0
        assert cache.get("c_existing") is None

    async def test_aget_lazy_loads_from_pg(self, fake_pg) -> None:
        fake_pg.table["c1"] = "hash_pg"
        cache = PgChunkHashCache(
            dsn="postgresql://x/y", lazy=True, size_limit=10,
        )
        await cache.initialize()
        # aget miss → 单查 PG
        v = await cache.aget("c1")
        assert v == "hash_pg"
        # 命中后进 LRU
        assert cache.size() == 1
        assert cache.get("c1") == "hash_pg"

    async def test_aget_unknown_returns_none(self, fake_pg) -> None:
        cache = PgChunkHashCache(
            dsn="postgresql://x/y", lazy=True, size_limit=10,
        )
        await cache.initialize()
        v = await cache.aget("nonexistent")
        assert v is None

    async def test_lazy_lru_evicts_under_pressure(self, fake_pg) -> None:
        for i in range(5):
            fake_pg.table[f"c{i}"] = f"hash_{i}"
        cache = PgChunkHashCache(
            dsn="postgresql://x/y", lazy=True, size_limit=2,
        )
        await cache.initialize()
        # 拉 3 个 → 第 1 个被驱逐
        await cache.aget("c0")
        await cache.aget("c1")
        await cache.aget("c2")
        assert cache.size() == 2
        # c0 不在 LRU；但 PG 还有 → 再 aget 拉回来
        v = await cache.aget("c0")
        assert v == "hash_0"

    async def test_lazy_flush_only_writes_pending(self, fake_pg) -> None:
        # 预置 PG 已有 c_existing；本次 set 新 c_new
        fake_pg.table["c_existing"] = "hash_old"
        cache = PgChunkHashCache(
            dsn="postgresql://x/y", lazy=True, size_limit=10,
        )
        await cache.initialize()
        cache.set("c_new", "hash_new")
        # flush 只写 pending
        n = await cache.flush()
        assert n == 1
        assert fake_pg.table["c_new"] == "hash_new"
        # c_existing 没被覆盖（M5 #3 老逻辑会重写整个 _cache）
        assert fake_pg.table["c_existing"] == "hash_old"

    async def test_factory_lazy_env_var(self, fake_pg, monkeypatch) -> None:
        monkeypatch.setenv("KAP_CHUNK_HASH_PG", "1")
        monkeypatch.setenv("KAP_CHUNK_HASH_LAZY", "1")
        monkeypatch.setenv("KAP_CHUNK_HASH_LIMIT", "50")
        cache = await get_chunk_hash_cache()
        assert isinstance(cache, PgChunkHashCache)
        # 私有字段访问验证（白盒测试，确保 env 解析对）
        assert cache._lazy is True
        assert cache._size_limit == 50
