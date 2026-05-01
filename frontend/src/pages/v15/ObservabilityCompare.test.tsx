/**
 * ObservabilityCompare smoke test（M13 #3）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ObservabilityCompare from './ObservabilityCompare';

vi.mock('@/services/observabilityApi', () => ({
  fetchDashboardMulti: vi.fn(),
}));

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string) => {
      const map: Record<string, string> = {
        'compare.title': '多 Project 横评仪表盘',
        'compare.subtitle': '4 维度对比',
        'compare.empty': '尚无任何 project',
        'compare.col.project': 'project_id',
        'compare.col.decisions': '决策数',
        'compare.col.queries': '查询数',
        'compare.col.useful': '有用率',
        'compare.col.latency': 'avg/p95',
        'compare.col.observations': '观察期',
        'compare.col.gt': 'GT',
        'compare.col.recall': 'R/P/F1',
        'observ.refresh': '刷新',
      };
      return map[key] || key;
    },
  }),
}));

vi.mock('@/components/v15/LanguageSwitcher', () => ({
  default: () => null,
}));

import { fetchDashboardMulti } from '@/services/observabilityApi';


const fakeMulti = {
  window: { since: null, until: null },
  project_ids: ['p1', 'p2'],
  rows: [
    {
      project_id: 'p1',
      decisions: {
        total: 10, by_type: {}, approval_rate: 0.8,
        promote_rollback_ratio: 2.0,
        window: { since: null, until: null, project_id: 'p1' },
      },
      queries: {
        total: 50, hits: 40, hit_rate: 0.8,
        avg_latency_ms: 120, p95_latency_ms: 250,
        feedback_total: 20, useful_count: 15, useful_rate: 0.75,
        feedback_coverage: 0.4,
        window: { since: null, until: null, project_id: 'p1' },
      },
      observations: { total: 1, active: 1, alerting: 0 },
      recall_eval: {
        ground_truth_count: 5,
        latest: {
          report_id: 'r1', k: 5,
          avg_recall: 0.85, avg_precision: 0.7, avg_f1: 0.77,
          created_at: '2026-04-30T10:00:00',
        },
      },
    },
    {
      project_id: 'p2',
      decisions: {
        total: 3, by_type: {}, approval_rate: 0.66,
        promote_rollback_ratio: 0.0,
        window: { since: null, until: null, project_id: 'p2' },
      },
      queries: {
        total: 8, hits: 5, hit_rate: 0.625,
        avg_latency_ms: 200, p95_latency_ms: 400,
        feedback_total: 0, useful_count: 0, useful_rate: 0,
        feedback_coverage: 0,
        window: { since: null, until: null, project_id: 'p2' },
      },
      observations: { total: 1, active: 0, alerting: 1 },
      recall_eval: {
        ground_truth_count: 0,
        latest: null,
      },
    },
  ],
};


describe('ObservabilityCompare', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchDashboardMulti).mockResolvedValue(fakeMulti);
  });

  it('renders both projects in table', async () => {
    render(<ObservabilityCompare />);
    await waitFor(() => {
      expect(screen.getByText('p1')).toBeInTheDocument();
    });
    expect(screen.getByText('p2')).toBeInTheDocument();
  });

  it('shows R/P/F1 for project with eval; "未评估" for project without', async () => {
    render(<ObservabilityCompare />);
    await waitFor(() => {
      expect(screen.getByText('p1')).toBeInTheDocument();
    });
    expect(screen.getByText(/85\.0%/)).toBeInTheDocument(); // p1 recall
    expect(screen.getByText(/未评估/)).toBeInTheDocument();    // p2
  });

  it('shows fallback when empty', async () => {
    vi.mocked(fetchDashboardMulti).mockResolvedValue({
      window: { since: null, until: null },
      project_ids: [], rows: [],
    });
    render(<ObservabilityCompare />);
    await waitFor(() => {
      expect(screen.getByText(/尚无任何 project/)).toBeInTheDocument();
    });
  });

  it('shows error on fetch failure', async () => {
    vi.mocked(fetchDashboardMulti).mockRejectedValue(new Error('PG down'));
    render(<ObservabilityCompare />);
    await waitFor(() => {
      expect(screen.getByText(/PG down/)).toBeInTheDocument();
    });
  });
});
