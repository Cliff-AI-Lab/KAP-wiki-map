"""多模态内容解析器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedContent:
    """解析器输出：提取的文本内容和元信息。"""
    text: str
    metadata: dict = field(default_factory=dict)
    parser_name: str = ""
    confidence: float = 1.0


class BaseParser(ABC):
    """多模态内容解析器抽象基类。"""

    @abstractmethod
    async def parse(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """将原始字节解析为文本内容。"""

    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """返回此解析器支持的 MIME 类型列表。"""
