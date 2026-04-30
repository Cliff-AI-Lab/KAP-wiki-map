/**
 * RecallTrendChart — 召回评估历史趋势 line chart（M12 #4）。
 *
 * 消费 GET /api/v1/observability/recall-eval/reports；
 * 按 created_at 升序展开 avg_recall / avg_precision / avg_f1 三条线。
 */
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { Loader2, TrendingUp } from 'lucide-react';

import {
  fetchRecallReports, type RecallReportSummary,
} from '@/services/observabilityApi';

interface Props {
  projectId?: string;
  limit?: number;
}

interface ChartPoint {
  /** X 轴标签（短日期） */
  label: string;
  recall: number;
  precision: number;
  f1: number;
}

function shortenDate(iso: string): string {
  // "2026-04-30T05:12:34" → "04-30 05:12"
  if (!iso) return '';
  const t = new Date(iso);
  if (isNaN(t.getTime())) return iso;
  const m = (t.getMonth() + 1).toString().padStart(2, '0');
  const d = t.getDate().toString().padStart(2, '0');
  const hh = t.getHours().toString().padStart(2, '0');
  const mm = t.getMinutes().toString().padStart(2, '0');
  return `${m}-${d} ${hh}:${mm}`;
}

export default function RecallTrendChart({ projectId, limit = 30 }: Props) {
  const [reports, setReports] = useState<RecallReportSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchRecallReports(projectId, limit)
      .then((rs) => {
        if (cancelled) return;
        setReports(rs);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, limit]);

  if (loading) {
    return (
      <div className="text-xs text-th-text-muted py-6 text-center">
        <Loader2 size={14} className="inline animate-spin mr-2" /> 加载历史报告...
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-xs text-rose-600 py-4">加载失败：{error}</div>
    );
  }
  if (!reports || reports.length === 0) {
    return (
      <div className="text-xs text-th-text-muted py-6 text-center border border-dashed border-th-border rounded-card">
        尚无评估报告（先在 SME 端运行 recall-eval）
      </div>
    );
  }

  // reports 按 created_at desc；图表需要 asc
  const data: ChartPoint[] = [...reports].reverse().map((r) => ({
    label: shortenDate(r.created_at),
    recall: r.avg_recall,
    precision: r.avg_precision,
    f1: r.avg_f1,
  }));

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={14} className="text-accent" />
        <span className="text-sm font-mono text-th-text-muted">
          召回评估历史（最近 {data.length} 份）
        </span>
      </div>
      <div className="w-full" style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.15)" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: 'rgba(148, 163, 184, 0.85)' }}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.3)' }}
            />
            <YAxis
              domain={[0, 1]}
              tick={{ fontSize: 10, fill: 'rgba(148, 163, 184, 0.85)' }}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.3)' }}
              tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                background: 'rgba(15, 23, 42, 0.92)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: 6,
                color: 'rgba(226, 232, 240, 0.95)',
              }}
              formatter={(value: any, name: any) => {
                const n = typeof value === 'number' ? value : Number(value);
                return [`${(n * 100).toFixed(1)}%`, String(name)];
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              iconType="circle"
            />
            <Line
              type="monotone" dataKey="recall" stroke="#10b981"
              strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }}
              name="recall"
            />
            <Line
              type="monotone" dataKey="precision" stroke="#3b82f6"
              strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }}
              name="precision"
            />
            <Line
              type="monotone" dataKey="f1" stroke="#f59e0b"
              strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }}
              name="f1"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
