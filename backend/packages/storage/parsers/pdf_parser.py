"""PDF 文档解析器 — 多后端切换。

M22 #1 起 PDFParser 不再是单一 pdfplumber 实现，而是按 `settings.pdf_parser_backend`
在 mineru / pdfplumber / mock 之间切换：

- **mineru**：高保真解析，保留版式 + 公式 LaTeX + 表格行列结构（私有化部署 +3GB 模型）
- **pdfplumber**：仅纯文本，KAP M0-M21 的默认行为
- **mock**：无任何 PDF 库时的确定性回退（demo / 单测用）

失败链：选中后端抛错 → 自动降级到下一档，最终兜底 mock，保证 W2 上传永不 500。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from typing import Callable

from packages.common import get_logger, settings
from packages.storage.parsers.base import (
    BaseParser,
    EquationBlock,
    ImageBlock,
    ParsedContent,
    TableBlock,
)

log = get_logger("parser.pdf")

# M22 #9 修 codex HIGH #1: PDF 解析是 CPU/IO 混合的同步操作,
# uvicorn 事件循环里直接调用会阻塞 worker, 用 to_thread 把它放进
# 线程池, MinerU 还会再加超时。生产可调大。
_PDF_PARSE_TIMEOUT_SEC = 60.0


# ── 各后端实现 ─────────────────────────────────────────────────


def _parse_with_mineru(raw_bytes: bytes) -> ParsedContent:
    """MinerU 高保真解析。

    MinerU API 在 v2.x 仍在演进，KAP 这层只对接 "结构化 dict 输出" 协议：
    解析结果应含 text / tables / equations / images 四类块，本函数把它们映射到
    KAP 的 ParsedContent。具体 entry function 由运维侧 mineru 版本决定，常见两种：

        # 路径 A: mineru>=2.0 顶层 parse_pdf
        from mineru import parse_pdf
        result = parse_pdf(raw_bytes, parse_method="auto")

        # 路径 B: magic-pdf 兼容层
        from magic_pdf.api.pdf_parser import parse
        result = parse(raw_bytes)

    若 mineru 未装或 API 不匹配，主动抛 ImportError / RuntimeError，由上层降级。
    """
    try:
        from mineru import parse_pdf  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(f"mineru not installed: {e}") from e

    result = parse_pdf(raw_bytes, parse_method="auto")  # type: ignore[operator]

    text_parts: list[str] = []
    tables: list[TableBlock] = []
    equations: list[EquationBlock] = []
    images: list[ImageBlock] = []

    for block in result.get("content_list", []):
        btype = block.get("type", "")
        page = int(block.get("page_idx", 0))
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "table":
            tables.append(TableBlock(
                rows=block.get("rows", []),
                caption=block.get("caption", ""),
                page=page,
                bbox=tuple(block["bbox"]) if "bbox" in block else None,
            ))
        elif btype == "equation":
            equations.append(EquationBlock(
                latex=block.get("latex", ""),
                inline=bool(block.get("inline", False)),
                page=page,
                surrounding_text=block.get("surrounding_text", ""),
            ))
        elif btype == "image":
            images.append(ImageBlock(
                minio_uri=block.get("minio_uri", ""),
                base64=block.get("base64", ""),
                caption=block.get("caption", ""),
                page=page,
                bbox=tuple(block["bbox"]) if "bbox" in block else None,
            ))

    return ParsedContent(
        text="\n\n".join(text_parts),
        metadata={
            "page_count": int(result.get("page_count", 0)),
            "file_size": len(raw_bytes),
            "table_count": len(tables),
            "equation_count": len(equations),
            "image_count": len(images),
        },
        parser_name="mineru",
        confidence=0.95,
        tables=tables,
        equations=equations,
        images=images,
    )


def _parse_with_pdfplumber(raw_bytes: bytes) -> ParsedContent:
    """pdfplumber 解析 — M0-M21 既有路径，仅抽纯文本。"""
    import pdfplumber

    pages_text = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

    full_text = "\n\n".join(pages_text)
    return ParsedContent(
        text=full_text,
        metadata={"page_count": len(pages_text), "file_size": len(raw_bytes)},
        parser_name="pdfplumber",
        confidence=0.9,
    )


def _parse_with_mock(raw_bytes: bytes) -> ParsedContent:
    """Mock 回退：无 PDF 库或全部后端失败时给确定性占位文本，保证管线不挂。"""
    file_hash = hashlib.md5(raw_bytes).hexdigest()[:8]
    size_kb = len(raw_bytes) / 1024
    est_pages = max(1, int(size_kb / 50))
    text = (
        f"[PDF文档] 文件哈希: {file_hash}, 大小: {size_kb:.1f}KB, "
        f"估计页数: {est_pages}页。\n"
        f"本文档为PDF格式，包含企业相关内容。"
        f"文档内容涵盖制度规范、流程说明、技术方案等信息。"
    )
    return ParsedContent(
        text=text,
        metadata={"page_count": est_pages, "file_size": len(raw_bytes), "mock": True},
        parser_name="pdf_mock",
        confidence=0.3,
    )


# 后端 → 实现函数的映射；降级链按 list 顺序尝试
_BACKENDS: dict[str, Callable[[bytes], ParsedContent]] = {
    "mineru": _parse_with_mineru,
    "pdfplumber": _parse_with_pdfplumber,
    "mock": _parse_with_mock,
}
_FALLBACK_CHAIN: dict[str, list[str]] = {
    "mineru": ["mineru", "pdfplumber", "mock"],
    "pdfplumber": ["pdfplumber", "mock"],
    "mock": ["mock"],
}


class PDFParser(BaseParser):
    """PDF 文档解析器。"""

    async def parse(self, raw_bytes: bytes, mime_type: str) -> ParsedContent:
        primary = getattr(settings, "pdf_parser_backend", "pdfplumber")
        chain = _FALLBACK_CHAIN.get(primary, _FALLBACK_CHAIN["pdfplumber"])
        # M22 #9 codex HIGH #2: 生产 (sandbox/prod) 禁止静默降级到 mock,
        # 防占位文本进知识库污染召回。dev 保留全链兜底。
        env = getattr(settings, "kap_env", "dev")
        if env in ("sandbox", "prod") and chain[-1] == "mock":
            chain = [b for b in chain if b != "mock"]

        last_err: Exception | None = None
        for backend_name in chain:
            try:
                # M22 #9 codex HIGH #1: 同步 PDF 解析放进线程池, 避免阻塞 uvicorn worker
                # mineru 加超时（默认 60s, 可调）, 其他后端速度快不强制
                if backend_name == "mineru":
                    result = await asyncio.wait_for(
                        asyncio.to_thread(_BACKENDS[backend_name], raw_bytes),
                        timeout=_PDF_PARSE_TIMEOUT_SEC,
                    )
                else:
                    result = await asyncio.to_thread(_BACKENDS[backend_name], raw_bytes)

                if backend_name != primary:
                    log.debug(
                        "pdf_parse_degraded",
                        chosen=primary,
                        actual=backend_name,
                        error=str(last_err) if last_err else "",
                    )
                return result
            except asyncio.TimeoutError as e:
                last_err = e
                log.warning("pdf_parse_timeout",
                            backend=backend_name, timeout=_PDF_PARSE_TIMEOUT_SEC)
                continue
            except Exception as e:
                last_err = e
                log.debug("pdf_parse_backend_failed",
                          backend=backend_name, error=str(e))
                continue
        # 所有后端都挂了（dev 模式 _parse_with_mock 不应失败; prod 模式可能全失败）
        raise RuntimeError(
            f"all pdf backends failed (env={env}, chain={chain}): {last_err}"
        )

    def supported_mime_types(self) -> list[str]:
        return ["application/pdf"]
