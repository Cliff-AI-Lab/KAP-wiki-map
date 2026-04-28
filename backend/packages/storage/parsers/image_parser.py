"""图片解析器 — LLM Vision API 识别，含 mock 回退。"""

from __future__ import annotations

import hashlib

from packages.common import get_logger
from packages.storage.parsers.base import BaseParser, ParsedContent

log = get_logger("parser.image")


class ImageParser(BaseParser):
    """图片内容识别（OCR + 描述）。"""

    async def parse(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        try:
            return await self._parse_vision(raw_bytes, mime_type)
        except Exception as e:
            log.debug("image_parse_fallback_to_mock", error=str(e))
            return self._parse_mock(raw_bytes, mime_type)

    async def _parse_vision(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """使用 LLM Vision API 识别图片内容。"""
        import base64
        from packages.common import settings

        if not settings.openai_api_key:
            raise RuntimeError("No OpenAI API key for vision")

        import httpx

        b64_image = base64.b64encode(raw_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "请描述这张图片的内容，提取其中的文字信息。用中文回答。"},
                                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
                            ],
                        }
                    ],
                    "max_tokens": 1000,
                },
            )
            data = resp.json()
            text = data["choices"][0]["message"]["content"]

        return ParsedContent(
            text=text,
            metadata={"file_size": len(raw_bytes), "mime_type": mime_type},
            parser_name="llm_vision",
            confidence=0.8,
        )

    def _parse_mock(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """Mock 模式：基于文件大小/hash生成确定性描述。"""
        file_hash = hashlib.md5(raw_bytes).hexdigest()[:8]
        size_kb = len(raw_bytes) / 1024
        ext = mime_type.split("/")[-1]
        text = (
            f"[图片] 格式: {ext}, 文件哈希: {file_hash}, 大小: {size_kb:.1f}KB。\n"
            f"图片内容描述：该图片为企业内部文档相关图片，"
            f"可能包含流程图、组织架构图、数据图表或操作截图等内容。"
        )
        return ParsedContent(
            text=text,
            metadata={"file_size": len(raw_bytes), "mime_type": mime_type, "mock": True},
            parser_name="image_mock",
            confidence=0.2,
        )

    def supported_mime_types(self) -> list[str]:
        return ["image/png", "image/jpeg", "image/gif", "image/webp"]
