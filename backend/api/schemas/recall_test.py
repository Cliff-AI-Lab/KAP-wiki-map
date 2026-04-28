"""召回测试 API 请求/响应模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RecallTestRequest(BaseModel):
    """召回测试请求。"""
    query: str = Field(..., min_length=1, max_length=2000, description="测试查询")
    top_k: int = Field(default=10, ge=1, le=100)

    # 范围过滤
    scope: str = Field(default="all", description="检索范围: all, folder, doc")
    scope_value: str = Field(default="", description="范围值: folder path 或 doc_id")

    # 检索模式
    mode: str = Field(default="hybrid", description="检索模式: similarity, keyword, hybrid")

    # 参数覆盖（None = 使用全局默认值）
    alpha: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="向量权重覆盖")
    beta: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="图谱权重覆盖")
    gamma: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="目录权重覆盖")
    delta: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="关键词权重覆盖")
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="最低分数阈值")

    # Reranker 控制
    use_reranker: bool = Field(default=True, description="是否使用重排序")

    # 期望结果（用于评估指标计算）
    expected_doc_ids: list[str] = Field(default_factory=list, description="期望召回的文档ID列表")


class ScoreBreakdown(BaseModel):
    """单条召回结果的详细评分拆解。"""
    chunk_id: str
    doc_id: str
    title: str = ""
    content: str = ""
    final_score: float = 0.0
    vector_score: float = 0.0
    graph_score: float = 0.0
    catalog_weight: float = 0.0
    keyword_score: float = 0.0
    category_path: str = ""
    chunk_strategy: str = ""
    is_parent: bool = False
    parent_chunk_id: Optional[str] = None


class RecallTestResponse(BaseModel):
    """召回测试响应。"""
    query: str
    mode: str
    scope: str
    total_hits: int = 0
    results: list[ScoreBreakdown] = Field(default_factory=list)
    latency_ms: int = 0

    # 实际使用的权重值
    effective_weights: dict[str, float] = Field(default_factory=dict)

    # 评估指标（仅在提供 expected_doc_ids 时计算）
    recall_at_k: Optional[float] = None
    precision_at_k: Optional[float] = None
    mrr: Optional[float] = None
    hit_expected: list[str] = Field(default_factory=list)
    missed_expected: list[str] = Field(default_factory=list)
