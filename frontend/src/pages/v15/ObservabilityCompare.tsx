/**
 * ObservabilityCompare — 多 project 横评仪表盘（M13 #3）。
 *
 * 一次拉 GET /api/v1/observability/dashboard/multi 全部 project 摘要，
 * 表格形式并排展示 4 维度指标，让运营快速横向对比。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Loader2, RefreshCw, Layers, AlertTriangle, BarChart3,
} from 'lucide-react';

import {
  fetchDashboardMulti, type DashboardMulti, type DashboardMultiRow,
} from '@/services/observabilityApi';
import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';


function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}


function ProjectRow({ row }: { row: DashboardMultiRow }) {
  const recall = row.recall_eval.latest;
  return (
    <tr className="border-t border-th-border hover:bg-hover/40 transition">
      <td className="px-3 py-2 font-mono text-xs text-th-text-primary">
        {row.project_id}
      </td>
      {/* decisions */}
      <td className="px-3 py-2 text-xs">
        {row.decisions.total}
        <span className="ml-1 text-th-text-muted">
          ({pct(row.decisions.approval_rate)})
        </span>
      </td>
      {/* queries */}
      <td className="px-3 py-2 text-xs">
        {row.queries.total}
        <span className="ml-1 text-th-text-muted">
          ({pct(row.queries.hit_rate)})
        </span>
      </td>
      <td className="px-3 py-2 text-xs">
        {pct(row.queries.useful_rate)}
        <span className="ml-1 text-th-text-muted">
          ({row.queries.feedback_total})
        </span>
      </td>
      <td className="px-3 py-2 text-xs">
        {row.queries.avg_latency_ms.toFixed(0)}/{row.queries.p95_latency_ms}ms
      </td>
      {/* observations */}
      <td className="px-3 py-2 text-xs">
        {row.observations.active} / {row.observations.total}
        {row.observations.alerting > 0 && (
          <span className="ml-1 text-rose-600">
            <AlertTriangle size={10} className="inline" />
            {row.observations.alerting}
          </span>
        )}
      </td>
      {/* recall_eval */}
      <td className="px-3 py-2 text-xs">{row.recall_eval.ground_truth_count}</td>
      <td className="px-3 py-2 text-xs">
        {recall ? (
          <span>
            R {pct(recall.avg_recall)} · P {pct(recall.avg_precision)} ·
            F1 {pct(recall.avg_f1)}
            <span className="ml-1 text-th-text-muted">@{recall.k}</span>
          </span>
        ) : (
          <span className="text-th-text-muted">未评估</span>
        )}
      </td>
    </tr>
  );
}


export default function ObservabilityCompare() {
  const { t } = useLocale();
  const [data, setData] = useState<DashboardMulti | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchDashboardMulti();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary flex items-center gap-2">
            <Layers size={20} className="text-accent" />
            {t('compare.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            {t('compare.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-btn border border-th-border px-3 py-1.5 text-sm text-th-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('observ.refresh')}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2 rounded text-xs bg-rose-500/10 text-rose-700 border border-rose-500/40">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="text-xs text-th-text-muted py-12 text-center">
          <Loader2 size={14} className="inline animate-spin mr-2" /> 加载中...
        </div>
      )}

      {data && data.rows.length === 0 && !loading && (
        <div className="text-xs text-th-text-muted py-8 text-center border border-dashed border-th-border rounded-card">
          {t('compare.empty')}
        </div>
      )}

      {data && data.rows.length > 0 && (
        <div className="rounded-card border border-th-border bg-elevated overflow-x-auto">
          <table className="min-w-full text-left">
            <thead className="text-xs font-mono text-th-text-muted">
              <tr className="border-b border-th-border">
                <th className="px-3 py-2">{t('compare.col.project')}</th>
                <th className="px-3 py-2">{t('compare.col.decisions')}</th>
                <th className="px-3 py-2">{t('compare.col.queries')}</th>
                <th className="px-3 py-2">{t('compare.col.useful')}</th>
                <th className="px-3 py-2">{t('compare.col.latency')}</th>
                <th className="px-3 py-2">{t('compare.col.observations')}</th>
                <th className="px-3 py-2">{t('compare.col.gt')}</th>
                <th className="px-3 py-2">{t('compare.col.recall')}</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <ProjectRow key={r.project_id} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 text-xs text-th-text-muted text-center">
        <BarChart3 size={12} className="inline mr-1" />
        数据来自 GET /api/v1/observability/dashboard/multi
      </div>
    </div>
  );
}
