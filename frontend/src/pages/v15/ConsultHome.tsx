/**
 * ConsultHome — 咨询中心 (块①) 入口（M21 #1）
 *
 * AI 对话式建知识体系：上传材料 → AI 识别行业 → 建议本体树 → SME 审核 → 一键落入知识中心
 *
 * 后端入口：
 *   POST /api/v1/architect/sessions
 *   POST /api/v1/architect/sessions/{id}/message
 *   GET  /api/v1/architect/sessions/{id}/draft
 *
 * 拆分部署时本页面在咨询中心 :8011；单体部署时在 :8001/8000。
 */
import { useEffect, useRef, useState } from 'react';
import { Send, Sparkles, Bot, User, Loader2, FileDown, Workflow } from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export default function ConsultHome() {
  const { t } = useLocale();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'system',
      content: t('consult.greeting'),
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 自动滚到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const ensureSession = async (): Promise<string> => {
    if (sessionId) return sessionId;
    const res = await fetch(`${API_BASE}/api/v1/architect/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ industry_hint: '' }),
    });
    if (!res.ok) throw new Error(`create session failed: ${res.status}`);
    const data = await res.json();
    const sid = data.session_id || data.id || '';
    setSessionId(sid);
    return sid;
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setError(null);
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setInput('');
    setSending(true);
    try {
      const sid = await ensureSession();
      const res = await fetch(
        `${API_BASE}/api/v1/architect/sessions/${encodeURIComponent(sid)}/message`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: text }),
        },
      );
      if (!res.ok) throw new Error(`send failed: ${res.status}`);
      const data = await res.json();
      const reply = data.assistant_message || data.content || data.reply || JSON.stringify(data);
      setMessages((m) => [...m, { role: 'assistant', content: reply }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const downloadDraft = async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/architect/sessions/${encodeURIComponent(sessionId)}/draft`,
      );
      if (!res.ok) throw new Error(`fetch draft failed: ${res.status}`);
      const text = await res.text();
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `architect-draft-${sessionId}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="p-6 max-w-screen-lg mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary flex items-center gap-2">
            <Sparkles size={20} className="text-accent" />
            {t('consult.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">{t('consult.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          {sessionId && (
            <button
              type="button"
              onClick={downloadDraft}
              className="inline-flex items-center gap-2 rounded-btn border border-th-border px-3 py-1.5 text-sm text-th-text-secondary hover:text-accent hover:border-accent"
            >
              <FileDown size={14} />
              {t('consult.downloadDraft')}
            </button>
          )}
        </div>
      </div>

      {/* 流程提示 */}
      <div className="mb-4 p-3 rounded-card bg-accent/5 border border-accent/30 text-xs text-th-text-muted flex items-start gap-2">
        <Workflow size={14} className="text-accent mt-0.5 shrink-0" />
        <div>{t('consult.flowHint')}</div>
      </div>

      {error && (
        <div className="mb-3 p-3 rounded-card border border-rose-500/40 bg-rose-50/40 text-rose-700 text-sm">
          {error}
        </div>
      )}

      {/* 对话区 */}
      <div
        ref={scrollRef}
        className="rounded-card border border-th-border bg-elevated p-4 mb-4 overflow-y-auto"
        style={{ height: 'calc(100vh - 360px)', minHeight: 320 }}
      >
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} t={t} />
        ))}
        {sending && (
          <div className="flex items-center gap-2 text-th-text-muted text-sm py-2">
            <Loader2 size={14} className="animate-spin" />
            {t('consult.thinking')}
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder={t('consult.placeholder')}
          className="flex-1 px-3 py-2 rounded-card border border-th-border bg-elevated text-sm focus:outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={send}
          disabled={sending || !input.trim()}
          className="px-4 py-2 rounded-btn bg-accent text-white disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"
        >
          {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {t('consult.send')}
        </button>
      </div>

      {sessionId && (
        <div className="mt-2 text-xs text-th-text-muted font-mono">
          session: {sessionId}
        </div>
      )}
    </div>
  );
}


function MessageBubble({
  role, content, t,
}: {
  role: 'user' | 'assistant' | 'system';
  content: string;
  t: (k: string) => string;
}) {
  const isUser = role === 'user';
  const isSystem = role === 'system';
  const Icon = isUser ? User : Bot;
  return (
    <div className={`flex gap-2 mb-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
          isUser ? 'bg-accent text-white' : 'bg-th-bg-subtle text-accent'
        }`}
      >
        <Icon size={14} />
      </div>
      <div
        className={`max-w-[78%] px-3 py-2 rounded-card text-sm whitespace-pre-wrap ${
          isUser
            ? 'bg-accent text-white'
            : isSystem
            ? 'bg-th-bg-subtle text-th-text-secondary border border-th-border'
            : 'bg-th-bg-subtle text-th-text-primary border border-th-border'
        }`}
      >
        <div className="text-[10px] mb-1 opacity-60 font-mono">
          {isUser ? t('consult.you') : isSystem ? 'system' : t('consult.architect')}
        </div>
        {content}
      </div>
    </div>
  );
}
