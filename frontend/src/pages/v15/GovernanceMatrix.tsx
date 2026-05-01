/**
 * GovernanceMatrix — M1 4×6 矩阵审核台看板（决策书 §5.2 D6）。
 *
 * 视图：6 工位（W1-W6 行）× 4 角色（DG/SME/SEC/AIOps 列）网格。
 * 每格显示该 (工位, 角色) 的待办计数；点格打开右侧抽屉，列出工单 + claim/escalate/decide。
 *
 * 设计选择（feedback memory）：
 * - 工程蓝图深色主题 + 角色染色（DG=蓝/SME=橙/SEC=红/AIOps=绿，柔光发光）
 * - 待办>0 的格子有动态脉冲发光（CSS animation），引导关注
 * - 抽屉滑入过渡（CSS transition）
 * - 不引入 emoji（feedback memory）
 *
 * obsidian 风格图谱（动态力导向）作为 M2 后续批 — 本页先做矩阵核心数据流。
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check, X, Edit3, ArrowUp, Loader2, RefreshCw, AlertCircle, Inbox, ArrowLeft,
} from 'lucide-react';

import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import SLAOverview from '@/components/v15/SLAOverview';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';
import {
  claimGovernanceItem,
  decideGovernanceItem,
  escalateGovernanceItem,
  fetchGovernanceMatrix,
  fetchGovernanceQueue,
  type GovernanceDecision,
  type GovernanceQueueItem,
  type MatrixResponse,
  type ReviewerRole,
  type Workstation,
} from '@/services/governanceApi';

// ════════════════════════════════════════════════════════════════════════
//  矩阵元数据（来源：决策书 §5.2 ROLE_WORKSTATION_MATRIX 镜像）
// ════════════════════════════════════════════════════════════════════════

const WORKSTATIONS: { code: Workstation; name: string }[] = [
  { code: 'W1', name: '解析' },
  { code: 'W2', name: '归类' },
  { code: 'W3', name: '切块' },
  { code: 'W4', name: '抽取' },
  { code: 'W5', name: '入库' },
  { code: 'W6', name: '监控' },
];

const ROLES: { code: ReviewerRole; name: string; color: string; glow: string }[] = [
  { code: 'DG',    name: '数据治理员', color: 'bg-sky-500',     glow: 'shadow-[0_0_18px_rgba(14,165,233,0.55)]' },
  { code: 'SME',   name: '业务专家',   color: 'bg-amber-500',   glow: 'shadow-[0_0_18px_rgba(245,158,11,0.55)]' },
  { code: 'SEC',   name: '安全审计员', color: 'bg-rose-500',    glow: 'shadow-[0_0_18px_rgba(244,63,94,0.55)]' },
  { code: 'AIOps', name: 'AI 运营员',  color: 'bg-emerald-500', glow: 'shadow-[0_0_18px_rgba(16,185,129,0.55)]' },
];

// 决策书 §5.2 R/C/I 矩阵
type Inv = 'R' | 'C' | 'I';
const INVOLVEMENT: Record<string, Inv> = {
  'W1-DG': 'R', 'W1-SME': 'I', 'W1-SEC': 'C', 'W1-AIOps': 'I',
  'W2-DG': 'R', 'W2-SME': 'C', 'W2-SEC': 'C', 'W2-AIOps': 'I',
  'W3-DG': 'R', 'W3-SME': 'I', 'W3-SEC': 'I', 'W3-AIOps': 'I',
  'W4-DG': 'I', 'W4-SME': 'R', 'W4-SEC': 'C', 'W4-AIOps': 'I',
  'W5-DG': 'R', 'W5-SME': 'C', 'W5-SEC': 'C', 'W5-AIOps': 'I',
  'W6-DG': 'I', 'W6-SME': 'R', 'W6-SEC': 'C', 'W6-AIOps': 'R',
};

function involvementOf(ws: Workstation, role: ReviewerRole): Inv {
  return INVOLVEMENT[`${ws}-${role}`] ?? 'I';
}

// ════════════════════════════════════════════════════════════════════════
//  单元格
// ════════════════════════════════════════════════════════════════════════

function MatrixCellBox({
  ws,
  role,
  count,
  active,
  onClick,
}: {
  ws: Workstation;
  role: ReviewerRole;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  const inv = involvementOf(ws, role);
  const roleMeta = ROLES.find((r) => r.code === role)!;
  const hasWork = count > 0;

  // 角色染色：R 强色 + 发光，C 中等色，I 极淡
  let bg = 'bg-th-elevated/30';
  let dot = 'bg-th-text-muted';
  let badge = '';
  let pulse = '';
  if (inv === 'R') {
    bg = active ? 'bg-th-elevated' : 'bg-th-elevated/80';
    dot = roleMeta.color;
    badge = 'R';
    if (hasWork) pulse = `${roleMeta.glow} animate-pulse-soft`;
  } else if (inv === 'C') {
    bg = active ? 'bg-th-elevated' : 'bg-th-elevated/60';
    dot = `${roleMeta.color} opacity-60`;
    badge = 'C';
    if (hasWork) pulse = roleMeta.glow;
  } else {
    badge = 'I';
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative h-20 rounded-card border transition-all text-left p-2 ${bg} ${pulse}
        ${active ? 'border-accent ring-2 ring-accent/40' : 'border-th-border hover:border-accent/60'}
        ${hasWork ? 'cursor-pointer' : 'cursor-default opacity-70'}`}
      disabled={!hasWork && !active}
    >
      <div className="flex items-center justify-between text-[10px] font-mono text-th-text-muted">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className={inv === 'R' ? 'text-th-text-primary font-semibold' : ''}>{badge}</span>
      </div>
      <div className="mt-1 text-2xl font-semibold text-th-text-primary text-center">
        {count}
      </div>
    </button>
  );
}

// ════════════════════════════════════════════════════════════════════════
//  抽屉 — 工单列表 + claim/decide/escalate
// ════════════════════════════════════════════════════════════════════════

function CellDrawer({
  ws,
  role,
  open,
  onClose,
  onChange,
}: {
  ws: Workstation | null;
  role: ReviewerRole | null;
  open: boolean;
  onClose: () => void;
  onChange: () => void;
}) {
  const { projectId } = useActiveProject();
  const [items, setItems] = useState<GovernanceQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId || !ws || !role) return;
    setLoading(true);
    setError(null);
    try {
      const list = await fetchGovernanceQueue(projectId, undefined, undefined, ws, role);
      // 按 priority desc / sla_due_at asc 排序
      list.sort((a, b) => (b.priority - a.priority));
      setItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, ws, role]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  async function handleClaim(id: string) {
    setBusyId(id);
    try {
      await claimGovernanceItem(id, 'admin');
      await load();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function handleEscalate(id: string) {
    const reason = window.prompt('升级原因（必填，回流训练用）：') ?? '';
    if (!reason.trim()) return;
    setBusyId(id);
    try {
      await escalateGovernanceItem(id, reason);
      await load();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDecide(id: string, d: GovernanceDecision) {
    setBusyId(id);
    try {
      await decideGovernanceItem(id, d);
      await load();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div
      className={`fixed inset-0 z-30 transition-opacity ${
        open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
      }`}
    >
      <div
        role="presentation"
        onClick={onClose}
        className={`absolute inset-0 bg-black/40 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
      />
      <aside
        className={`absolute right-0 top-0 h-full w-full max-w-2xl bg-th-bg border-l border-th-border shadow-2xl
          transition-transform ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <div className="flex items-center justify-between p-4 border-b border-th-border">
          <div>
            <div className="text-sm text-th-text-muted">
              {ws} {WORKSTATIONS.find((w) => w.code === ws)?.name} ·
              {' '}
              {ROLES.find((r) => r.code === role)?.name}（{role}）
              {' '}
              <span className="font-mono">{ws && role ? involvementOf(ws, role) : ''}</span>
            </div>
            <div className="text-base font-semibold text-th-text-primary mt-0.5">工单列表</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-btn text-th-text-muted hover:bg-hover"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {error && (
            <div className="rounded-card border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-700">
              {error}
            </div>
          )}
          {loading ? (
            <div className="text-sm text-th-text-muted text-center py-8">
              <Loader2 className="inline animate-spin mr-2" size={14} /> 加载中...
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-th-text-muted text-center py-12">
              <Inbox className="inline mr-2" size={16} />
              本格无待办工单
            </div>
          ) : (
            items.map((it) => (
              <article
                key={it.id}
                className="rounded-card border border-th-border bg-elevated p-3"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-th-text-primary truncate">{it.title}</div>
                    <div className="text-xs text-th-text-muted mt-0.5 truncate">
                      {it.description}
                    </div>
                    <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-th-text-muted">
                      <span>状态 {it.status}</span>
                      <span>优先级 {it.priority}</span>
                      {it.confidence != null && (
                        <span>置信度 {(it.confidence * 100).toFixed(0)}%</span>
                      )}
                      {it.claimed_by && <span>认领 {it.claimed_by}</span>}
                      {it.sla_due_at && (
                        <span>
                          SLA <SLATag due={it.sla_due_at} />
                        </span>
                      )}
                    </div>
                    {it.escalation_reason && (
                      <div className="text-[11px] text-amber-700 mt-1 truncate">
                        <ArrowUp className="inline" size={10} /> {it.escalation_reason}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3">
                  {it.status === 'pending' && (
                    <button
                      type="button"
                      disabled={busyId === it.id}
                      onClick={() => handleClaim(it.id)}
                      className="px-2.5 py-1 rounded-btn border border-th-border text-xs hover:bg-hover disabled:opacity-40"
                    >
                      认领
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busyId === it.id}
                    onClick={() => handleDecide(it.id, 'approve')}
                    className="px-2.5 py-1 rounded-btn border border-emerald-500/40 text-xs text-emerald-700 hover:bg-emerald-500/10 disabled:opacity-40"
                  >
                    <Check className="inline" size={11} /> 通过
                  </button>
                  <button
                    type="button"
                    disabled={busyId === it.id}
                    onClick={() => handleDecide(it.id, 'reject')}
                    className="px-2.5 py-1 rounded-btn border border-rose-500/40 text-xs text-rose-700 hover:bg-rose-500/10 disabled:opacity-40"
                  >
                    <X className="inline" size={11} /> 驳回
                  </button>
                  <button
                    type="button"
                    disabled={busyId === it.id}
                    onClick={() => handleDecide(it.id, 'edit')}
                    className="px-2.5 py-1 rounded-btn border border-th-border text-xs hover:bg-hover disabled:opacity-40"
                  >
                    <Edit3 className="inline" size={11} /> 改
                  </button>
                  <button
                    type="button"
                    disabled={busyId === it.id || it.assigned_role === null}
                    onClick={() => handleEscalate(it.id)}
                    className="px-2.5 py-1 rounded-btn border border-amber-500/40 text-xs text-amber-700 hover:bg-amber-500/10 disabled:opacity-40 ml-auto"
                  >
                    <ArrowUp className="inline" size={11} /> 升级
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

function SLATag({ due }: { due: string }) {
  const dueMs = new Date(due).getTime();
  const remainMin = Math.round((dueMs - Date.now()) / 60000);
  if (remainMin < 0) {
    return <span className="text-rose-700">已超时 {-remainMin}min</span>;
  }
  if (remainMin < 30) {
    return <span className="text-amber-700">还剩 {remainMin}min</span>;
  }
  return <span>还剩 {remainMin}min</span>;
}

// ════════════════════════════════════════════════════════════════════════
//  主页面
// ════════════════════════════════════════════════════════════════════════

export default function GovernanceMatrix() {
  const { projectId, loading: projectsLoading } = useActiveProject();
  const { t } = useLocale();
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ ws: Workstation; role: ReviewerRole } | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const m = await fetchGovernanceMatrix(projectId);
      setMatrix(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  function cellCount(ws: Workstation, role: ReviewerRole): number {
    if (!matrix) return 0;
    const cell = matrix.cells.find(
      (c) => c.workstation === ws && c.assigned_role === role,
    );
    return cell?.count ?? 0;
  }

  if (projectsLoading) {
    return <div className="text-sm text-th-text-muted">项目加载中...</div>;
  }
  if (!projectId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-8 text-center">
        <div className="text-th-text-primary mb-2">尚未选择项目</div>
        <Link to="/projects" className="text-sm text-accent hover:underline">
          去项目列表
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/v15/manage"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-btn text-xs text-th-text-muted hover:text-th-text-primary hover:bg-hover"
        >
          <ArrowLeft size={12} /> 治理首页
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-th-text-primary">
          {t('matrix.title')}
        </h1>
        <span className="text-xs text-th-text-muted font-mono">
          {t('matrix.subtitle')}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn border border-th-border text-xs text-th-text-secondary hover:text-th-text-primary hover:bg-hover disabled:opacity-50 transition"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {t('observ.refresh')}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          <AlertCircle className="inline mr-2" size={14} /> {error}
        </div>
      )}

      {/* M14 #4 · SLA 总览（跨 cell 一眼看全） */}
      <SLAOverview projectId={projectId} />

      {/* 顶部统计 */}
      <div className="grid grid-cols-4 gap-4">
        {ROLES.map((r) => {
          const sum = WORKSTATIONS.reduce((a, ws) => a + cellCount(ws.code, r.code), 0);
          return (
            <div
              key={r.code}
              className={`rounded-card border border-th-border bg-elevated p-4`}
            >
              <div className="flex items-center gap-2 text-xs font-mono text-th-text-muted">
                <span className={`w-2 h-2 rounded-full ${r.color}`} />
                {r.name}（{r.code}）
              </div>
              <div className="text-3xl font-semibold text-th-text-primary mt-1">{sum}</div>
              <div className="text-xs text-th-text-muted mt-1">主审 + 协审 待办</div>
            </div>
          );
        })}
      </div>

      {/* 4×6 矩阵 */}
      <div className="rounded-card border border-th-border bg-elevated p-5 overflow-x-auto">
        <div className="grid grid-cols-[88px_repeat(4,minmax(0,1fr))] gap-2 min-w-[640px]">
          {/* 表头：工位列名 */}
          <div className="text-[11px] text-th-text-muted font-mono">工位 \ 角色</div>
          {ROLES.map((r) => (
            <div key={r.code} className="flex items-center gap-2 text-xs text-th-text-secondary px-2">
              <span className={`w-2 h-2 rounded-full ${r.color}`} />
              {r.code}
            </div>
          ))}

          {/* 6 行 */}
          {WORKSTATIONS.map((ws) => (
            <div key={ws.code} className="contents">
              <div className="flex items-center text-xs text-th-text-secondary font-mono px-2">
                {ws.code} {ws.name}
              </div>
              {ROLES.map((r) => (
                <MatrixCellBox
                  key={`${ws.code}-${r.code}`}
                  ws={ws.code}
                  role={r.code}
                  count={cellCount(ws.code, r.code)}
                  active={selected?.ws === ws.code && selected?.role === r.code}
                  onClick={() => setSelected({ ws: ws.code, role: r.code })}
                />
              ))}
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-4 text-[11px] text-th-text-muted">
          <span>{t('matrix.legendR')}</span>
          <span>{t('matrix.legendC')}</span>
          <span>{t('matrix.legendI')}</span>
          <span className="ml-auto font-mono">
            {t('matrix.totalPending', { n: matrix?.total ?? 0 })}
            {matrix?.uncategorized ? ` · ${matrix.uncategorized}` : ''}
          </span>
        </div>
      </div>

      <CellDrawer
        ws={selected?.ws ?? null}
        role={selected?.role ?? null}
        open={selected !== null}
        onClose={() => setSelected(null)}
        onChange={load}
      />
    </div>
  );
}
