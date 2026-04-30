"""
问答 API 请求/响应模型模块。

定义智能问答接口的 Pydantic 数据模型，包括：
- AskRequest: 用户提问请求
- SourceItem: 单条来源文档信息（含多维度评分）
- AskResponse: 问答响应（答案 + 来源列表 + 元信息）
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """智能问答请求模型。"""
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20)                     # 返回来源文档数量上限
    target_category: Optional[str] = Field(default=None, description="限定知识目录")  # 限定检索范围的目录路径
    project_id: str = Field(default="default", description="项目ID")  # 多项目隔离标识


class SourceItem(BaseModel):
    """来源文档项，包含文档信息和多维度检索评分。

    评分维度说明：
    - score: 综合最终得分（加权融合后的结果）
    - vector_score: 向量相似度得分（语义匹配）
    - graph_score: 图谱关联得分（实体关系匹配）
    - catalog_weight: 目录权重得分（知识分类相关性）
    - keyword_score: 关键词匹配得分
    """
    doc_id: str                    # 文档唯一标识
    title: str = ""                # 文档标题
    content: str = ""              # 匹配内容片段（已截断）
    score: float = 0.0             # 综合最终得分
    vector_score: float = 0.0      # 向量相似度得分
    graph_score: float = 0.0       # 图谱关联得分
    catalog_weight: float = 0.0    # 目录权重得分
    keyword_score: float = 0.0     # 关键词匹配得分
    source_system: str = ""        # 来源系统标识
    category_path: str = ""        # 所属知识目录路径


class AskResponse(BaseModel):
    """智能问答响应模型。"""
    answer: str                                # LLM 生成的回答
    sources: list[SourceItem] = []             # 参考来源文档列表
    intent_category: str = ""                  # 识别到的用户意图分类
    latency_ms: int = 0                        # 端到端处理耗时（毫秒）
    query_id: str = ""                         # M12 #2 portal 反馈用，关联 query_log
