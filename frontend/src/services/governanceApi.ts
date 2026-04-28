/**
 * governanceApi.ts — V15 治理 API 封装
 *
 * 对应后端 api/routers/governance.py 的 4 个端点。
 */

export type GovernanceAgent = 'curator' | 'auditor' | 'deduper' | 'standardizer' | 'gardener';
export type GovernanceKind = 'draft_pending' | 'unverified' | 'conflict' | 'standardize_suggest' | 'archive_suggest';
export type GovernanceStatus = 'pending' | 'approved' | 'rejected' | 'edited';
export type GovernanceDecision = 'approve' | 'reject' | 'edit';

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
): Promise<GovernanceQueueItem[]> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (status) qs.set('status', status);
  if (agent) qs.set('agent', agent);
  return req(`/api/v1/governance/queue?${qs.toString()}`);
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
