"""公式专用切片器 — EquationBlock → KnowledgeChunk（M22 #2）。

公式独立成 chunk，**LaTeX 原样保留** + 周边文本一并入 content 作为语义上下文。
这样向量召回时既能匹配公式符号（latex 字符串），也能匹配学科描述。
"""

from __future__ import annotations

from datetime import datetime

from packages.common.types import ChunkStrategy, KnowledgeChunk
from packages.storage.parsers.base import EquationBlock


def _make_chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}_eq{idx:04d}"


def chunk_equation(
    eq: EquationBlock,
    doc_id: str,
    idx_offset: int = 0,
    category_path: str = "",
    doc_type: str = "",
    source_system: str = "",
    updated_at: datetime | None = None,
    org_id: str = "default",
    domain_id: str = "",
) -> list[KnowledgeChunk]:
    """把 EquationBlock 切成单个 KnowledgeChunk（无公式则返回空）。"""
    if not eq.latex or not eq.latex.strip():
        return []

    lines = []
    if eq.surrounding_text:
        lines.append(eq.surrounding_text.strip())

    fence = "$" if eq.inline else "$$"
    lines.append(f"[公式{'·内联' if eq.inline else ''}]")
    lines.append(f"{fence}{eq.latex}{fence}")
    if eq.page:
        lines.append(f"页 {eq.page}")

    content = "\n".join(lines)

    return [KnowledgeChunk(
        chunk_id=_make_chunk_id(doc_id, idx_offset),
        doc_id=doc_id,
        chunk_index=idx_offset,
        content=content,
        chunk_strategy=ChunkStrategy.EQUATION.value,
        category_path=category_path,
        doc_type=doc_type,
        source_system=source_system,
        updated_at=updated_at,
        org_id=org_id,
        domain_id=domain_id,
    )]
