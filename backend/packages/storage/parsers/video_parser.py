"""视频解析器 — 音频提取 + 语音转录，含 mock 回退。"""

from __future__ import annotations

import hashlib

from packages.common import get_logger
from packages.storage.parsers.base import BaseParser, ParsedContent

log = get_logger("parser.video")


class VideoParser(BaseParser):
    """视频内容转录（音频提取 → ASR）。"""

    async def parse(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        try:
            return await self._parse_transcribe(raw_bytes, mime_type)
        except Exception as e:
            log.debug("video_parse_fallback_to_mock", error=str(e))
            return self._parse_mock(raw_bytes, mime_type)

    async def _parse_transcribe(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """使用 Whisper API 转录视频音频。"""
        from packages.common import settings

        if not settings.openai_api_key:
            raise RuntimeError("No OpenAI API key for transcription")

        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            ext = mime_type.split("/")[-1]
            resp = await client.post(
                f"{settings.openai_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                files={"file": (f"video.{ext}", raw_bytes, mime_type)},
                data={"model": "whisper-1", "language": "zh"},
            )
            data = resp.json()
            text = data.get("text", "")

        return ParsedContent(
            text=text,
            metadata={"file_size": len(raw_bytes), "mime_type": mime_type},
            parser_name="whisper",
            confidence=0.75,
        )

    def _parse_mock(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        """Mock 模式：基于文件大小估算时长并生成描述。"""
        file_hash = hashlib.md5(raw_bytes).hexdigest()[:8]
        size_mb = len(raw_bytes) / (1024 * 1024)
        est_minutes = max(1, int(size_mb / 10))
        ext = mime_type.split("/")[-1]
        text = (
            f"[视频] 格式: {ext}, 文件哈希: {file_hash}, "
            f"大小: {size_mb:.1f}MB, 估计时长: {est_minutes}分钟。\n"
            f"视频内容摘要：该视频为企业内部培训或会议录像，"
            f"内容涵盖业务流程讲解、技术方案演示或安全培训等主题。"
        )
        return ParsedContent(
            text=text,
            metadata={
                "file_size": len(raw_bytes),
                "mime_type": mime_type,
                "estimated_duration_min": est_minutes,
                "mock": True,
            },
            parser_name="video_mock",
            confidence=0.2,
        )

    def supported_mime_types(self) -> list[str]:
        return ["video/mp4", "video/avi", "video/quicktime"]
