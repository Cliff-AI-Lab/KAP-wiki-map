/**
 * GroundTruthReview smoke test（M11 #3）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import GroundTruthReview from './GroundTruthReview';

vi.mock('@/hooks/useActiveProject', () => ({
  useActiveProject: () => ({
    projectId: 'p1', projects: [], loading: false, error: null,
    setActive: vi.fn(), refresh: vi.fn(),
  }),
}));

vi.mock('@/services/observabilityApi', () => ({
  fetchGroundTruthCandidates: vi.fn(),
  fetchGroundTruthList: vi.fn(),
  addGroundTruth: vi.fn(),
  deleteGroundTruth: vi.fn(),
}));

import {
  fetchGroundTruthCandidates,
  fetchGroundTruthList,
  addGroundTruth,
  deleteGroundTruth,
} from '@/services/observabilityApi';

const fakeCandidates = [
  {
    candidate_id: 'gtc_1',
    project_id: 'p1',
    query_text: '电机故障如何处理',
    proposed_doc_ids: ['doc_a', 'doc_b'],
    sample_size: 5,
    useful_rate: 1.0,
    reasoning: '5 次查询，5 次反馈，5 useful（占 100%）; doc_ids 来源: intersection',
  },
];

const fakeExisting = [
  {
    gt_id: 'gt_existing',
    project_id: 'p1',
    query_text: '已入库问题',
    expected_doc_ids: ['x', 'y', 'z'],
    note: 'demo',
    created_at: '2026-04-30T00:00:00',
  },
];


describe('GroundTruthReview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchGroundTruthCandidates).mockResolvedValue(fakeCandidates);
    vi.mocked(fetchGroundTruthList).mockResolvedValue(fakeExisting);
    vi.mocked(addGroundTruth).mockResolvedValue({
      gt_id: 'gt_new',
      project_id: 'p1',
      query_text: '电机故障如何处理',
      expected_doc_ids: ['doc_a', 'doc_b'],
      note: '',
      created_at: '2026-04-30T01:00:00',
    });
    vi.mocked(deleteGroundTruth).mockResolvedValue({
      gt_id: 'gt_existing', removed: true,
    });
  });

  it('renders candidate cards and existing GT list', async () => {
    render(<GroundTruthReview />);

    await waitFor(() => {
      expect(screen.getByText('电机故障如何处理')).toBeInTheDocument();
    });
    // useful_rate 100% 来自卡片右上角徽章
    expect(screen.getByText(/useful_rate 100%/)).toBeInTheDocument();
    expect(screen.getByText('已入库问题')).toBeInTheDocument();
  });

  it('confirms a candidate via add API', async () => {
    render(<GroundTruthReview />);

    await waitFor(() => {
      expect(screen.getByText('电机故障如何处理')).toBeInTheDocument();
    });

    const confirmBtn = screen.getByText(/确认入库/);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(addGroundTruth).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: 'p1',
          query_text: '电机故障如何处理',
          expected_doc_ids: ['doc_a', 'doc_b'],
        }),
      );
    });

    // 入库成功 flash 显示
    await waitFor(() => {
      expect(screen.getByText(/入库成功/)).toBeInTheDocument();
    });
  });

  it('skips a candidate locally (no API call)', async () => {
    render(<GroundTruthReview />);
    await waitFor(() => {
      expect(screen.getByText('电机故障如何处理')).toBeInTheDocument();
    });

    const skipBtn = screen.getByText(/跳过/);
    fireEvent.click(skipBtn);

    await waitFor(() => {
      expect(screen.queryByText('电机故障如何处理')).not.toBeInTheDocument();
    });
    expect(addGroundTruth).not.toHaveBeenCalled();
  });

  it('shows fallback text when no candidates', async () => {
    vi.mocked(fetchGroundTruthCandidates).mockResolvedValue([]);
    render(<GroundTruthReview />);
    await waitFor(() => {
      expect(screen.getByText(/暂无候选/)).toBeInTheDocument();
    });
  });
});
