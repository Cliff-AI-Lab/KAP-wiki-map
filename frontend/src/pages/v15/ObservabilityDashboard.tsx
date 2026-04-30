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
import RecallTrendChart from '@/components/v15/RecallTrendChart';

// ════════════════════════════════════════════════════════════════════════
//  小组件
// ════════════════════════════════════════════════════════════════════════

function MetricCard({
  title, icon, children, alert,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  alert?: boolean;
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
            告警
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

function EmptyOrLoading({ loading, error, empty }: {
  loading: boolean;
  error: string | null;
  empty?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-th-text-muted text-xs py-4">
        <Loader2 size={14} className="animate-spin" /> 加载中...
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-rose-600 text-xs py-4">加载失败：{error}</div>
    );
  }
  if (empty) {
    return (
      <div className="text-th-text-muted text-xs py-4">暂无数据</div>
    );
  }
  return null;
}

function PercentBadge({ value }: { value: number }) {
  const pct = (value * 100).toFixed(1);
  return <span className="tabular-nums">{pct}%</span>;
}

// ════════════════════════════════════════════════════════════════════════
//  主页面
// ════════════════════════════════════════════════════════════════════════

export default function ObservabilityDashboard() {
  const { projectId: activeProjectId } = useActiveProject();
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
    else setErrors(e => ({ ...e, dashboard: dashRes.reason?.message || '请求失败' }));

    if (trendRes.status === 'fulfilled') setTrend(trendRes.value);
    else setErrors(e => ({ ...e, trend: trendRes.reason?.message || '请求失败' }));

    if (condRes.status === 'fulfilled') setConditionHealth(condRes.value);
    else setErrors(e => ({ ...e, condition: condRes.reason?.message || '请求失败' }));

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
            运营观察仪表盘
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            决策书 §5.3 KAP IP 引擎 · 全维度运营观察
            {projectId && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-mono">
                {projectId}
              </span>
            )}
          </p>
        </div>
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
          刷新
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 演化决策 */}
        <MetricCard title="演化决策（M6 #3）" icon={<GitMerge size={16} />}>
          <EmptyOrLoading
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.decisions.total === 0}
          />
          {dashboard && dashboard.decisions.total > 0 && (
            <>
              <StatRow
                label="总决策数"
                value={dashboard.decisions.total}
              />
              <StatRow
                label="本体批准 / 驳回"
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
                label="批准率"
                value={<PercentBadge value={dashboard.decisions.approval_rate} />}
              />
              <StatRow
                label="灰度切换 / 回滚"
                value={
                  <>
                    {dashboard.decisions.by_type.promote ?? 0}
                    <span className="mx-1 text-th-text-muted">/</span>
                    {dashboard.decisions.by_type.rollback ?? 0}
                  </>
                }
              />
              <StatRow
                label="切换 / 回滚比"
                value={dashboard.decisions.promote_rollback_ratio.toFixed(2)}
              />
            </>
          )}
        </MetricCard>

        {/* 查询召回 */}
        <MetricCard title="查询召回（M7+M8）" icon={<Search size={16} />}>
          <EmptyOrLoading
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.queries.total === 0}
          />
          {dashboard && dashboard.queries.total > 0 && (
            <>
              <StatRow
                label="查询总数 / 命中数"
                value={`${dashboard.queries.total} / ${dashboard.queries.hits}`}
              />
              <StatRow
                label="命中率"
                value={<PercentBadge value={dashboard.queries.hit_rate} />}
              />
              <StatRow
                label="平均延时"
                value={`${dashboard.queries.avg_latency_ms.toFixed(0)}`}
                hint="ms"
              />
              <StatRow
                label="P95 延时"
                value={`${dashboard.queries.p95_latency_ms}`}
                hint="ms"
              />
              <StatRow
                label="用户反馈率"
                value={<PercentBadge value={dashboard.queries.feedback_coverage} />}
                hint={`(${dashboard.queries.feedback_total})`}
              />
              <StatRow
                label="有用率"
                value={
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare size={12} className="text-accent" />
                    <PercentBadge value={dashboard.queries.useful_rate} />
                  </span>
                }
              />
            </>
          )}
        </MetricCard>

        {/* 7 天观察期 */}
        <MetricCard
          title="7 天观察期（M5 #2 + M6 #2）"
          icon={<Clock size={16} />}
          alert={!!dashboard && dashboard.observations.alerting > 0}
        >
          <EmptyOrLoading
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
            empty={!!dashboard && dashboard.observations.total === 0}
          />
          {dashboard && dashboard.observations.total > 0 && (
            <>
              <StatRow
                label="活跃观察期"
                value={dashboard.observations.active}
              />
              <StatRow
                label="告警中"
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
                label="历史观察期"
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
                        <StatusBadge status={o.status} />
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
          title="召回评估（M8 #2 + M9）"
          icon={<Target size={16} />}
        >
          <EmptyOrLoading
            loading={loading && !dashboard}
            error={errors.dashboard ?? null}
          />
          {dashboard && (
            <>
              <StatRow
                label="Ground Truth 集"
                value={dashboard.recall_eval.ground_truth_count}
              />
              {dashboard.recall_eval.latest ? (
                <>
                  <StatRow
                    label="最新 avg_recall"
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_recall}
                      />
                    }
                    hint={`@${dashboard.recall_eval.latest.k}`}
                  />
                  <StatRow
                    label="avg_precision"
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_precision}
                      />
                    }
                  />
                  <StatRow
                    label="avg_f1"
                    value={
                      <PercentBadge
                        value={dashboard.recall_eval.latest.avg_f1}
                      />
                    }
                  />
                  <StatRow
                    label="评估 query 数"
                    value={dashboard.recall_eval.latest.total_queries}
                  />
                </>
              ) : (
                <div className="text-th-text-muted text-xs py-2">
                  尚未运行评估
                </div>
              )}
            </>
          )}
        </MetricCard>

        {/* 召回率趋势 */}
        <MetricCard
          title="召回率趋势（M9 #2）"
          icon={
            trend && trend.recall_delta < 0 ? (
              <TrendingDown size={16} />
            ) : (
              <TrendingUp size={16} />
            )
          }
          alert={!!trend?.recall_alert || !!trend?.precision_alert}
        >
          <EmptyOrLoading
            loading={loading && !trend}
            error={errors.trend ?? null}
            empty={!!trend && trend.samples < 2}
          />
          {trend && trend.samples >= 2 && trend.current && trend.baseline && (
            <>
              <StatRow
                label="样本数"
                value={trend.samples}
              />
              <StatRow
                label="召回率（baseline → current）"
                value={
                  <>
                    <PercentBadge value={trend.baseline.avg_recall} />
                    <span className="mx-1 text-th-text-muted">→</span>
                    <PercentBadge value={trend.current.avg_recall} />
                  </>
                }
              />
              <StatRow
                label="召回率 delta"
                value={
                  <DeltaBadge value={trend.recall_delta} alert={trend.recall_alert} />
                }
              />
              <StatRow
                label="精确率 delta"
                value={
                  <DeltaBadge value={trend.precision_delta} alert={trend.precision_alert} />
                }
              />
              <StatRow
                label="F1 delta"
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
          title="监测条件健康度（M10 #2）"
          icon={<Activity size={16} />}
        >
          <EmptyOrLoading
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
                    <span className="text-xs font-mono text-th-text-secondary">
                      {key}
                    </span>
                    <span className="text-xs text-th-text-muted">
                      {health.approved}/{health.rejected}/{health.pending}
                      <span className="ml-1 text-th-text-muted">(批/驳/待)</span>
                    </span>
                  </div>
                  <div className="text-xs text-th-text-muted">
                    {health.tuning_suggestion}
                  </div>
                  {health.common_reject_reasons.length > 0 && (
                    <div className="mt-1 text-xs text-th-text-muted">
                      <span className="font-medium">常见驳回:</span>{' '}
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

      <div className="mt-6 text-xs text-th-text-muted text-center">
        <BarChart3 size={12} className="inline mr-1" />
        数据来自 GET /api/v1/observability/dashboard + /trend + /condition-health + /recall-eval/reports
      </div>
    </div>
  );
}

// ── 状态徽章 ──

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    watching:    { label: '观察中', className: 'bg-emerald-500/10 text-emerald-700' },
    alert:       { label: '告警',   className: 'bg-rose-500/10 text-rose-700' },
    expired:     { label: '已过期', className: 'bg-th-border text-th-text-muted' },
    rolled_back: { label: '已回滚', className: 'bg-amber-500/10 text-amber-700' },
  };
  const cfg = map[status] ?? { label: status, className: 'bg-th-border text-th-text-muted' };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cfg.className}`}>
      {cfg.label}
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
