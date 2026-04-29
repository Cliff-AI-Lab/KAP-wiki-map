"""M4 批 1 · 增量哈希单测（决策书 §5.3 成本控制命门）。"""

from __future__ import annotations

from packages.rebuild import (
    ChunkHashCache,
    compute_chunk_hash,
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
