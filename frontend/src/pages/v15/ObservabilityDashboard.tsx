/**
 * ObservabilityDashboard — 运营观察仪表盘（M10 #3）
 *
 * 一次拉 GET /api/v1/observability/dashboard 的全维度数据：
 *   - 演化决策（approve/reject/promote/rollback 计数 + 派生比率）
 *   - 查询召回（hit_rate / 用户反馈 useful_rate / p95 latency）
 *   - 7 天观察期（活跃 / 告警计数 + 近期 items）
 *   - 召回评估（最新 avg_recall + ground truth 集大小）
 *   - 召回率趋势（current vs baseline，跌破阈值时告警）
 *   - 监测条件健康度（4 监测条件 SME approve_rate + 调优建议）
 *
 * 设计：
 *   - 卡片栅格布局（2 列）
 *   - Lucide icons，禁用 emoji（CLAUDE.md 全局约束）
 *   - 失败时 fallback 到友好的"加载失败"卡片，不阻断其他卡片渲染
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Activity, AlertTriangle, BarChart3, CheckCircle2, Clock,
  GitMerge, Loader2, MessageSquare, RefreshCw, Search, Target,
  TrendingDown, TrendingUp, XCircle,
} from 'lucide-react';

import {
  fetchDashboard, fetchRecallTrend, fetchConditionHealth,
  type Dashboard, type RecallTrend, type ConditionHealth,
} from '@/services/observabilityApi';
import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import RecallTrendChart from '@/components/v15/RecallTrendChart';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';

// ════════════════════════════════════════════════════════════════════════
//  小组件
// ════════════════════════════════════════════════════════════════════════

function MetricCard({
  title, icon, children, alert, alertLabel,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  alert?: boolean;
  alertLabel?: string;
}) {
  return (
    <div
      className={`rounded-card border p-4 bg-elevated transition-all ${
        alert
          ? 'border-rose-500/60 shadow-card-hover'
          : 'border-th-border hover:shadow-card-hover'
      }`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className={alert ? 'text-rose-600' : 'text-accent'}>{icon}</span>
        <h3 className="text-sm font-mono text-th-text-muted">{title}</h3>
        {alert && (
          <span className="ml-auto text-xs text-rose-600 font-medium">
            {alertLabel}
          </span>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function StatRow({
  label, value, hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between py-1">
      <span className="text-xs text-th-text-muted">{label}</span>
      <span className="text-sm font-medium text-th-text-primary tabular-nums">
        {value}
        {hint && (
          <span className="ml-1 text-xs text-th-text-muted">{hint}</span>
        )}
      </span>
    </div>
  );
}

function EmptyOrLoading({ loading, error, empty, t }: {
  loading: boolean;
  error: string | null;
  empty?: boolean;
  t: (k: string) => string;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-th-text-muted text-xs py-4">
        <Loader2 size={14} className="animate-spin" /> {t('common.loading')}
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-rose-600 text-xs py-4">{t('common.loadFailed')}：{error}</div>
    );
  }
  if (empty) {
    return (
      <div className="text-th-text-muted text-xs py-4">{t('observ.empty')}</div>
    );
  }
  return null;
}

function PercentBadge({ value }: { value: number }) {
  const pct = (value * 100).toFixed(1);
  return <span className="tabular-nums">{pct}%</span>;
}

// M18 #4 · 反馈原因 Top 5 横条统计
function FeedbackReasonsPanel({
  reasons, t,
}: {
  reasons: Record<string, number> | undefined;
  t: (k: string) => string;
}) {
  const entries = reasons
    ? Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 5)
    : [];
  if (entries.length === 0) return null;

  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  const max = Math.max(...entries.map(([, n]) => n));

  return (
    <div className="mt-3 pt-3 border-t border-th-border">
      <div className="flex items-center justify-between mb-2 text-xs text-th-text-muted">
        <span className="font-mono">{t('observ.feedbackReasons.title')}</span>
        <span>
          {t('observ.feedbackReasons.totalNegFeedback')}: {total}
        </span>
      </div>
      <div className="space-y-1">
        {entries.map(([reason, count]) => (
          <div key={reason} className="text-xs">
            <div className="flex justify-between mb-0.5">
              <span className="font-mono text-th-text-secondary">{reason}</span>
              <span className="tabular-nums text-th-text-muted">{count}</span>
            </div>
            <div className="h-1.5 bg-th-bg-subtle rounded-full overflow-hidden">
              <div
                className="h-full bg-accent/70"
                style={{ width: `${(count / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════
//  主页面
// ════════════════════════════════════════════════════════════════════════

export default function ObservabilityDashboard() {
  const { projectId: activeProjectId } = useActiveProject();
  const { t } = useLocale();
  const projectId = activeProjectId || undefined;

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [trend, setTrend] = useState<RecallTrend | null>(null);
  const [conditionHealth, setConditionHealth] = useState<
    Record<string, ConditionHealth> | null
  >(null);

  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{
    dashboard?: string; trend?: string; condition?: string;
  }>({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErrors({});

    const [dashRes, trendRes, condRes] = await Promise.allSettled([
      fetchDashboard(projectId),
      fetchRecallTrend(projectId),
      fetchConditionHealth(projectId),
    ]);

    if (dashRes.status === 'fulfilled') setDashboard(dashRes.value);
    else setErrors(e => ({ ...e, dashboard: dashRes.reason?.message || t('observ.fetchFailed') }));

    if (trendRes.status === 'fulfilled') setTrend(trendRes.value);
    else setErrors(e => ({ ...e, trend: trendRes.reason?.message || t('observ.fetchFailed') }));

    if (condRes.status === 'fulfilled') setConditionHealth(condRes.value);
    else setErrors(e => ({ ...e, condition: condRes.reason?.message || t('observ.fetchFailed') }));

    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary">
            {t('observ.dashboard.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            {t('observ.dashboard.subtitle')}
            {projectId && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-mono">
                {projectId}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={loadAll}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-btn border border-th-border px-3 py-1.5 text-sm text-th-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {t('observ.refresh')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 演化决策 */}
        <MetricCard title={t('observ.card.decisions')} icon={<GitMerge size={16} />}>
          <EmptyOrLoading
            t={t}
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.decisions.total === 0}
          />
          {dashboard && dashboard.decisions.total > 0 && (
            <>
              <StatRow
                label={t('observ.row.totalDecisions')}
                value={dashboard.decisions.total}
              />
              <StatRow
                label={t('observ.row.approveReject')}
                value={
                  <>
                    <CheckCircle2 size={12} className="inline mr-1 text-emerald-600" />
                    {dashboard.decisions.by_type.approve_proposal ?? 0}
                    <span className="mx-1 text-th-text-muted">/</span>
                    <XCircle size={12} className="inline mx-1 text-rose-600" />
                    {dashboard.decisions.by_type.reject_proposal ?? 0}
                  </>
                }
              />
              <StatRow
                label={t('observ.row.approvalRate')}
                value={<PercentBadge value={dashboard.decisions.approval_rate} />}
              />
              <StatRow
                label={t('observ.row.promoteRollback')}
                value={
                  <>
                    {dashboard.decisions.by_type.promote ?? 0}
                    <span className="mx-1 text-th-text-muted">/</span>
                    {dashboard.decisions.by_type.rollback ?? 0}
                  </>
                }
              />
              <StatRow
                label={t('observ.row.promoteRatio')}
                value={dashboard.decisions.promote_rollback_ratio.toFixed(2)}
              />
            </>
          )}
        </MetricCard>

        {/* 查询召回 */}
        <MetricCard title={t('observ.card.queries')} icon={<Search size={16} />}>
          <EmptyOrLoading
            t={t}
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.queries.total === 0}
          />
          {dashboard && dashboard.queries.total > 0 && (
            <>
              <StatRow
                label={t('observ.row.queryTotalHits')}
                value={`${dashboard.queries.total} / ${dashboard.queries.hits}`}
              />
              <StatRow
                label={t('observ.row.hitRate')}
                value={<PercentBadge value={dashboard.queries.hit_rate} />}
              />
              <StatRow
                label={t('observ.row.avgLatency')}
                value={`${dashboard.queries.avg_latency_ms.toFixed(0)}`}
                hint="ms"
              />
              <StatRow
                label={t('observ.row.p95Latency')}
                value={`${dashboard.queries.p95_latency_ms}`}
                hint="ms"
              />
              <StatRow
                label={t('observ.row.feedbackRate')}
                value={<PercentBadge value={dashboard.queries.feedback_coverage} />}
                hint={`(${dashboard.queries.feedback_total})`}
              />
              <StatRow
                label={t('observ.row.usefulRate')}
                value={
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare size={12} className="text-accent" />
                    <PercentBadge value={dashboard.queries.useful_rate} />
                  </span>
                }
              />
              <FeedbackReasonsPanel
                reasons={dashboard.queries.feedback_reasons}
                t={t}
              />
            </>
          )}
        </MetricCard>

        {/* 7 天观察期 */}
        <MetricCard
          title={t('observ.card.observations')}
          icon={<Clock size={16} />}
          alert={!!dashboard && dashboard.observations.alerting > 0}
          alertLabel={t('observ.status.alert')}
        >
          <EmptyOrLoading
            t={t}
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.observations.total === 0}
          />
          {dashboard && dashboard.observations.total > 0 && (
            <>
              <StatRow
                label={t('observ.row.activeWindow')}
                value={dashboard.observations.active}
              />
              <StatRow
                label={t('observ.row.alerting')}
                value={
                  <span
                    className={
                      dashboard.observations.alerting > 0
                        ? 'text-rose-600 font-medium'
                        : ''
                    }
                  >
                    {dashboard.observations.alerting}
                  </span>
                }
              />
              <StatRow
                label={t('observ.row.totalWindow')}
                value={dashboard.observations.total}
              />
              {dashboard.observations.items.length > 0 && (
                <div className="mt-3 space-y-1">
                  {dashboard.observations.items.slice(0, 5).map(o => (
                    <div
                      key={o.observation_id}
                      className="flex items-center justify-between text-xs py-1 border-t border-th-border first:border-t-0"
                    >
                      <span className="font-mono text-th-text-muted">
                        {o.project_id} · {o.version}
                      </span>
                      <span className="flex items-center gap-1">
                        <StatusBadge status={o.status} t={t} />
                        {o.alerts_count > 0 && (
                          <span className="text-rose-600 ml-1">
                            <AlertTriangle size={10} className="inline" />
                            {o.alerts_count}
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </MetricCard>

        {/* 召回评估 */}
        <MetricCard
          title={t('observ.card.recallEval')}
          icon={<Target size={16} />}
        >
          <EmptyOrLoading
            t={t}
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
          />
          {dashboard && (
            <>
              <StatRow
                label={t('observ.gtSet')}
                value={dashboard.recall_eval.ground_truth_count}
              />
              {dashboard.recall_eval.latest ? (
                <>
                  <StatRow
                    label={t('observ.row.latestRecall')}
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_recall}
                      />
                    }
                    hint={`@${dashboard.recall_eval.latest.k}`}
                  />
                  <StatRow
                    label={t('observ.row.latestPrecision')}
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_precision}
                      />
                    }
                  />
                  <StatRow
                    label={t('observ.row.latestF1')}
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_f1}
                      />
                    }
                  />
                  <StatRow
                    label={t('observ.row.totalQueries')}
                    value={dashboard.recall_eval.latest.total_queries}
                  />
                </>
              ) : (
                <div className="text-th-text-muted text-xs py-2">
                  {t('observ.notEvaluated')}
                </div>
              )}
            </>
          )}
        </MetricCard>

        {/* 召回率趋势 */}
        <MetricCard
          title={t('observ.card.recallTrend')}
          icon={
            trend && trend.recall_delta < 0 ? (
              <TrendingDown size={16} />
            ) : (
              <TrendingUp size={16} />
            )
          }
          alert={!!trend?.recall_alert || !!trend?.precision_alert}
          alertLabel={t('observ.status.alert')}
        >
          <EmptyOrLoading
            t={t}
            loading={loading && !trend}
            error={errors.trend ?? null}
            empty={!!trend && trend.samples < 2}
          />
          {trend && trend.samples >= 2 && trend.current && trend.baseline && (
            <>
              <StatRow
                label={t('observ.row.k')}
                value={trend.samples}
              />
              <StatRow
                label={t('observ.row.recallTrendPair')}
                value={
                  <>
                    <PercentBadge value={trend.baseline.avg_recall} />
                    <span className="mx-1 text-th-text-muted">→</span>
                    <PercentBadge value={trend.current.avg_recall} />
                  </>
                }
              />
              <StatRow
                label={t('observ.row.recallDelta')}
                value={
                  <DeltaBadge value={trend.recall_delta} alert={trend.recall_alert} />
                }
              />
              <StatRow
                label={t('observ.row.precisionDelta')}
                value={
                  <DeltaBadge value={trend.precision_delta} alert={trend.precision_alert} />
                }
              />
              <StatRow
                label={t('observ.row.f1Delta')}
                value={<DeltaBadge value={trend.f1_delta} />}
              />
              {trend.alert_messages.length > 0 && (
                <div className="mt-3 p-2 rounded bg-rose-500/10 border border-rose-500/30">
                  {trend.alert_messages.map((m, i) => (
                    <div key={i} className="text-xs text-rose-700 flex items-start gap-1">
                      <AlertTriangle size={10} className="mt-0.5 shrink-0" />
                      <span>{m}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </MetricCard>

        {/* 监测条件健康度 */}
        <MetricCard
          title={t('observ.card.conditionHealth')}
          icon={<Activity size={16} />}
        >
          <EmptyOrLoading
            t={t}
            loading={loading && !conditionHealth}
            error={errors.condition ?? null}
          />
          {conditionHealth && (
            <div className="space-y-3">
              {Object.entries(conditionHealth).map(([key, health]) => (
                <div
                  key={key}
                  className="border-t border-th-border first:border-t-0 pt-2 first:pt-0"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-th-text-secondary">
                      {t(`cond.${key}` as const) || key}
                      <span className="ml-1 font-mono text-th-text-muted">{key}</span>
                    </span>
                    <span className="text-xs text-th-text-muted">
                      {health.approved}/{health.rejected}/{health.pending}
                      <span className="ml-1 text-th-text-muted">
                        ({t('observ.legendApproveRejectPending')})
                      </span>
                    </span>
                  </div>
                  <div className="text-xs text-th-text-muted">
                    {health.suggestion_code
                      ? t(
                          `condhealth.suggest.${health.suggestion_code}` as const,
                          (health.suggestion_params ?? {}) as Record<string, string | number>,
                        )
                      : health.tuning_suggestion}
                  </div>
                  {health.common_reject_reasons.length > 0 && (
                    <div className="mt-1 text-xs text-th-text-muted">
                      <span className="font-medium">{t('observ.commonRejectReasons')}:</span>{' '}
                      {health.common_reject_reasons.join('；')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </MetricCard>
      </div>

      {/* M12 #4 召回评估历史趋势曲线 */}
      <div className="mt-4 rounded-card border border-th-border bg-elevated p-4">
        <RecallTrendChart projectId={projectId} limit={30} />
      </div>

      {import.meta.env.DEV && (
        <div className="mt-6 text-xs text-th-text-muted text-center font-mono">
          <BarChart3 size={12} className="inline mr-1" />
          GET /api/v1/observability/{`{`}dashboard,trend,condition-health,recall-eval/reports{`}`}
        </div>
      )}
    </div>
  );
}

// ── 状态徽章 ──

function StatusBadge({ status, t }: {
  status: string;
  t: (k: string) => string;
}) {
  const classMap: Record<string, string> = {
    watching:    'bg-emerald-500/10 text-emerald-700',
    alert:       'bg-rose-500/10 text-rose-700',
    expired:     'bg-th-border text-th-text-muted',
    rolled_back: 'bg-amber-500/10 text-amber-700',
  };
  const className = classMap[status] ?? 'bg-th-border text-th-text-muted';
  const labelKey = `observ.status.${status}`;
  const label = t(labelKey);
  // 若字典未命中则 t() 返回 key 本身，回落 status 字符串
  const finalLabel = label === labelKey ? status : label;
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${className}`}>
      {finalLabel}
    </span>
  );
}

// ── delta 徽章 ──

function DeltaBadge({ value, alert }: { value: number; alert?: boolean }) {
  const sign = value > 0 ? '+' : '';
  const className = alert
    ? 'text-rose-600 font-medium'
    : value > 0
    ? 'text-emerald-700'
    : value < 0
    ? 'text-rose-600'
    : 'text-th-text-muted';
  return (
    <span className={className}>
      {sign}{(value * 100).toFixed(1)}pp
    </span>
  );
}
