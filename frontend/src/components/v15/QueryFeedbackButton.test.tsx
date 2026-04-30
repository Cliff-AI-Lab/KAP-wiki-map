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

  it('submits useful=true on thumbs up click', async () => {
    const onSubmitted = vi.fn();
    render(<QueryFeedbackButton queryId="q_test" onSubmitted={onSubmitted} />);

    fireEvent.click(screen.getByTitle('标记为有用'));

    await waitFor(() => {
      expect(submitQueryFeedback).toHaveBeenCalledWith('q_test', true);
    });
    await waitFor(() => {
      expect(onSubmitted).toHaveBeenCalledWith(true);
    });
  });

  it('submits useful=false on thumbs down click', async () => {
    render(<QueryFeedbackButton queryId="q_test" />);
    fireEvent.click(screen.getByTitle('标记为无用'));
    await waitFor(() => {
      expect(submitQueryFeedback).toHaveBeenCalledWith('q_test', false);
    });
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
