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


# M22 #9 codex LOW: 长度上限防 prompt injection / 异常公式撑爆 chunk
MAX_LATEX_CHARS = 2000
MAX_SURROUNDING_CHARS = 1000


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
    """把 EquationBlock 切成单个 KnowledgeChunk（无公式则返回空）。

    M22 #9 codex LOW: latex / surrounding_text 加长度上限, 防异常公式撑爆。
    """
    if not eq.latex or not eq.latex.strip():
        return []

    # 截断防爆
    latex = eq.latex[:MAX_LATEX_CHARS]
    if len(eq.latex) > MAX_LATEX_CHARS:
        latex += " …(截断)"
    surrounding = (eq.surrounding_text or "")[:MAX_SURROUNDING_CHARS]
    if len(eq.surrounding_text or "") > MAX_SURROUNDING_CHARS:
        surrounding += " …(截断)"

    lines = []
    if surrounding:
        lines.append(surrounding.strip())

    fence = "$" if eq.inline else "$$"
    lines.append(f"[公式{'·内联' if eq.inline else ''}]")
    lines.append(f"{fence}{latex}{fence}")
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
