/**
 * 咨询中心 — 三中心统一设计 (M21 #4)
 *
 * 严格按 distinctive.css Nordic Minimalism 系统渲染。
 * 与 GovernanceHome / ReaderHome 共用 CenterShell + CenterHero + Pipeline + StatTile + KapCard。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Send, Loader2, FileDown, FolderPlus, Upload, Filter, Network, BookOpen,
  Bot, User, CornerDownLeft, Sparkles, Paperclip, FileText,
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
import { ingestFiles, type IngestDocResult } from '@/services/api';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

type StageId = 'W1' | 'W2' | 'W3' | 'W4' | 'W5';

interface Msg {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: Date;
  // M22 #16: 对话流上传 — 用 attachments 表示上传的文件元数据 (user 角色 file_upload)
  attachments?: Array<{ name: string; size: number }>;
  // M22 #16: assistant 给的"识别 + 入库分类"结果, 渲染为 per-doc chip + inline 调整入口
  analysis?: IngestDocResult[];
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
  // M22 #15: 当前展开编辑的 doc_id (null = 没有展开)
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [savingDocId, setSavingDocId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // M22 #16: 对话流上传 — fileInput 引用 + 上传中标记
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingInChat, setUploadingInChat] = useState(false);

  // 所有 hook 必须在条件 return 前调用（React Hooks 规则）
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  // M22 #13: industry 切换 → ensure 真实项目 + 自动 seed L1 domains
  // M22 #15.1: 同步把顶栏 active project 切到该项目, 让消费/知识中心默认看相同数据
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
          // 同步顶栏 active project (跨中心共享上下文, 消费中心立即能拿对项目)
          try {
            localStorage.setItem('wikimap-active-project', d.id);
            // M22 #18: 通知所有 useActiveProject 实例 (顶栏 / 知识中心 / 消费中心) 立即切换
            window.dispatchEvent(new Event('kap:active-project-changed'));
          } catch {}
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

  /**
   * M22 #16 · 对话流内上传 — 用户从聊天框 paperclip 触发, 文件作为 user message
   * 显示在对话流中, ingest 完成后追加 assistant 识别结果 message (含 per-doc chip),
   * 同步切到 W3 + recentDocs 给 W3 中央卡片用。
   */
  const uploadInChat = async (files: File[]) => {
    if (!files.length || uploadingInChat) return;
    setUploadingInChat(true);
    // 1. user file_upload message
    const attachments = files.map(f => ({ name: f.name, size: f.size }));
    const userMsgContent = `📎 上传 ${files.length} 个材料:\n` +
      files.map(f => `  · ${f.name} (${(f.size / 1024).toFixed(1)} KB)`).join('\n');
    setMessages(m => [...m, {
      id: shortId(), role: 'user', content: userMsgContent,
      attachments, ts: new Date(),
    }]);

    try {
      const projId = actualProjectId || industry || 'default';
      const r = await ingestFiles(files, projId);
      const docs = r.documents || [];
      // 2. recentDocs 同步 (W3 中央卡片用)
      setRecentDocs(docs);
      // 3. assistant analysis message
      let summary = `◆ LLM 已识别 ${docs.length} 个文档:\n`;
      docs.forEach(d => {
        const cat = d.domain_path || d.category_path || '未分类';
        const reviewTag = d.needs_review ? ' [待 SME 审核]' : '';
        summary += `  · ${d.title} → ${d.decision} (${(d.confidence * 100).toFixed(0)}%, 归入 "${cat}")${reviewTag}\n`;
      });
      const pending = docs.filter(d => d.needs_review).length;
      if (pending > 0) {
        summary += `\n${pending} 个文档待审。点对话框内文档卡片可调整分类 / 决策, 或切到 W3 去噪审核台批量处理。`;
      } else {
        summary += '\n所有文档已自动归入推荐分支, 可切到 W4 查看知识体系树。';
      }
      setMessages(m => [...m, {
        id: shortId(), role: 'assistant', content: summary,
        analysis: docs, ts: new Date(),
      }]);
      // 4. 自动切 W3 (但用户可选择留在对话中审核)
      setStage('W3');
    } catch (e) {
      setError(`上传失败: ${(e as Error).message}`);
      setMessages(m => [...m, {
        id: shortId(), role: 'system',
        content: `⚠ 上传或识别失败: ${(e as Error).message}`,
        ts: new Date(),
      }]);
    } finally {
      setUploadingInChat(false);
    }
  };

  // M22 #15 · 人工调整文档元数据 (decision / keywords / category_path / domain_id)
  const patchDoc = async (
    docId: string,
    patch: Partial<{ decision: string; keywords: string[]; category_path: string; domain_id: string }>,
  ) => {
    setSavingDocId(docId);
    try {
      const projId = actualProjectId || industry || 'default';
      const r = await fetch(
        `${API_BASE}/api/v1/knowledge/documents/${encodeURIComponent(docId)}?project_id=${encodeURIComponent(projId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        },
      );
      if (!r.ok) throw new Error(`patch failed: ${r.status}`);
      // 乐观更新本地 recentDocs
      setRecentDocs(prev => prev.map(d => {
        if (d.doc_id !== docId) return d;
        return {
          ...d,
          decision: (patch.decision ?? d.decision) as IngestDocResult['decision'],
          keywords: patch.keywords ?? d.keywords,
          category_path: patch.category_path ?? d.category_path,
          domain_id: patch.domain_id ?? d.domain_id,
        };
      }));
      setEditingDocId(null);
    } catch (e) {
      setError(`保存失败: ${(e as Error).message}`);
    } finally {
      setSavingDocId(null);
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
                        {/* M22 #14: 体系归属链 (从 domain_id 转中文 label) */}
                        {d.domain_path && (
                          <div className="kap-mono-tag mt-0.5"
                               style={{ color: 'hsl(var(--primary))', fontSize: 10 }}>
                            ◆ 体系归属: {d.domain_path}
                          </div>
                        )}
                        {d.category_path && d.category_path !== d.domain_path && (
                          <div className="kap-mono-tag"
                               style={{ color: 'hsl(var(--muted-foreground))', fontSize: 10 }}>
                            → 推荐入: {d.category_path}
                          </div>
                        )}
                        {/* M22 #14: 关键词标签 (LLM 提炼) */}
                        {d.keywords && d.keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {d.keywords.map(kw => (
                              <span key={kw} className="kap-badge"
                                    style={{ fontSize: 9.5, padding: '1px 5px' }}>
                                #{kw}
                              </span>
                            ))}
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
                        {/* M22 #15: 人工调整入口 */}
                        <div className="mt-1 flex justify-end">
                          <button
                            onClick={() => setEditingDocId(editingDocId === d.doc_id ? null : d.doc_id)}
                            className="kap-btn kap-btn-ghost"
                            style={{ fontSize: 10, padding: '2px 8px' }}
                          >
                            {editingDocId === d.doc_id ? '✕ 取消' : '✎ 调整'}
                          </button>
                        </div>
                        {editingDocId === d.doc_id && (
                          <DocEditor
                            doc={d}
                            saving={savingDocId === d.doc_id}
                            onSave={(patch) => patchDoc(d.doc_id, patch)}
                          />
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
            {/* M22 #15.1: actualProjectId 还在 ensure 时显示 loading, 避免渲染空树 */}
            {!actualProjectId ? (
              <div className="text-xs text-center py-12"
                   style={{ color: 'hsl(var(--muted-foreground))' }}>
                <Loader2 size={20} className="animate-spin mx-auto mb-2"
                         style={{ color: 'hsl(var(--primary))' }} />
                正在为 {industryLabel || industry} 加载行业知识体系（48 个域）...
              </div>
            ) : (
              <>
                {/* M22 #15.1: 体系生成摘要卡片 - 让用户看到"体系已形成" */}
                <div className="mb-4 p-3 rounded-btn"
                     style={{
                       background: 'hsl(var(--muted) / 0.4)',
                       border: '1px solid hsl(var(--border))',
                     }}>
                  <div className="kap-mono-tag mb-2"
                       style={{ color: 'hsl(var(--primary))' }}>
                    ◆ 知识体系已形成
                  </div>
                  <div className="text-xs" style={{ lineHeight: 1.6 }}>
                    <div>
                      行业: <span style={{ fontWeight: 600 }}>{industryLabel || industry}</span>
                      {' · '}
                      项目 ID: <span className="kap-mono-tag" style={{ fontSize: 10 }}>{actualProjectId}</span>
                    </div>
                    <div style={{ color: 'hsl(var(--muted-foreground))', marginTop: 4 }}>
                      L1 行业预置 4 级模板 + L2 企业自有体系 (LLM 自动生成 / 人工调整)。
                      下方树展开看完整体系, 点节点查文档归属。
                    </div>
                    {recentDocs.length > 0 && (
                      <div style={{ marginTop: 6, color: 'hsl(var(--primary))' }}>
                        ◇ 本次上传 {recentDocs.length} 个文档已归入体系:
                        {' '}
                        {Array.from(new Set(recentDocs.map(d => d.domain_path).filter(Boolean))).join(' · ')}
                      </div>
                    )}
                  </div>
                </div>
                <TaxonomyStep
                  projectId={actualProjectId}
                  embedded
                  onComplete={() => setStage('W5')}
                />
              </>
            )}
          </KapCard>
        )}
        {stage === 'W5' && (
          <KapCard eyebrow={`▶ ${t('consult.w5.label')}`} frost>
            {!actualProjectId ? (
              <div className="text-xs text-center py-12"
                   style={{ color: 'hsl(var(--muted-foreground))' }}>
                <Loader2 size={20} className="animate-spin mx-auto mb-2"
                         style={{ color: 'hsl(var(--primary))' }} />
                正在为 {industryLabel || industry} 准备 Wiki 编织...
              </div>
            ) : (
              <>
                {/* M22 #15.1: Wiki 编织摘要 */}
                <div className="mb-4 p-3 rounded-btn"
                     style={{
                       background: 'hsl(var(--muted) / 0.4)',
                       border: '1px solid hsl(var(--border))',
                     }}>
                  <div className="kap-mono-tag mb-2"
                       style={{ color: 'hsl(var(--primary))' }}>
                    ◆ Wiki 三层编织 + 端到端跑通
                  </div>
                  <div className="text-xs" style={{ lineHeight: 1.6 }}>
                    KAP 将上传材料按知识体系编织成 3 层 Wiki:
                    <span className="kap-mono-tag mx-1" style={{ fontSize: 10 }}>source</span>(每文档一页)
                    {' · '}
                    <span className="kap-mono-tag mx-1" style={{ fontSize: 10 }}>domain</span>(域级聚合)
                    {' · '}
                    <span className="kap-mono-tag mx-1" style={{ fontSize: 10 }}>index</span>(顶级索引)
                    {' · '}
                    同步入库 (向量化 + 图谱化) → 下方报告查看进度。
                  </div>
                  <div style={{ marginTop: 8, color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>
                    点 "完成 · 进入知识中心" 切换到知识中心查看完整入库结果 (消费中心可调用 Wiki / RAG / 图谱 三路召回)
                  </div>
                </div>
                <CompiledStep
                  projectId={actualProjectId}
                  embedded
                  onComplete={() => {
                    // M22 #15.1+#18: 跳转前把顶栏 active project 切到 actualProjectId
                    // 让消费中心 / 知识中心都默认看这个项目的数据 (能召回)
                    try {
                      localStorage.setItem('wikimap-active-project', actualProjectId);
                      window.dispatchEvent(new Event('kap:active-project-changed'));
                    } catch {}
                    window.location.href = '/v15/manage';
                  }}
                />
              </>
            )}
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

          {/* 输入区 (M22 #16: 加附件上传按钮, 与 send 并列) */}
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
              {/* M22 #16: 附件上传按钮 (paperclip) */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingInChat}
                className="kap-btn"
                title="上传材料 (PDF/Word/Excel/Markdown/TXT)"
              >
                {uploadingInChat
                  ? <Loader2 size={12} className="animate-spin" />
                  : <Paperclip size={12} />}
                附件
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.md,.markdown,.txt,.rtf"
                multiple
                onChange={e => {
                  const fs = Array.from(e.target.files || []);
                  if (fs.length) uploadInChat(fs);
                  e.target.value = '';  // reset 让同名文件可重复传
                }}
                className="hidden"
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
              [ENTER] {t('consult.sendHint')} · [SHIFT+ENTER] {t('consult.newlineHint')} · [📎附件] 直接在对话上传材料
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


// M22 #15 · 文档人工调整 inline 编辑器
function DocEditor({
  doc, saving, onSave,
}: {
  doc: IngestDocResult;
  saving: boolean;
  onSave: (patch: { decision?: string; keywords?: string[]; category_path?: string; domain_id?: string }) => void;
}) {
  const [decision, setDecision] = useState(doc.decision);
  const [keywordsText, setKeywordsText] = useState((doc.keywords || []).join(', '));
  const [categoryPath, setCategoryPath] = useState(doc.category_path || '');
  const [domainId, setDomainId] = useState(doc.domain_id || '');

  return (
    <div className="mt-2 p-2 rounded-btn" style={{
      background: 'hsl(var(--muted) / 0.6)',
      border: '1px dashed hsl(var(--primary) / 0.4)',
      fontSize: 11,
    }}>
      {/* decision */}
      <div className="mb-2">
        <div className="kap-mono-tag mb-1" style={{ fontSize: 9.5 }}>decision</div>
        <div className="flex gap-1">
          {(['KEEP', 'ARCHIVE', 'DISCARD'] as const).map(opt => (
            <button
              key={opt}
              onClick={() => setDecision(opt)}
              className={`kap-btn ${decision === opt ? 'kap-btn-primary' : ''}`}
              style={{ fontSize: 10, padding: '2px 8px' }}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>
      {/* domain_id */}
      <div className="mb-2">
        <div className="kap-mono-tag mb-1" style={{ fontSize: 9.5 }}>体系 domain_id (e.g. manufacturing/quality/inspection)</div>
        <input
          value={domainId}
          onChange={e => setDomainId(e.target.value)}
          className="kap-input"
          style={{ fontSize: 11, padding: '3px 6px', width: '100%' }}
        />
      </div>
      {/* category_path */}
      <div className="mb-2">
        <div className="kap-mono-tag mb-1" style={{ fontSize: 9.5 }}>category_path 中文分类</div>
        <input
          value={categoryPath}
          onChange={e => setCategoryPath(e.target.value)}
          className="kap-input"
          style={{ fontSize: 11, padding: '3px 6px', width: '100%' }}
        />
      </div>
      {/* keywords */}
      <div className="mb-2">
        <div className="kap-mono-tag mb-1" style={{ fontSize: 9.5 }}>keywords (英文逗号分隔)</div>
        <textarea
          value={keywordsText}
          onChange={e => setKeywordsText(e.target.value)}
          rows={2}
          className="kap-input"
          style={{ fontSize: 11, padding: '3px 6px', width: '100%', resize: 'none' }}
        />
      </div>
      <div className="flex justify-end">
        <button
          disabled={saving}
          onClick={() => {
            const kws = keywordsText.split(',').map(s => s.trim()).filter(Boolean);
            onSave({
              decision: decision !== doc.decision ? decision : undefined,
              keywords: kws.join(',') !== (doc.keywords || []).join(',') ? kws : undefined,
              category_path: categoryPath !== doc.category_path ? categoryPath : undefined,
              domain_id: domainId !== doc.domain_id ? domainId : undefined,
            });
          }}
          className="kap-btn kap-btn-primary"
          style={{ fontSize: 10, padding: '3px 10px' }}
        >
          {saving ? '保存中...' : '保存调整'}
        </button>
      </div>
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
        {/* M22 #16: attachments chip (user 角色 file_upload) */}
        {m.attachments && m.attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {m.attachments.map((f, i) => (
              <span key={`${f.name}-${i}`} className="kap-badge"
                    style={{ fontSize: 10, padding: '2px 7px',
                             background: 'hsl(var(--muted) / 0.6)' }}>
                <FileText size={10} style={{ display: 'inline', marginRight: 3 }} />
                {f.name}
              </span>
            ))}
          </div>
        )}
        {/* M22 #16: analysis 卡片 (assistant 角色 doc 分析结果) */}
        {m.analysis && m.analysis.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {m.analysis.map(d => {
              const tone = d.decision === 'KEEP'    ? 'hsl(var(--success))'
                         : d.decision === 'ARCHIVE' ? 'hsl(var(--warning))'
                         : d.decision === 'DISCARD' ? 'hsl(var(--destructive))'
                         : 'hsl(var(--muted-foreground))';
              return (
                <li key={d.doc_id} style={{
                  padding: '0.4rem 0.6rem',
                  background: 'hsl(var(--muted) / 0.4)',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 'calc(var(--radius) - 4px)',
                  fontSize: 11.5, lineHeight: 1.5,
                }}>
                  <div className="flex items-center gap-2">
                    <span className="kap-badge"
                          style={{ color: tone, borderColor: tone, fontSize: 10 }}>
                      {d.decision}
                    </span>
                    <span className="flex-1 truncate" style={{ fontWeight: 500 }}>
                      {d.title}
                    </span>
                    <span style={{ fontSize: 10, color: 'hsl(var(--muted-foreground))' }}>
                      {(d.confidence * 100).toFixed(0)}%
                    </span>
                    {d.needs_review && (
                      <span className="kap-badge kap-badge-warning" style={{ fontSize: 10 }}>
                        待审
                      </span>
                    )}
                  </div>
                  {d.domain_path && (
                    <div style={{ color: 'hsl(var(--primary))', fontSize: 10, marginTop: 2 }}>
                      ◆ 体系: {d.domain_path}
                    </div>
                  )}
                  {d.keywords && d.keywords.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {d.keywords.slice(0, 6).map(kw => (
                        <span key={kw} className="kap-badge"
                              style={{ fontSize: 9.5, padding: '1px 5px' }}>
                          #{kw}
                        </span>
                      ))}
                      {d.keywords.length > 6 && (
                        <span style={{ fontSize: 9.5, color: 'hsl(var(--muted-foreground))' }}>
                          +{d.keywords.length - 6}
                        </span>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
