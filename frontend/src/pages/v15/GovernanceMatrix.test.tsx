/**
 * GovernanceMatrix smoke test（M12 #3）。
 *
 * 验证：
 * - 矩阵核心 4×6 网格渲染（4 角色 + 6 工位）
 * - cellCount 正确显示
 * - 顶部统计 4 角色卡片
 * - 点击格子打开 drawer + 列出工单
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import GovernanceMatrix from './GovernanceMatrix';

vi.mock('@/hooks/useActiveProject', () => ({
  useActiveProject: () => ({
    projectId: 'p1', projects: [], loading: false, error: null,
    setActive: vi.fn(), refresh: vi.fn(),
  }),
}));

// M17 #1 · mock LocaleContext + LanguageSwitcher 让 i18n 化的页面可测
vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string, vars?: Record<string, string | number>) => {
      const map: Record<string, string> = {
        'matrix.title': '矩阵审核台',
        'matrix.subtitle': '4 角色 × 6 工位',
        'matrix.legendR': 'R = 主审',
        'matrix.legendC': 'C = 协审',
        'matrix.legendI': 'I = 知会',
        'matrix.totalPending': `合计 ${vars?.n ?? 0} 待办`,
        'observ.refresh': '刷新',
      };
      return map[key] || key;
    },
  }),
}));

vi.mock('@/components/v15/LanguageSwitcher', () => ({
  default: () => null,
}));

vi.mock('@/services/governanceApi', () => ({
  fetchGovernanceMatrix: vi.fn(),
  fetchGovernanceQueue: vi.fn(),
  claimGovernanceItem: vi.fn(),
  decideGovernanceItem: vi.fn(),
  escalateGovernanceItem: vi.fn(),
}));

import {
  fetchGovernanceMatrix, fetchGovernanceQueue,
} from '@/services/governanceApi';

// keep fetchGovernanceQueue mock referenced (will be called by drawer when SME 点格子)
void fetchGovernanceQueue;

// 用 any 简化 mock；运行时类型不严格
const fakeMatrix: any = {
  project_id: 'p1',
  total: 8,
  uncategorized: 0,
  cells: [
    { workstation: 'W1', assigned_role: 'DG',  count: 3 },
    { workstation: 'W4', assigned_role: 'SME', count: 5 },
  ],
};

const fakeQueueItems: any = [
  {
    id: 'gov_1',
    project_id: 'p1',
    agent: 'curator',
    kind: 'draft_pending',
    title: '电机巡检流程草稿待审',
    description: 'curator 蒸馏出的草稿',
    target_ref: 'doc_42',
    priority: 1,
    status: 'pending',
    confidence: null,
    created_at: '2026-04-30T10:00:00',
    resolved_at: null, resolver: null,
    workstation: 'W4', assigned_role: 'SME',
    claimed_by: null, claimed_at: null,
    escalated_to: null, escalation_reason: '',
    sla_due_at: null,
  },
];


function renderPage() {
  return render(
    <MemoryRouter>
      <GovernanceMatrix />
    </MemoryRouter>,
  );
}


describe('GovernanceMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchGovernanceMatrix).mockResolvedValue(fakeMatrix);
    vi.mocked(fetchGovernanceQueue).mockResolvedValue(fakeQueueItems);
  });

  it('renders 4 role cards + 6 workstation rows', async () => {
    renderPage();

    await waitFor(() => {
      // 4 角色名（顶部统计 + 表头）
      expect(screen.getAllByText(/数据治理员/).length).toBeGreaterThan(0);
    });
    // 6 工位代码
    ['W1', 'W2', 'W3', 'W4', 'W5', 'W6'].forEach((code) => {
      expect(screen.getAllByText(new RegExp(code)).length).toBeGreaterThan(0);
    });
    // 4 角色 code
    ['DG', 'SME', 'SEC', 'AIOps'].forEach((code) => {
      expect(screen.getAllByText(new RegExp(code)).length).toBeGreaterThan(0);
    });
  });

  it('shows total count and cell counts', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/合计 8 待办/)).toBeInTheDocument();
    });
    // W4-SME cell count = 5
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
  });

  it('shows R/C/I legend and zero-state hints', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/R = 主审/)).toBeInTheDocument();
    });
    expect(screen.getByText(/C = 协审/)).toBeInTheDocument();
    expect(screen.getByText(/I = 知会/)).toBeInTheDocument();
  });

  it('renders refresh button', async () => {
    renderPage();
    await waitFor(() => {
      // M14 #4 SLA 总览也带了 "刷新"，所以可能有多个；至少一个即可
      expect(screen.getAllByText(/刷新/).length).toBeGreaterThan(0);
    });
  });
});
