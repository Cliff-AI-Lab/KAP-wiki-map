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
