"""混合评分引擎单元测试。"""

from packages.retrieval.hybrid_scorer import compute_hybrid_score, compute_catalog_weight


class TestHybridScorer:
    """四通道混合评分测试。"""

    def test_four_channel_scoring(self):
        score = compute_hybrid_score(
            vector_score=0.8,
            graph_score=0.6,
            catalog_weight=0.5,
            keyword_score=0.9,
            alpha=0.35, beta=0.25, gamma=0.15, delta=0.25,
        )
        expected = 0.35 * 0.8 + 0.25 * 0.6 + 0.15 * 0.5 + 0.25 * 0.9
        assert abs(score - round(expected, 4)) < 0.001

    def test_backward_compatible_three_channel(self):
        """keyword_score 默认为 0，保持向后兼容。"""
        score = compute_hybrid_score(
            0.8, 0.6, 0.5,
            alpha=0.4, beta=0.35, gamma=0.25, delta=0.0,
        )
        expected = 0.4 * 0.8 + 0.35 * 0.6 + 0.25 * 0.5
        assert abs(score - round(expected, 4)) < 0.001

    def test_zero_weight_not_ignored(self):
        """权重为 0.0 时不应被忽略（修复了 `or` 运算符的 bug）。"""
        score = compute_hybrid_score(
            vector_score=1.0,
            graph_score=1.0,
            catalog_weight=1.0,
            keyword_score=1.0,
            alpha=0.0, beta=0.0, gamma=0.0, delta=1.0,
        )
        assert abs(score - 1.0) < 0.001

    def test_all_zeros(self):
        score = compute_hybrid_score(0.0, 0.0, 0.0, 0.0)
        assert score == 0.0


class TestCatalogWeight:
    """目录匹配权重测试。"""

    def test_exact_match(self):
        assert compute_catalog_weight("tech/api", "tech/api") == 1.0

    def test_parent_child(self):
        assert compute_catalog_weight("tech/api/v1", "tech/api") == 0.7

    def test_sibling(self):
        assert compute_catalog_weight("tech/api", "tech/web") == 0.4

    def test_no_relation(self):
        assert compute_catalog_weight("tech/api", "hr/policy") == 0.1

    def test_empty_paths(self):
        assert compute_catalog_weight("", "tech/api") == 0.5
        assert compute_catalog_weight("tech/api", "") == 0.5
