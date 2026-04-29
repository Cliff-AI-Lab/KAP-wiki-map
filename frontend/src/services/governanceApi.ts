/**
 * governanceApi.ts — V15 治理 API 封装
 *
 * 对应后端 api/routers/governance.py 的 4 个端点。
 */

export type GovernanceAgent =
  | 'curator' | 'auditor' | 'deduper' | 'standardizer' | 'gardener'
  | 'distillation';  // M1 W4 写入侧蒸馏管线产出
export type GovernanceKind =
  | 'draft_pending' | 'unverified' | 'conflict' | 'standardize_suggest' | 'archive_suggest'
  | 'low_confidence_extract';  // M1 W4 低置信度抽取
export type GovernanceStatus = 'pending' | 'reviewing' | 'approved' | 'rejected' | 'edited' | 'escalated';
export type GovernanceDecision = 'approve' | 'reject' | 'edit';

// M1 4×6 矩阵审核台（决策书 §5.2 D6）
export type Workstation = 'W1' | 'W2' | 'W3' | 'W4' | 'W5' | 'W6';
export type ReviewerRole = 'DG' | 'SME' | 'SEC' | 'AIOps';

export interface GovernanceQueueItem {
  id: string;
  project_id: string;
  agent: GovernanceAgent;
  kind: GovernanceKind;
  title: string;
  description: string;
  target_ref: string;
  priority: number;
  status: GovernanceStatus;
  created_at: string;
  resolved_at: string | null;
  resolver: string | null;
  // M1 矩阵字段
  workstation: Workstation | null;
  assigned_role: ReviewerRole | null;
  claimed_by: string | null;
  claimed_at: string | null;
  escalated_to: ReviewerRole | null;
  escalation_reason: string;
  sla_due_at: string | null;
  confidence: number | null;
}

// M1 矩阵看板响应
export interface MatrixCell {
  workstation: Workstation;
  assigned_role: ReviewerRole;
  count: number;
}
export interface MatrixResponse {
  project_id: string;
  cells: MatrixCell[];
  total: number;
  uncategorized: number;
}

export interface GovernanceHealth {
  wiki_coverage: number;
  rag_fallback_rate: number;
  provenance_score: number;
  queue_counts: Record<GovernanceAgent, number>;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function req<T>(path: string, init: RequestInit = {}, timeout = 30_000): Promise<T> {
  const ctl = new AbortController();
  const tid = setTimeout(() => ctl.abort(), timeout);
  try {
    const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
    if (init.body) headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    const r = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: ctl.signal });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `请求失败: ${r.status}`);
    }
    if (r.status === 204) return {} as T;
    const t = await r.text();
    return t ? (JSON.parse(t) as T) : ({} as T);
  } finally {
    clearTimeout(tid);
  }
}

export function fetchGovernanceQueue(
  projectId: string,
  status?: string,
  agent?: string,
  workstation?: Workstation,
  assignedRole?: ReviewerRole,
): Promise<GovernanceQueueItem[]> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (status) qs.set('status', status);
  if (agent) qs.set('agent', agent);
  if (workstation) qs.set('workstation', workstation);
  if (assignedRole) qs.set('assigned_role', assignedRole);
  return req(`/api/v1/governance/queue?${qs.toString()}`);
}

// M1 矩阵 API
export function fetchGovernanceMatrix(projectId: string): Promise<MatrixResponse> {
  return req(`/api/v1/governance/matrix?project_id=${encodeURIComponent(projectId)}`);
}

export function claimGovernanceItem(
  itemId: string,
  claimer: string,
): Promise<GovernanceQueueItem> {
  return req(`/api/v1/governance/queue/${encodeURIComponent(itemId)}/claim`, {
    method: 'POST',
    body: JSON.stringify({ claimer }),
  });
}

export function escalateGovernanceItem(
  itemId: string,
  reason: string,
): Promise<GovernanceQueueItem> {
  return req(`/api/v1/governance/queue/${encodeURIComponent(itemId)}/escalate`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export function fetchGovernanceHealth(projectId: string): Promise<GovernanceHealth> {
  return req(`/api/v1/governance/health?project_id=${encodeURIComponent(projectId)}`);
}

export function decideGovernanceItem(
  itemId: string,
  decision: GovernanceDecision,
  resolver = 'admin',
): Promise<GovernanceQueueItem> {
  return req(`/api/v1/governance/queue/${encodeURIComponent(itemId)}/decide`, {
    method: 'POST',
    body: JSON.stringify({ decision, resolver }),
  });
}

export function seedGovernanceDemo(projectId: string): Promise<{ seeded: number }> {
  return req(`/api/v1/governance/seed?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });
}

/** V15 Phase I+K: 手动触发治理 Agent 运行 */
export interface AgentRunResult {
  agent: string;
  ok: boolean;
  scanned: number;
  produced: number;
  skipped: number;
  errors: string[];
  detail: Record<string, unknown>;
}

export function runGovernanceAgent(
  projectId: string,
  agentName: GovernanceAgent,
): Promise<AgentRunResult> {
  return req(
    `/api/v1/governance/agents/${agentName}/run?project_id=${encodeURIComponent(projectId)}`,
    { method: 'POST' },
    180_000,
  );
}
