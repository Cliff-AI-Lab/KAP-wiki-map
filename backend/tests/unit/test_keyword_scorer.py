"""BM25 关键词检索单元测试。"""

from packages.retrieval.keyword_scorer import BM25Scorer


class TestBM25Scorer:
    """BM25 评分器测试。"""

    def test_empty_corpus(self):
        scorer = BM25Scorer()
        assert scorer.search("test") == []

    def test_empty_query(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": "c1", "doc_id": "d1", "content": "内容"},
        ])
        assert scorer.search("") == []

    def test_basic_search(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": "c1", "doc_id": "d1", "content": "Docker部署指南，包含容器配置"},
            {"chunk_id": "c2", "doc_id": "d2", "content": "报销制度说明，财务流程"},
        ])
        results = scorer.search("Docker部署")
        assert len(results) >= 1
        assert results[0]["chunk_id"] == "c1"

    def test_scores_normalized(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": "c1", "doc_id": "d1", "content": "hello world test"},
            {"chunk_id": "c2", "doc_id": "d2", "content": "world peace"},
        ])
        results = scorer.search("hello world")
        assert all(0 <= r["score"] <= 1.0 for r in results)
        # 最高分应该是 1.0（归一化后）
        if results:
            assert results[0]["score"] == 1.0

    def test_incremental_add(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": "c1", "doc_id": "d1", "content": "初始文档"},
        ])
        scorer.add_chunks([
            {"chunk_id": "c2", "doc_id": "d2", "content": "新增文档"},
        ])
        assert scorer._n_docs == 2

    def test_top_k_limit(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": f"c{i}", "doc_id": f"d{i}", "content": f"文档{i}内容测试"}
            for i in range(20)
        ])
        results = scorer.search("文档内容", top_k=5)
        assert len(results) <= 5

    def test_chinese_tokenization(self):
        tokens = BM25Scorer._tokenize("人工智能是AI技术")
        # 应包含中文 bigram 和英文单词
        assert any("ai" in t.lower() for t in tokens)
        assert "人工" in tokens  # 中文 bigram

    def test_no_match_returns_empty(self):
        scorer = BM25Scorer()
        scorer.build_index([
            {"chunk_id": "c1", "doc_id": "d1", "content": "完全不相关的内容"},
        ])
        # 查询中的术语在文档中不存在时
        results = scorer.search("xyz123")
        assert len(results) == 0
