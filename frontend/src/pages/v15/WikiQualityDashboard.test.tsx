/**
 * WikiQualityDashboard smoke test（M18 #2）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import WikiQualityDashboard from './WikiQualityDashboard';

vi.mock('@/services/observabilityApi', () => ({
  fetchWikiQualityAggregate: vi.fn(),
  fetchWikiQualityList: vi.fn(),
  fetchWikiQualityTrend: vi.fn(),
}));

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string) => {
      const map: Record<string, string> = {
        'wq.title': 'Wiki 质量看板',
        'wq.subtitle': '6 维 LLM-Critic',
        'wq.aggCard': '聚合摘要',
        'wq.totalScored': '已评分',
        'wq.alertingCount': '告警',
        'wq.avgOverall': '平均',
        'wq.radar': '雷达',
        'wq.alertList': '告警清单',
        'wq.empty': '暂无',
        'wq.emptyClean': '暂无评分',
        'wq.dim.consistency': '一致性',
        'wq.dim.completeness': '完整性',
        'wq.dim.evidence': '证据',
        'wq.dim.repetition': '去重',
        'wq.dim.freshness': '时效',
        'wq.dim.cross_domain': '跨域',
        'wq.col.page': '页',
        'wq.col.type': '类型',
        'wq.col.overall': '总分',
        'wq.col.scoredAt': '时间',
        'wq.filterAlerting': '只看告警',
        'wq.trend': '历史趋势',
        'wq.trendDelta': 'delta',
        'wq.trendAlert': '趋势告警',
        'observ.refresh': '刷新',
        'observ.empty': '暂无数据',
      };
      return map[key] || key;
    },
  }),
}));

vi.mock('@/components/v15/LanguageSwitcher', () => ({
  default: () => null,
}));

vi.mock('@/hooks/useActiveProject', () => ({
  useActiveProject: () => ({ projectId: 'p1' }),
}));

// recharts 的 ResponsiveContainer 在 happy-dom 没有 ResizeObserver；伪造下尺寸即可
vi.mock('recharts', async (orig) => {
  const real = await orig<typeof import('recharts')>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 600, height: 260 }}>{children}</div>
    ),
  };
});

import {
  fetchWikiQualityAggregate, fetchWikiQualityList,
  fetchWikiQualityTrend,
} from '@/services/observabilityApi';


const fakeAgg = {
  total_scored: 12,
  alerting_count: 3,
  avg_overall: 0.72,
  avg_dimensions: {
    consistency: 0.78, completeness: 0.74, evidence: 0.7,
    repetition: 0.85, freshness: 0.65, cross_domain: 0.6,
  },
};

const fakeList = [
  {
    page_id: 'src/d1', page_type: 'source_summary', project_id: 'p1',
    consistency: { score: 0.4, reason: '不一致' },
    completeness: { score: 0.5, reason: '' },
    evidence: { score: 0.5, reason: '' },
    repetition: { score: 0.6, reason: '' },
    freshness: { score: 0.4, reason: '' },
    cross_domain: { score: 0.5, reason: '' },
    overall: 0.48,
    quality_alert: true,
    error: '',
    scored_at: '2026-05-01T10:00:00',
  },
  {
    page_id: 'energy/maintenance', page_type: 'domain_overview', project_id: 'p1',
    consistency: { score: 0.9, reason: '' },
    completeness: { score: 0.85, reason: '' },
    evidence: { score: 0.85, reason: '' },
    repetition: { score: 0.95, reason: '' },
    freshness: { score: 0.8, reason: '' },
    cross_domain: { score: 0.78, reason: '' },
    overall: 0.86,
    quality_alert: false,
    error: '',
    scored_at: '2026-05-01T11:00:00',
  },
];


describe('WikiQualityDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWikiQualityAggregate).mockResolvedValue(fakeAgg);
    vi.mocked(fetchWikiQualityList).mockResolvedValue(fakeList);
    vi.mocked(fetchWikiQualityTrend).mockResolvedValue({
      samples: 0, buckets: [],
      current_avg_overall: 0, earliest_avg_overall: 0,
      delta: 0, trend_alert: false,
    });
  });

  it('renders aggregate stats and list rows', async () => {
    render(<WikiQualityDashboard />);
    await waitFor(() => {
      expect(screen.getByText('src/d1')).toBeInTheDocument();
    });
    expect(screen.getByText('energy/maintenance')).toBeInTheDocument();
    expect(screen.getByText('72.0%')).toBeInTheDocument();   // avg_overall
    expect(screen.getByText('48.0%')).toBeInTheDocument();   // alerting page
    expect(screen.getByText('86.0%')).toBeInTheDocument();   // healthy page
  });

  it('shows empty state when no scores', async () => {
    vi.mocked(fetchWikiQualityList).mockResolvedValue([]);
    vi.mocked(fetchWikiQualityAggregate).mockResolvedValue({
      total_scored: 0, alerting_count: 0, avg_overall: 0,
      avg_dimensions: {
        consistency: 0, completeness: 0, evidence: 0,
        repetition: 0, freshness: 0, cross_domain: 0,
      },
    });
    render(<WikiQualityDashboard />);
    await waitFor(() => {
      expect(screen.getByText('暂无评分')).toBeInTheDocument();
    });
  });

  it('shows error on aggregate fetch failure', async () => {
    vi.mocked(fetchWikiQualityAggregate).mockRejectedValue(new Error('PG down'));
    render(<WikiQualityDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/PG down/)).toBeInTheDocument();
    });
  });

  it('renders trend chart when buckets exist', async () => {
    vi.mocked(fetchWikiQualityTrend).mockResolvedValue({
      samples: 30,
      buckets: [
        {
          first_at: '2026-04-01T00:00:00', last_at: '2026-04-02T00:00:00',
          count: 10, avg_overall: 0.85, alerting: 0,
        },
        {
          first_at: '2026-04-03T00:00:00', last_at: '2026-04-04T00:00:00',
          count: 10, avg_overall: 0.75, alerting: 1,
        },
        {
          first_at: '2026-04-05T00:00:00', last_at: '2026-04-06T00:00:00',
          count: 10, avg_overall: 0.65, alerting: 3,
        },
      ],
      current_avg_overall: 0.65,
      earliest_avg_overall: 0.85,
      delta: -0.20,
      trend_alert: true,
    });
    render(<WikiQualityDashboard />);
    await waitFor(() => {
      expect(screen.getByText('历史趋势')).toBeInTheDocument();
    });
    expect(screen.getByText(/趋势告警/)).toBeInTheDocument();
    expect(screen.getByText(/-20\.00pp/)).toBeInTheDocument();
  });
});
