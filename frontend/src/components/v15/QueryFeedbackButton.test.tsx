/**
 * QueryFeedbackButton smoke test（M12 #2）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import QueryFeedbackButton from './QueryFeedbackButton';

vi.mock('@/services/observabilityApi', () => ({
  submitQueryFeedback: vi.fn(),
}));

import { submitQueryFeedback } from '@/services/observabilityApi';


describe('QueryFeedbackButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(submitQueryFeedback).mockResolvedValue({
      query_id: 'q_test', useful: true,
    });
  });

  it('returns null when no queryId', () => {
    const { container } = render(<QueryFeedbackButton queryId="" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders both useful and not-useful buttons', () => {
    render(<QueryFeedbackButton queryId="q_test" />);
    expect(screen.getByTitle('标记为有用')).toBeInTheDocument();
    expect(screen.getByTitle('标记为无用')).toBeInTheDocument();
  });

  it('submits useful=true on thumbs up click (no reasons popup)', async () => {
    const onSubmitted = vi.fn();
    render(<QueryFeedbackButton queryId="q_test" onSubmitted={onSubmitted} />);

    fireEvent.click(screen.getByTitle('标记为有用'));

    // M16 #3：useful=true 直接提交（不显示 reasons popup）
    await waitFor(() => {
      expect(submitQueryFeedback).toHaveBeenCalledWith('q_test', true, '', []);
    });
    await waitFor(() => {
      expect(onSubmitted).toHaveBeenCalledWith(true);
    });
  });

  it('thumbs down opens reason popup; submit with selected tags', async () => {
    render(<QueryFeedbackButton queryId="q_test" />);
    fireEvent.click(screen.getByTitle('标记为无用'));

    // M16 #3：useful=false 弹 reason 选项
    await waitFor(() => {
      expect(screen.getByText('答错')).toBeInTheDocument();
    });
    expect(submitQueryFeedback).not.toHaveBeenCalled();

    // 选两个标签
    fireEvent.click(screen.getByText('答错'));
    fireEvent.click(screen.getByText('信息过期'));

    // 点提交
    fireEvent.click(screen.getByText(/提交/));
    await waitFor(() => {
      expect(submitQueryFeedback).toHaveBeenCalledWith(
        'q_test', false, '', ['wrong_answer', 'outdated'],
      );
    });
  });

  it('cancel button closes popup without submit', async () => {
    render(<QueryFeedbackButton queryId="q_test" />);
    fireEvent.click(screen.getByTitle('标记为无用'));
    await waitFor(() => {
      expect(screen.getByText('答错')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText('取消'));
    await waitFor(() => {
      expect(screen.queryByText('答错')).not.toBeInTheDocument();
    });
    expect(submitQueryFeedback).not.toHaveBeenCalled();
  });

  it('shows error message on submit failure', async () => {
    vi.mocked(submitQueryFeedback).mockRejectedValue(new Error('Network down'));

    render(<QueryFeedbackButton queryId="q_test" />);
    fireEvent.click(screen.getByTitle('标记为有用'));

    await waitFor(() => {
      expect(screen.getByText(/Network down/)).toBeInTheDocument();
    });
  });
});
