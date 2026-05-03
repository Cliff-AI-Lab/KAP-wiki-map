/**
 * ObservabilityDashboard smoke test（M11 #2）。
 *
 * 范围：
 * - mock 三个 fetch 端点（dashboard / trend / condition-health）
 * - 渲染后验证关键文字出现（卡片标题 + 主指标值）
 * - 单端点失败时其他卡片仍渲染（Promise.allSettled 行为验证）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ObservabilityDashboard from './ObservabilityDashboard';

// mock useActiveProject 直接返回固定 project
vi.mock('@/hooks/useActiveProject', () => ({
  useActiveProject: () => ({
    projectId: 'test-project',
    projects: [],
    loading: false,
    error: null,
    setActive: vi.fn(),
    refresh: vi.fn(),
  }),
}));

// M16 #1 · mock LocaleContext 提供静态 zh 翻译
vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh',
    setLocale: vi.fn(),
    t: (key: string) => {
      const map: Record<string, string> = {
        'observ.dashboard.title': '运营观察仪表盘',
        'observ.dashboard.subtitle': 'KAP IP 引擎全维度运营观察',
        'observ.refresh': '刷新',
        'observ.card.decisions': '演化决策',
        'observ.card.queries': '查询召回',
        'observ.card.observations': '7 天观察期',
        'observ.card.recallEval': '召回评估',
        'observ.card.recallTrend': '召回率趋势',
        'observ.card.conditionHealth': '监测条件健康度',
        'observ.alert': '告警',
        'observ.empty': '暂无数据',
        'observ.loading': '加载中...',
        'observ.feedbackReasons.title': '反馈原因 Top 5',
        'observ.feedbackReasons.empty': '暂无负反馈',
        'observ.feedbackReasons.totalNegFeedback': '负反馈样本',
        'common.loading': '加载中...',
        'common.loadFailed': '加载失败',
        'observ.fetchFailed': '请求失败',
        'observ.gtSet': 'Ground Truth 集',
        'observ.notEvaluated': '尚未运行评估',
        'observ.status.alert': '告警',
      };
      return map[key] || key;
    },
  }),
}));

// mock observabilityApi 四个 fetch（M12 #4 加 fetchRecallReports）
vi.mock('@/services/observabilityApi', async () => {
  return {
    fetchDashboard: vi.fn(),
    fetchRecallTrend: vi.fn(),
    fetchConditionHealth: vi.fn(),
    fetchRecallReports: vi.fn(),
  };
});

import {
  fetchDashboard, fetchRecallTrend, fetchConditionHealth,
  fetchRecallReports,
} from '@/services/observabilityApi';

const fakeDashboard = {
  window: { since: null, until: null, project_id: 'test-project' },
  decisions: {
    total: 10,
    by_type: { approve_proposal: 6, reject_proposal: 2, promote: 2 },
    approval_rate: 0.75,
    promote_rollback_ratio: 2.0,
    window: { since: null, until: null, project_id: 'test-project' },
  },
  queries: {
    total: 100,
    hits: 80,
    hit_rate: 0.8,
    avg_latency_ms: 120.5,
    p95_latency_ms: 250,
    feedback_total: 30,
    useful_count: 25,
    useful_rate: 0.833,
    feedback_coverage: 0.3,
    window: { since: null, until: null, project_id: 'test-project' },
  },
  observations: {
    total: 2,
    active: 1,
    alerting: 0,
    items: [
      {
        observation_id: 'obs_1',
        project_id: 'test-project',
        version: 'v1',
        status: 'watching' as const,
        alerts_count: 0,
        snapshots_count: 3,
        promoted_at: '2026-04-30T00:00:00',
        expires_at: '2026-05-07T00:00:00',
      },
    ],
  },
  recall_eval: {
    ground_truth_count: 5,
    latest: {
      report_id: 'reval_abc',
      version: 'v1',
      k: 5,
      total_queries: 5,
      avg_recall: 0.85,
      avg_precision: 0.7,
      avg_f1: 0.77,
      created_at: '2026-04-30T01:00:00',
    },
  },
};

const fakeTrend = {
  samples: 3,
  baseline: {
    report_id: 'r1', avg_recall: 0.9, avg_precision: 0.8, avg_f1: 0.85,
    created_at: '2026-04-29T00:00:00',
  },
  current: {
    report_id: 'r3', avg_recall: 0.85, avg_precision: 0.7, avg_f1: 0.77,
    created_at: '2026-04-30T00:00:00',
  },
  recall_delta: -0.05,
  precision_delta: -0.10,
  f1_delta: -0.08,
  recall_alert: false,
  precision_alert: false,
  alert_messages: [],
};

const fakeConditionHealth = {
  new_entity_type: {
    condition_type: 'new_entity_type',
    total: 8, approved: 6, rejected: 2, pending: 0,
    approve_rate: 0.75,
    common_reject_reasons: [],
    tuning_suggestion: '接受率高 (75%)，prompt 健康',
  },
  relation_solidification: {
    condition_type: 'relation_solidification',
    total: 0, approved: 0, rejected: 0, pending: 0,
    approve_rate: 0.0,
    common_reject_reasons: [],
    tuning_suggestion: '样本不足 (0 < 5)，暂无法评估 prompt 健康度',
  },
  relation_split: {
    condition_type: 'relation_split',
    total: 0, approved: 0, rejected: 0, pending: 0,
    approve_rate: 0.0,
    common_reject_reasons: [],
    tuning_suggestion: '样本不足',
  },
  standard_upgrade: {
    condition_type: 'standard_upgrade',
    total: 0, approved: 0, rejected: 0, pending: 0,
    approve_rate: 0.0,
    common_reject_reasons: [],
    tuning_suggestion: '样本不足',
  },
};


describe('ObservabilityDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchDashboard).mockResolvedValue(fakeDashboard);
    vi.mocked(fetchRecallTrend).mockResolvedValue(fakeTrend);
    vi.mocked(fetchConditionHealth).mockResolvedValue(fakeConditionHealth);
    vi.mocked(fetchRecallReports).mockResolvedValue([]);
  });

  it('renders all 6 cards with key metrics', async () => {
    render(<ObservabilityDashboard />);

    // 卡片标题（每张一个）
    await waitFor(() => {
      expect(screen.getByText(/演化决策/)).toBeInTheDocument();
    });
    expect(screen.getByText(/查询召回/)).toBeInTheDocument();
    expect(screen.getByText(/7 天观察期/)).toBeInTheDocument();
    expect(screen.getByText(/召回评估/)).toBeInTheDocument();
    expect(screen.getByText(/召回率趋势/)).toBeInTheDocument();
    expect(screen.getByText(/监测条件健康度/)).toBeInTheDocument();

    // 决策卡：approval_rate 75.0%
    await waitFor(() => {
      const approvalEls = screen.getAllByText('75.0%');
      expect(approvalEls.length).toBeGreaterThan(0);
    });

    // 查询卡：hit_rate 80.0%
    expect(screen.getByText('80.0%')).toBeInTheDocument();
    // P95 latency 250 ms
    expect(screen.getByText('250')).toBeInTheDocument();

    // 召回评估：avg_recall 85.0% 出现
    expect(screen.getAllByText('85.0%').length).toBeGreaterThan(0);
  });

  it('shows project chip with active project', async () => {
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText('test-project')).toBeInTheDocument();
    });
  });

  it('renders despite trend fetch failure (single card error)', async () => {
    vi.mocked(fetchRecallTrend).mockRejectedValue(new Error('PG down'));

    render(<ObservabilityDashboard />);

    // 其他卡片仍渲染
    await waitFor(() => {
      expect(screen.getByText(/演化决策/)).toBeInTheDocument();
    });
    // trend 卡片显示加载失败
    await waitFor(() => {
      expect(screen.getByText(/加载失败/)).toBeInTheDocument();
    });
  });

  it('renders condition health suggestions', async () => {
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/接受率高/)).toBeInTheDocument();
    });
    // 4 条件 condition_type 名都出现
    expect(screen.getByText('new_entity_type')).toBeInTheDocument();
    expect(screen.getByText('relation_solidification')).toBeInTheDocument();
    expect(screen.getByText('relation_split')).toBeInTheDocument();
    expect(screen.getByText('standard_upgrade')).toBeInTheDocument();
  });

  // M18 #4 · 反馈原因 top 5 横条
  it('renders top feedback reasons panel when feedback_reasons present', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue({
      ...fakeDashboard,
      queries: {
        ...fakeDashboard.queries,
        feedback_reasons: {
          wrong_answer: 8,
          irrelevant: 5,
          format_issue: 3,
          outdated: 2,
          incomplete: 1,
        },
        top_reasons: [
          'wrong_answer', 'irrelevant', 'format_issue',
          'outdated', 'incomplete',
        ],
      },
    });
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/反馈原因 Top 5/)).toBeInTheDocument();
    });
    expect(screen.getByText('wrong_answer')).toBeInTheDocument();
    expect(screen.getByText('irrelevant')).toBeInTheDocument();
    expect(screen.getByText('format_issue')).toBeInTheDocument();
    // 各原因都出现（具体计数避免与其他卡冲突）
    expect(screen.getByText('outdated')).toBeInTheDocument();
    expect(screen.getByText('incomplete')).toBeInTheDocument();
  });

  it('hides feedback reasons panel when none present', async () => {
    // fakeDashboard.queries 没 feedback_reasons → panel 不出现
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/查询召回/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/反馈原因 Top 5/)).not.toBeInTheDocument();
  });
});
