"""知识管理 API 请求/响应模型。"""

from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field


# ── 响应模型 ──────────────────────────────────────────


class KnowledgeStats(BaseModel):
    """知识库统计信息。"""

    total_documents: int = 0
    kept: int = 0
    archived: int = 0
    discarded: int = 0
    pending_review: int = 0
    vector_chunks: int = 0
    knowledge_domains: int = 0
    doc_cards: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    by_doc_type: dict[str, int] = Field(default_factory=dict)
    by_source_system: dict[str, int] = Field(default_factory=dict)


class DocumentSummary(BaseModel):
    """文档摘要（列表用）。"""

    id: str
    title: str = ""
    doc_type: str = ""
    decision: str = ""
    status: str = ""
    kpi_retain: Optional[float] = None
    source_system: str = ""
    summary: str = ""
    category_path: str = ""
    keywords: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PaginatedDocuments(BaseModel):
    """分页文档列表。"""

    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 1
    documents: list[DocumentSummary] = Field(default_factory=list)

    @staticmethod
    def build(
        docs: list[DocumentSummary],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedDocuments":
        return PaginatedDocuments(
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
            documents=docs,
        )


class DocumentDetail(BaseModel):
    """文档详情（含实体和关联文档）。"""

    id: str
    title: str = ""
    doc_type: str = ""
    decision: str = ""
    status: str = ""
    kpi_retain: Optional[float] = None
    source_system: str = ""
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    judge_reasoning: Optional[dict] = None
    department_id: str = ""
    access_level: str = "INTERNAL"
    category_path: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    ingested_at: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    related_doc_ids: list[str] = Field(default_factory=list)


class CatalogNode(BaseModel):
    """知识目录树节点。"""

    path: str
    name: str
    doc_count: int = 0
    children: list["CatalogNode"] = Field(default_factory=list)


class SearchHit(BaseModel):
    """搜索结果条目。"""

    doc_id: str
    chunk_id: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    doc_type: str = ""
    source_system: str = ""
    category_path: str = ""


class SearchResponse(BaseModel):
    """搜索响应。"""

    query: str
    total_hits: int = 0
    results: list[SearchHit] = Field(default_factory=list)
    latency_ms: int = 0


# ── M22 #4 · ISS 解析结果 bypass 入口 ──


# 合法 content_type 与 ChunkStrategy 一一对应
_ALLOWED_CONTENT_TYPES = {
    "text",           # 普通文本 chunk（fixed / parent_child / semantic 都映射这里）
    "table_row",      # 表格行级 chunk（M22 #2）
    "equation",       # 公式 chunk（M22 #2）
    "image_caption",  # 图像 caption chunk（M22 #2）
}


class StructuredChunkInput(BaseModel):
    """外部已解析的单个 chunk。"""

    content: str = Field(..., min_length=1, max_length=20000)
    content_type: str = Field(
        default="text",
        description=f"chunk 类型: {' / '.join(sorted(_ALLOWED_CONTENT_TYPES))}",
    )
    # 可选属性，写进 KnowledgeChunk 同名字段
    category_path: str = ""
    domain_id: str = ""


class StructuredChunksRequest(BaseModel):
    """M22 #4 bypass 入口请求 — 跳过 KAP 自有解析器, 直接吃外部送来的结构化 chunks。

    适用场景:
    1. 客户用商用 OCR / 解析平台（ABBYY / TextIn / MinerU 自部署）
    2. ISS-Knowledge-Parser 已有产物复用, 避免重复解析
    3. 单元测试 / 调试时跳过解析直接喂语料

    本端点 **不走** distillation pipeline / 4×6 矩阵审核台 — 信任外部解析结果。
    实体抽取 + 图谱入库留给 W6 后置异步任务（M22 #5 relation_extractor 完成后接通）。
    """

    doc_id: str = Field(..., min_length=1, max_length=128)
    doc_title: str = ""
    project_id: str = Field(default="default")
    parser_name: str = Field(..., min_length=1, max_length=128,
                             description="外部解析器名 + 版本, 用于审计追溯")
    source_system: str = Field(default="external")
    doc_type: str = ""
    category_path: str = ""
    domain_id: str = ""
    access_level: str = "INTERNAL"
    chunks: list[StructuredChunkInput] = Field(..., min_length=1, max_length=2000)


class StructuredChunksResponse(BaseModel):
    """bypass 入口响应。"""

    status: str = "ok"
    doc_id: str
    chunks_stored: int = 0
    parser_name: str = ""
    audit_logged: bool = False
