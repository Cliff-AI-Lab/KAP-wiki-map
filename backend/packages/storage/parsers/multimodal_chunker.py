"""多模态切片协调器 — ParsedContent → 全模态 KnowledgeChunk 列表（M22 #2）。

W6 入库链路应该调这个函数, 而不是直接调 chunker.chunk_document:
chunk_document 只处理 text, 会把 MinerU 抽出的 tables / equations / images 丢掉.

输出顺序：text chunks → table row chunks → equation chunks → image caption chunks,
chunk_index 在三段之间连续递增, 保证 doc_index_store / vector_store 可一致检索.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from packages.common.types import ChunkStrategy, KnowledgeChunk
from packages.storage.chunker import chunk_document
from packages.storage.parsers.base import ParsedContent
from packages.storage.parsers.equation_parser import chunk_equation
from packages.storage.parsers.table_parser import chunk_table


def _safe_image_ref(minio_uri: str) -> str:
    """M22 #9 codex MED: minio_uri 全路径不进可召回正文, 改用稳定哈希前缀。

    完整 URI 通过 doc_id + chunk_id 反查 raw_store / 图像表获取（M23 候选）。
    这里只输出 minio:img_<8 字符 hash>, 防止 portal/RAG 召回时泄露内部桶名/对象路径。
    """
    if not minio_uri:
        return ""
    digest = hashlib.sha256(minio_uri.encode("utf-8")).hexdigest()[:8]
    return f"minio:img_{digest}"


def _make_image_chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}_img{idx:04d}"


def _chunk_image_captions(
    pc: ParsedContent,
    doc_id: str,
    idx_offset: int,
    common_kwargs: dict,
) -> list[KnowledgeChunk]:
    """每张图独立产一个 caption chunk（无 caption 跳过, 等 M23 VLM 处理器补全）。"""
    chunks: list[KnowledgeChunk] = []
    cursor = idx_offset
    for img in pc.images:
        if not img.caption:
            continue
        parts = [f"[图像] {img.caption}"]
        if img.page:
            parts.append(f"页 {img.page}")
        if img.minio_uri:
            # M22 #9 codex MED: 用脱敏 hash 引用而非完整 minio URI, 防泄露内部对象路径
            parts.append(f"ref={_safe_image_ref(img.minio_uri)}")
        chunks.append(KnowledgeChunk(
            chunk_id=_make_image_chunk_id(doc_id, cursor),
            doc_id=doc_id,
            chunk_index=cursor,
            content="\n".join(parts),
            chunk_strategy=ChunkStrategy.IMAGE_CAPTION.value,
            **common_kwargs,
        ))
        cursor += 1
    return chunks


def chunks_from_parsed_content(
    pc: ParsedContent,
    doc_id: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
    category_path: str = "",
    doc_type: str = "",
    source_system: str = "",
    updated_at: datetime | None = None,
    strategy: str | None = None,
    org_id: str = "default",
    domain_id: str = "",
) -> list[KnowledgeChunk]:
    """把 ParsedContent 切成全模态 KnowledgeChunk 列表（text + table + equation + image）。"""
    common_kwargs = dict(
        category_path=category_path,
        doc_type=doc_type,
        source_system=source_system,
        updated_at=updated_at,
        org_id=org_id,
        domain_id=domain_id,
    )

    # 1) text chunks（沿用 M0+ 的 chunker.chunk_document 三策略）
    text_chunks = chunk_document(
        doc_id=doc_id,
        content=pc.text or "",
        chunk_size=chunk_size,
        overlap=overlap,
        strategy=strategy,
        **common_kwargs,
    )

    cursor = len(text_chunks)

    # 2) tables → 行级 chunks
    table_chunks: list[KnowledgeChunk] = []
    for table in pc.tables:
        new_chunks = chunk_table(table, doc_id=doc_id, idx_offset=cursor, **common_kwargs)
        table_chunks.extend(new_chunks)
        cursor += len(new_chunks)

    # 3) equations → 单 chunk per equation
    eq_chunks: list[KnowledgeChunk] = []
    for eq in pc.equations:
        new_chunks = chunk_equation(eq, doc_id=doc_id, idx_offset=cursor, **common_kwargs)
        eq_chunks.extend(new_chunks)
        cursor += len(new_chunks)

    # 4) images → caption chunks（M22 #2 阶段只切 caption, VLM 语义留 M23+）
    img_chunks = _chunk_image_captions(pc, doc_id=doc_id, idx_offset=cursor,
                                       common_kwargs=common_kwargs)

    return text_chunks + table_chunks + eq_chunks + img_chunks
