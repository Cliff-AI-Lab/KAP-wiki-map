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
    """Judge Agent 的输出。

    M0-tech-debt 坑 3 改造新增追溯字段：

    - ``needs_review``：规则 R3 命中（KPI 居中 + 低置信度）→ 需 SME 复核
    - ``rule_hit``：决策命中的规则编号（R1/R2/R3/R4/R5），便于审计
    - ``decision_reason``：人类可读的决策理由
    - ``thresholds_source``：阈值来源（``yaml:templates/<industry>/judge-thresholds.yaml`` 等）
    """
    reasoning: JudgeReasoning = Field(default_factory=JudgeReasoning)
    decision: Decision = Decision.KEEP
    confidence: float = 0.5
    kpi_retain: float = 0.5
    summary: str = ""
    key_entities: list[str] = Field(default_factory=list)
    # ── 决策追溯字段（M0-tech-debt 坑 3）──
    needs_review: bool = False
    rule_hit: str = ""
    decision_reason: str = ""
    thresholds_source: str = ""


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

GovernanceAgent = Literal[
    "curator", "auditor", "deduper", "standardizer", "gardener",
    "distillation",  # M1 W4 写入侧：蒸馏管线低置信度产出
    "ontology_evolution",  # M3 #1：本体演化提议器
]
GovernanceKind = Literal[
    "draft_pending", "unverified", "conflict", "standardize_suggest", "archive_suggest",
    "low_confidence_extract",  # M1 W4：实体抽取低置信度待 SME 审核（决策书 §5.2 W4 必审）
    "ontology_proposal",        # M3 #1：本体演化提议（决策书 §5.3 D8）
]
# M1 矩阵审核台扩展：reviewing（已认领）/ escalated（D12 SLA 升级）
GovernanceStatus = Literal["pending", "reviewing", "approved", "rejected", "edited", "escalated"]
GovernanceDecision = Literal["approve", "reject", "edit"]

# M1 4×6 矩阵审核台（决策书 §5.2 D6 + §5.5 D12）
Workstation = Literal["W1", "W2", "W3", "W4", "W5", "W6"]
ReviewerRole = Literal["DG", "SME", "SEC", "AIOps"]
ReviewerInvolvement = Literal["R", "C", "I"]  # R 主审 / C 协审 / I 知会


# M2 #4 块① 知识咨询智能体（决策书 §4 / PRD §3）
ArchitectStage = Literal[
    "identify",   # 行业识别中（上传样本 → 推断行业）
    "propose",    # 主树提议中（基于行业模板 → LLM 修订）
    "refine",     # 客户对话调整中（add/remove/rename，M3 完整 CRUD）
    "export",     # 已导出（注册到 INDUSTRY_REGISTRY）
]


# M2 LLM-Critic 6 维质疑（决策书 §5.5 D13）
CriticDimension = Literal[
    "consistency",  # 一致性 — 实体定义/关系是否在不同文档中冲突
    "completeness", # 完整性 — 本体要求的必填属性是否覆盖
    "evidence",     # 证据强度 — 论断是否有原文充分支撑
    "duplication",  # 重复性 — 与图谱已有节点是否高度相似
    "timeliness",   # 时效性 — 引用标准/制度是否已作废
    "cross_domain", # 跨域 — 跨文档关联推断（最有价值）
]


class CriticFinding(BaseModel):
    """单维度质疑发现。"""
    dimension: CriticDimension
    severity: float = Field(default=0.5, ge=0.0, le=1.0)  # 0=无疑 / 1=重大问题
    finding: str = ""           # 具体问题描述
    evidence: str = ""          # 原文佐证（短句引用）
    suggestion: str = ""        # 处置建议


class CriticResult(BaseModel):
    """Critic Agent 完整产出（决策书 §5.5 6 维清单）。"""
    findings: list[CriticFinding] = Field(default_factory=list)
    overall_severity: float = Field(default=0.0, ge=0.0, le=1.0)  # 6 维 max
    summary: str = ""           # 一句话总结，写入审核台 description

    def has_blocking_issue(self, threshold: float = 0.6) -> bool:
        """是否存在阻断级问题（severity >= threshold 任一维）。"""
        return any(f.severity >= threshold for f in self.findings)


# M2 #4 块① 主树草稿 + 会话状态（PRD F1.2-F1.7）

class IndustryCandidate(BaseModel):
    """行业识别候选（top 3 用，PRD F1.2.5 置信度展示）。"""
    industry_code: str
    industry_name: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)


class TaxonomyDraft(BaseModel):
    """主树草稿（导出前的 IndustryTemplate 子集）。"""
    industry_code: str = ""           # manufacturing / energy 等
    industry_name: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    taxonomy: list = Field(default_factory=list)  # list[TaxonomyNode]，避免循环 import
    recognized_signals: list[str] = Field(default_factory=list)  # PRD F1.2.5 识别依据
    top_candidates: list[IndustryCandidate] = Field(default_factory=list)
    # M3 #3a Facet 提议器（PRD F1.4）：doc_type → FacetSchema dict
    facets: dict = Field(default_factory=dict)  # dict[str, FacetSchema]，导出时挂到 IndustryTemplate
    # M3 #3b 命名规范（PRD F1.5）
    naming_convention: dict = Field(default_factory=dict)  # NamingConvention dump，避免循环 import


class NamingField(BaseModel):
    """命名规范单字段（决策书 §4.4 拼接顺序）。"""
    key: str                              # 字段 key（hierarchy_code / domain_code / doc_type / title / version / access_level / owner / lifecycle）
    name: str                             # 中文显示
    required: bool = True
    placeholder: str = ""                 # 默认/示例值
    description: str = ""


class NamingConvention(BaseModel):
    """命名规范定义（PRD F1.5）。

    决策书 §4.4 默认模板：
        [层级编码]-[业务域代码]-[文档类型]-[标题]-[版本]-[密级]-[Owner]-[生命周期态]
    示例：KB-CS-SOP-投诉处理-v2.3-内部-客服部-生效中
    """
    industry_code: str = ""
    project_id: str = ""
    separator: str = "-"
    fields: list[NamingField] = Field(default_factory=list)
    example: str = ""                     # 拼接预览
    notes: str = ""

    def template_string(self) -> str:
        """返回模板拼接字符串，如 '[层级编码]-[业务域代码]-...'"""
        return self.separator.join(f"[{f.name}]" for f in self.fields)


class ArchitectSession(BaseModel):
    """块① 对话会话（M2 lite 内存存储；M3 落 PG）。"""
    session_id: str
    project_id: str
    stage: ArchitectStage = "identify"
    draft: TaxonomyDraft | None = None
    history: list[dict] = Field(default_factory=list)  # [{role, content, timestamp}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# M3 #1 双层本体（决策书 §5.3 D8/D9）

OntologyLayer = Literal["L1", "L2"]  # L1 平台预置（行业稳定）/ L2 客户私有可演化


class OntologyEntityType(BaseModel):
    """实体类型定义（如 "产品" / "工艺" / "缺陷"）。

    决策书 §5.3：L1 行业基础本体（制造业概念 / 能源 IEC CIM）+
    L2 客户专有的产品树/装置编码（LLM 提议 SME 审批）。
    """
    type_id: str                          # 英文 stable id (product / process / defect)
    type_name: str                        # 中文显示
    description: str = ""
    layer: OntologyLayer = "L2"
    parent_type_id: str = ""              # 类型继承（如 electric_equipment → equipment）
    required_properties: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)  # 典型实例（NER 关键词命中）


class OntologyRelationType(BaseModel):
    """关系类型定义（含定义域 + 值域约束）。"""
    type_id: str
    type_name: str
    description: str = ""
    layer: OntologyLayer = "L2"
    source_types: list[str] = Field(default_factory=list)  # 允许的源实体类型 ids
    target_types: list[str] = Field(default_factory=list)  # 允许的目标实体类型 ids
    examples: list[str] = Field(default_factory=list)


class OntologyVersion(BaseModel):
    """本体版本快照（决策书 §5.3 ont-v2.3.0 模式）。"""
    version: str                          # ont-v1.0.0 / ont-v1.1.0
    layer: OntologyLayer
    industry_code: str = ""               # L1 必填（manufacturing/energy）；L2 用 project_id 关联
    project_id: str = ""                  # L2 必填；L1 = "" 全局
    entity_types: list[OntologyEntityType] = Field(default_factory=list)
    relation_types: list[OntologyRelationType] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    created_by: str = ""                  # SME user_id（L1 = "system"）
    notes: str = ""

    def entity_type_ids(self) -> set[str]:
        return {e.type_id for e in self.entity_types}

    def relation_type_ids(self) -> set[str]:
        return {r.type_id for r in self.relation_types}


class OntologyDiff(BaseModel):
    """两版本之间的差异（用于演化审计 + 灰度切换 M4 用）。"""
    from_version: str
    to_version: str
    added_entity_types: list[str] = Field(default_factory=list)
    removed_entity_types: list[str] = Field(default_factory=list)
    modified_entity_types: list[str] = Field(default_factory=list)
    added_relation_types: list[str] = Field(default_factory=list)
    removed_relation_types: list[str] = Field(default_factory=list)
    modified_relation_types: list[str] = Field(default_factory=list)


# M3 #4 W4 实体抽取（决策书 §5.2 W4 工位 SME 必审）

class ExtractedEntity(BaseModel):
    """W4 实体抽取产出。"""
    entity_id: str                    # doc_id+name 哈希或自定义稳定 id
    name: str                         # 实体名（如 "汽轮机1#"）
    type_id: str                      # 关联 OntologyEntityType.type_id
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_sensitive: bool = False        # 决策书 §5.4 敏感实体标记
    properties: dict = Field(default_factory=dict)
    evidence: str = ""                # 原文佐证片段


class ExtractedRelation(BaseModel):
    """W4 关系抽取产出。"""
    source_entity_id: str
    target_entity_id: str
    relation_type_id: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str = ""


class ExtractionResult(BaseModel):
    """单文档完整抽取产出（W4 工位）。"""
    doc_id: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sensitive_entity_count: int = 0
    error: str = ""


class OntologyEvolutionProposal(BaseModel):
    """本体演化提议（决策书 §5.3 LLM 提议 + SME 审批）。"""
    proposal_id: str
    project_id: str
    layer: OntologyLayer = "L2"           # 通常 L2（L1 由平台维护）
    proposed_entity_type: OntologyEntityType | None = None
    proposed_relation_type: OntologyRelationType | None = None
    evidence_count: int = 0               # 触发条件证据数（如未匹配实体数量）
    sample_entities: list[str] = Field(default_factory=list)
    reasoning: str = ""                   # LLM 给的理由
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    resolver: str = ""
    resolved_at: datetime | None = None


class GovernanceQueueItem(BaseModel):
    """治理工单 — V15 4 Agent 产出 + M1 矩阵审核台扩展。

    V15 字段维持兼容（agent / kind / status 旧值不破坏）。
    M1 新增 8 个可选字段承接 4×6 矩阵 + D12 SLA 升级语义；
    旧调用方零改造，新调用方按需填充。
    """
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

    # M1 矩阵审核台扩展（决策书 §5.2 ReviewTask 模型最小子集）
    workstation: Optional[Workstation] = None       # 所属工位 W1-W6
    assigned_role: Optional[ReviewerRole] = None    # 当前主审角色
    claimed_by: Optional[str] = None                # 认领人 user_id
    claimed_at: Optional[datetime] = None
    escalated_to: Optional[ReviewerRole] = None     # 升级目标角色（D12）
    escalation_reason: str = ""
    sla_due_at: Optional[datetime] = None           # 截止时刻；超时由 sweep_overdue_tasks 升级
    confidence: Optional[float] = None              # LLM Critic 置信度 0-1（决定是否入审核台）
