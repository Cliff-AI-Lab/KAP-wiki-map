"""多模态解析器单元测试。"""

import pytest
from packages.storage.parsers import parse_content
from packages.storage.parsers.base import EquationBlock, ImageBlock, ParsedContent, TableBlock
from packages.storage.parsers.pdf_parser import PDFParser
from packages.storage.parsers.image_parser import ImageParser
from packages.storage.parsers.video_parser import VideoParser


@pytest.mark.asyncio
class TestParserRouter:
    """路由函数测试。"""

    async def test_plain_text_passthrough(self):
        text = "这是一段纯文本内容"
        result = await parse_content(text.encode("utf-8"), "text/plain")
        assert result.text == text
        assert result.parser_name == "text_fallback"

    async def test_unknown_mime_fallback(self):
        result = await parse_content(b"some data", "application/unknown")
        assert result.parser_name == "text_fallback"

    async def test_pdf_dispatches_to_parser(self):
        result = await parse_content(b"fake pdf bytes", "application/pdf")
        assert "pdf" in result.parser_name.lower()
        assert len(result.text) > 0

    async def test_image_dispatches_to_parser(self):
        result = await parse_content(b"fake image bytes", "image/png")
        assert "image" in result.parser_name.lower() or "mock" in result.parser_name.lower()
        assert len(result.text) > 0

    async def test_video_dispatches_to_parser(self):
        result = await parse_content(b"fake video bytes", "video/mp4")
        assert "video" in result.parser_name.lower() or "mock" in result.parser_name.lower()
        assert len(result.text) > 0


@pytest.mark.asyncio
class TestPDFParser:
    """PDF 解析器测试。"""

    async def test_mock_pdf_parse(self):
        parser = PDFParser()
        result = await parser.parse(b"not a real pdf", "application/pdf")
        assert "PDF" in result.text
        assert result.metadata.get("mock") is True

    async def test_supported_mime_types(self):
        parser = PDFParser()
        assert "application/pdf" in parser.supported_mime_types()


@pytest.mark.asyncio
class TestPDFParserBackends:
    """M22 #1 · PDF 多后端切换测试。"""

    async def test_default_backend_is_pdfplumber(self, monkeypatch):
        # 默认 settings.pdf_parser_backend = pdfplumber；fake bytes 失败 → 自动降级 mock
        from packages.storage.parsers import pdf_parser as pdf_mod
        monkeypatch.setattr(pdf_mod.settings, "pdf_parser_backend", "pdfplumber", raising=False)
        parser = PDFParser()
        result = await parser.parse(b"not a real pdf", "application/pdf")
        # pdfplumber 失败 → mock 兜底
        assert result.parser_name in ("pdfplumber", "pdf_mock")

    async def test_mineru_falls_back_when_not_installed(self, monkeypatch):
        # KAP_PDF_PARSER=mineru 但 mineru 未装 → 应降级 pdfplumber → mock
        from packages.storage.parsers import pdf_parser as pdf_mod
        monkeypatch.setattr(pdf_mod.settings, "pdf_parser_backend", "mineru", raising=False)
        parser = PDFParser()
        result = await parser.parse(b"not a real pdf", "application/pdf")
        # 降级路径里至少有一个不抛错
        assert result.parser_name in ("mineru", "pdfplumber", "pdf_mock")

    async def test_mock_backend_explicit(self, monkeypatch):
        from packages.storage.parsers import pdf_parser as pdf_mod
        monkeypatch.setattr(pdf_mod.settings, "pdf_parser_backend", "mock", raising=False)
        parser = PDFParser()
        result = await parser.parse(b"any bytes", "application/pdf")
        assert result.parser_name == "pdf_mock"
        assert result.metadata.get("mock") is True

    async def test_mineru_mock_returns_tables_equations(self, monkeypatch):
        # 模拟 mineru 已安装且返回结构化结果 → ParsedContent 应填充 tables/equations/images
        from packages.storage.parsers import pdf_parser as pdf_mod

        def _fake_mineru(raw_bytes: bytes) -> ParsedContent:
            return ParsedContent(
                text="MinerU 解析的文本",
                metadata={
                    "page_count": 3,
                    "file_size": len(raw_bytes),
                    "table_count": 1,
                    "equation_count": 1,
                    "image_count": 1,
                },
                parser_name="mineru",
                confidence=0.95,
                tables=[TableBlock(rows=[["a", "b"], ["1", "2"]], caption="t1", page=1)],
                equations=[EquationBlock(latex=r"E=mc^2", page=2, surrounding_text="爱因斯坦")],
                images=[ImageBlock(minio_uri="minio://bucket/img1", caption="图1", page=3)],
            )

        monkeypatch.setitem(pdf_mod._BACKENDS, "mineru", _fake_mineru)
        monkeypatch.setattr(pdf_mod.settings, "pdf_parser_backend", "mineru", raising=False)
        parser = PDFParser()
        result = await parser.parse(b"pdf bytes", "application/pdf")
        assert result.parser_name == "mineru"
        assert len(result.tables) == 1
        assert result.tables[0].caption == "t1"
        assert len(result.equations) == 1
        assert result.equations[0].latex == r"E=mc^2"
        assert len(result.images) == 1
        assert result.metadata["table_count"] == 1


class TestParsedContentFields:
    """M22 #1 · ParsedContent 扩展字段。"""

    def test_default_multimodal_fields_empty(self):
        # 老调用方只传 text 不传 tables/equations/images 不应破坏
        pc = ParsedContent(text="hello")
        assert pc.tables == []
        assert pc.equations == []
        assert pc.images == []

    def test_table_block_carries_header(self):
        tb = TableBlock(rows=[["col1", "col2"], ["v1", "v2"]], header_row=0)
        assert tb.header_row == 0
        assert tb.rows[0] == ["col1", "col2"]

    def test_equation_block_surrounding_text(self):
        eq = EquationBlock(latex=r"\sum_{i=1}^n x_i", surrounding_text="求和公式")
        assert "求和公式" in eq.surrounding_text
        assert eq.inline is False


@pytest.mark.asyncio
class TestImageParser:
    """Image 解析器测试。"""

    async def test_mock_image_parse(self):
        parser = ImageParser()
        result = await parser.parse(b"fake png data", "image/png")
        assert result.parser_name == "image_mock"
        assert result.metadata.get("mock") is True

    async def test_supported_mime_types(self):
        parser = ImageParser()
        mimes = parser.supported_mime_types()
        assert "image/png" in mimes
        assert "image/jpeg" in mimes


@pytest.mark.asyncio
class TestVideoParser:
    """Video 解析器测试。"""

    async def test_mock_video_parse(self):
        parser = VideoParser()
        result = await parser.parse(b"fake video data", "video/mp4")
        assert result.parser_name == "video_mock"
        assert result.metadata.get("mock") is True

    async def test_supported_mime_types(self):
        parser = VideoParser()
        assert "video/mp4" in parser.supported_mime_types()

    async def test_deterministic_mock(self):
        parser = VideoParser()
        r1 = await parser.parse(b"same data", "video/mp4")
        r2 = await parser.parse(b"same data", "video/mp4")
        assert r1.text == r2.text
