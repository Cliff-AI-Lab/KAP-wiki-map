"""Reranker 单元测试。"""

import pytest
from packages.retrieval.reranker import MockReranker
from packages.common.types import SearchResult


@pytest.mark.asyncio
class TestMockReranker:
    """MockReranker 测试。"""

    async def test_rerank_respects_top_k(self):
        reranker = MockReranker()
        results = [
            SearchResult(doc_id=f"d{i}", content=f"内容 {i}", score=0.5)
            for i in range(10)
        ]
        reranked = await reranker.rerank("测试查询", results, top_k=3)
        assert len(reranked) == 3

    async def test_rerank_boosts_keyword_match(self):
        reranker = MockReranker()
        results = [
            SearchResult(doc_id="d1", content="Docker部署指南配置容器", score=0.5),
            SearchResult(doc_id="d2", content="报销制度说明", score=0.5),
        ]
        reranked = await reranker.rerank("Docker部署", results, top_k=2)
        # 同基础分下，Docker部署指南应因关键词匹配被提升到第一
        assert reranked[0].doc_id == "d1"

    async def test_rerank_preserves_all_when_top_k_equals_input(self):
        reranker = MockReranker()
        results = [
            SearchResult(doc_id="d1", content="内容A", score=0.8),
            SearchResult(doc_id="d2", content="内容B", score=0.6),
        ]
        reranked = await reranker.rerank("查询", results, top_k=5)
        assert len(reranked) == 2  # 不会超过输入数量

    async def test_rerank_does_not_mutate_originals(self):
        reranker = MockReranker()
        original = SearchResult(doc_id="d1", content="Docker部署", score=0.5)
        results = [original]
        reranked = await reranker.rerank("Docker", results, top_k=1)
        # 原始对象的 score 不应被修改
        assert original.score == 0.5
