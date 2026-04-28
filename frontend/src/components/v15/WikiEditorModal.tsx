/**
 * WikiEditorModal — V15 Phase G: 人工编辑 Wiki 页
 *
 * Karpathy LLM Wiki 第 9 条：Wiki 必须可被人编辑。
 * 打开时尝试加载 pageId 现有内容；404 则初始化为空（"新建"模式）。
 * 保存调 updateWikiPage (PUT upsert)，version 自动 +1。
 */
import { useEffect, useState } from 'react';
import { X, Save, Loader2, FileText, AlertTriangle } from 'lucide-react';
import {
  fetchWikiPage,
  updateWikiPage,
  type WikiPageDetail,
} from '@/services/api';

interface Props {
  open: boolean;
  pageId: string;
  projectId: string;
  initialTitle?: string;
  initialContent?: string;
  onClose: () => void;
  onSaved: (page: WikiPageDetail) => void;
}

export function WikiEditorModal({
  open,
  pageId,
  projectId,
  initialTitle,
  initialContent,
  onClose,
  onSaved,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [existed, setExisted] = useState(false);
  const [version, setVersion] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchWikiPage(pageId, projectId)
      .then((p) => {
        if (cancelled) return;
        setTitle(p.title);
        setContent(p.content);
        setVersion(p.version);
        setExisted(true);
      })
      .catch(() => {
        if (cancelled) return;
        // 404 视为新建
        setTitle(initialTitle ?? pageId);
        setContent(initialContent ?? `# ${initialTitle ?? pageId}\n\n> 从空白起草（Karpathy Wiki：LLM 草稿 ∥ 人工编辑）\n\n## 概述\n\n请在此处填写内容...\n`);
        setVersion(null);
        setExisted(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, pageId, projectId, initialTitle, initialContent]);

  if (!open) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateWikiPage(pageId, {
        title,
        content,
        status: 'published',
        editor: 'admin',
      }, projectId);
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative w-[900px] max-h-[85vh] rounded-xl overflow-hidden flex flex-col bg-elevated border border-th-border shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-th-border">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-accent" />
            <div>
              <div className="font-medium text-th-text-primary">
                {existed ? `编辑 Wiki` : `新建 Wiki`}
              </div>
              <div className="text-xs text-th-text-muted font-mono">
                {pageId}
                {existed && version !== null && (
                  <> · v{version} → v{version + 1} (保存后)</>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="btn-ghost rounded-lg p-1.5 text-th-text-muted hover:text-th-text-primary"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-th-text-muted">
              <Loader2 size={14} className="animate-spin" /> 加载中...
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs uppercase tracking-wider text-th-text-muted mb-1">
                  标题
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-btn border border-th-border bg-surface px-3 py-2 text-sm text-th-text-primary outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wider text-th-text-muted mb-1">
                  Markdown 正文
                </label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={18}
                  spellCheck={false}
                  className="w-full rounded-btn border border-th-border bg-surface px-3 py-2 text-sm text-th-text-primary outline-none focus:border-accent font-mono leading-6 resize-none"
                />
                <div className="text-xs text-th-text-muted mt-1 font-mono">
                  {content.length} 字 · 支持 Markdown 语法（# 标题 / **粗体** / [[cross_ref]] / `code`）
                </div>
              </div>
            </>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-btn border border-th-error/30 bg-th-error/5 p-3 text-sm text-th-error">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 p-4 border-t border-th-border">
          <div className="text-xs text-th-text-muted">
            {existed ? '编辑已有页 · version 自动 +1' : '从空白新建 · 初始 v1'}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={saving}
              className="btn-secondary rounded-btn px-4 py-2 text-sm"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving || loading || !title.trim() || !content.trim()}
              className="inline-flex items-center gap-2 rounded-btn bg-accent px-4 py-2 text-sm text-white font-medium hover:brightness-95 disabled:opacity-40 transition"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
