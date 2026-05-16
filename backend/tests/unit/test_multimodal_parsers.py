"""M22 #2 · 表格 / 公式 / 多模态 chunker 单测。"""

from __future__ import annotations

import pytest

from packages.common.types import ChunkStrategy
from packages.storage.parsers import chunks_from_parsed_content
from packages.storage.parsers.base import (
    EquationBlock,
    ImageBlock,
    ParsedContent,
    TableBlock,
)
from packages.storage.parsers.equation_parser import chunk_equation
from packages.storage.parsers.table_parser import chunk_table


class TestTableParser:
    def test_basic_row_chunks_with_header_injection(self):
        table = TableBlock(
            rows=[
                ["设备", "厂家", "投运年"],
                ["1号风机", "金风", "2018"],
                ["2号风机", "远景", "2020"],
            ],
            caption="风电场设备清单",
            page=3,
        )
        chunks = chunk_table(table, doc_id="d1", idx_offset=10)
        assert len(chunks) == 2  # 表头本身不入 chunk
        c0 = chunks[0]
        assert c0.chunk_strategy == ChunkStrategy.TABLE_ROW.value
        assert c0.chunk_index == 10
        # 表头列名必须被注入 content
        assert "设备=1号风机" in c0.content
        assert "厂家=金风" in c0.content
        assert "风电场设备清单" in c0.content
        assert "页 3" in c0.content

    def test_skip_empty_rows_handled(self):
        table = TableBlock(rows=[["A", "B"], ["", ""], ["1", "2"]], caption="t")
        chunks = chunk_table(table, doc_id="d1")
        # 全空数据行不会被过滤（保留空 chunk 是 caller 决策），但应至少有 2 个
        assert len(chunks) == 2

    def test_large_table_rolling_window(self):
        # 51 行（1 表头 + 50 数据），> TABLE_ROLL_THRESHOLD，每 20 行带回列名
        rows = [["A", "B"]] + [[str(i), f"v{i}"] for i in range(51)]
        # 长度 = 52, > 50
        table = TableBlock(rows=rows, caption="大表")
        chunks = chunk_table(table, doc_id="d1")
        # 至少一行 chunk 含列名摘要
        assert any("列: A | B" in c.content for c in chunks)


class TestEquationParser:
    def test_basic_equation_with_surrounding_text(self):
        eq = EquationBlock(
            latex=r"E = mc^2",
            inline=False,
            page=2,
            surrounding_text="爱因斯坦质能方程：",
        )
        chunks = chunk_equation(eq, doc_id="d1", idx_offset=5)
        assert len(chunks) == 1
        c = chunks[0]
        assert c.chunk_strategy == ChunkStrategy.EQUATION.value
        assert c.chunk_index == 5
        assert "爱因斯坦质能方程" in c.content
        assert r"$$E = mc^2$$" in c.content
        assert "页 2" in c.content

    def test_inline_equation_uses_single_dollar(self):
        eq = EquationBlock(latex=r"x^2", inline=True)
        chunks = chunk_equation(eq, doc_id="d1")
        assert len(chunks) == 1
        assert r"$x^2$" in chunks[0].content
        assert "内联" in chunks[0].content

    def test_empty_latex_yields_no_chunk(self):
        eq = EquationBlock(latex="")
        assert chunk_equation(eq, doc_id="d1") == []


class TestMultimodalChunker:
    def test_chunks_from_parsed_content_text_only(self):
        pc = ParsedContent(text="一段简单的文本内容，足够走默认 fixed 切片器。" * 5)
        chunks = chunks_from_parsed_content(pc, doc_id="d1")
        assert len(chunks) >= 1
        assert all(c.chunk_strategy == ChunkStrategy.FIXED.value for c in chunks)

    def test_chunks_from_parsed_content_multimodal_ordering(self):
        # text + 1 table（2 数据行）+ 1 equation + 1 image caption
        pc = ParsedContent(
            text="纯文本部分。" * 80,
            tables=[TableBlock(
                rows=[["a", "b"], ["1", "2"], ["3", "4"]],
                caption="表 X",
            )],
            equations=[EquationBlock(latex=r"a+b", surrounding_text="加法：")],
            images=[ImageBlock(caption="图 Y", page=1, minio_uri="minio://k/i1")],
        )
        chunks = chunks_from_parsed_content(pc, doc_id="d1")
        kinds = [c.chunk_strategy for c in chunks]
        # 顺序：fixed* → table_row* → equation* → image_caption*
        first_table = kinds.index(ChunkStrategy.TABLE_ROW.value)
        first_eq = kinds.index(ChunkStrategy.EQUATION.value)
        first_img = kinds.index(ChunkStrategy.IMAGE_CAPTION.value)
        assert first_table < first_eq < first_img
        # chunk_index 连续递增
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)
        assert indices == list(range(indices[0], indices[0] + len(indices)))

    def test_chunks_from_parsed_content_skips_caption_less_images(self):
        pc = ParsedContent(
            text="abc",
            images=[
                ImageBlock(caption="", page=1),     # 无 caption 跳过
                ImageBlock(caption="图 A", page=2),  # 保留
            ],
        )
        chunks = chunks_from_parsed_content(pc, doc_id="d1")
        img_chunks = [c for c in chunks
                      if c.chunk_strategy == ChunkStrategy.IMAGE_CAPTION.value]
        assert len(img_chunks) == 1
        assert "图 A" in img_chunks[0].content
