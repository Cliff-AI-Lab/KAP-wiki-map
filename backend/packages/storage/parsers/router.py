"""多模态内容解析路由 — 按 MIME 类型分发到对应解析器。

本模块是文档导入流水线的入口，负责根据上传文件的 MIME 类型，
将内容分发到正确的解析器（PDF / 图片 / 视频）进行结构化提取。
对于未注册的 MIME 类型，回退为 UTF-8 纯文本解码。

支持的解析器：
- PDFParser: 处理 application/pdf 等 PDF 类文件
- ImageParser: 处理 image/png、image/jpeg 等图片文件
- VideoParser: 处理 video/mp4 等视频文件

扩展方式：
    新增解析器只需继承 BaseParser 并实现 supported_mime_types() 和 parse()，
    然后在本模块的解析器列表中注册即可自动生效。
"""

from __future__ import annotations

from packages.common import get_logger
from packages.storage.parsers.base import BaseParser, ParsedContent
from packages.storage.parsers.pdf_parser import PDFParser
from packages.storage.parsers.image_parser import ImageParser
from packages.storage.parsers.video_parser import VideoParser
from packages.storage.parsers.docx_parser import DOCXParser

log = get_logger("parser.router")

# ── 解析器注册表构建 ────────────────────────────────────────────
# 实例化各解析器，遍历其声明的 MIME 类型，构建 MIME → 解析器 的快速查找表
_pdf = PDFParser()
_image = ImageParser()
_video = VideoParser()
_docx = DOCXParser()

_PARSERS: dict[str, BaseParser] = {}
for parser in [_pdf, _image, _video, _docx]:
    for mt in parser.supported_mime_types():
        _PARSERS[mt] = parser


async def parse_content(file_bytes: bytes, mime_type: str) -> ParsedContent:
    """根据 MIME 类型路由到对应解析器，将原始字节流解析为结构化内容。

    Args:
        file_bytes: 文件的原始字节内容
        mime_type: 文件的 MIME 类型（如 "application/pdf"、"image/png"）

    Returns:
        ParsedContent: 解析后的结构化内容，包含提取的文本、元数据和解析器名称。
            对于未知 MIME 类型，回退为 UTF-8 文本解码（替换无法解码的字节）。
    """
    # 在注册表中查找对应的解析器
    parser = _PARSERS.get(mime_type)

    if parser is None:
        # 未找到匹配解析器，回退为纯文本解码
        log.debug("parser_text_fallback", mime_type=mime_type)
        return ParsedContent(
            text=file_bytes.decode("utf-8", errors="replace"),
            metadata={"mime_type": mime_type},
            parser_name="text_fallback",
        )

    # 分发到对应解析器处理
    log.debug("parser_dispatch", mime_type=mime_type, parser=type(parser).__name__)
    return await parser.parse(file_bytes, mime_type)
