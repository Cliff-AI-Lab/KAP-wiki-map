/**
 * QueryFeedbackButton — 问答有用 / 无用反馈按钮（M12 #2 + M16 #3 reasons）。
 *
 * 接 POST /api/v1/observability/queries/{query_id}/feedback。
 * useful=true 直接提交；useful=false 弹出多选标签后提交。
 */
import { useState } from 'react';
import { ThumbsUp, ThumbsDown, Loader2, Check, X } from 'lucide-react';

import { submitQueryFeedback } from '@/services/observabilityApi';

interface Props {
  queryId: string;
  /** 紧凑模式：水平排列两个按钮，无文字 */
  compact?: boolean;
  onSubmitted?: (useful: boolean) => void;
}

const REASON_OPTIONS = [
  { id: 'wrong_answer', label: '答错' },
  { id: 'irrelevant', label: '答非所问' },
  { id: 'format_issue', label: '格式问题' },
  { id: 'outdated', label: '信息过期' },
  { id: 'incomplete', label: '不完整' },
];

export default function QueryFeedbackButton({
  queryId, compact = false, onSubmitted,
}: Props) {
  const [submitted, setSubmitted] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<'useful' | 'not_useful' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showReasons, setShowReasons] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);

  if (!queryId) return null;

  const submitNow = async (useful: boolean, reasons: string[]) => {
    setBusy(useful ? 'useful' : 'not_useful');
    setError(null);
    try {
      await submitQueryFeedback(queryId, useful, '', reasons);
      setSubmitted(useful);
      setShowReasons(false);
      onSubmitted?.(useful);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const handle = async (useful: boolean) => {
    if (useful) {
      // useful=true 直接提交
      await submitNow(true, []);
    } else {
      // useful=false 先弹选项
      setShowReasons(true);
    }
  };

  const toggleReason = (id: string) => {
    setSelectedReasons((prev) =>
      prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id],
    );
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

      {/* M16 #3 · 多选反馈原因 popup */}
      {showReasons && (
        <div className="ml-2 inline-flex items-center gap-1 px-2 py-1 rounded-btn border border-rose-500/40 bg-rose-500/5">
          <span className="text-[10px] text-rose-700 mr-1">原因：</span>
          {REASON_OPTIONS.map((opt) => {
            const sel = selectedReasons.includes(opt.id);
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => toggleReason(opt.id)}
                className={`text-[10px] px-1.5 py-0.5 rounded-full border transition ${
                  sel
                    ? 'border-rose-500 bg-rose-500/15 text-rose-700'
                    : 'border-th-border text-th-text-muted hover:border-rose-500/40'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => submitNow(false, selectedReasons)}
            className="text-[10px] px-1.5 py-0.5 rounded-btn border border-rose-500/40 text-rose-700 hover:bg-rose-500/10 disabled:opacity-40 ml-1"
          >
            {busy === 'not_useful' ? (
              <Loader2 size={10} className="inline animate-spin" />
            ) : (
              <Check size={10} className="inline" />
            )}
            <span className="ml-0.5">提交</span>
          </button>
          <button
            type="button"
            onClick={() => { setShowReasons(false); setSelectedReasons([]); }}
            className="text-[10px] px-1 text-th-text-muted hover:text-th-text-primary"
            aria-label="取消"
          >
            <X size={10} />
          </button>
        </div>
      )}
    </div>
  );
}
