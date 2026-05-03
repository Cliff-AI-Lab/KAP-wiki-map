/**
 * WikiQualityDashboard — Wiki 编译质量看板（M18 #2）。
 *
 * 三块：
 *   1. 聚合摘要卡（total_scored / alerting_count / avg_overall）
 *   2. 6 维雷达图（recharts RadarChart）
 *   3. 告警页清单（quality_alert=true 的页面表格）
 *
 * 数据源：M17 #3 后端 /observability/wiki-quality + /aggregate
 */
import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, BarChart3, Loader2, RefreshCw, Target, TrendingDown, TrendingUp,
} from 'lucide-react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts';

import {
  fetchWikiQualityAggregate, fetchWikiQualityList, fetchWikiQualityTrend,
  type WikiQualityAggregate, type WikiQualityScore, type WikiQualityTrend,
} from '@/services/observabilityApi';
import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';

const DIMENSIONS = [
  'consistency', 'completeness', 'evidence',
  'repetition', 'freshness', 'cross_domain',
] as const;
type DimKey = (typeof DIMENSIONS)[number];

export default function WikiQualityDashboard() {
  const { projectId: activeProjectId } = useActiveProject();
  const { t } = useLocale();
  const projectId = activeProjectId || undefined;

  const [agg, setAgg] = useState<WikiQualityAggregate | null>(null);
  const [scores, setScores] = useState<WikiQualityScore[]>([]);
  const [trend, setTrend] = useState<WikiQualityTrend | null>(null);
  const [onlyAlerting, setOnlyAlerting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [aggRes, listRes, trendRes] = await Promise.all([
        fetchWikiQualityAggregate(projectId),
        fetchWikiQualityList({ projectId, onlyAlerting }),
        fetchWikiQualityTrend({ projectId, bucketSize: 10, maxBuckets: 30 }),
      ]);
      setAgg(aggRes);
      setScores(listRes);
      setTrend(trendRes);
    } catch (e) {
      setError((e as Error).message || 'load failed');
    } finally {
      setLoading(false);
    }
  }, [projectId, onlyAlerting]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const radarData = agg
    ? DIMENSIONS.map(dim => ({
        dim: t(`wq.dim.${dim}` as const),
        value: Number((agg.avg_dimensions[dim] ?? 0).toFixed(3)),
      }))
    : [];

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary">
            {t('wq.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            {t('wq.subtitle')}
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
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('observ.refresh')}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-card border border-rose-500/40 bg-rose-50/40 text-rose-700 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* 聚合摘要卡 */}
        <div className="rounded-card border border-th-border p-4 bg-elevated">
          <div className="flex items-center gap-2 mb-3">
            <Target size={16} className="text-accent" />
            <h3 className="text-sm font-mono text-th-text-muted">
              {t('wq.aggCard')}
            </h3>
          </div>
          {!agg ? (
            <div className="text-th-text-muted text-xs py-4">{t('observ.empty')}</div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              <Stat label={t('wq.totalScored')} value={agg.total_scored} />
              <Stat
                label={t('wq.alertingCount')}
                value={agg.alerting_count}
                alert={agg.alerting_count > 0}
              />
              <Stat
                label={t('wq.avgOverall')}
                value={(agg.avg_overall * 100).toFixed(1) + '%'}
              />
            </div>
          )}
        </div>

        {/* 6 维雷达 */}
        <div className="rounded-card border border-th-border p-4 bg-elevated">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={16} className="text-accent" />
            <h3 className="text-sm font-mono text-th-text-muted">
              {t('wq.radar')}
            </h3>
          </div>
          {radarData.length === 0 ? (
            <div className="text-th-text-muted text-xs py-4">{t('observ.empty')}</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#cbd5e1" />
                <PolarAngleAxis dataKey="dim" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
                <Radar
                  name="avg"
                  dataKey="value"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.35}
                />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* M19 #1 · 历史趋势线图 */}
      {trend && trend.samples > 0 && (
        <div className="mb-6 rounded-card border border-th-border p-4 bg-elevated">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              {trend.trend_alert ? (
                <TrendingDown size={16} className="text-rose-600" />
              ) : (
                <TrendingUp size={16} className="text-emerald-600" />
              )}
              <h3 className="text-sm font-mono text-th-text-muted">
                {t('wq.trend')}
              </h3>
              {trend.trend_alert && (
                <span className="text-xs text-rose-600 font-medium">
                  {t('wq.trendAlert')}
                </span>
              )}
            </div>
            <span className="text-xs text-th-text-muted">
              {t('wq.trendDelta')}:{' '}
              <span
                className={`tabular-nums ${
                  trend.delta < 0 ? 'text-rose-600' : 'text-emerald-700'
                }`}
              >
                {(trend.delta * 100).toFixed(2)}pp
              </span>
            </span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart
              data={trend.buckets.map((b, i) => ({
                idx: i,
                avg: Number((b.avg_overall * 100).toFixed(2)),
                count: b.count,
                alerting: b.alerting,
              }))}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="idx" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="avg"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 告警 / 全量列表 */}
      <div className="rounded-card border border-th-border bg-elevated">
        <div className="flex items-center justify-between p-4 border-b border-th-border">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-rose-600" />
            <h3 className="text-sm font-mono text-th-text-muted">
              {t('wq.alertList')}
            </h3>
          </div>
          <label className="flex items-center gap-2 text-xs text-th-text-muted">
            <input
              type="checkbox"
              checked={onlyAlerting}
              onChange={e => setOnlyAlerting(e.target.checked)}
            />
            {t('wq.filterAlerting')}
          </label>
        </div>

        {scores.length === 0 ? (
          <div className="p-6 text-center text-th-text-muted text-sm">
            {t('wq.emptyClean')}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-th-bg-subtle text-th-text-muted text-xs">
              <tr>
                <th className="text-left p-2 font-mono">{t('wq.col.page')}</th>
                <th className="text-left p-2 font-mono">{t('wq.col.type')}</th>
                <th className="text-right p-2 font-mono">{t('wq.col.overall')}</th>
                <th className="text-left p-2 font-mono">{t('wq.col.scoredAt')}</th>
              </tr>
            </thead>
            <tbody>
              {scores.map(s => (
                <tr
                  key={s.page_id}
                  className={`border-t border-th-border ${
                    s.quality_alert ? 'bg-rose-50/40' : ''
                  }`}
                >
                  <td className="p-2 font-mono text-xs">{s.page_id}</td>
                  <td className="p-2 text-xs text-th-text-muted">{s.page_type}</td>
                  <td
                    className={`p-2 text-right tabular-nums font-medium ${
                      s.quality_alert ? 'text-rose-600' : 'text-th-text-primary'
                    }`}
                  >
                    {(s.overall * 100).toFixed(1)}%
                  </td>
                  <td className="p-2 text-xs text-th-text-muted">
                    {new Date(s.scored_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Stat({
  label, value, alert,
}: { label: string; value: React.ReactNode; alert?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-th-text-muted">{label}</span>
      <span
        className={`text-xl font-semibold tabular-nums ${
          alert ? 'text-rose-600' : 'text-th-text-primary'
        }`}
      >
        {value}
      </span>
    </div>
  );
}
