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


def _make_chunk_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}_t{idx:04d}"


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
) -> list[KnowledgeChunk]:
    """把 TableBlock 切成行级 KnowledgeChunk。"""
    if not table.rows:
        return []

    header_row = table.header_row if 0 <= table.header_row < len(table.rows) else 0
    headers = [str(c) for c in table.rows[header_row]]

    chunks: list[KnowledgeChunk] = []
    cursor = idx_offset
    data_row_count = 0  # 已写入的数据行计数, 用于滚动窗口

    for ridx, row in enumerate(table.rows):
        if ridx == header_row:
            continue

        cells = [str(c) for c in row]
        parts = []
        for cidx, cell in enumerate(cells):
            col = headers[cidx] if cidx < len(headers) else f"col_{cidx}"
            if str(cell).strip():
                parts.append(f"{col}={cell}")

        prefix_parts = [f"[表格] {table.caption or '未命名表'}"]
        if table.page:
            prefix_parts.append(f"页 {table.page}")
        prefix_parts.append(f"第 {ridx} 行")

        # 大表滚动窗口：每 ROLL_WINDOW 行带回表头摘要, 避免长表召回时列名漂移
        if data_row_count > 0 and data_row_count % ROLL_WINDOW == 0 \
                and len(table.rows) > TABLE_ROLL_THRESHOLD:
            prefix_parts.append("列: " + " | ".join(headers))

        content = " · ".join(prefix_parts) + "\n" + " | ".join(parts)

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
