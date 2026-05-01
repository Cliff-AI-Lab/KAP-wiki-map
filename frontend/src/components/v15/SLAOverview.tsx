/**
 * SLAOverview — 跨 cell SLA 总览（M14 #4）。
 *
 * 视图：拉所有工单 + 按 sla_due_at 计算 overdue / nearing / 健康 三档。
 * 不依赖 GovernanceMatrix 内部 cell；独立面板让 SME 一眼看全。
 *
 * 阈值：
 *   - overdue: now > sla_due_at
 *   - nearing: sla_due_at - now < 1 hour（接近过期）
 *   - 健康: 其余
 */
import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, Clock, CheckCircle2, Loader2, RefreshCw,
} from 'lucide-react';

import {
  fetchGovernanceQueue,
  type GovernanceQueueItem,
} from '@/services/governanceApi';

interface Props {
  projectId: string;
  /** nearing 阈值（秒），默认 3600 = 1 小时 */
  nearingSeconds?: number;
}

interface Bucket {
  overdue: GovernanceQueueItem[];
  nearing: GovernanceQueueItem[];
  healthy: number;
  noSla: number;
}

function bucketize(
  items: GovernanceQueueItem[],
  nearingSeconds: number,
  nowMs: number,
): Bucket {
  const overdue: GovernanceQueueItem[] = [];
  const nearing: GovernanceQueueItem[] = [];
  let healthy = 0;
  let noSla = 0;
  for (const it of items) {
    if (it.status !== 'pending' && it.status !== 'reviewing') continue;
    if (!it.sla_due_at) {
      noSla += 1;
      continue;
    }
    const due = new Date(it.sla_due_at).getTime();
    if (isNaN(due)) {
      noSla += 1;
      continue;
    }
    const remainSec = (due - nowMs) / 1000;
    if (remainSec < 0) {
      overdue.push(it);
    } else if (remainSec < nearingSeconds) {
      nearing.push(it);
    } else {
      healthy += 1;
    }
  }
  return { overdue, nearing, healthy, noSla };
}

function formatRemain(dueIso: string, nowMs: number): string {
  const due = new Date(dueIso).getTime();
  if (isNaN(due)) return '-';
  const diffSec = Math.round((due - nowMs) / 1000);
  const abs = Math.abs(diffSec);
  const sign = diffSec < 0 ? '已超 ' : '剩 ';
  if (abs < 60) return `${sign}${abs}秒`;
  if (abs < 3600) return `${sign}${Math.floor(abs / 60)}分`;
  if (abs < 86400) return `${sign}${(abs / 3600).toFixed(1)}小时`;
  return `${sign}${(abs / 86400).toFixed(1)}天`;
}

export default function SLAOverview({
  projectId, nearingSeconds = 3600,
}: Props) {
  const [items, setItems] = useState<GovernanceQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const all = await fetchGovernanceQueue(projectId);
      setItems(all);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const nowMs = Date.now();
  const bucket = bucketize(items, nearingSeconds, nowMs);

  return (
    <div className="rounded-card border border-th-border bg-elevated p-4">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={14} className="text-accent" />
        <span className="text-sm font-mono text-th-text-muted">
          SLA 总览
        </span>
        {loading && (
          <Loader2 size={12} className="animate-spin text-th-text-muted" />
        )}
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-btn border border-th-border text-[11px] text-th-text-muted hover:text-accent hover:border-accent disabled:opacity-40"
        >
          <RefreshCw size={10} /> 刷新
        </button>
      </div>

      {error && (
        <div className="text-xs text-rose-600 py-2">{error}</div>
      )}

      <div className="grid grid-cols-4 gap-3 text-xs">
        <div
          className={`rounded p-2 border ${
            bucket.overdue.length > 0
              ? 'border-rose-500/60 bg-rose-500/10'
              : 'border-th-border'
          }`}
        >
          <div className="flex items-center gap-1 text-th-text-muted">
            <AlertTriangle size={11} />
            已超时
          </div>
          <div className={`text-lg font-semibold mt-0.5 ${
            bucket.overdue.length > 0 ? 'text-rose-600' : 'text-th-text-primary'
          }`}>
            {bucket.overdue.length}
          </div>
        </div>

        <div
          className={`rounded p-2 border ${
            bucket.nearing.length > 0
              ? 'border-amber-500/60 bg-amber-500/10'
              : 'border-th-border'
          }`}
        >
          <div className="flex items-center gap-1 text-th-text-muted">
            <Clock size={11} />
            即将到期
          </div>
          <div className={`text-lg font-semibold mt-0.5 ${
            bucket.nearing.length > 0 ? 'text-amber-700' : 'text-th-text-primary'
          }`}>
            {bucket.nearing.length}
          </div>
        </div>

        <div className="rounded p-2 border border-th-border">
          <div className="flex items-center gap-1 text-th-text-muted">
            <CheckCircle2 size={11} />
            健康
          </div>
          <div className="text-lg font-semibold mt-0.5 text-emerald-700">
            {bucket.healthy}
          </div>
        </div>

        <div className="rounded p-2 border border-th-border">
          <div className="flex items-center gap-1 text-th-text-muted">
            未设 SLA
          </div>
          <div className="text-lg font-semibold mt-0.5 text-th-text-primary">
            {bucket.noSla}
          </div>
        </div>
      </div>

      {/* 已超时列表（前 5）*/}
      {bucket.overdue.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="text-[11px] font-mono text-rose-600">
            <AlertTriangle size={10} className="inline" /> 已超时工单
          </div>
          {bucket.overdue.slice(0, 5).map((it) => (
            <div
              key={it.id}
              className="flex items-center justify-between py-1 text-xs border-t border-th-border first:border-t-0"
            >
              <span className="truncate text-th-text-primary">{it.title}</span>
              <span className="text-rose-600 font-mono ml-2 shrink-0">
                {formatRemain(it.sla_due_at!, nowMs)}
              </span>
            </div>
          ))}
          {bucket.overdue.length > 5 && (
            <div className="text-[11px] text-th-text-muted">
              ... 还有 {bucket.overdue.length - 5} 条
            </div>
          )}
        </div>
      )}
    </div>
  );
}
