"""重排序模块 — 支持 API-based cross-encoder reranker 和 mock 模式。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from packages.common import get_logger, settings
from packages.common.types import SearchResult

log = get_logger("retrieval.reranker")


class BaseReranker(ABC):
    """重排序器基类。"""

    @abstractmethod
    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        """对候选结果进行重排序，返回 top_k 结果。"""
        ...


class APIReranker(BaseReranker):
    """
    API-based reranker，兼容 OpenAI API 格式的 reranker 端点。
    适用 Qwen3-Reranker-4B 等部署为 API 服务的本地模型。
    """

    def __init__(self, endpoint: str, model: str, api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                resp = await client.post(
                    f"{self.endpoint}/v1/rerank",
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": [r.content[:1000] for r in results],
                        "top_n": top_k,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            # 解析响应: {"results": [{"index": int, "relevance_score": float}]}
            ranked_indices = sorted(
                data["results"],
                key=lambda x: x["relevance_score"],
                reverse=True,
            )[:top_k]

            reranked = []
            for item in ranked_indices:
                idx = item["index"]
                if 0 <= idx < len(results):
                    result = results[idx].model_copy()
                    result.score = item["relevance_score"]
                    reranked.append(result)

            log.info("api_rerank_done", input_count=len(results), output_count=len(reranked))
            return reranked

        except Exception as e:
            log.warning("api_rerank_failed_fallback", error=str(e))
            return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]


class MockReranker(BaseReranker):
    """Mock reranker — 保持原始评分排序，PoC 测试用。"""

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int
    ) -> list[SearchResult]:
        log.debug("mock_rerank", count=len(results), top_k=top_k)
        query_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]\w+", query.lower()))

        scored = []
        for r in results:
            content_lower = r.content.lower()
            match_count = sum(1 for t in query_terms if t in content_lower)
            boosted = r.model_copy()
            boosted.score = r.score + match_count * 0.02
            scored.append(boosted)

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


def create_reranker() -> BaseReranker:
    """工厂函数：根据配置创建对应的 reranker 实例。"""
    if settings.reranker_provider == "api" and settings.reranker_endpoint:
        return APIReranker(
            endpoint=settings.reranker_endpoint,
            model=settings.reranker_model,
            api_key=settings.reranker_api_key,
        )
    else:
        return MockReranker()
