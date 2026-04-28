/**
 * 前端类型定义 - 镜像后端 Pydantic Schema
 *
 * 本文件定义了前后端共享的数据结构，与后端 schemas 保持一致。
 * 当后端 Schema 变更时应同步更新此文件。
 *
 * 主要类型：
 * - KnowledgeStats: 知识库统计
 * - DocumentSummary / DocumentDetail: 文档摘要与详情
 * - CatalogNode: 目录树节点
 * - SearchHit / SearchResponse: 搜索结果
 * - AskRequest / AskResponse: 问答请求与响应
 */

/** 知识库统计概览 */
export interface KnowledgeStats {
  total_documents: number;
  kept: number;
  archived: number;
  discarded: number;
  pending_review: number;
  /** 向量分块数 */
  vector_chunks: number;
  /** 图谱节点数 */
  graph_nodes: number;
  /** 图谱边数 */
  graph_edges: number;
  /** 按文档类型分组计数 */
  by_doc_type: Record<string, number>;
  /** 按来源系统分组计数 */
  by_source_system: Record<string, number>;
}

/** 文档摘要信息 */
export interface DocumentSummary {
  id: string;
  title: string;
  doc_type: string;
  /** 治理决策（KEEP / ARCHIVE / DISCARD） */
  decision: string;
  /** 文档状态（ACTIVE / PENDING_REVIEW / ARCHIVED / DISCARDED） */
  status: string;
  /** 保留指标得分 */
  kpi_retain: number | null;
  source_system: string;
  summary: string;
  /** 目录路径 */
  category_path: string;
  keywords: string[];
  created_at: string | null;
  updated_at: string | null;
}

/** 分页文档列表 */
export interface PaginatedDocuments {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  documents: DocumentSummary[];
}

/** 文档详情（含审核推理、权限、关联实体等） */
export interface DocumentDetail {
  id: string;
  title: string;
  doc_type: string;
  decision: string;
  status: string;
  kpi_retain: number | null;
  source_system: string;
  summary: string;
  keywords: string[];
  judge_reasoning: JudgeReasoning | null;
  department_id: string;
  access_level: string;
  category_path: string;
  created_at: string | null;
  updated_at: string | null;
  ingested_at: string | null;
  entities: string[];
  related_doc_ids: string[];
}

/** 裁判推理结构（AI 自动评估各维度得分与分析） */
export interface JudgeReasoning {
  recency_analysis?: string;
  recency_score?: number;
  density_analysis?: string;
  density_score?: number;
  completeness_analysis?: string;
  completeness_score?: number;
  redundancy_analysis?: string;
  redundancy_score?: number;
}

/** 目录树节点 */
export interface CatalogNode {
  path: string;
  name: string;
  doc_count: number;
  children: CatalogNode[];
}

/** 搜索命中项 */
export interface SearchHit {
  doc_id: string;
  chunk_id: string;
  title: string;
  content: string;
  score: number;
  doc_type: string;
  source_system: string;
  category_path: string;
}

/** 搜索响应 */
export interface SearchResponse {
  query: string;
  total_hits: number;
  results: SearchHit[];
  latency_ms: number;
}

/** 问答引用来源项（含多路得分） */
export interface SourceItem {
  doc_id: string;
  title: string;
  content: string;
  score: number;
  vector_score: number;
  graph_score: number;
  catalog_weight: number;
  source_system: string;
  category_path: string;
}

/** 问答请求体 */
export interface AskRequest {
  question: string;
  top_k?: number;
  target_category?: string | null;
}

/** 问答响应体 */
export interface AskResponse {
  answer: string;
  sources: SourceItem[];
  intent_category: string;
  latency_ms: number;
}
