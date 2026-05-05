/**
 * ConsultHome — 咨询中心 (M21 #3 重做版)
 *
 * 业务：AI 知识架构师对话 → 上传 → 去噪审核 → 体系输出 → Wiki 编织（W1-W5）
 *
 * 设计方向：Engineering Blueprint Terminal（工程蓝图终端）
 *   - Nord 深色 + 工业控制台 + 制图蓝本意象
 *   - 单宽体技术字 (JetBrains Mono / IBM Plex Mono) 标识时间戳/会话 ID
 *   - 5 工位生产线进度条 (W1→W5) 替代普通 stepper
 *   - 左终端聊天 / 右蓝图产物预览 分栏
 *   - 角落注册标记 + scan line + grid 背景
 *
 * 不使用：紫渐变 / Inter / 通用 ChatGPT 卡片
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Send,
  CornerDownLeft,
  Upload,
  Filter,
  Network,
  BookOpen,
  FolderPlus,
  Loader2,
  FileDown,
  Bot,
  CircleDot,
  ArrowRight,
  Activity,
  AlertCircle,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';
import type { TranslationKey } from '@/lib/i18n';

// ────────────────────────────────────────────────────────────
//  Types & Constants
// ────────────────────────────────────────────────────────────

type StageId = 'W1' | 'W2' | 'W3' | 'W4' | 'W5';

interface StageMeta {
  id: StageId;
  iconKey: 'project' | 'upload' | 'filter' | 'schema' | 'wiki';
  labelKey: TranslationKey;
  hintKey: TranslationKey;
}

const STAGES: StageMeta[] = [
  { id: 'W1', iconKey: 'project', labelKey: 'consult.w1.label', hintKey: 'consult.w1.hint' },
  { id: 'W2', iconKey: 'upload',  labelKey: 'consult.w2.label', hintKey: 'consult.w2.hint' },
  { id: 'W3', iconKey: 'filter',  labelKey: 'consult.w3.label', hintKey: 'consult.w3.hint' },
  { id: 'W4', iconKey: 'schema',  labelKey: 'consult.w4.label', hintKey: 'consult.w4.hint' },
  { id: 'W5', iconKey: 'wiki',    labelKey: 'consult.w5.label', hintKey: 'consult.w5.hint' },
];

/** architect 后端对话阶段 → 业务 W 工位映射 */
function mapArchitectStageToW(stage: string | null | undefined): StageId {
  switch (stage) {
    case 'identify': return 'W1';
    case 'propose':  return 'W4';
    case 'refine':   return 'W4';
    case 'export':   return 'W5';
    // 其他保留当前
    default:         return 'W1';
  }
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: Date;
  id: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

// 字体堆栈（避免通用 Inter / Roboto）
const MONO_STACK =
  '"JetBrains Mono", "IBM Plex Mono", "Fira Code", ui-monospace, "SF Mono", Menlo, monospace';
const SANS_STACK =
  '"IBM Plex Sans", "Söhne", "Noto Sans SC", system-ui, sans-serif';
const SERIF_STACK_CN =
  '"Noto Serif SC", "Source Han Serif SC", "PingFang SC", serif';


// ────────────────────────────────────────────────────────────
//  Stage icon resolver
// ────────────────────────────────────────────────────────────
function StageIcon({ kind, size = 14 }: {
  kind: StageMeta['iconKey'];
  size?: number;
}) {
  const cls = 'shrink-0';
  if (kind === 'project') return <FolderPlus size={size} className={cls} />;
  if (kind === 'upload')  return <Upload     size={size} className={cls} />;
  if (kind === 'filter')  return <Filter     size={size} className={cls} />;
  if (kind === 'schema')  return <Network    size={size} className={cls} />;
  return <BookOpen size={size} className={cls} />;
}


// ────────────────────────────────────────────────────────────
//  ID + timestamp helpers
// ────────────────────────────────────────────────────────────
function shortId() {
  return Math.random().toString(36).slice(2, 8).toUpperCase();
}
function fmtTs(d: Date) {
  return d.toTimeString().slice(0, 8);
}
function fmtDate(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}.${m}.${dd}`;
}


// ════════════════════════════════════════════════════════════
//  Main
// ════════════════════════════════════════════════════════════
export default function ConsultHome() {
  const { t } = useLocale();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [stage, setStage] = useState<StageId>('W1');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'system',
      content: t('consult.greeting'),
      ts: new Date(),
      id: shortId(),
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚到底
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
      body: JSON.stringify({
        // 后端要求 project_id；UI 没显式选项目时用 default
        // (后续可加项目选择器作为 W1 工位的实际表单)
        project_id: 'default',
        sample_texts: [],
      }),
    });
    if (!res.ok) {
      throw new Error(`create session failed: ${res.status}`);
    }
    const data = await res.json();
    const sid = data.session_id || data.id || `local-${shortId()}`;
    setSessionId(sid);
    if (typeof data.stage === 'string') {
      setStage(mapArchitectStageToW(data.stage));
    }
    return sid;
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setError(null);
    const userMsg: ChatMessage = {
      role: 'user', content: text, ts: new Date(), id: shortId(),
    };
    setMessages(m => [...m, userMsg]);
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
      // 后端 MessageResponse 字段是 assistant；其他名兜底
      const reply =
        data.assistant
        || data.assistant_message
        || data.content
        || data.reply
        || JSON.stringify(data);
      setMessages(m => [
        ...m,
        { role: 'assistant', content: reply, ts: new Date(), id: shortId() },
      ]);
      // 后端返回 architect stage → 映射到业务 W 工位
      if (typeof data.stage === 'string') {
        setStage(mapArchitectStageToW(data.stage));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
      // 焦点回输入框
      requestAnimationFrame(() => inputRef.current?.focus());
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
      a.download = `kap-architect-draft-${sessionId}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const sessionLabel = useMemo(() => {
    if (!sessionId) return t('consult.sessionPending');
    const tail = sessionId.slice(-8).toUpperCase();
    return `SESSION·${tail}`;
  }, [sessionId, t]);

  const today = useMemo(() => fmtDate(new Date()), []);
  const stageIdx = STAGES.findIndex(s => s.id === stage);

  return (
    <div
      className="min-h-screen text-th-text-primary"
      style={{
        fontFamily: SANS_STACK,
        background:
          'radial-gradient(ellipse 60% 60% at 20% 0%, rgba(94,129,172,0.10), transparent 60%),\n           radial-gradient(ellipse 80% 60% at 100% 100%, rgba(136,192,208,0.06), transparent 70%),\n           #1B2230',
      }}
    >
      {/* 微噪声 + 扫描线 */}
      <div
        aria-hidden="true"
        className="fixed inset-0 pointer-events-none opacity-[0.04]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(180deg, rgba(255,255,255,0.6) 0 1px, transparent 1px 4px)',
          mixBlendMode: 'overlay',
        }}
      />

      <div className="relative max-w-screen-2xl mx-auto px-6 pt-6 pb-10">

        {/* ── Header ──────────────────────────────────────── */}
        <Header
          sessionLabel={sessionLabel}
          today={today}
          onDownload={downloadDraft}
          canDownload={!!sessionId}
          t={t}
        />

        {/* ── 5 工位流水进度 ───────────────────────────── */}
        <PipelineBar stage={stage} stageIdx={stageIdx} setStage={setStage} t={t} />

        {/* ── 错误提示 ────────────────────────────────── */}
        {error && (
          <div
            className="mt-4 flex items-start gap-2 px-3 py-2 border rounded-sm"
            style={{
              borderColor: 'rgba(191,97,106,0.45)',
              background: 'rgba(191,97,106,0.08)',
              fontFamily: MONO_STACK,
            }}
          >
            <AlertCircle size={14} className="mt-0.5 text-rose-300 shrink-0" />
            <div className="text-xs text-rose-200">
              <span className="opacity-60 mr-2">[ERR]</span>
              {error}
            </div>
          </div>
        )}

        {/* ── 主区：左终端 / 右蓝图 ─────────────────── */}
        <div className="mt-5 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_480px] gap-5">
          {/* 终端 */}
          <Terminal
            messages={messages}
            sending={sending}
            input={input}
            setInput={setInput}
            onSend={send}
            inputRef={inputRef}
            scrollRef={scrollRef}
            t={t}
          />

          {/* 蓝图 */}
          <BlueprintPanel stage={stage} sessionId={sessionId} t={t} />
        </div>

        {/* ── 底部状态栏 ─────────────────────────────── */}
        <Footer sessionId={sessionId} stage={stage} t={t} />
      </div>
    </div>
  );
}


// ════════════════════════════════════════════════════════════
//  Header
// ════════════════════════════════════════════════════════════
function Header({
  sessionLabel, today, onDownload, canDownload, t,
}: {
  sessionLabel: string;
  today: string;
  onDownload: () => void;
  canDownload: boolean;
  t: (k: TranslationKey) => string;
}) {
  return (
    <header className="flex items-end justify-between gap-4">
      {/* 左：标题 + 副标 */}
      <div className="flex items-end gap-4">
        <div
          className="hidden md:flex items-center justify-center w-12 h-12 border"
          style={{
            borderColor: 'rgba(136,192,208,0.45)',
            background: 'rgba(136,192,208,0.06)',
          }}
          aria-hidden="true"
        >
          <Bot size={20} style={{ color: '#88C0D0' }} />
        </div>
        <div>
          <div
            className="text-[11px] tracking-[0.32em] uppercase text-th-text-muted"
            style={{ fontFamily: MONO_STACK }}
          >
            KAP · CONSULT TERMINAL
          </div>
          <h1
            className="mt-1 text-3xl md:text-4xl leading-none"
            style={{
              fontFamily: SERIF_STACK_CN,
              fontWeight: 600,
              letterSpacing: '0.04em',
            }}
          >
            {t('consult.title')}
          </h1>
          <div
            className="mt-1.5 text-xs text-th-text-muted max-w-2xl"
            style={{ fontFamily: SANS_STACK }}
          >
            {t('consult.subtitle')}
          </div>
        </div>
      </div>

      {/* 右：会话信息 + 操作 */}
      <div className="flex items-center gap-3 shrink-0">
        <div
          className="hidden md:flex flex-col items-end leading-tight"
          style={{ fontFamily: MONO_STACK }}
        >
          <span className="text-[10px] uppercase tracking-[0.24em] text-th-text-muted">
            {today}
          </span>
          <span
            className="text-[11px]"
            style={{ color: '#88C0D0', letterSpacing: '0.08em' }}
          >
            {sessionLabel}
          </span>
        </div>
        <LanguageSwitcher />
        <button
          type="button"
          onClick={onDownload}
          disabled={!canDownload}
          className="group inline-flex items-center gap-2 px-3 py-2 border text-xs disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          style={{
            fontFamily: MONO_STACK,
            borderColor: 'rgba(136,192,208,0.45)',
            color: '#D8DEE9',
            letterSpacing: '0.06em',
          }}
        >
          <FileDown size={13} />
          {t('consult.downloadDraft').toUpperCase()}
        </button>
      </div>
    </header>
  );
}


// ════════════════════════════════════════════════════════════
//  Pipeline Bar — 5 工位生产线
// ════════════════════════════════════════════════════════════
function PipelineBar({
  stage, stageIdx, setStage, t,
}: {
  stage: StageId;
  stageIdx: number;
  setStage: (s: StageId) => void;
  t: (k: TranslationKey) => string;
}) {
  return (
    <div
      className="mt-7 relative border"
      style={{
        borderColor: 'rgba(216,222,233,0.10)',
        background: 'rgba(46,52,64,0.45)',
      }}
    >
      {/* 角注册标记 */}
      <CornerMarks />

      <div
        className="px-5 py-2 text-[10px] uppercase tracking-[0.32em] text-th-text-muted border-b"
        style={{
          fontFamily: MONO_STACK,
          borderColor: 'rgba(216,222,233,0.08)',
        }}
      >
        <span style={{ color: '#88C0D0' }}>▶</span>{' '}
        {t('consult.pipelineLabel')}
        <span className="ml-2 opacity-60">
          [{stageIdx + 1}/{STAGES.length}]
        </span>
      </div>

      <div className="px-3 sm:px-5 py-5">
        <div className="flex items-stretch gap-1 sm:gap-2 overflow-x-auto">
          {STAGES.map((s, i) => {
            const active = s.id === stage;
            const past = i < stageIdx;
            const future = i > stageIdx;
            return (
              <div key={s.id} className="flex items-stretch flex-1 min-w-[120px]">
                <button
                  type="button"
                  onClick={() => setStage(s.id)}
                  className="group relative flex-1 flex flex-col gap-1 items-start px-3 py-3 transition-all"
                  style={{
                    fontFamily: MONO_STACK,
                    background: active ? 'rgba(136,192,208,0.10)' : 'transparent',
                    border: '1px solid',
                    borderColor: active
                      ? 'rgba(136,192,208,0.7)'
                      : past
                        ? 'rgba(163,190,140,0.35)'
                        : 'rgba(216,222,233,0.12)',
                    boxShadow: active
                      ? '0 0 0 1px rgba(136,192,208,0.25), inset 0 0 32px rgba(136,192,208,0.08)'
                      : 'none',
                    cursor: 'pointer',
                  }}
                >
                  {/* 顶部 station id */}
                  <div className="flex items-center gap-2 w-full">
                    <span
                      className="text-[10px] tracking-[0.16em] px-1.5 py-0.5 border"
                      style={{
                        color: active ? '#EBCB8B' : past ? '#A3BE8C' : '#6F7889',
                        borderColor: active ? '#EBCB8B' : past ? '#A3BE8C' : 'rgba(216,222,233,0.18)',
                        background: active ? 'rgba(235,203,139,0.06)' : 'transparent',
                      }}
                    >
                      {s.id}
                    </span>
                    <StageIcon
                      kind={s.iconKey}
                      size={13}
                    />
                    {active && (
                      <span
                        className="ml-auto inline-flex items-center gap-1 text-[9px] tracking-[0.18em]"
                        style={{ color: '#EBCB8B' }}
                      >
                        <span
                          className="inline-block w-1.5 h-1.5 rounded-full"
                          style={{
                            background: '#EBCB8B',
                            animation: 'kapPulse 1.5s ease-in-out infinite',
                          }}
                        />
                        ACTIVE
                      </span>
                    )}
                    {past && (
                      <span
                        className="ml-auto text-[9px] tracking-[0.18em]"
                        style={{ color: '#A3BE8C' }}
                      >
                        DONE
                      </span>
                    )}
                  </div>

                  {/* label / hint */}
                  <div
                    className="text-[13px] mt-0.5"
                    style={{
                      fontFamily: SANS_STACK,
                      color: future ? '#7B8290' : '#ECEFF4',
                      fontWeight: active ? 600 : 500,
                    }}
                  >
                    {t(s.labelKey)}
                  </div>
                  <div
                    className="text-[10px] text-th-text-muted leading-snug"
                    style={{ fontFamily: SANS_STACK }}
                  >
                    {t(s.hintKey)}
                  </div>
                </button>

                {/* 连接线 (除了最后一个) */}
                {i < STAGES.length - 1 && (
                  <div className="flex items-center px-1 sm:px-2 shrink-0">
                    <ArrowRight
                      size={14}
                      style={{
                        color: i < stageIdx ? '#A3BE8C' : 'rgba(216,222,233,0.25)',
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 底部 keyframe */}
      <style>{`
        @keyframes kapPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.4; transform: scale(0.6); }
        }
        @keyframes kapTermBlink {
          0%, 49% { opacity: 1; }
          50%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}


function CornerMarks() {
  const colour = 'rgba(136,192,208,0.6)';
  return (
    <>
      <span aria-hidden="true" className="absolute top-0 left-0 w-3 h-3"
        style={{ borderTop: `1px solid ${colour}`, borderLeft: `1px solid ${colour}` }} />
      <span aria-hidden="true" className="absolute top-0 right-0 w-3 h-3"
        style={{ borderTop: `1px solid ${colour}`, borderRight: `1px solid ${colour}` }} />
      <span aria-hidden="true" className="absolute bottom-0 left-0 w-3 h-3"
        style={{ borderBottom: `1px solid ${colour}`, borderLeft: `1px solid ${colour}` }} />
      <span aria-hidden="true" className="absolute bottom-0 right-0 w-3 h-3"
        style={{ borderBottom: `1px solid ${colour}`, borderRight: `1px solid ${colour}` }} />
    </>
  );
}


// ════════════════════════════════════════════════════════════
//  Terminal — 左侧对话区
// ════════════════════════════════════════════════════════════
function Terminal({
  messages, sending, input, setInput, onSend,
  inputRef, scrollRef, t,
}: {
  messages: ChatMessage[];
  sending: boolean;
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  t: (k: TranslationKey) => string;
}) {
  return (
    <div
      className="relative border flex flex-col"
      style={{
        borderColor: 'rgba(216,222,233,0.10)',
        background: 'rgba(46,52,64,0.55)',
        minHeight: 520,
      }}
    >
      <CornerMarks />

      {/* 头条 */}
      <div
        className="px-5 py-2 flex items-center justify-between border-b"
        style={{
          borderColor: 'rgba(216,222,233,0.08)',
          fontFamily: MONO_STACK,
        }}
      >
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.32em] text-th-text-muted">
          <span style={{ color: '#88C0D0' }}>▶</span>
          {t('consult.terminal.label')}
        </div>
        <div
          className="flex items-center gap-1.5 text-[10px] tracking-[0.16em]"
          style={{ color: '#A3BE8C' }}
        >
          <Activity size={10} />
          <span style={{ animation: 'kapPulse 2s ease-in-out infinite' }}>●</span>
          ONLINE
        </div>
      </div>

      {/* 消息流 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-4 space-y-4"
        style={{
          backgroundImage:
            'linear-gradient(rgba(216,222,233,0.025) 1px, transparent 1px)',
          backgroundSize: '100% 28px',
        }}
      >
        {messages.map(m => (
          <Line key={m.id} msg={m} t={t} />
        ))}
        {sending && (
          <div
            className="flex items-center gap-2 text-xs"
            style={{ fontFamily: MONO_STACK, color: '#88C0D0' }}
          >
            <span className="opacity-60">[{fmtTs(new Date())}]</span>
            <Loader2 size={12} className="animate-spin" />
            {t('consult.thinking')}
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div
        className="border-t px-3 py-3"
        style={{ borderColor: 'rgba(216,222,233,0.08)' }}
      >
        <div className="flex items-start gap-2">
          <span
            className="pl-1 pt-2 text-sm"
            style={{ fontFamily: MONO_STACK, color: '#88C0D0' }}
            aria-hidden="true"
          >
            ▶
          </span>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            rows={2}
            placeholder={t('consult.placeholder')}
            className="flex-1 bg-transparent outline-none resize-none text-sm py-2 px-2"
            style={{
              fontFamily: MONO_STACK,
              color: '#ECEFF4',
              caretColor: '#88C0D0',
            }}
            aria-label={t('consult.placeholder')}
          />
          <button
            type="button"
            onClick={onSend}
            disabled={sending || !input.trim()}
            className="inline-flex items-center gap-1 px-3 py-2 text-[11px] tracking-[0.18em] uppercase border disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            style={{
              fontFamily: MONO_STACK,
              borderColor: '#88C0D0',
              color: '#88C0D0',
            }}
          >
            <Send size={12} />
            {t('consult.send')}
            <CornerDownLeft size={10} className="opacity-50 ml-1" />
          </button>
        </div>
        <div
          className="mt-1.5 px-2 text-[10px] text-th-text-muted opacity-70"
          style={{ fontFamily: MONO_STACK, letterSpacing: '0.06em' }}
        >
          [ENTER] {t('consult.sendHint')} · [SHIFT+ENTER] {t('consult.newlineHint')}
        </div>
      </div>
    </div>
  );
}


function Line({ msg, t }: { msg: ChatMessage; t: (k: TranslationKey) => string }) {
  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';

  let tag = '';
  let tagColor = '';
  if (isUser) { tag = 'YOU';  tagColor = '#EBCB8B'; }
  else if (isSystem) { tag = 'SYS';  tagColor = '#6F7889'; }
  else { tag = 'ARCH'; tagColor = '#88C0D0'; }

  return (
    <div
      className="leading-relaxed"
      style={{ fontFamily: SANS_STACK, color: '#ECEFF4' }}
    >
      <div
        className="flex items-baseline gap-2 mb-1"
        style={{ fontFamily: MONO_STACK }}
      >
        <span className="text-[10px] text-th-text-muted opacity-70">
          [{fmtTs(msg.ts)}]
        </span>
        <span
          className="text-[10px] tracking-[0.16em] px-1.5 py-0.5 border"
          style={{
            color: tagColor,
            borderColor: tagColor,
            background: `${tagColor}10`,
          }}
        >
          {tag}
        </span>
        <span className="text-[9px] text-th-text-muted opacity-40">
          #{msg.id}
        </span>
      </div>
      <div
        className="pl-4 text-[13.5px] whitespace-pre-wrap"
        style={{
          borderLeft: `2px solid ${tagColor}40`,
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}


// ════════════════════════════════════════════════════════════
//  Blueprint Panel — 右侧产物预览
// ════════════════════════════════════════════════════════════
function BlueprintPanel({
  stage, sessionId, t,
}: {
  stage: StageId;
  sessionId: string | null;
  t: (k: TranslationKey) => string;
}) {
  const meta = STAGES.find(s => s.id === stage)!;

  return (
    <aside
      className="relative border flex flex-col"
      style={{
        borderColor: 'rgba(216,222,233,0.10)',
        background: 'rgba(46,52,64,0.55)',
        minHeight: 520,
      }}
    >
      <CornerMarks />

      <div
        className="px-5 py-2 border-b flex items-center justify-between"
        style={{
          borderColor: 'rgba(216,222,233,0.08)',
          fontFamily: MONO_STACK,
        }}
      >
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.32em] text-th-text-muted">
          <span style={{ color: '#88C0D0' }}>▶</span>
          {t('consult.blueprint.label')}
        </div>
        <div
          className="text-[10px] tracking-[0.18em]"
          style={{ color: '#EBCB8B' }}
        >
          {meta.id}
        </div>
      </div>

      {/* 蓝图区（grid 背景） */}
      <div
        className="relative flex-1 p-5"
        style={{
          backgroundImage:
            'linear-gradient(rgba(136,192,208,0.06) 1px, transparent 1px),\n             linear-gradient(90deg, rgba(136,192,208,0.06) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      >
        <BlueprintContent stage={stage} t={t} />
      </div>

      {/* 底部操作 */}
      <div
        className="border-t px-4 py-3 flex items-center justify-between"
        style={{
          borderColor: 'rgba(216,222,233,0.08)',
          fontFamily: MONO_STACK,
        }}
      >
        <div className="text-[10px] text-th-text-muted">
          {sessionId
            ? <>SESSION · <span style={{ color: '#88C0D0' }}>{sessionId.slice(-8)}</span></>
            : t('consult.sessionPending')}
        </div>
        <button
          type="button"
          disabled={!sessionId}
          className="text-[10px] tracking-[0.18em] uppercase px-2.5 py-1 border disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          style={{
            borderColor: 'rgba(163,190,140,0.45)',
            color: '#A3BE8C',
          }}
          title={t('consult.commitToStorage')}
        >
          ↗ {t('consult.commit')}
        </button>
      </div>
    </aside>
  );
}


function BlueprintContent({
  stage, t,
}: {
  stage: StageId;
  t: (k: TranslationKey) => string;
}) {
  // W1
  if (stage === 'W1') {
    return (
      <BPSection
        title={t('consult.w1.bp.title')}
        rows={[
          [t('consult.w1.bp.r1'), '—'],
          [t('consult.w1.bp.r2'), '—'],
          [t('consult.w1.bp.r3'), '—'],
        ]}
      />
    );
  }
  if (stage === 'W2') {
    return (
      <BPSection
        title={t('consult.w2.bp.title')}
        rows={[
          [t('consult.w2.bp.r1'), '0'],
          [t('consult.w2.bp.r2'), '0'],
          [t('consult.w2.bp.r3'), '0%'],
        ]}
      />
    );
  }
  if (stage === 'W3') {
    return (
      <BPSection
        title={t('consult.w3.bp.title')}
        rows={[
          [t('consult.w3.bp.r1'), '0'],
          [t('consult.w3.bp.r2'), '0'],
          [t('consult.w3.bp.r3'), '0'],
          [t('consult.w3.bp.r4'), '0'],
        ]}
      />
    );
  }
  if (stage === 'W4') {
    return (
      <BPSection
        title={t('consult.w4.bp.title')}
        rows={[
          [t('consult.w4.bp.r1'), '0'],
          [t('consult.w4.bp.r2'), '0'],
          [t('consult.w4.bp.r3'), 'L1+L2'],
        ]}
      />
    );
  }
  // W5
  return (
    <BPSection
      title={t('consult.w5.bp.title')}
      rows={[
        [t('consult.w5.bp.r1'), '0'],
        [t('consult.w5.bp.r2'), '0'],
        [t('consult.w5.bp.r3'), 'index/domain/source'],
      ]}
    />
  );
}


function BPSection({
  title, rows,
}: {
  title: string;
  rows: [string, string][];
}) {
  return (
    <div
      className="h-full relative border-l-2 pl-5"
      style={{
        borderColor: 'rgba(136,192,208,0.45)',
        fontFamily: MONO_STACK,
      }}
    >
      <div
        className="text-[11px] tracking-[0.18em] uppercase mb-4"
        style={{ color: '#88C0D0' }}
      >
        ◇ {title}
      </div>
      <div className="space-y-2.5">
        {rows.map(([k, v]) => (
          <div
            key={k}
            className="flex items-baseline justify-between gap-3 text-xs"
            style={{
              borderBottom: '1px dashed rgba(216,222,233,0.08)',
              paddingBottom: '4px',
            }}
          >
            <span className="text-th-text-muted opacity-80">{k}</span>
            <span style={{ color: '#ECEFF4' }} className="font-medium">
              {v}
            </span>
          </div>
        ))}
      </div>

      {/* placeholder waiting blob */}
      <div
        className="mt-8 inline-flex items-center gap-2 text-[10px] tracking-[0.18em] uppercase"
        style={{ color: '#6F7889' }}
      >
        <CircleDot size={11} />
        <span>{title} · awaiting input</span>
      </div>
    </div>
  );
}


// ════════════════════════════════════════════════════════════
//  Footer — 状态条
// ════════════════════════════════════════════════════════════
function Footer({
  sessionId, stage, t,
}: {
  sessionId: string | null;
  stage: StageId;
  t: (k: TranslationKey) => string;
}) {
  return (
    <footer
      className="mt-4 flex items-center justify-between text-[10px] tracking-[0.18em] uppercase"
      style={{ fontFamily: MONO_STACK, color: '#6F7889' }}
    >
      <div className="flex items-center gap-3">
        <span style={{ color: '#88C0D0' }}>⌘ KAP / consult</span>
        <span className="opacity-50">·</span>
        <span>{t('consult.footer.flow')}</span>
      </div>
      <div className="flex items-center gap-3">
        <span>STAGE · <span style={{ color: '#EBCB8B' }}>{stage}</span></span>
        <span className="opacity-50">·</span>
        <span>
          {sessionId
            ? <>STATE · <span style={{ color: '#A3BE8C' }}>READY</span></>
            : <>STATE · <span style={{ color: '#6F7889' }}>IDLE</span></>}
        </span>
      </div>
    </footer>
  );
}
