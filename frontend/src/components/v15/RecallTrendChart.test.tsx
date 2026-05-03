/**
 * RecallTrendChart smoke test（M12 #4）。
 *
 * recharts 在 happy-dom 环境下用 ResponsiveContainer 需要给定容器尺寸；
 * 测试主要验证非图表内容（loading / empty / error）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import RecallTrendChart from './RecallTrendChart';

vi.mock('@/services/observabilityApi', () => ({
  fetchRecallReports: vi.fn(),
}));

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string) => {
      const map: Record<string, string> = {
        'common.loading': '加载历史报告...',
        'common.loadFailed': '加载失败',
        'observ.noReports': '尚无评估报告（先在 SME 端运行 recall-eval）',
      };
      return map[key] || key;
    },
  }),
}));

import { fetchRecallReports } from '@/services/observabilityApi';


describe('RecallTrendChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    vi.mocked(fetchRecallReports).mockImplementation(
      () => new Promise(() => {}),
    );
    render(<RecallTrendChart projectId="p1" />);
    expect(screen.getByText(/加载历史报告/)).toBeInTheDocument();
  });

  it('shows empty state when no reports', async () => {
    vi.mocked(fetchRecallReports).mockResolvedValue([]);
    render(<RecallTrendChart projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/尚无评估报告/)).toBeInTheDocument();
    });
  });

  it('renders chart label when reports loaded', async () => {
    vi.mocked(fetchRecallReports).mockResolvedValue([
      {
        report_id: 'r1', project_id: 'p1', version: 'v1', k: 5,
        total_queries: 5, avg_recall: 0.85, avg_precision: 0.7,
        avg_f1: 0.77, created_at: '2026-04-30T10:00:00',
      },
      {
        report_id: 'r2', project_id: 'p1', version: 'v1', k: 5,
        total_queries: 5, avg_recall: 0.9, avg_precision: 0.75,
        avg_f1: 0.82, created_at: '2026-04-30T11:00:00',
      },
    ]);
    render(<RecallTrendChart projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/召回评估历史/)).toBeInTheDocument();
    });
    // 不严格断言 SVG 内容（recharts ResponsiveContainer 0×0 在 happy-dom 不绘）
  });

  it('shows error state on fetch failure', async () => {
    vi.mocked(fetchRecallReports).mockRejectedValue(new Error('PG down'));
    render(<RecallTrendChart projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    });
  });
});
