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
// M22 #11 · 中央区 W3/W4/W5 嵌入既有 step 组件（顶层路由 /import/* 保留兼容）
import ReviewStep from '@/pages/v15/import/ReviewStep';
import TaxonomyStep from '@/pages/v15/import/TaxonomyStep';
import CompiledStep from '@/pages/v15/import/CompiledStep';
import type { IngestDocResult } from '@/services/api';

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
  // M22 #13: actualProjectId 是后端 ensure-by-industry 返回的真实 proj_xxx,
  // 而非 industry code 直接作 project_id (旧 M22 #11 导致 DomainStore 空树问题)
  const [actualProjectId, setActualProjectId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([
    { id: shortId(), role: 'system', content: t('consult.greeting'), ts: new Date() },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // M22 #12: 最近一次上传的 per-doc 详情, 跨 stage 共享给 W3 ReviewStep 上方展示
  const [recentDocs, setRecentDocs] = useState<IngestDocResult[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 所有 hook 必须在条件 return 前调用（React Hooks 规则）
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  // M22 #13: industry 切换 → ensure 真实项目 + 自动 seed L1 domains
  useEffect(() => {
    if (!industry) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(
          `${API_BASE}/api/v1/projects/ensure-by-industry?industry_code=${encodeURIComponent(industry)}`,
          { method: 'POST' },
        );
        if (!r.ok) throw new Error(`ensure project failed: ${r.status}`);
        const d = await r.json();
        if (!cancelled && d.id) {
          setActualProjectId(d.id);
        }
      } catch (e) {
        if (!cancelled) {
          setError(`项目初始化失败: ${(e as Error).message}`);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [industry]);

  // 未选行业 → 显示行业选择（hooks 全部 declared 后再 return）
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

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    // 行业 code 用作 project_id（后端会按 industry 加载 L1 模板）
    const projectId = actualProjectId || industry || 'default';
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

  /**
   * M22 #11 · 上传完后给 architect session 注入"已上传 X 个文件: ..."的 user message,
   * 让 LLM 接住产 W3 提议。如 session 还没创建则先 ensureSession。
   * 失败不阻塞 UI 流程（只 console + setError），W3 仍会切到。
   *
   * M22 #12: 加 docResults 参数, 把每个文档的 LLM 判定 + 分类推荐 + 待审标记
   * 拼成结构化 message, 让 architect LLM 看到完整识别结果再给后续建议。
   */
  const sendUploadNotification = async (
    fileNames: string[],
    totalFiles: number,
    docResults?: Array<{
      title: string; decision: string; category_path: string;
      confidence: number; needs_review: boolean;
    }>,
  ) => {
    try {
      const preview = fileNames.slice(0, 5).join(', ');
      const suffix = totalFiles > 5 ? `, ...等 ${totalFiles} 个` : '';
      let content = `我已上传 ${totalFiles} 个文件: ${preview}${suffix}`;

      // M22 #12: 把 LLM 已识别的 per-doc 结果一并喂给 architect, 让它给"入库建议 / 分类规划"反馈
      if (docResults && docResults.length > 0) {
        const lines = docResults.slice(0, 20).map(d => {
          const cat = d.category_path || '未分类';
          const reviewTag = d.needs_review ? ' [待 SME 审核]' : '';
          return `  - ${d.title} → ${d.decision} (置信 ${(d.confidence * 100).toFixed(0)}%, 推荐入 "${cat}")${reviewTag}`;
        });
        content += '\n\nLLM 自动识别 + 入库分类:\n' + lines.join('\n');
        const pending = docResults.filter(d => d.needs_review).length;
        if (pending > 0) {
          content += `\n\n请基于这些识别结果, 告诉我: (1) 这批材料是否属于我的行业 (2) ${pending} 个待审建议怎么处理 (3) 是否需要调整知识体系 / 新增分支`;
        } else {
          content += `\n\n所有材料 LLM 已自动入库到推荐分支, 请告诉我: (1) 是否需要调整任何文档的分类 (2) 知识体系是否需要新分支`;
        }
      }

      // 1. 本地显示这条 user message
      setMessages(m => [...m, {
        id: shortId(), role: 'user', content, ts: new Date(),
      }]);

      // 2. 发给 architect LLM
      const sid = await ensureSession();
      const r = await fetch(
        `${API_BASE}/api/v1/architect/sessions/${encodeURIComponent(sid)}/message`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        },
      );
      if (!r.ok) throw new Error(`upload notification failed: ${r.status}`);
      const d = await r.json();
      const reply = d.assistant || d.assistant_message || d.content || '';
      if (reply) {
        setMessages(m => [...m, {
          id: shortId(), role: 'assistant', content: reply, ts: new Date(),
        }]);
      }
      if (typeof d.stage === 'string') setStage(mapArchitectStage(d.stage));
    } catch (e) {
      // 不阻塞 UI 流程: 仅显示错误, W3 切换仍执行
      setError(`上传通知 LLM 失败: ${(e as Error).message}`);
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

      {/* 主区：左中央 (2fr) / 右侧栏 (1fr); M22 #11 中央区按 stage 切换 */}
      <div className="kap-grid-2" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)' }}>
        {/* 左中央：W1/W2 对话 | W3 去噪 | W4 体系 | W5 编织 */}
        {stage === 'W3' && (
          <KapCard eyebrow={`▶ ${t('consult.w3.label')}`} frost>
            {/* M22 #12: 刚刚上传的 LLM 判定结果, 让用户在 W3 看到完整识别+分类推荐 */}
            {recentDocs.length > 0 && (
              <div className="mb-4 p-3 rounded-btn"
                   style={{
                     background: 'hsl(var(--muted) / 0.4)',
                     border: '1px solid hsl(var(--border))',
                   }}>
                <div className="kap-mono-tag mb-2"
                     style={{ color: 'hsl(var(--primary))' }}>
                  ◇ 本次上传 LLM 自动识别 + 入库分类 ({recentDocs.length} 个文档)
                </div>
                <ul className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {recentDocs.map(d => {
                    const tone = d.decision === 'KEEP'    ? 'hsl(var(--success))'
                               : d.decision === 'ARCHIVE' ? 'hsl(var(--warning))'
                               : d.decision === 'DISCARD' ? 'hsl(var(--destructive))'
                               : 'hsl(var(--muted-foreground))';
                    return (
                      <li key={d.doc_id} className="text-xs"
                          style={{ lineHeight: 1.5 }}>
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="kap-badge"
                                style={{ color: tone, borderColor: tone, fontSize: 10 }}>
                            {d.decision}
                          </span>
                          <span className="flex-1 truncate" style={{ fontWeight: 500 }}>
                            {d.title}
                          </span>
                          <span className="kap-mono-tag" style={{ fontSize: 10 }}>
                            {(d.confidence * 100).toFixed(0)}%
                          </span>
                          {d.needs_review && (
                            <span className="kap-badge kap-badge-warning"
                                  style={{ fontSize: 10 }}>待审</span>
                          )}
                        </div>
                        {d.category_path && (
                          <div className="kap-mono-tag"
                               style={{ color: 'hsl(var(--muted-foreground))', fontSize: 10 }}>
                            → 推荐入: {d.category_path}
                          </div>
                        )}
                        {d.reasoning && (
                          <div className="mt-0.5"
                               style={{
                                 color: 'hsl(var(--muted-foreground))',
                                 fontSize: 10.5, lineHeight: 1.5,
                               }}>
                            {d.reasoning.length > 200 ? d.reasoning.slice(0, 200) + '...' : d.reasoning}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            <ReviewStep
              projectId={actualProjectId || industry || 'default'}
              embedded
              onComplete={() => setStage('W4')}
            />
          </KapCard>
        )}
        {stage === 'W4' && (
          <KapCard eyebrow={`▶ ${t('consult.w4.label')}`} frost>
            <TaxonomyStep
              projectId={actualProjectId || industry || 'default'}
              embedded
              onComplete={() => setStage('W5')}
            />
          </KapCard>
        )}
        {stage === 'W5' && (
          <KapCard eyebrow={`▶ ${t('consult.w5.label')}`} frost>
            <CompiledStep
              projectId={actualProjectId || industry || 'default'}
              embedded
              onComplete={() => {
                // 流程完成 → 推送到知识中心 (路由)
                window.location.href = '/v15/manage';
              }}
            />
          </KapCard>
        )}
        {(stage === 'W1' || stage === 'W2') && (
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
        )}

        {/* 右：进度 + 上传 (W1/W2) — Blueprint 旧卡 M22 #11 移除 (替换为中央真功能页) */}
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

          {/* 上传卡 — W1/W2 阶段才显示 (W3 起中央区是真功能页, 不再需上传入口) */}
          {(stage === 'W1' || stage === 'W2') && (
            <ConsultUploader
              projectId={actualProjectId || industry || 'default'}
              onUploaded={async (r, files) => {
                // M22 #11+#12: 上传完通知 LLM (含 per-doc 识别结果) 然后推 W3
                if (r.documents) setRecentDocs(r.documents);
                const names = files.map(f => f.name);
                await sendUploadNotification(names, files.length, r.documents);
                setStage('W3');
              }}
            />
          )}

          {/* 当前 stage badge + 提示 — 替代旧 Blueprint 占位卡 */}
          <KapCard
            eyebrow={`▶ ${t('consult.blueprint.label')}`}
            rightSlot={
              <span className="kap-badge kap-badge-warning">{stage}</span>
            }
          >
            <div className="text-xs" style={{ color: 'var(--kap-snow-4)', lineHeight: 1.6 }}>
              {stage === 'W1' && '选择行业 + AI 对话识别企业知识体系入口'}
              {stage === 'W2' && '上传企业资料 (PDF/Word/Excel/Markdown), 触发 W3 去噪审核'}
              {stage === 'W3' && '中央区显示文档去噪审核队列, LLM 已打分待人工复核异议项'}
              {stage === 'W4' && '中央区显示四级知识体系树 (L1 行业 + L2 企业), 可调整后确认推进'}
              {stage === 'W5' && 'Wiki 三层 (index/domain/source) 编织 + 图谱/向量库完成度报告'}
            </div>
          </KapCard>
        </div>
      </div>
    </CenterShell>
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
