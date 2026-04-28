"""全局共享数据模型。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── 枚举 ─────────────────────────────────────────────

class SourceSystem(str, Enum):
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECOM = "wecom"
    OA = "oa"
    LOCAL = "local"


class DocType(str, Enum):
    REGULATION = "规章制度"
    MEETING_NOTES = "会议纪要"
    TECH_DOC = "技术文档"
    PROCESS = "流程说明"
    TRAINING = "培训材料"
    NOTICE = "通知公告"
    CHAT_RECORD = "聊天记录"
    OTHER = "其他"


class Decision(str, Enum):
    KEEP = "KEEP"
    ARCHIVE = "ARCHIVE"
    DISCARD = "DISCARD"


class DocStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DISCARDED = "DISCARDED"
    PENDING_REVIEW = "PENDING_REVIEW"


class AccessLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"


class EstimatedValue(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ChunkStrategy(str, Enum):
    FIXED = "fixed"
    PARENT_CHILD = "parent_child"
    SEMANTIC = "semantic"


# ── 数据模型 ──────────────────────────────────────────

class Attachment(BaseModel):
    """文档附件（图片/PDF/视频等）。"""
    file_url: str = ""
    mime_type: str = "application/octet-stream"
    file_name: str = ""
    file_size: int = 0


class RawDocument(BaseModel):
    """从连接器采集到的原始文档。"""
    doc_id: str
    title: str
    content: str
    source_system: SourceSystem
    source_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: str = ""
    last_modifier: str = ""
    file_size: int = 0
    metadata: dict = Field(default_factory=dict)
    org_id: str = "default"
    content_type: str = "text/plain"
    attachments: list[Attachment] = Field(default_factory=list)


class MentionedEntity(BaseModel):
    name: str
    type: str  # V8: 人物, 部门, 设备装置, 制度法规, 流程工艺, 物料化学品, 标准规范, 位置区域 (兼容旧类型)


class LibrarianResult(BaseModel):
    """Librarian Agent 的输出。"""
    doc_type: DocType = DocType.OTHER
    version_id: Optional[str] = None
    key_topics: list[str] = Field(default_factory=list)
    mentioned_entities: list[MentionedEntity] = Field(default_factory=list)
    is_conversational: bool = False
    estimated_value: EstimatedValue = EstimatedValue.MEDIUM


class OverlapGroup(BaseModel):
    doc_ids: list[str]
    overlap_type: str  # 完全重复, 部分重复, 版本迭代, 内容矛盾
    description: str
    recommended_primary: Optional[str] = None


class ConflictItem(BaseModel):
    doc_a_id: str
    doc_b_id: str
    conflict_point: str
    severity: str = "MEDIUM"  # HIGH, MEDIUM, LOW


class AuditResult(BaseModel):
    """Conflict Auditor Agent 的输出。"""
    overlap_groups: list[OverlapGroup] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    summary: str = ""
    max_overlap_score: float = 0.0


class JudgeReasoning(BaseModel):
    recency_analysis: str = ""
    recency_score: float = 5.0
    density_analysis: str = ""
    density_score: float = 5.0
    completeness_analysis: str = ""
    completeness_score: float = 5.0
    redundancy_analysis: str = ""
    redundancy_score: float = 5.0


class JudgeResult(BaseModel):
    """Judge Agent 的输出。"""
    reasoning: JudgeReasoning = Field(default_factory=JudgeReasoning)
    decision: Decision = Decision.KEEP
    confidence: float = 0.5
    kpi_retain: float = 0.5
    summary: str = ""
    key_entities: list[str] = Field(default_factory=list)


class EntityRelation(BaseModel):
    source: str
    relation: str
    target: str


class CatalogSection(BaseModel):
    """文档目录条目 — 每个章节的索引卡。"""
    level: int = 1                          # 目录层级 1/2/3
    title: str = ""                         # 章节标题
    brief: str = ""                         # 一句话描述（关键信息）
    key_terms: list[str] = Field(default_factory=list)  # 该节关键词


class RefinedResult(BaseModel):
    """Refiner Agent 的输出。"""
    summary: str = ""
    catalog: list[CatalogSection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    entities: list[MentionedEntity] = Field(default_factory=list)
    relations: list[EntityRelation] = Field(default_factory=list)
    index_text: str = ""                    # 融合摘要+目录+关键词的索引全文
    domain_id: str = ""                     # 匹配的知识域 ID
    doc_description: str = ""               # 给 LLM 读的文档描述
    key_elements: list[str] = Field(default_factory=list)  # 关键要素


class WikiPage(BaseModel):
    """Wiki 知识页 — Karpathy LLM Wiki 多层编译产物（V11.2 知识图鉴）。

    三层 Wiki 体系:
    - index:          项目级索引页（全局目录 + 域列表 + 交叉引用图）
    - domain_overview: 域级概览页（聚合该域下所有 source 页的编译综述）
    - source_summary:  源文档页（每篇文档的独立知识 Wiki 页）
    """
    page_id: str                                    # 唯一ID: "index" / domain_id / "src/{doc_id}"
    title: str = ""
    content: str = ""                               # Markdown 正文
    summary: str = ""                               # 200字摘要
    page_type: str = "domain_overview"              # index / domain_overview / source_summary
    parent_page_id: str = ""                        # 层级: source→domain, domain→index
    source_doc_ids: list[str] = Field(default_factory=list)  # 溯源文档ID
    cross_refs: list[str] = Field(default_factory=list)      # 交叉引用 page_id
    compiled_at: Optional[datetime] = None
    version: int = 1
    status: str = "published"                       # published / stale / draft


class RouteDecision(BaseModel):
    """双路径查询路由决策（V11 知识图鉴）。"""
    path: str = "rag"                               # "wiki" | "rag" | "hybrid"
    wiki_page_id: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""


class DocumentIndex(BaseModel):
    """文档索引卡 — 用于第一阶段粗检索。"""
    doc_id: str
    title: str = ""
    summary: str = ""
    catalog: list[CatalogSection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    doc_type: str = ""
    category_path: str = ""
    org_id: str = "default"
    index_text: str = ""                    # 拼接后的索引全文（用于向量化）
    embedding: list[float] = Field(default_factory=list)


class KnowledgeDomain(BaseModel):
    """知识域 — 知识体系的一个分类节点（类似 Skills 的 Skill 定义）。"""
    domain_id: str              # 如 "regulation/finance"
    name: str                   # 如 "财务管理"
    parent_id: str = ""         # 父域 ID（空=一级域）
    description: str = ""       # 给 LLM 读的描述（50-200字）
    doc_count: int = 0
    is_system: bool = True      # True=基础框架, False=LLM 扩展的


class DocumentCard(BaseModel):
    """文档索引卡 — 每份文档的描述（给 LLM 路由时读的）。"""
    doc_id: str
    title: str = ""
    domain_id: str = ""         # 所属知识域
    description: str = ""       # 给 LLM 读的文档描述（100-300字）
    key_elements: list[str] = Field(default_factory=list)   # 关键要素
    keywords: list[str] = Field(default_factory=list)


class KnowledgeChunk(BaseModel):
    """入库的知识切片。"""
    chunk_id: str
    doc_id: str
    chunk_index: int
    content: str
    embedding: list[float] = Field(default_factory=list)
    category_path: str = ""
    domain_id: str = ""         # 所属知识域（用于 Skills 模式过滤）
    doc_type: str = ""
    source_system: str = ""
    department_id: str = ""
    access_level: str = "INTERNAL"
    updated_at: Optional[datetime] = None
    parent_chunk_id: Optional[str] = None
    chunk_strategy: str = "fixed"
    is_parent: bool = False
    org_id: str = "default"


class SearchResult(BaseModel):
    """单条检索结果。"""
    doc_id: str
    chunk_id: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    vector_score: float = 0.0
    graph_score: float = 0.0
    catalog_weight: float = 0.0
    keyword_score: float = 0.0
    doc_type: str = ""
    source_system: str = ""
    category_path: str = ""
    domain_id: str = ""
    updated_at: Optional[datetime] = None
    org_id: str = "default"


class QAResponse(BaseModel):
    """问答 API 的返回。"""
    answer: str
    sources: list[SearchResult] = Field(default_factory=list)
    intent_category: str = ""
    routed_domains: list[str] = Field(default_factory=list)  # LLM 路由选择的知识域
    route_path: str = "rag"  # V11: "wiki" | "rag" | "hybrid" — 双引擎路径标识
    latency_ms: int = 0


# === V15 Phase C: 治理工单 ===

from typing import Literal

GovernanceAgent = Literal["curator", "auditor", "deduper", "standardizer", "gardener"]
GovernanceKind = Literal["draft_pending", "unverified", "conflict", "standardize_suggest", "archive_suggest"]
GovernanceStatus = Literal["pending", "approved", "rejected", "edited"]
GovernanceDecision = Literal["approve", "reject", "edit"]


class GovernanceQueueItem(BaseModel):
    """治理工单 — 四 Agent 产出的待人工决策事项。"""
    id: str
    project_id: str
    agent: GovernanceAgent
    kind: GovernanceKind
    title: str = Field(max_length=120)
    description: str = ""
    target_ref: str = ""      # 关联 wiki_page_id 或 raw_id
    priority: int = 50         # 0-100
    status: GovernanceStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    resolved_at: Optional[datetime] = None
    resolver: Optional[str] = None
