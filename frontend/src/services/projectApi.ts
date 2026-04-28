/**
 * 项目管理 API
 *
 * 本模块封装项目生命周期管理相关接口：
 * - 行业模板查询（含分类体系 taxonomy）
 * - 项目 CRUD（创建、列表、详情）
 *
 * 对接后端 /api/v1/projects/* 端点
 */

/** API 基础路径 */
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

/**
 * 通用 HTTP 请求封装（与 api.ts 独立，避免循环依赖）
 * @param endpoint - API 端点路径
 * @param options - fetch 配置项
 */
async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `请求失败: ${response.status}`);
  }
  return response.json();
}

// ========== 类型定义 ==========

/** 行业选项（行业选择列表用） */
export interface IndustryItem {
  code: string;
  name: string;
  name_en: string;
  icon: string;
  description: string;
  department_count: number;
  domain_count: number;
}

/** 分类体系树节点（行业模板中的层级分类） */
export interface TaxonomyNode {
  id: string;
  name: string;
  level: number;
  description: string;
  children: TaxonomyNode[];
}

/** 行业模板（含完整分类体系） */
export interface IndustryTemplate {
  code: string;
  name: string;
  name_en: string;
  icon: string;
  description: string;
  taxonomy: TaxonomyNode[];
}

/** 创建项目请求体 */
export interface ProjectCreateRequest {
  name: string;
  industry_code: string;
  description?: string;
}

/** 项目摘要信息（列表页展示用） */
export interface ProjectSummary {
  id: string;
  name: string;
  industry_code: string;
  industry_name: string;
  description: string;
  status: string;
  doc_count: number;
  domain_count: number;
  created_at: string | null;
}

/** 项目详情（在摘要基础上扩展分类体系快照） */
export interface ProjectDetail extends ProjectSummary {
  taxonomy_snapshot: TaxonomyNode[] | null;
  updated_at: string | null;
}

// ========== API 函数 ==========

/** 获取所有可用行业列表 */
export function fetchIndustries(): Promise<IndustryItem[]> {
  return request('/api/v1/projects/industries');
}

/**
 * 获取指定行业的模板详情（含分类体系）
 * @param code - 行业代码
 */
export function fetchIndustryTemplate(code: string): Promise<IndustryTemplate> {
  return request(`/api/v1/projects/industries/${encodeURIComponent(code)}/template`);
}

/**
 * 创建新项目
 * @param data - 项目名称、行业代码、描述
 */
export function createProject(data: ProjectCreateRequest): Promise<ProjectSummary> {
  return request('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** 获取所有项目列表 */
export function fetchProjects(): Promise<ProjectSummary[]> {
  return request('/api/v1/projects');
}

/**
 * 获取项目详情
 * @param id - 项目唯一标识
 */
export function fetchProject(id: string): Promise<ProjectDetail> {
  return request(`/api/v1/projects/${encodeURIComponent(id)}`);
}
