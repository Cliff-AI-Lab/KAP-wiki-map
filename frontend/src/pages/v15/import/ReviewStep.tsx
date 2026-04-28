/**
 * ReviewStep — 第 2 步: 去噪审核 (Nord 风, 借鉴 V14 但完全重做)
 *
 * 显示 LLM 已打分的文档队列, 默认是 PENDING 中的人工复核项.
 * 三栏统计 (KEEP/ARCHIVE/DISCARD) + 列表 + 决策按钮.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Loader2, Check, Archive, Trash2, AlertTriangle, RefreshCw, ArrowRight, Filter,
} from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';
import {
  fetchReviewQueue, resolveReview, fetchStats,
  type ReviewQueueItem, type KnowledgeStats,
} from '@/services/api';

type StatusFilter = 'PENDING' | 'RESOLVED' | 'ALL';

export default function ReviewStep() {
  const { projectId } = useActiveProject();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('PENDING');
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [q, s] = await Promise.all([
        fetchReviewQueue(statusFilter === 'ALL' ? '' : statusFilter, projectId),
        fetchStats(projectId),
      ]);
      setQueue(q);
      setStats(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter]);

  useEffect(() => { reload(); }, [reload]);

  async function decide(item: ReviewQueueItem, decision: 'KEEP' | 'ARCHIVE' | 'DISCARD') {
    if (!projectId) return;
    setBusyId(item.doc_id);
    try {
      await resolveReview(item.doc_id, decision, 'admin');
      // 本地移除
      setQueue((prev) => prev.filter((x) => x.doc_id !== item.doc_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  const counts = {
    KEEP:    stats?.kept ?? 0,
    ARCHIVE: stats?.archived ?? 0,
    DISCARD: stats?.discarded ?? 0,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="v15-display text-xl text-th-text-primary">第 2 步 · 去噪审核</h2>
          <p className="text-xs text-th-text-muted mt-1">
            LLM 已为每篇文档打 KEEP/ARCHIVE/DISCARD · 这里复核置信度低的或异议项
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-btn border border-th-border bg-elevated text-[11px] v15-mono">
            {(['PENDING','RESOLVED','ALL'] as StatusFilter[]).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1.5 transition ${statusFilter === s ? 'bg-accent text-[color:var(--color-bg-base)]' : 'text-th-text-muted hover:text-th-text-primary'}`}
              >
                {s}
              </button>
            ))}
          </div>
          <button
            onClick={reload}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-btn border border-th-border text-[11px] v15-mono text-th-text-muted hover:text-th-text-primary"
          >
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            刷新
          </button>
        </div>
      </div>

      {/* 三栏统计 */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="待审" hint="status=PENDING" value={queue.length} tone="bg-amber-500/40" />
        <StatCard label="保留 KEEP" value={counts.KEEP} tone="bg-th-success/40" />
        <StatCard label="归档 ARCHIVE" value={counts.ARCHIVE} tone="bg-th-warning/40" />
        <StatCard label="丢弃 DISCARD" value={counts.DISCARD} tone="bg-th-error/40" />
      </div>

      {error && (
        <div className="rounded-btn border border-th-error/40 bg-th-error/5 p-3 text-sm text-th-error flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
        </div>
      )}

      {/* 列表 */}
      <div className="rounded-card border border-th-border bg-elevated/60">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-th-border">
          <Filter size={14} className="text-accent" />
          <span className="text-sm font-semibold text-th-text-primary">复核队列</span>
          <span className="text-[10px] text-th-text-muted v15-mono ml-auto">共 {queue.length} 条</span>
        </div>
        <div className="max-h-[440px] overflow-y-auto">
          {queue.length === 0 ? (
            <div className="text-xs text-th-text-muted text-center py-12">
              {loading ? '加载中...' : statusFilter === 'PENDING' ? '没有待审项 · LLM 自动决策完成' : '空'}
            </div>
          ) : (
            queue.map((item) => (
              <div
                key={item.doc_id}
                className="px-4 py-3 border-b border-th-border/50 last:border-b-0 hover:bg-hover/40 transition"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <DecisionBadge decision={item.proposed_decision} />
                      <span className="text-[11px] v15-mono text-th-text-muted">
                        信心 {(item.confidence * 100).toFixed(0)}%
                      </span>
                      {item.kpi_retain != null && (
                        <span className="text-[11px] v15-mono text-th-text-muted">
                          KPI {(item.kpi_retain * 100).toFixed(0)}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-th-text-primary mt-1 truncate">
                      {item.title || item.doc_id}
                    </div>
                    {item.reason && (
                      <div className="text-[11px] text-th-text-muted mt-1 line-clamp-2">{item.reason}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <DecideBtn
                      label="保留" tone="success"
                      onClick={() => decide(item, 'KEEP')}
                      busy={busyId === item.doc_id}
                      icon={<Check size={11} />}
                    />
                    <DecideBtn
                      label="归档" tone="warning"
                      onClick={() => decide(item, 'ARCHIVE')}
                      busy={busyId === item.doc_id}
                      icon={<Archive size={11} />}
                    />
                    <DecideBtn
                      label="丢弃" tone="error"
                      onClick={() => decide(item, 'DISCARD')}
                      busy={busyId === item.doc_id}
                      icon={<Trash2 size={11} />}
                    />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Next */}
      <div className="text-right">
        <button
          onClick={() => navigate('/v15/manage/import/taxonomy')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent text-[color:var(--color-bg-base)] text-xs font-medium hover:brightness-95"
        >
          进入第 3 步 · 知识体系 <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
}

function StatCard({ label, hint, value, tone }: { label: string; hint?: string; value: number; tone: string }) {
  return (
    <div className="rounded-card border border-th-border bg-elevated p-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-th-text-muted">{label}</span>
        <span className={`w-2 h-2 rounded-full ${tone}`} />
      </div>
      <div className="text-2xl font-semibold text-th-text-primary mt-1 v15-display">{value}</div>
      {hint && <div className="text-[10px] text-th-text-muted v15-mono mt-1">{hint}</div>}
    </div>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const map: Record<string, { color: string; label: string }> = {
    KEEP:    { color: 'bg-th-success/30 text-th-success', label: 'KEEP' },
    ARCHIVE: { color: 'bg-th-warning/30 text-th-warning', label: 'ARCHIVE' },
    DISCARD: { color: 'bg-th-error/30 text-th-error',     label: 'DISCARD' },
  };
  const { color, label } = map[decision] ?? { color: 'bg-hover text-th-text-muted', label: decision };
  return <span className={`px-2 py-0.5 rounded-pill text-[10px] v15-mono ${color}`}>{label}</span>;
}

function DecideBtn({ label, tone, onClick, busy, icon }: {
  label: string;
  tone: 'success' | 'warning' | 'error';
  onClick: () => void;
  busy?: boolean;
  icon: React.ReactNode;
}) {
  const colors = {
    success: 'border-th-success/40 text-th-success hover:bg-th-success/10',
    warning: 'border-th-warning/40 text-th-warning hover:bg-th-warning/10',
    error:   'border-th-error/40 text-th-error hover:bg-th-error/10',
  };
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-btn border bg-transparent text-[11px] v15-mono transition disabled:opacity-50 ${colors[tone]}`}
    >
      {busy ? <Loader2 size={11} className="animate-spin" /> : icon}
      {label}
    </button>
  );
}
