"""多模态解析器单元测试。"""

import pytest
from packages.storage.parsers import parse_content
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
