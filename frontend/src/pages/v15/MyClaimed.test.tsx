/**
 * MyClaimed smoke test（M13 #2）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MyClaimed from './MyClaimed';

vi.mock('@/hooks/useActiveProject', () => ({
  useActiveProject: () => ({
    projectId: 'p1', projects: [], loading: false, error: null,
    setActive: vi.fn(), refresh: vi.fn(),
  }),
}));

vi.mock('@/hooks/useCurrentUser', () => ({
  useCurrentUser: () => ({ userId: 'admin', setUser: vi.fn() }),
}));

vi.mock('@/services/governanceApi', () => ({
  fetchGovernanceQueue: vi.fn(),
  decideGovernanceItem: vi.fn(),
}));

import {
  fetchGovernanceQueue, decideGovernanceItem,
} from '@/services/governanceApi';


function makeItem(id: string, claimedBy: string, status: string): any {
  return {
    id, project_id: 'p1', agent: 'curator', kind: 'draft_pending',
    title: `工单 ${id}`, description: 'desc', target_ref: 'doc',
    priority: 1, status, confidence: null,
    created_at: '2026-04-30T10:00:00',
    resolved_at: null, resolver: null,
    workstation: 'W4', assigned_role: 'SME',
    claimed_by: claimedBy, claimed_at: '2026-04-30T11:00:00',
    escalated_to: null, escalation_reason: '',
    sla_due_at: null,
  };
}


function renderPage() {
  return render(
    <MemoryRouter>
      <MyClaimed />
    </MemoryRouter>,
  );
}


describe('MyClaimed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchGovernanceQueue).mockResolvedValue([
      makeItem('a1', 'admin', 'reviewing'),
      makeItem('a2', 'admin', 'reviewing'),
      makeItem('b1', 'other_user', 'reviewing'),  // 不属于 admin
      makeItem('a3', 'admin', 'approved'),         // 已决策，不展示
    ]);
    vi.mocked(decideGovernanceItem).mockResolvedValue({} as any);
  });

  it('shows only admin-claimed reviewing items', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('工单 a1')).toBeInTheDocument();
    });
    expect(screen.getByText('工单 a2')).toBeInTheDocument();
    expect(screen.queryByText('工单 b1')).not.toBeInTheDocument();
    expect(screen.queryByText('工单 a3')).not.toBeInTheDocument();
  });

  it('toggles select all', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('工单 a1')).toBeInTheDocument();
    });
    expect(screen.getByText(/已选 0 \/ 2/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('全选'));
    expect(screen.getByText(/已选 2 \/ 2/)).toBeInTheDocument();
  });

  it('bulk approve calls decideGovernanceItem for each selected', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('工单 a1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('全选'));
    fireEvent.click(screen.getByText('批量通过'));

    await waitFor(() => {
      expect(decideGovernanceItem).toHaveBeenCalledTimes(2);
    });
    // 完成 flash
    await waitFor(() => {
      expect(screen.getByText(/批量通过 完成/)).toBeInTheDocument();
    });
  });

  it('shows fallback when no claims', async () => {
    vi.mocked(fetchGovernanceQueue).mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/未找到 admin 认领的工单/)).toBeInTheDocument();
    });
  });
});
