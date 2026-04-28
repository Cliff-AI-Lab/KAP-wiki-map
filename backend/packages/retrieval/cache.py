"""结果缓存层 — Redis 缓存检索与问答结果。

OPT-13: 对重复查询直接返回缓存，避免重复执行 LLM 路由 / 向量检索 / 混合评分。
Redis 不可用时自动降级为无缓存模式（不影响功能）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from packages.common import get_logger, settings
from packages.common.types import QAResponse, SearchResult

log = get_logger("retrieval.cache")

_KEY_PREFIX_SEARCH = "bw:search:"
_KEY_PREFIX_QA = "bw:qa:"


class ResultCache:
    """Redis 结果缓存，支持自动降级。"""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis = None
        self._available = False
        url = redis_url or settings.redis_url
        try:
            import redis as redis_lib
            self._redis = redis_lib.Redis.from_url(
                url, decode_responses=True, socket_connect_timeout=2,
            )
            self._redis.ping()
            self._available = True
            log.info("cache_connected", url=url)
        except Exception as e:
            log.warning("cache_unavailable", error=str(e), url=url)
            self._redis = None

    # ── 搜索结果缓存 ──────────────────────────────────────

    def get_search(
        self,
        query: str,
        top_k: int,
        target_category: str | None,
        org_id: str,
        user_access_level: str,
    ) -> list[SearchResult] | None:
        """读取搜索缓存，未命中返回 None。"""
        if not self._available:
            return None
        key = self._make_key(
            _KEY_PREFIX_SEARCH,
            query=query, top_k=top_k,
            category=target_category or "",
            org=org_id, access=user_access_level,
        )
        try:
            data = self._redis.get(key)
            if data is None:
                return None
            items = json.loads(data)
            results = [SearchResult.model_validate(item) for item in items]
            log.info("cache_hit", type="search", key_short=key[-12:])
            return results
        except Exception as e:
            log.warning("cache_get_error", type="search", error=str(e))
            return None

    def set_search(
        self,
        query: str,
        top_k: int,
        target_category: str | None,
        org_id: str,
        user_access_level: str,
        results: list[SearchResult],
    ) -> None:
        """写入搜索缓存。"""
        if not self._available or not results:
            return
        key = self._make_key(
            _KEY_PREFIX_SEARCH,
            query=query, top_k=top_k,
            category=target_category or "",
            org=org_id, access=user_access_level,
        )
        try:
            data = json.dumps(
                [r.model_dump(mode="json") for r in results],
                ensure_ascii=False,
            )
            self._redis.setex(key, settings.cache_search_ttl, data)
            log.debug("cache_set", type="search", key_short=key[-12:], count=len(results))
        except Exception as e:
            log.warning("cache_set_error", type="search", error=str(e))

    # ── 问答结果缓存 ──────────────────────────────────────

    def get_qa(
        self,
        question: str,
        top_k: int | None,
        target_category: str | None,
        org_id: str,
        user_access_level: str = "INTERNAL",
        user_department: str | None = None,
    ) -> QAResponse | None:
        """读取问答缓存，未命中返回 None。"""
        if not self._available:
            return None
        key = self._make_key(
            _KEY_PREFIX_QA,
            question=question, top_k=top_k or 0,
            category=target_category or "",
            org=org_id,
            access=user_access_level,
            department=user_department or "",
        )
        try:
            data = self._redis.get(key)
            if data is None:
                return None
            result = QAResponse.model_validate_json(data)
            log.info("cache_hit", type="qa", key_short=key[-12:])
            return result
        except Exception as e:
            log.warning("cache_get_error", type="qa", error=str(e))
            return None

    def set_qa(
        self,
        question: str,
        top_k: int | None,
        target_category: str | None,
        org_id: str,
        response: QAResponse,
        user_access_level: str = "INTERNAL",
        user_department: str | None = None,
    ) -> None:
        """写入问答缓存。"""
        if not self._available:
            return
        key = self._make_key(
            _KEY_PREFIX_QA,
            question=question, top_k=top_k or 0,
            category=target_category or "",
            org=org_id,
            access=user_access_level,
            department=user_department or "",
        )
        try:
            data = response.model_dump_json()
            self._redis.setex(key, settings.cache_qa_ttl, data)
            log.debug("cache_set", type="qa", key_short=key[-12:])
        except Exception as e:
            log.warning("cache_set_error", type="qa", error=str(e))

    # ── 缓存失效 ──────────────────────────────────────────

    def invalidate_all(self) -> None:
        """清除所有书虫缓存（数据入库后调用）。"""
        if not self._available:
            return
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match="bw:*", count=100)
                if keys:
                    self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            log.info("cache_invalidated", deleted=deleted)
        except Exception as e:
            log.warning("cache_invalidate_error", error=str(e))

    # ── 内部方法 ──────────────────────────────────────────

    @staticmethod
    def _make_key(prefix: str, **params: Any) -> str:
        """生成缓存 key：prefix + SHA256(参数排序序列化)。"""
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}{digest}"

    @property
    def available(self) -> bool:
        return self._available

    async def close(self) -> None:
        if self._redis:
            self._redis.close()
