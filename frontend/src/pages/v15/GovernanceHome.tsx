/**
 * GovernanceHome — 治理模式首页（Phase C: 接真实 API）
 *
 * 顶部：标题 + 灌入 Demo 按钮
 * 中部：四 Agent 工单聚合卡 → 点击切换下方工单详情列表
 * 下部：工单详情列表（按选中 agent 过滤）+ 审核三按钮（通过/打回/改）
 * 底部：健康面板（真实 health 数据三进度条）
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check, X, Edit3, Download, Loader2, Play,
  FolderPlus, Upload, Filter, Network, BookOpen, GitBranch, ArrowRight, Inbox,
  LayoutGrid,
} from 'lucide-react';

import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import type { TranslationKey } from '@/lib/i18n';
import { WikiEditorModal } from '@/components/v15/WikiEditorModal';
import { runGovernanceAgent, type AgentRunResult } from '@/services/governanceApi';
import {
  fetchGovernanceHealth,
  fetchGovernanceQueue,
  decideGovernanceItem,
  seedGovernanceDemo,
  type GovernanceAgent,
  type GovernanceDecision,
  type GovernanceHealth,
  type GovernanceQueueItem,
} from '@/services/governanceApi';

type AgentRow = { key: GovernanceAgent; labelKey: TranslationKey; tone: string; kindKey: string };

const AGENTS: AgentRow[] = [
  { key: 'curator',      labelKey: 'agent.curator',      tone: 'bg-accent',      kindKey: 'gov.kindDraft' },
  { key: 'auditor',      labelKey: 'agent.auditor',      tone: 'bg-amber-500',   kindKey: 'gov.kindUnverified' },
  { key: 'deduper',      labelKey: 'agent.deduper',      tone: 'bg-rose-500',    kindKey: 'gov.kindConflict' },
  { key: 'standardizer', labelKey: 'agent.standardizer', tone: 'bg-indigo-400',  kindKey: 'gov.kindStandardize' },
  { key: 'gardener',     labelKey: 'agent.gardener',     tone: 'bg-emerald-500', kindKey: 'gov.kindArchive' },
];

function AgentStatCard({
  agent,
  label,
  tone,
  kindLabel,
  count,
  active,
  running,
  onClick,
  onRun,
}: {
  agent: GovernanceAgent;
  label: string;
  tone: string;
  kindLabel: string;
  count: number;
  active: boolean;
  running: boolean;
  onClick: () => void;
  onRun: () => void;
}) {
  const { t } = useLocale();
  return (
    <div
      className={`relative text-left rounded-card border p-4 transition-all ${
        active
          ? 'border-accent shadow-card-hover bg-elevated'
          : 'border-th-border bg-elevated hover:shadow-card-hover'
      }`}
    >
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className="absolute inset-0 rounded-card"
        aria-label={`切换 ${label}`}
      />
      <div className="relative pointer-events-none">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono text-th-text-muted">{label}</span>
          <span className={`w-2 h-2 rounded-full ${tone}`} />
        </div>
        <div className="text-3xl font-semibold text-th-text-primary">{count}</div>
        <div className="text-sm text-th-text-muted mt-1">{kindLabel}</div>
      </div>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onRun(); }}
        disabled={running}
        className="relative z-10 mt-3 inline-flex items-center gap-1 rounded-btn border border-th-border px-2 py-1 text-[11px] text-th-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition"
      >
        {running ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
        {running ? t('pipeline.running') : t('pipeline.run')}
      </button>
      <div className="sr-only">{agent}</div>
    </div>
  );
}

function DecisionButtons({
  onDecide,
  disabled,
}: {
  onDecide: (d: GovernanceDecision) => void;
  disabled: boolean;
}) {
  const { t } = useLocale();
  const base =
    'inline-flex items-center gap-1 px-2.5 py-1 rounded-btn text-xs font-medium border transition disabled:opacity-40';
  return (
    <div className="flex items-center gap-2 shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onDecide('approve')}
        className={`${base} border-emerald-500/40 text-emerald-700 hover:bg-emerald-500/10`}
      >
        <Check size={12} /> {t('gov.btnApprove')}
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onDecide('reject')}
        className={`${base} border-rose-500/40 text-rose-700 hover:bg-rose-500/10`}
      >
        <X size={12} /> {t('gov.btnReject')}
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onDecide('edit')}
        className={`${base} border-th-border text-accent hover:bg-hover`}
      >
        <Edit3 size={12} /> {t('gov.btnEdit')}
      </button>
    </div>
  );
}

/** target_ref 规格化成 Wiki page_id — seed 种了 'wiki/xxx' / 'page/xxx' 前缀 */
function refToPageId(ref: string): string {
  if (ref.startsWith('wiki/')) return `domain/${ref.slice(5)}`;
  if (ref.startsWith('page/')) return ref.slice(5);
  return ref;
}

function QueueList({
  items,
  onDecide,
  onEdit,
  busyId,
}: {
  items: GovernanceQueueItem[];
  onDecide: (id: string, d: GovernanceDecision) => void;
  onEdit: (item: GovernanceQueueItem) => void;
  busyId: string | null;
}) {
  const { t } = useLocale();
  if (items.length === 0) {
    return (
      <div className="text-sm text-th-text-muted py-6 text-center">
        {t('gov.emptyQueue')}
      </div>
    );
  }
  return (
    <ul className="divide-y divide-th-border">
      {items.map((it) => {
        const tone = AGENTS.find((a) => a.key === it.agent)?.tone ?? 'bg-th-text-muted';
        const resolved = it.status !== 'pending';
        return (
          <li
            key={it.id}
            className={`py-3 flex items-start gap-4 ${resolved ? 'opacity-40' : ''}`}
          >
            <span className={`w-2 h-2 rounded-full mt-2 shrink-0 ${tone}`} />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-th-text-primary truncate">{it.title}</div>
              <div className="text-xs text-th-text-muted truncate mt-0.5">
                {it.description} · <span className="font-mono">{it.target_ref}</span> · priority {it.priority}
              </div>
              {resolved && (
                <div className="text-xs text-th-text-muted font-mono mt-1">
                  <Check size={11} className="inline -mt-0.5 mr-1" />{it.status} by {it.resolver ?? '?'}
                </div>
              )}
            </div>
            <DecisionButtons
              onDecide={(d) => {
                if (d === 'edit') onEdit(it);
                else onDecide(it.id, d);
              }}
              disabled={resolved || busyId === it.id}
            />
          </li>
        );
      })}
    </ul>
  );
}

function HealthPanel({ health }: { health: GovernanceHealth | null }) {
  const { t } = useLocale();
  if (!health) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-5 text-sm text-th-text-muted">...</div>
    );
  }
  const metrics: { name: string; val: number; hint: string; down?: boolean }[] = [
    { name: t('gov.metricCoverage'),  val: health.wiki_coverage,      hint: t('gov.hintCoverage') },
    { name: t('gov.metricFallback'),  val: health.rag_fallback_rate,  hint: t('gov.hintFallback'), down: true },
    { name: t('gov.metricProvenance'),val: health.provenance_score,   hint: t('gov.hintProvenance') },
  ];
  return (
    <div className="rounded-card border border-th-border bg-elevated p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm font-semibold text-th-text-primary">{t('gov.health')}</div>
        <div className="text-xs text-th-text-muted font-mono">{t('gov.healthSub')}</div>
      </div>
      <div className="space-y-3">
        {metrics.map((m) => (
          <div key={m.name} className="flex items-center gap-3 text-sm">
            <div className="w-32 text-th-text-muted">{m.name}</div>
            <div className="flex-1 h-2 rounded-pill bg-hover overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${m.val}%` }} />
            </div>
            <div className="w-16 text-right font-mono text-th-text-primary">
              {m.val}%{m.down ? ' ↓' : ''}
            </div>
            <div className="w-40 text-th-text-muted text-xs">{m.hint}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function GovernanceHome() {
  const { t } = useLocale();
  const { projectId, loading: projectsLoading } = useActiveProject();

  const [health, setHealth] = useState<GovernanceHealth | null>(null);
  const [queue, setQueue] = useState<GovernanceQueueItem[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<GovernanceAgent>('curator');
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<GovernanceQueueItem | null>(null);
  const [runningAgent, setRunningAgent] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<AgentRunResult | null>(null);

  const loadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [h, q] = await Promise.all([
        fetchGovernanceHealth(projectId),
        fetchGovernanceQueue(projectId, 'pending'),
      ]);
      setHealth(h);
      setQueue(q);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleSeed() {
    if (!projectId) return;
    setSeeding(true);
    try {
      await seedGovernanceDemo(projectId);
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeeding(false);
    }
  }

  async function handleRunAgent(agentName: GovernanceAgent) {
    if (!projectId) return;
    setRunningAgent(agentName);
    setError(null);
    try {
      const r = await runGovernanceAgent(projectId, agentName);
      setLastRun(r);
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunningAgent(null);
    }
  }

  async function handleDecide(id: string, decision: GovernanceDecision) {
    setBusyId(id);
    try {
      const updated = await decideGovernanceItem(id, decision);
      setQueue((prev) => prev.map((it) => (it.id === id ? updated : it)));
      // 本地更新 health 的 queue_counts（预估，不必重拉）
      setHealth((h) => {
        if (!h) return h;
        const agent = updated.agent;
        const next = { ...h.queue_counts };
        next[agent] = Math.max(0, (next[agent] ?? 0) - 1);
        return { ...h, queue_counts: next };
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  if (projectsLoading) {
    return <div className="text-sm text-th-text-muted">{t('reader.loadingProject')}</div>;
  }

  if (!projectId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-8 text-center">
        <div className="text-th-text-primary mb-2">{t('reader.emptyProject')}</div>
        <div className="text-sm text-th-text-muted">{t('reader.emptyProjectHint')}</div>
      </div>
    );
  }

  const filtered = queue.filter((it) => it.agent === selectedAgent);
  const counts: Record<string, number> = health?.queue_counts ?? {};

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-accent" />
        <h1 className="text-2xl font-semibold tracking-tight text-th-text-primary">
          {t('gov.title')}
        </h1>
        <span className="text-xs text-th-text-muted font-mono">
          {t('gov.subtitle')}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Link
            to="/v15/manage/matrix"
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn border border-accent/40 text-xs text-accent hover:bg-accent/10 transition"
          >
            <LayoutGrid size={12} /> {t('pipeline.matrix')}
          </Link>
          <button
            type="button"
            onClick={handleSeed}
            disabled={seeding}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn border border-th-border text-xs text-th-text-secondary hover:text-th-text-primary hover:bg-hover disabled:opacity-50 transition"
          >
            {seeding ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            {t('gov.seedDemo')}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-th-border bg-elevated p-3 text-sm text-th-error">
          {error}
        </div>
      )}

      {/* === 知识体系建立流程 (V14 完整 pipeline 入口) === */}
      <KnowledgePipeline projectId={projectId} />

      <div className="grid grid-cols-5 gap-4">
        {AGENTS.map((a) => (
          <AgentStatCard
            key={a.key}
            agent={a.key}
            label={t(a.labelKey)}
            tone={a.tone}
            kindLabel={t(a.kindKey as any)}
            count={counts[a.key] ?? 0}
            active={selectedAgent === a.key}
            running={runningAgent === a.key}
            onClick={() => setSelectedAgent(a.key)}
            onRun={() => handleRunAgent(a.key)}
          />
        ))}
      </div>

      {lastRun && (
        <div className="rounded-card border border-th-border bg-elevated p-3 text-xs font-mono text-th-text-muted flex items-center gap-3">
          <span className="text-accent">[{lastRun.agent}]</span>
          <span>scanned={lastRun.scanned}</span>
          <span>produced={lastRun.produced}</span>
          <span>skipped={lastRun.skipped}</span>
          {lastRun.errors.length > 0 && (
            <span className="text-th-error">errors={lastRun.errors.length}</span>
          )}
        </div>
      )}

      <div className="rounded-card border border-th-border bg-elevated p-5">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-semibold text-th-text-primary">
            {(() => {
              const ag = AGENTS.find((a) => a.key === selectedAgent);
              return ag ? t(ag.labelKey) : selectedAgent;
            })()} · {t('gov.queueDetail')}
          </div>
          <div className="text-xs text-th-text-muted font-mono">
            {loading ? '...' : t('gov.countTotal', { n: filtered.length })}
          </div>
        </div>
        <QueueList items={filtered} onDecide={handleDecide} onEdit={setEditingItem} busyId={busyId} />
      </div>

      <HealthPanel health={health} />

      {editingItem && projectId && (
        <WikiEditorModal
          open={true}
          pageId={refToPageId(editingItem.target_ref)}
          projectId={projectId}
          initialTitle={editingItem.title}
          onClose={() => setEditingItem(null)}
          onSaved={async () => {
            // 保存成功后把工单标 edited + 本地状态更新
            try {
              const { decideGovernanceItem } = await import('@/services/governanceApi');
              const updated = await decideGovernanceItem(editingItem.id, 'edit');
              setQueue((prev) => prev.map((it) => (it.id === editingItem.id ? updated : it)));
              setHealth((h) => {
                if (!h) return h;
                const next = { ...h.queue_counts };
                next[editingItem.agent] = Math.max(0, (next[editingItem.agent] ?? 0) - 1);
                return { ...h, queue_counts: next };
              });
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            }
            setEditingItem(null);
          }}
        />
      )}
    </div>
  );
}

/* ============================================
   知识体系建立流程 (V14 完整 pipeline 入口)
   6 步: 项目 → 上传 → 去噪 → Schema → Wiki → 图谱
   ============================================ */
function KnowledgePipeline({ projectId }: { projectId: string | null }) {
  const { t } = useLocale();
  const steps = [
    { icon: FolderPlus,  labelKey: 'pipeline.s1.label' as const, descKey: 'pipeline.s1.desc' as const, path: (_pid: string) => `/projects` },
    { icon: Upload,      labelKey: 'pipeline.s2.label' as const, descKey: 'pipeline.s2.desc' as const, path: (_pid: string) => `/v15/manage/import/upload` },
    { icon: Filter,      labelKey: 'pipeline.s3.label' as const, descKey: 'pipeline.s3.desc' as const, path: (_pid: string) => `/v15/manage/import/review` },
    { icon: Network,     labelKey: 'pipeline.s4.label' as const, descKey: 'pipeline.s4.desc' as const, path: (_pid: string) => `/v15/manage/import/taxonomy` },
    { icon: BookOpen,    labelKey: 'pipeline.s5.label' as const, descKey: 'pipeline.s5.desc' as const, path: (_pid: string) => `/v15/manage/wiki/domain/energy/safety/hazard` },
    { icon: GitBranch,   labelKey: 'pipeline.s6.label' as const, descKey: 'pipeline.s6.desc' as const, path: (_pid: string) => `/v15/manage/graph` },
  ];

  return (
    <div className="rounded-card border border-th-border bg-elevated p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-btn bg-accent/10 grid place-items-center">
            <Inbox size={14} className="text-accent" />
          </div>
          <div>
            <div className="text-sm font-semibold text-th-text-primary">{t('pipeline.title')}</div>
            <div className="text-xs text-th-text-muted mt-0.5 v15-mono">
              {t('pipeline.subtitle')}
              {projectId && (<span> · {projectId.slice(0, 16)}{projectId.length > 16 ? '...' : ''}</span>)}
            </div>
          </div>
        </div>
        <Link
          to="/projects"
          className="text-xs px-3 py-1.5 rounded-btn border border-th-border text-th-text-secondary hover:text-th-text-primary hover:border-th-border-hover transition"
        >
          {t('pipeline.switch')}
        </Link>
      </div>

      {!projectId ? (
        <div className="text-sm text-th-text-muted py-4 text-center">
          {t('pipeline.empty')}
        </div>
      ) : (
        <div className="flex items-stretch gap-2">
          {steps.map((s, i) => {
            const Icon = s.icon;
            return (
              <div key={s.labelKey} className="flex items-center flex-1">
                <Link
                  to={s.path(projectId)}
                  className="group flex-1 flex flex-col items-center gap-1.5 p-3 rounded-card border border-th-border hover:border-accent hover:bg-hover transition"
                >
                  <Icon size={20} className="text-th-text-muted group-hover:text-accent transition-colors" />
                  <div className="text-xs font-medium text-th-text-primary">{t(s.labelKey)}</div>
                  <div className="text-[10px] text-th-text-muted">{t(s.descKey)}</div>
                </Link>
                {i < steps.length - 1 && (
                  <ArrowRight size={14} className="text-th-text-muted shrink-0 mx-1" />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
