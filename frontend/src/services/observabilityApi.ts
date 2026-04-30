/**
 * observabilityApi.ts — 运营观察 API 封装（M10 #3）
 *
 * 对应后端 api/routers/observability.py 的全部端点：
 *   GET  /api/v1/observability/dashboard          综合仪表盘（一次拉全）
 *   GET  /api/v1/observability/decisions          决策事件列表
 *   GET  /api/v1/observability/decisions/aggregate
 *   GET  /api/v1/observability/queries            查询事件列表
 *   GET  /api/v1/observability/queries/aggregate
 *   GET  /api/v1/observability/recall-eval/trend
 *   GET  /api/v1/observability/recall-eval/latest
 *   GET  /api/v1/observability/condition-health
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(
  endpoint: string, init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(`${API_BASE}${endpoint}`, { ...init, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `请求失败: ${res.status}`);
  }
  if (res.status === 204) return {} as T;
  const text = await res.text();
  return text ? JSON.parse(text) : ({} as T);
}

// ════════════════════════════════════════════════════════════════════════
//  类型定义
// ════════════════════════════════════════════════════════════════════════

/** 决策事件聚合 */
export interface DecisionsAggregate {
  total: number;
  by_type: Record<string, number>;
  approval_rate: number;
  promote_rollback_ratio: number;
  window: {
    since: string | null;
    until: string | null;
    project_id: string | null;
  };
}

/** 查询事件聚合 */
export interface QueriesAggregate {
  total: number;
  hits: number;
  hit_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  feedback_total: number;
  useful_count: number;
  useful_rate: number;
  feedback_coverage: number;
  window: {
    since: string | null;
    until: string | null;
    project_id: string | null;
  };
}

/** 观察期摘要（dashboard 用） */
export interface ObservationSummary {
  observation_id: string;
  project_id: string;
  version: string;
  status: 'watching' | 'alert' | 'expired' | 'rolled_back';
  alerts_count: number;
  snapshots_count: number;
  promoted_at: string;
  expires_at: string;
}

/** 召回评估摘要 */
export interface RecallEvalLatest {
  report_id: string;
  version: string;
  k: number;
  total_queries: number;
  avg_recall: number;
  avg_precision: number;
  avg_f1: number;
  created_at: string;
}

/** Dashboard 响应 */
export interface Dashboard {
  window: {
    since: string | null;
    until: string | null;
    project_id: string | null;
  };
  decisions: DecisionsAggregate;
  queries: QueriesAggregate;
  observations: {
    total: number;
    active: number;
    alerting: number;
    items: ObservationSummary[];
  };
  recall_eval: {
    ground_truth_count: number;
    latest: RecallEvalLatest | null;
  };
}

/** 召回率趋势 */
export interface RecallTrend {
  samples: number;
  baseline: {
    report_id: string;
    avg_recall: number;
    avg_precision: number;
    avg_f1: number;
    created_at: string;
  } | null;
  current: {
    report_id: string;
    avg_recall: number;
    avg_precision: number;
    avg_f1: number;
    created_at: string;
  } | null;
  recall_delta: number;
  precision_delta: number;
  f1_delta: number;
  recall_alert: boolean;
  precision_alert: boolean;
  alert_messages: string[];
}

/** 监测条件健康度 */
export interface ConditionHealth {
  condition_type: string;
  total: number;
  approved: number;
  rejected: number;
  pending: number;
  approve_rate: number;
  common_reject_reasons: string[];
  tuning_suggestion: string;
}

// ════════════════════════════════════════════════════════════════════════
//  API
// ════════════════════════════════════════════════════════════════════════

function buildQuery(params: Record<string, string | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') qs.set(k, v);
  }
  return qs.toString() ? `?${qs}` : '';
}

export function fetchDashboard(projectId?: string): Promise<Dashboard> {
  const qs = buildQuery({ project_id: projectId });
  return request(`/api/v1/observability/dashboard${qs}`);
}

export function fetchRecallTrend(
  projectId?: string, lookback = 10,
): Promise<RecallTrend> {
  const qs = buildQuery({
    project_id: projectId, lookback: String(lookback),
  });
  return request(`/api/v1/observability/recall-eval/trend${qs}`);
}

export function fetchConditionHealth(
  projectId?: string,
): Promise<Record<string, ConditionHealth>> {
  const qs = buildQuery({ project_id: projectId });
  return request(`/api/v1/observability/condition-health${qs}`);
}

// ════════════════════════════════════════════════════════════════════════
//  M10 #1 + M11 #1 · ground truth 自动构造
// ════════════════════════════════════════════════════════════════════════

export interface GroundTruthCandidate {
  candidate_id: string;
  project_id: string;
  query_text: string;
  proposed_doc_ids: string[];
  sample_size: number;
  useful_rate: number;
  reasoning: string;
}

export interface GroundTruthQuery {
  gt_id: string;
  project_id: string;
  query_text: string;
  expected_doc_ids: string[];
  note: string;
  created_at: string;
}

export function fetchGroundTruthCandidates(params: {
  projectId?: string;
  minUsefulRate?: number;
  minSamples?: number;
  maxResults?: number;
}): Promise<GroundTruthCandidate[]> {
  const qs = buildQuery({
    project_id: params.projectId,
    min_useful_rate: params.minUsefulRate?.toString(),
    min_samples: params.minSamples?.toString(),
    max_results: params.maxResults?.toString(),
  });
  return request(`/api/v1/observability/ground-truth/auto-construct${qs}`);
}

export function fetchGroundTruthList(
  projectId?: string,
): Promise<GroundTruthQuery[]> {
  const qs = buildQuery({ project_id: projectId });
  return request(`/api/v1/observability/ground-truth${qs}`);
}

export function addGroundTruth(body: {
  project_id?: string;
  query_text: string;
  expected_doc_ids: string[];
  note?: string;
}): Promise<GroundTruthQuery> {
  return request('/api/v1/observability/ground-truth', {
    method: 'POST',
    body: JSON.stringify({
      project_id: body.project_id ?? '',
      query_text: body.query_text,
      expected_doc_ids: body.expected_doc_ids,
      note: body.note ?? '',
    }),
  });
}

export function deleteGroundTruth(gtId: string): Promise<{ gt_id: string; removed: boolean }> {
  return request(
    `/api/v1/observability/ground-truth/${encodeURIComponent(gtId)}`,
    { method: 'DELETE' },
  );
}

// ════════════════════════════════════════════════════════════════════════
//  M8 #1 · portal 用户反馈
// ════════════════════════════════════════════════════════════════════════

export function submitQueryFeedback(
  queryId: string, useful: boolean, note = '',
): Promise<{ query_id: string; useful: boolean }> {
  return request(
    `/api/v1/observability/queries/${encodeURIComponent(queryId)}/feedback`,
    {
      method: 'POST',
      body: JSON.stringify({ useful, note }),
    },
  );
}
