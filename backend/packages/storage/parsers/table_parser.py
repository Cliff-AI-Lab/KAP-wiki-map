"""表格专用切片器 — TableBlock → KnowledgeChunk 列表（M22 #2）。

策略：每数据行独立成 chunk，**表头注入到 content 前缀**，避免 chunker
切分后失去列名上下文。caption / page 也一并编码到 content，保留语义锚点。

大表（> TABLE_ROLL_THRESHOLD 行）每 ROLL_WINDOW 行重新带一次表头（滚动窗口），
召回长表格时不会越查越蒙。
"""

from __future__ import annotations

from datetime import datetime

from packages.common.types import ChunkStrategy, KnowledgeChunk
from packages.storage.parsers.base import TableBlock

# 大表滚动窗口阈值
TABLE_ROLL_THRESHOLD = 50
ROLL_WINDOW = 20
# M22 #9 codex MED: 单行 chunk 长度上限, 防宽表/超长单元格撑爆向量库
MAX_ROW_CHARS = 4000
CELL_TRUNCATE_HINT = " …(截断)"


def _make_chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}_t{idx:04d}"


def _normalize_headers(raw_headers: list) -> list[str]:
    """M22 #9 codex LOW: 表头规范化 — 空表头 fallback col_N, 重复列名加后缀。"""
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, h in enumerate(raw_headers):
        name = str(h).strip() if h is not None else ""
        if not name:
            name = f"col_{i}"
        # 重复列名加后缀: col, col, col → col, col_2, col_3
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def chunk_table(
    table: TableBlock,
    doc_id: str,
    idx_offset: int = 0,
    category_path: str = "",
    doc_type: str = "",
    source_system: str = "",
    updated_at: datetime | None = None,
    org_id: str = "default",
    domain_id: str = "",
    skip_empty_rows: bool = True,
    max_row_chars: int = MAX_ROW_CHARS,
) -> list[KnowledgeChunk]:
    """把 TableBlock 切成行级 KnowledgeChunk。

    Args:
        skip_empty_rows: M22 #9 codex LOW: 默认跳过全空数据行, 避免污染向量索引
        max_row_chars: M22 #9 codex MED: 单行 content 长度上限, 超长截断
    """
    if not table.rows:
        return []

    header_row = table.header_row if 0 <= table.header_row < len(table.rows) else 0
    headers = _normalize_headers(table.rows[header_row])

    chunks: list[KnowledgeChunk] = []
    cursor = idx_offset
    data_row_count = 0

    for ridx, row in enumerate(table.rows):
        if ridx == header_row:
            continue

        cells = [str(c) for c in row]

        # M22 #9 codex LOW: 全空数据行跳过
        if skip_empty_rows and not any(c.strip() for c in cells):
            continue

        parts = []
        for cidx, cell in enumerate(cells):
            col = headers[cidx] if cidx < len(headers) else f"col_{cidx}"
            if str(cell).strip():
                parts.append(f"{col}={cell}")

        prefix_parts = [f"[表格] {table.caption or '未命名表'}"]
        if table.page:
            prefix_parts.append(f"页 {table.page}")
        prefix_parts.append(f"第 {ridx} 行")

        if data_row_count > 0 and data_row_count % ROLL_WINDOW == 0 \
                and len(table.rows) > TABLE_ROLL_THRESHOLD:
            prefix_parts.append("列: " + " | ".join(headers))

        content = " · ".join(prefix_parts) + "\n" + " | ".join(parts)

        # M22 #9 codex MED: 长度截断
        if len(content) > max_row_chars:
            content = content[:max_row_chars] + CELL_TRUNCATE_HINT

        chunks.append(KnowledgeChunk(
            chunk_id=_make_chunk_id(doc_id, cursor),
            doc_id=doc_id,
            chunk_index=cursor,
            content=content,
            chunk_strategy=ChunkStrategy.TABLE_ROW.value,
            category_path=category_path,
            doc_type=doc_type,
            source_system=source_system,
            updated_at=updated_at,
            org_id=org_id,
            domain_id=domain_id,
        ))
        cursor += 1
        data_row_count += 1

    return chunks
