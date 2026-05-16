"""多模态内容解析器基类。

M22 #1 起 ParsedContent 不再只承载文本，还可携带表格 / 公式 / 图像三类结构化块。
解析器若不识别这些模态，对应字段保持空列表即可，不影响既有调用方。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TableBlock:
    """单张表格 — 行列结构 + 表头 + 可选标题与上下文。

    rows[0] 默认作为表头（若 header_row 字段存在，按它指示），后续行级 chunker
    会把表头注入 metadata.facet，避免行 chunk 失去列名语义。
    """
    rows: list[list[str]]
    caption: str = ""
    page: int = 0
    bbox: tuple[float, float, float, float] | None = None
    header_row: int = 0


@dataclass
class EquationBlock:
    """数学公式 — LaTeX 形式 + 周边文本上下文。"""
    latex: str
    inline: bool = False
    page: int = 0
    surrounding_text: str = ""


@dataclass
class ImageBlock:
    """图像块 — 引用 / 标题 / 位置。

    引用字段优先级：minio_uri > base64（避免大图把 ParsedContent 撑爆）。
    """
    minio_uri: str = ""
    base64: str = ""
    caption: str = ""
    page: int = 0
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class ParsedContent:
    """解析器输出：提取的文本内容和元信息。

    M22 #1：扩展 tables / equations / images 三个结构化模态字段。
    旧调用方只用 text/metadata 不受影响。
    """
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parser_name: str = ""
    confidence: float = 1.0
    tables: list[TableBlock] = field(default_factory=list)
    equations: list[EquationBlock] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)


class BaseParser(ABC):
    """多模态内容解析器抽象基类。"""

    @abstractmethod
    async def parse(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """将原始字节解析为文本内容。"""

    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """返回此解析器支持的 MIME 类型列表。"""
