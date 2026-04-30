/**
 * QueryFeedbackButton — 问答有用 / 无用反馈按钮（M12 #2）。
 *
 * 接 POST /api/v1/observability/queries/{query_id}/feedback。
 * 已反馈后按钮变高亮态；可再次点击切换。
 */
import { useState } from 'react';
import { ThumbsUp, ThumbsDown, Loader2, Check } from 'lucide-react';

import { submitQueryFeedback } from '@/services/observabilityApi';

interface Props {
  queryId: string;
  /** 紧凑模式：水平排列两个按钮，无文字 */
  compact?: boolean;
  onSubmitted?: (useful: boolean) => void;
}

export default function QueryFeedbackButton({
  queryId, compact = false, onSubmitted,
}: Props) {
  const [submitted, setSubmitted] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<'useful' | 'not_useful' | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!queryId) return null;

  const handle = async (useful: boolean) => {
    setBusy(useful ? 'useful' : 'not_useful');
    setError(null);
    try {
      await submitQueryFeedback(queryId, useful);
      setSubmitted(useful);
      onSubmitted?.(useful);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const baseClass =
    'inline-flex items-center gap-1 px-2 py-1 rounded-btn text-xs font-medium border transition disabled:opacity-40';
  const activeUseful = submitted === true;
  const activeNot = submitted === false;

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => handle(true)}
        className={`${baseClass} ${
          activeUseful
            ? 'border-emerald-500 bg-emerald-500/15 text-emerald-700'
            : 'border-th-border text-th-text-secondary hover:border-emerald-500/40 hover:text-emerald-700'
        }`}
        title="标记为有用"
      >
        {busy === 'useful' ? (
          <Loader2 size={11} className="animate-spin" />
        ) : activeUseful ? (
          <Check size={11} />
        ) : (
          <ThumbsUp size={11} />
        )}
        {!compact && (activeUseful ? '已标记有用' : '有用')}
      </button>

      <button
        type="button"
        disabled={busy !== null}
        onClick={() => handle(false)}
        className={`${baseClass} ${
          activeNot
            ? 'border-rose-500 bg-rose-500/15 text-rose-700'
            : 'border-th-border text-th-text-secondary hover:border-rose-500/40 hover:text-rose-700'
        }`}
        title="标记为无用"
      >
        {busy === 'not_useful' ? (
          <Loader2 size={11} className="animate-spin" />
        ) : (
          <ThumbsDown size={11} />
        )}
        {!compact && (activeNot ? '已标记无用' : '无用')}
      </button>

      {error && (
        <span className="text-[10px] text-rose-600">{error}</span>
      )}
    </div>
  );
}
