/**
 * 知识图鉴 Wiki-Map API 服务层
 *
 * 对接后端 /api/v1/knowledge/* 和 /api/v1/qa/* 端点
 * V11: 所有端点支持 projectId + 请求超时 + AbortSignal
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

/** 默认请求超时（毫秒） */
const DEFAULT_TIMEOUT = 30_000;

// ========== 通用请求 ==========

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  timeout = DEFAULT_TIMEOUT,
): Promise<T> {
  const controller = new AbortController();
  const existingSignal = options.signal;

  // 合并外部 signal 和超时 signal
  if (existingSignal) {
    existingSignal.addEventListener('abort', () => controller.abort());
  }
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    // GET 请求不发 Content-Type（避免不必要的 CORS preflight）
    const headers: Record<string, string> = { ...options.headers as Record<string, string> };
    if (options.body) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `请求失败: ${response.status}`);
    }
    // 204 No Content 或空响应
    if (response.status === 204) return {} as T;
    const text = await response.text();
    return text ? JSON.parse(text) : ({} as T);
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      if (existingSignal?.aborted) throw err; // 外部取消，直接传播
      throw new Error('请求超时，请稍后重试');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** 追加 project_id 到 URL query string */
function withProject(url: string, projectId?: string): string {
  if (!projectId) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}project_id=${encodeURIComponent(projectId)}`;
}

// ========== 类型定义 ==========

/** 知识库统计概览 */
export interface KnowledgeStats {
  /** 文档总数 */
  total_documents: number;
  /** 保留数 */
  kept: number;
  /** 归档数 */
  archived: number;
  /** 丢弃数 */
  discarded: number;
  /** 待审核数 */
  pending_review: number;
  /** 向量分块数 */
  vector_chunks: number;
  /** 知识领域数 */
  knowledge_domains: number;
  /** 文档卡片数 */
  doc_cards: number;
  /** 图谱节点数 */
  graph_nodes: number;
  /** 图谱边数 */
  graph_edges: number;
  /** 按文档类型分组计数 */
  by_doc_type: Record<string, number>;
  /** 按来源系统分组计数 */
  by_source_system: Record<string, number>;
}

/** 文档摘要信息（列表页展示用） */
export interface DocumentSummary {
  id: string;
  title: string;
  /** 文档类型（如 policy、report 等） */
  doc_type: string;
  /** 治理决策（KEEP / ARCHIVE / DISCARD） */
  decision: string;
  /** 文档状态（ACTIVE / PENDING_REVIEW / ARCHIVED / DISCARDED） */
  status: string;
  /** 保留指标得分，null 表示尚未评估 */
  kpi_retain: number | null;
  /** 来源系统标识 */
  source_system: string;
  summary: string;
  keywords: string[];
  /** 目录路径（如 "能源/发电/风电"） */
  category_path: string;
  created_at: string | null;
  updated_at: string | null;
}

/** 文档详情（在摘要基础上扩展审核推理、权限等字段） */
export interface DocumentDetail extends DocumentSummary {
  judge_reasoning: Record<string, unknown> | null;
  department_id: string;
  access_level: string;
  ingested_at: string | null;
  entities: string[];
  related_doc_ids: string[];
}

/** 分页文档列表响应 */
export interface PaginatedDocuments {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  documents: DocumentSummary[];
}

/** 目录树节点（递归结构） */
export interface CatalogNode {
  path: string;
  name: string;
  doc_count: number;
  children: CatalogNode[];
}

/** 知识领域信息 */
export interface DomainInfo {
  domain_id: string;
  name: string;
  parent_id: string | null;
  description: string;
  doc_count: number;
  is_system: boolean;
}

/** 领域列表响应（含 LLM 可读的目录文本） */
export interface DomainsResponse {
  total_domains: number;
  total_doc_cards: number;
  domains: DomainInfo[];
  catalog_text_for_llm: string;
}

/** 知识图谱节点 */
export interface GraphNode {
  id: string;
  type: string;
  label: string;
}

/** 知识图谱边（关系） */
export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

/** 图谱概览（节点、边及统计） */
export interface GraphOverview {
  node_count: number;
  edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  level?: string;
}

/** 搜索命中结果项 */
export interface SearchHit {
  doc_id: string;
  chunk_id: string;
  title: string;
  content: string;
  score: number;
  doc_type?: string;
  source_system?: string;
  category_path?: string;
}

/** 搜索响应（含命中列表和耗时） */
export interface SearchResponse {
  query: string;
  total_hits: number;
  results: SearchHit[];
  latency_ms: number;
}

/** 问答引用来源 */
export interface QASource {
  doc_id: string;
  title: string;
  content: string;
  score: number;
  source_system: string;
  category_path: string;
}

/** 问答响应（含生成的回答、引用来源和意图分类） */
export interface QAResponse {
  answer: string;
  sources: QASource[];
  intent_category?: string;
  route_path?: string;  // V11: "wiki" | "rag" | "hybrid"
  routed_domains?: string[];
  latency_ms?: number;
  query_id?: string;  // M12 #2 portal 反馈用
}

/** 数据导入结果（含采集、蒸馏、存储统计） */
export interface IngestDocResult {
  doc_id: string;
  title: string;
  decision: 'KEEP' | 'ARCHIVE' | 'DISCARD' | 'UNKNOWN';
  domain_id: string;
  category_path: string;       // M22 #12: LLM 推荐入库分支 (e.g. 制造/工艺/质量管理)
  summary: string;
  doc_type: string;
  entity_count: number;
  keyword_count: number;
  confidence: number;          // 0-1
  needs_review: boolean;
  reasoning: string;           // M22 #12: 6 维 Critic 反馈拼接的判定理由
}

export interface IngestResult {
  status: string;
  message?: string;
  total_collected?: number;
  total_uploaded?: number;
  parsed?: number;
  parse_errors?: string[];
  source_counts?: Record<string, number>;
  distillation?: {
    kept: number;
    archived: number;
    discarded: number;
    noise_filtered: number;
  };
  storage?: {
    documents?: number;
    documents_kept?: number;
    vector_chunks: number;
    wiki_pages?: number;
    knowledge_domains?: number;
    doc_cards?: number;
    graph_nodes?: number;
    graph_edges?: number;
  };
  documents?: IngestDocResult[];   // M22 #12: per-doc 详细结果 (LLM 决策 / 分类推荐 / 理由)
}

// ========== 知识库 API ==========

/**
 * 获取知识库统计数据
 * @param projectId - 可选项目 ID，不传则查全局
 */
export function fetchStats(projectId?: string): Promise<KnowledgeStats> {
  return request(withProject('/api/v1/knowledge/stats', projectId));
}

/**
 * 分页查询文档列表
 * @param params - 筛选与分页参数（状态、决策、文档类型、来源系统、页码等）
 */
export function fetchDocuments(params?: {
  status?: string;
  decision?: string;
  doc_type?: string;
  source_system?: string;
  page?: number;
  page_size?: number;
  projectId?: string;
}): Promise<PaginatedDocuments> {
  const qs = new URLSearchParams();
  if (params) {
    const { projectId, ...rest } = params;
    Object.entries(rest).forEach(([k, v]) => {
      if (v !== undefined) qs.set(k, String(v));
    });
    if (projectId) qs.set('project_id', projectId);
  }
  const suffix = qs.toString() ? `?${qs}` : '';
  return request(`/api/v1/knowledge/documents${suffix}`);
}

/**
 * 获取单个文档详情
 * @param docId - 文档唯一标识
 */
export function fetchDocument(docId: string, projectId?: string): Promise<DocumentDetail> {
  return request(withProject(`/api/v1/knowledge/documents/${encodeURIComponent(docId)}`, projectId));
}

/**
 * 向量搜索文档
 * @param q - 搜索查询文本
 * @param topK - 返回前 K 条结果，默认 10
 * @param projectId - 可选项目 ID
 */
export function searchDocs(q: string, topK = 10, projectId?: string): Promise<SearchResponse> {
  let url = `/api/v1/knowledge/search?q=${encodeURIComponent(q)}&top_k=${topK}`;
  if (projectId) url += `&project_id=${encodeURIComponent(projectId)}`;
  return request(url);
}

/** 获取知识目录树 */
export function fetchCatalog(projectId?: string): Promise<CatalogNode[]> {
  return request(withProject('/api/v1/knowledge/catalog', projectId));
}

/** 获取知识领域列表 */
export function fetchDomains(projectId?: string): Promise<DomainsResponse> {
  return request(withProject('/api/v1/knowledge/domains', projectId));
}

/**
 * 获取知识图谱概览
 * @param _level - 已弃用（V7 仅保留 Entity 层），保留以兼容旧调用
 * @param projectId - 可选项目 ID
 * @param domainId - 可选领域 ID，用于过滤特定领域的图谱
 */
export function fetchGraphOverview(_level?: string, projectId?: string, domainId?: string): Promise<GraphOverview> {
  // V7: level 参数不再需要（只有 Entity 层），保留参数兼容性
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (domainId) params.set('domain_id', domainId);
  const qs = params.toString();
  return request(`/api/v1/knowledge/graph-overview${qs ? '?' + qs : ''}`);
}

/**
 * 获取人工审核队列
 * @param status - 审核状态过滤，默认 'PENDING'
 */
/** 审核队列条目（与 DocumentSummary 字段不同） */
export interface ReviewQueueItem {
  doc_id: string;
  title?: string;
  proposed_decision: string;
  confidence: number;
  kpi_retain?: number;
  reason?: string;
  status: string;
}

export function fetchReviewQueue(status = 'PENDING', projectId?: string): Promise<ReviewQueueItem[]> {
  let url = `/api/v1/knowledge/review-queue?status=${status}`;
  if (projectId) url += `&project_id=${encodeURIComponent(projectId)}`;
  return request(url);
}

/**
 * 处理审核决策
 * @param docId - 文档 ID
 * @param decision - 最终决策（KEEP / ARCHIVE / DISCARD）
 * @param reviewer - 审核人，默认 'admin'
 */
export function resolveReview(docId: string, decision: string, reviewer = 'admin') {
  const params = new URLSearchParams({ final_decision: decision, reviewer });
  return request(`/api/v1/knowledge/review-queue/${encodeURIComponent(docId)}/resolve?${params}`, {
    method: 'POST',
  });
}

/** 获取归档文档列表 */
export function fetchArchive(): Promise<DocumentSummary[]> {
  return request('/api/v1/knowledge/archive');
}

/** 从归档中恢复文档 */
export function restoreArchive(docId: string) {
  return request(`/api/v1/knowledge/archive/${encodeURIComponent(docId)}/restore`, { method: 'POST' });
}

/**
 * 触发演示数据导入
 * @param projectId - 可选项目 ID
 * @param force - 是否强制重新导入（覆盖已有数据）
 */
export function ingestDemo(projectId?: string, force = false): Promise<IngestResult> {
  let url = `/api/v1/knowledge/ingest-demo?force=${force}`;
  if (projectId) url += `&project_id=${encodeURIComponent(projectId)}`;
  return request(url, { method: 'POST' });
}

/**
 * 上传文件并触发知识导入
 * @param files - 待上传的文件列表
 * @param projectId - 项目 ID，默认 'default'
 */
export async function ingestFiles(files: File[], projectId = 'default'): Promise<IngestResult> {
  const formData = new FormData();
  formData.append('project_id', projectId);
  for (const f of files) {
    formData.append('files', f);
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300_000); // 5min for large uploads
  try {
    const res = await fetch(`${API_BASE}/api/v1/knowledge/ingest`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `上传失败: ${res.status}`);
    }
    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

// ========== 问答 API ==========

/**
 * 提交问答请求（检索增强生成）
 * @param question - 用户提问文本
 * @param topK - 检索的参考文档数，默认 5
 * @param projectId - 可选项目 ID
 */
export function askQuestion(question: string, topK = 5, projectId?: string): Promise<QAResponse> {
  return request('/api/v1/qa/ask', {
    method: 'POST',
    body: JSON.stringify({ question, top_k: topK, project_id: projectId || 'default' }),
  });
}

// ========== 审计 API ==========

/**
 * 获取审计日志
 * @param limit - 返回条数上限，默认 100
 */
export function fetchAuditLogs(limit = 100) {
  return request<Record<string, unknown>[]>(`/api/v1/audit/logs?limit=${limit}`);
}

// ── V11.2: Wiki API (Karpathy三层Wiki体系) ──

export type WikiPageType = 'source_summary' | 'domain_overview' | 'index';

export interface WikiPageSummary {
  page_id: string;
  title: string;
  summary: string;
  page_type: WikiPageType;
  parent_page_id: string;
  source_doc_count: number;
  cross_ref_count: number;
  compiled_at: string | null;
  version: number;
  status: string;
}

export interface WikiPageDetail {
  page_id: string;
  title: string;
  content: string;
  summary: string;
  page_type: WikiPageType;
  parent_page_id: string;
  source_doc_ids: string[];
  cross_refs: string[];
  compiled_at: string | null;
  version: number;
  status: string;
}

export interface WikiStats {
  total_pages: number;
  published_pages: number;
  stale_pages: number;
  source_pages: number;
  domain_pages: number;
  index_pages: number;
  total_source_docs: number;
  domain_coverage: number;
}

export function fetchWikiPages(projectId?: string): Promise<WikiPageSummary[]> {
  return request(withProject('/api/v1/wiki/pages', projectId));
}

export function fetchWikiPage(pageId: string, projectId?: string): Promise<WikiPageDetail> {
  return request(withProject(`/api/v1/wiki/pages/${encodeURIComponent(pageId)}`, projectId));
}

export function fetchWikiStats(projectId?: string): Promise<WikiStats> {
  return request(withProject('/api/v1/wiki/stats', projectId));
}

/** V15 Phase G: 更新/新建 Wiki 页 (upsert 语义)。 */
export interface WikiPageUpdateBody {
  title: string;
  content: string;
  summary?: string;
  page_type?: string;
  parent_page_id?: string;
  source_doc_ids?: string[];
  cross_refs?: string[];
  status?: string;
  editor?: string;
}

export function updateWikiPage(
  pageId: string,
  body: WikiPageUpdateBody,
  projectId?: string,
): Promise<WikiPageDetail> {
  return request(withProject(`/api/v1/wiki/pages/${encodeURIComponent(pageId)}`, projectId), {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}
