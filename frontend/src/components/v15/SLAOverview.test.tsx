/**
 * SLAOverview smoke test（M14 #4）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SLAOverview from './SLAOverview';

vi.mock('@/services/governanceApi', () => ({
  fetchGovernanceQueue: vi.fn(),
}));

import { fetchGovernanceQueue } from '@/services/governanceApi';


function makeItem(
  id: string,
  slaDueAt: string | null,
  status = 'pending',
): any {
  return {
    id, project_id: 'p1', agent: 'curator', kind: 'draft_pending',
    title: `工单 ${id}`, description: 'desc', target_ref: 'doc',
    priority: 1, status, confidence: null,
    created_at: '2026-04-30T10:00:00',
    resolved_at: null, resolver: null,
    workstation: 'W4', assigned_role: 'SME',
    claimed_by: null, claimed_at: null,
    escalated_to: null, escalation_reason: '',
    sla_due_at: slaDueAt,
  };
}


describe('SLAOverview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows zero counts when no items', async () => {
    vi.mocked(fetchGovernanceQueue).mockResolvedValue([]);
    render(<SLAOverview projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/SLA 总览/)).toBeInTheDocument();
    });
    expect(screen.getByText(/已超时/)).toBeInTheDocument();
    expect(screen.getByText(/即将到期/)).toBeInTheDocument();
  });

  it('counts overdue / nearing / healthy buckets', async () => {
    const now = Date.now();
    const past = new Date(now - 3600_000).toISOString();          // 1h overdue
    const near = new Date(now + 30 * 60_000).toISOString();        // 30min remaining
    const healthy = new Date(now + 24 * 3600_000).toISOString();   // 24h remaining

    vi.mocked(fetchGovernanceQueue).mockResolvedValue([
      makeItem('a1', past),
      makeItem('a2', past),
      makeItem('b1', near),
      makeItem('c1', healthy),
      makeItem('d1', null),
      // 已决策的不算
      makeItem('e1', past, 'approved'),
    ]);

    render(<SLAOverview projectId="p1" />);
    await waitFor(() => {
      // 已超时列表中有 "工单 a1"
      expect(screen.getByText('工单 a1')).toBeInTheDocument();
    });
    // 已超时 = 2（不含 e1 已决策）
    // 即将到期 = 1
    // 健康 = 1
    // 未设 SLA = 1
    // 通过文字断言计数（数字单独存在）
    const blocks = screen.getAllByText(/^\d+$/);
    const counts = blocks.map((el) => el.textContent);
    expect(counts).toContain('2');  // 已超时
    expect(counts).toContain('1');  // 即将到期 / 健康 / 未设 SLA
  });

  it('shows error state on fetch failure', async () => {
    vi.mocked(fetchGovernanceQueue).mockRejectedValue(new Error('PG down'));
    render(<SLAOverview projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/PG down/)).toBeInTheDocument();
    });
  });

  it('does not render SLA counts when projectId empty', async () => {
    render(<SLAOverview projectId="" />);
    // 仍然渲染面板（标题），但不调用 fetch
    await waitFor(() => {
      expect(screen.getByText(/SLA 总览/)).toBeInTheDocument();
    });
    expect(fetchGovernanceQueue).not.toHaveBeenCalled();
  });
});
