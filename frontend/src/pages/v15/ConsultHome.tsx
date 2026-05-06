/**
 * 咨询中心 — 三中心统一设计 (M21 #4)
 *
 * 严格按 distinctive.css Nordic Minimalism 系统渲染。
 * 与 GovernanceHome / ReaderHome 共用 CenterShell + CenterHero + Pipeline + StatTile + KapCard。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Send, Loader2, FileDown, FolderPlus, Upload, Filter, Network, BookOpen,
  Bot, User, CornerDownLeft, Sparkles,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import {
  CenterShell, CenterHero, Pipeline, KapCard, type Station,
} from '@/components/v15/CenterShell';
import ConsultUploader from '@/components/v15/ConsultUploader';
import IndustryPicker, {
  loadSavedIndustry, clearSavedIndustry,
} from '@/components/v15/IndustryPicker';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

type StageId = 'W1' | 'W2' | 'W3' | 'W4' | 'W5';

interface Msg {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: Date;
}

function shortId() { return Math.random().toString(36).slice(2, 8).toUpperCase(); }
function fmtTs(d: Date) { return d.toTimeString().slice(0, 8); }

function mapArchitectStage(s: string | null | undefined): StageId {
  if (s === 'identify') return 'W1';
  if (s === 'propose')  return 'W4';
  if (s === 'refine')   return 'W4';
  if (s === 'export')   return 'W5';
  return 'W1';
}


export default function ConsultHome() {
  const { t } = useLocale();

  // M21 #9 · 行业前置：未选行业 → IndustryPicker；选完才进入对话
  const [industry, setIndustry] = useState<string | null>(loadSavedIndustry);
  const [industryLabel, setIndustryLabel] = useState<string>('');

  const [stage, setStage] = useState<StageId>('W1');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([
    { id: shortId(), role: 'system', content: t('consult.greeting'), ts: new Date() },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 未选行业 → 显示行业选择
  if (!industry) {
    return (
      <CenterShell>
        <IndustryPicker
          onConfirm={(code, label) => {
            setIndustry(code);
            setIndustryLabel(label);
          }}
        />
      </CenterShell>
    );
  }

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    // 行业 code 用作 project_id（后端会按 industry 加载 L1 模板）
    const projectId = industry || 'default';
    const r = await fetch(`${API_BASE}/api/v1/architect/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, sample_texts: [] }),
    });
    if (!r.ok) throw new Error(`create session failed: ${r.status}`);
    const d = await r.json();
    const sid = d.session_id || d.id || `local-${shortId()}`;
    setSessionId(sid);
    if (typeof d.stage === 'string') setStage(mapArchitectStage(d.stage));
    return sid;
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setError(null);
    setMessages(m => [...m, { id: shortId(), role: 'user', content: text, ts: new Date() }]);
    setInput('');
    setSending(true);
    try {
      const sid = await ensureSession();
      const r = await fetch(
        `${API_BASE}/api/v1/architect/sessions/${encodeURIComponent(sid)}/message`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: text }),
        },
      );
      if (!r.ok) throw new Error(`send failed: ${r.status}`);
      const d = await r.json();
      const reply = d.assistant || d.assistant_message || d.content || JSON.stringify(d);
      setMessages(m => [...m, {
        id: shortId(), role: 'assistant', content: reply, ts: new Date(),
      }]);
      if (typeof d.stage === 'string') setStage(mapArchitectStage(d.stage));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  const downloadDraft = async () => {
    if (!sessionId) return;
    try {
      const r = await fetch(
        `${API_BASE}/api/v1/architect/sessions/${encodeURIComponent(sessionId)}/draft`,
      );
      if (!r.ok) throw new Error(`fetch draft failed: ${r.status}`);
      const text = await r.text();
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `kap-draft-${sessionId}.md`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const stageIdx = ['W1', 'W2', 'W3', 'W4', 'W5'].indexOf(stage);
  const stations: Station[] = (
    [
      { id: 'W1', icon: FolderPlus, key: 'consult.w1.label' as const, hk: 'consult.w1.hint' as const },
      { id: 'W2', icon: Upload,     key: 'consult.w2.label' as const, hk: 'consult.w2.hint' as const },
      { id: 'W3', icon: Filter,     key: 'consult.w3.label' as const, hk: 'consult.w3.hint' as const },
      { id: 'W4', icon: Network,    key: 'consult.w4.label' as const, hk: 'consult.w4.hint' as const },
      { id: 'W5', icon: BookOpen,   key: 'consult.w5.label' as const, hk: 'consult.w5.hint' as const },
    ]
  ).map((s, i) => ({
    id: s.id,
    labelKey: s.key,
    hintKey: s.hk,
    icon: s.icon,
    state: i === stageIdx ? 'active' : i < stageIdx ? 'done' : 'pending',
  }));

  return (
    <CenterShell>
      <CenterHero
        kind="consult"
        titleKey="consult.heroTitle"
        subtitleKey="consult.heroSub"
        rightSlot={
          <>
            <button
              type="button"
              onClick={() => {
                clearSavedIndustry();
                setIndustry(null);
                setIndustryLabel('');
                setSessionId(null);
                setMessages([
                  { id: shortId(), role: 'system', content: t('consult.greeting'), ts: new Date() },
                ]);
                setStage('W1');
              }}
              className="kap-btn"
              title={industryLabel || industry || ''}
            >
              <Sparkles size={13} />
              {industryLabel || industry} · {t('consult.changeIndustry')}
            </button>
            <button
              type="button"
              disabled={!sessionId}
              onClick={downloadDraft}
              className="kap-btn"
            >
              <FileDown size={13} />
              {t('consult.downloadDraft')}
            </button>
          </>
        }
      />

      <Pipeline
        labelKey="kap.tagPipeline"
        stations={stations}
        onClickStation={(id) => setStage(id as StageId)}
      />

      {error && (
        <div className="kap-card mb-6" style={{
          padding: '0.8rem 1rem',
          borderColor: 'var(--kap-aurora-red)',
          background: 'rgba(191,97,106,0.08)',
        }}>
          <span className="kap-mono-tag" style={{ color: 'var(--kap-aurora-red)' }}>
            ERR · {error}
          </span>
        </div>
      )}

      {/* 主区：左对话 (8) / 右进度 (4) */}
      <div className="kap-grid-2" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)' }}>
        {/* 左：对话 */}
        <KapCard
          eyebrow={`▶ ${t('consult.terminal.label')}`}
          frost
          rightSlot={
            sessionId ? (
              <span className="kap-mono-tag" style={{ color: 'var(--kap-frost)' }}>
                ● {sessionId.slice(-8).toUpperCase()}
              </span>
            ) : (
              <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
                ○ {t('consult.sessionPending')}
              </span>
            )
          }
        >
          <div
            ref={scrollRef}
            className="overflow-y-auto pr-2"
            style={{ height: '460px' }}
          >
            <div className="kap-stagger space-y-4">
              {messages.map(m => <MsgRow key={m.id} m={m} t={t} />)}
              {sending && (
                <div className="flex items-center gap-2" style={{
                  fontFamily: 'var(--kap-font-mono)',
                  fontSize: 12,
                  color: 'var(--kap-frost)',
                }}>
                  <Loader2 size={12} className="animate-spin" />
                  {t('consult.thinking')}
                </div>
              )}
            </div>
          </div>

          {/* 输入区 */}
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(216,222,233,0.08)' }}>
            <div className="flex items-start gap-2">
              <span style={{
                fontFamily: 'var(--kap-font-mono)',
                color: 'var(--kap-frost)',
                fontSize: 16, paddingTop: 8,
              }}>▶</span>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
                }}
                rows={2}
                placeholder={t('consult.placeholder')}
                className="kap-input"
                style={{ resize: 'none', fontFamily: 'var(--kap-font-mono)', fontSize: 13 }}
              />
              <button
                type="button"
                onClick={send}
                disabled={sending || !input.trim()}
                className="kap-btn kap-btn-primary"
              >
                <Send size={12} />
                {t('consult.send')}
                <CornerDownLeft size={11} className="opacity-60" />
              </button>
            </div>
            <div className="mt-1 kap-mono-tag" style={{ color: 'var(--kap-snow-4)', letterSpacing: '0.10em' }}>
              [ENTER] {t('consult.sendHint')} · [SHIFT+ENTER] {t('consult.newlineHint')}
            </div>
          </div>
        </KapCard>

        {/* 右：进度 + 蓝图 */}
        <div className="space-y-4">
          <KapCard eyebrow={`▶ ${t('kap.cardConsultProgress')}`}>
            <div className="space-y-2.5">
              {stations.map(s => (
                <div key={s.id} className="flex items-center gap-3 py-1">
                  <span
                    className="kap-mono-tag w-8 text-center px-1 py-0.5 border"
                    style={{
                      color: s.state === 'active' ? 'var(--kap-aurora-yellow)'
                            : s.state === 'done' ? 'var(--kap-aurora-green)'
                            : 'var(--kap-snow-4)',
                      borderColor: s.state === 'active' ? 'var(--kap-aurora-yellow)'
                            : s.state === 'done' ? 'var(--kap-aurora-green)'
                            : 'rgba(216,222,233,0.15)',
                    }}
                  >
                    {s.id}
                  </span>
                  <div className="flex-1" style={{ fontFamily: 'var(--kap-font-display)', fontWeight: s.state === 'active' ? 700 : 400 }}>
                    {t(s.labelKey)}
                  </div>
                  {s.state === 'active' && (
                    <span className="kap-pulse w-1.5 h-1.5 rounded-full" style={{ background: 'var(--kap-aurora-yellow)' }} />
                  )}
                </div>
              ))}
            </div>
          </KapCard>

          <ConsultUploader
            projectId="default"
            onUploaded={(_r) => {
              // 上传后推进 stage 到 W3 (去噪审核)
              setStage('W3');
            }}
          />

          <KapCard
            eyebrow={`▶ ${t('consult.blueprint.label')}`}
            rightSlot={
              <span className="kap-badge kap-badge-warning">{stage}</span>
            }
          >
            <div
              style={{
                background: 'hsl(var(--muted) / 0.4)',
                border: '1px solid hsl(var(--border))',
                borderRadius: 'calc(var(--radius) - 4px)',
                padding: '1rem',
                minHeight: 160,
              }}
            >
              <div
                className="kap-mono-tag mb-3"
                style={{ color: 'hsl(var(--primary))' }}
              >
                ◇ {t(`consult.${stage.toLowerCase()}.bp.title` as 'consult.w1.bp.title')}
              </div>
              <BlueprintRows stage={stage} t={t} />
            </div>
          </KapCard>
        </div>
      </div>
    </CenterShell>
  );
}


function BlueprintRows({ stage, t }: { stage: StageId; t: (k: string) => string }) {
  const rows: [string, string][] = stage === 'W1' ? [
    [t('consult.w1.bp.r1'), '—'], [t('consult.w1.bp.r2'), '—'], [t('consult.w1.bp.r3'), '—'],
  ] : stage === 'W2' ? [
    [t('consult.w2.bp.r1'), '0'], [t('consult.w2.bp.r2'), '0'], [t('consult.w2.bp.r3'), '0%'],
  ] : stage === 'W3' ? [
    [t('consult.w3.bp.r1'), '0'], [t('consult.w3.bp.r2'), '0'], [t('consult.w3.bp.r3'), '0'], [t('consult.w3.bp.r4'), '0'],
  ] : stage === 'W4' ? [
    [t('consult.w4.bp.r1'), '0'], [t('consult.w4.bp.r2'), '0'], [t('consult.w4.bp.r3'), 'L1+L2'],
  ] : [
    [t('consult.w5.bp.r1'), '0'], [t('consult.w5.bp.r2'), '0'], [t('consult.w5.bp.r3'), 'index/domain/source'],
  ];

  return (
    <div className="space-y-2">
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex items-baseline justify-between gap-3 pb-1.5"
          style={{
            borderBottom: '1px dashed hsl(var(--border))',
            fontFamily: 'var(--font-sans)',
            fontSize: 12.5,
          }}
        >
          <span style={{ color: 'hsl(var(--muted-foreground))' }}>{k}</span>
          <span style={{ color: 'hsl(var(--foreground))', fontWeight: 500 }}>{v}</span>
        </div>
      ))}
    </div>
  );
}


function MsgRow({ m, t }: { m: Msg; t: (k: string) => string }) {
  const isUser = m.role === 'user';
  const isSys = m.role === 'system';
  let tag: string, color: string, Icon: typeof Bot;
  if (isUser)      { tag = 'YOU';  color = 'hsl(var(--warning))';     Icon = User; }
  else if (isSys)  { tag = 'SYS';  color = 'hsl(var(--muted-foreground))'; Icon = Bot;  }
  else             { tag = 'ARCH'; color = 'hsl(var(--primary))';     Icon = Bot;  }

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1" style={{ fontFamily: 'var(--font-mono)' }}>
        <Icon size={11} style={{ color }} />
        <span className="kap-mono-tag" style={{ color, borderColor: color, padding: '1px 6px', border: '1px solid', borderRadius: 4 }}>
          {tag}
        </span>
        <span className="kap-mono-tag" style={{ color: 'hsl(var(--muted-foreground))', opacity: 0.7 }}>
          [{fmtTs(m.ts)}]
        </span>
        <span className="kap-mono-tag" style={{ color: 'hsl(var(--muted-foreground))', opacity: 0.4 }}>
          #{m.id}
        </span>
      </div>
      <div
        className="pl-5 whitespace-pre-wrap"
        style={{
          borderLeft: `2px solid ${color}`,
          fontFamily: 'var(--font-sans)',
          fontWeight: 400,
          fontSize: 13.5,
          lineHeight: 1.6,
          color: 'hsl(var(--foreground))',
        }}
      >
        {m.content}
      </div>
    </div>
  );
}
