"""切片器单元测试 — 覆盖三种策略 + 向后兼容性。"""

import pytest
from packages.storage.chunker import chunk_document


class TestFixedChunking:
    """固定长度切片策略测试。"""

    def test_empty_content_returns_empty(self):
        assert chunk_document("d1", "") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_document("d1", "   \n\t  ") == []

    def test_short_content_single_chunk(self):
        chunks = chunk_document("d1", "短文本", strategy="fixed")
        assert len(chunks) == 1
        assert chunks[0].chunk_strategy == "fixed"
        assert chunks[0].content == "短文本"

    def test_sentence_boundary_awareness(self):
        """验证切片倾向于在句号处断开。"""
        text = "这是第一段内容。" * 30 + "这是第二段内容。" * 30
        chunks = chunk_document("d1", text, chunk_size=100, overlap=20, strategy="fixed")
        assert len(chunks) > 1
        # 非末尾切片应倾向于在句号处结束
        for c in chunks[:-1]:
            content = c.content.rstrip()
            assert content.endswith("。") or len(c.content) <= 100

    def test_backward_compatible_defaults(self):
        """旧的调用方式仍然有效。"""
        chunks = chunk_document("d1", "x" * 1000, chunk_size=500, overlap=100)
        assert all(c.chunk_strategy == "fixed" for c in chunks)
        assert len(chunks) >= 2

    def test_chunk_ids_unique(self):
        chunks = chunk_document("d1", "内容" * 500, strategy="fixed")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_metadata_propagated(self):
        chunks = chunk_document(
            "d1", "测试内容" * 100,
            category_path="tech/api",
            doc_type="技术文档",
            source_system="feishu",
            strategy="fixed",
        )
        for c in chunks:
            assert c.category_path == "tech/api"
            assert c.doc_type == "技术文档"
            assert c.source_system == "feishu"


class TestParentChildChunking:
    """父子分段策略测试。"""

    def test_parent_child_structure(self):
        text = "# 第一章\n这是第一章的内容。\n\n# 第二章\n这是第二章的内容。"
        chunks = chunk_document("d1", text, strategy="parent_child")
        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if c.parent_chunk_id]
        assert len(parents) >= 1
        # 每个子切片引用的父切片ID应该有效
        parent_ids = {p.chunk_id for p in parents}
        for child in children:
            assert child.parent_chunk_id in parent_ids

    def test_parent_child_all_strategy_tagged(self):
        text = "# A\nContent A.\n\n# B\nContent B."
        chunks = chunk_document("d1", text, strategy="parent_child")
        assert all(c.chunk_strategy == "parent_child" for c in chunks)

    def test_double_newline_fallback(self):
        """没有 markdown 标题时，按双换行分段。"""
        text = "段落一的内容。\n\n段落二的内容。\n\n段落三的内容。"
        chunks = chunk_document("d1", text, strategy="parent_child")
        parents = [c for c in chunks if c.is_parent]
        assert len(parents) >= 2

    def test_single_section_produces_parent_and_children(self):
        """单个长段落应产生一个父切片和多个子切片。"""
        text = "这是一段很长的内容。" * 200  # 约1800字符
        chunks = chunk_document("d1", text, strategy="parent_child")
        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if c.parent_chunk_id]
        assert len(parents) >= 1
        assert len(children) >= 1


class TestSemanticChunking:
    """语义切片策略测试。"""

    def test_semantic_produces_chunks(self):
        text = "人工智能是计算机科学的一个分支。" * 20 + "今天天气很好，适合出去散步。" * 20
        chunks = chunk_document("d1", text, strategy="semantic")
        assert len(chunks) >= 1
        assert all(c.chunk_strategy == "semantic" for c in chunks)

    def test_semantic_short_text_fallback_to_fixed(self):
        """极短文本应退化为固定切片。"""
        chunks = chunk_document("d1", "只有一句话。", strategy="semantic")
        assert len(chunks) == 1

    def test_semantic_chunk_ids_unique(self):
        text = "第一个话题的内容。" * 30 + "完全不同的第二个话题。" * 30
        chunks = chunk_document("d1", text, strategy="semantic")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
