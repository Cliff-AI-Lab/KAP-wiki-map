"""增量哈希（决策书 §5.3 成本控制命门）。

核心逻辑：
- chunk content sha256 哈希
- 上次重抽时记录每个 chunk 的 hash
- 本次重抽：hash 一致 → 跳过 W4 LLM 抽取，仅按新本体重映射类型
- hash 不一致 → 调 W4 entity_extractor 重新抽取

M4 lite：内存 ChunkHashCache（仅当次重抽周期有效）。
M5 持久化到 PG `chunk_hashes` 表，跨重抽周期复用。
"""

from __future__ import annotations

import hashlib

from packages.common import get_logger

log = get_logger("rebuild.incremental_hash")


def compute_chunk_hash(content: str) -> str:
    """SHA-256 内容哈希。空内容返回空串。"""
    if not content:
        return ""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChunkHashCache:
    """chunk_id → hash 缓存。

    M4 lite 内存模式（per rebuild job）；M5 接 PG 跨周期持久化。
    """

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


def should_reextract(
    chunk_id: str,
    current_hash: str,
    cache: ChunkHashCache,
) -> bool:
    """判断是否需要重新调 W4 LLM 抽取。

    Returns:
        True = 哈希变了或无缓存 → 调 W4 抽取
        False = 哈希一致 → 跳过抽取（仅按新本体重映射类型）
    """
    if not current_hash:
        return True  # 空哈希视为变更（保守）
    cached = cache.get(chunk_id)
    if cached is None:
        return True  # 第一次见 → 必须抽取
    return cached != current_hash
