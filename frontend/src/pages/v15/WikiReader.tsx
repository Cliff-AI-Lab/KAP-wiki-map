/**
 * WikiReader — V15 Phase H: 阅读模式 + 交叉引用跳转 + 溯源穿透
 *
 * 路由: /v15/wiki/:pageId*  (pageId 可含 slash, 如 domain/energy/safety/hazard)
 *
 * 交叉引用处理：
 *   [[xxx]]          → <a href="/v15/wiki/xxx">
 *   [← doc_id]       → <a href="/v15/raw/doc_id"> 打开溯源浮层 (而非跳转)
 *
 * Karpathy Wiki 第 6 条: 交叉引用 + 溯源完整链
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowLeft, Edit3, FileText, ExternalLink, X } from 'lucide-react';

import { useActiveProject } from '@/hooks/useActiveProject';
import { fetchWikiPage, fetchDocument, type WikiPageDetail, type DocumentDetail } from '@/services/api';
import { WikiEditorModal } from '@/components/v15/WikiEditorModal';

/** 预处理 Markdown: [[xx]] 转成普通 link，[← doc_id] 转成溯源 link */
function preprocessMarkdown(md: string): string {
  let out = md;
  // [[domain/foo/bar]] -> [domain/foo/bar](/v15/wiki/domain/foo/bar)
  out = out.replace(/\[\[([^\]]+)\]\]/g, (_m, ref: string) => {
    const clean = ref.trim();
    return `[${clean}](/v15/wiki/${encodeURI(clean)})`;
  });
  // [← doc_id]  或 [<- doc_id] -> [← doc_id](/v15/raw/doc_id)
  out = out.replace(/\[(?:←|<-)\s*([^\]]+?)\]/g, (_m, docId: string) => {
    const id = docId.trim();
    return `[← ${id}](/v15/raw/${encodeURIComponent(id)})`;
  });
  return out;
}

function RawSourcePopup({
  docId,
  projectId,
  onClose,
}: {
  docId: string;
  projectId: string;
  onClose: () => void;
}) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDocument(docId, projectId)
      .then((d) => !cancelled && setDoc(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [docId, projectId]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative w-[800px] max-h-[80vh] rounded-xl bg-elevated border border-th-border shadow-lg flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-th-border">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-accent" />
            <div>
              <div className="text-sm font-medium text-th-text-primary">溯源 · 原始文档</div>
              <div className="text-xs text-th-text-muted font-mono">{docId}</div>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost rounded-lg p-1.5 text-th-text-muted">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {loading && <div className="text-sm text-th-text-muted">加载中...</div>}
          {error && (
            <div className="text-sm text-th-error">原文不可读取: {error}</div>
          )}
          {doc && (
            <div className="space-y-3">
              <div className="text-base font-semibold text-th-text-primary">{doc.title || docId}</div>
              <div className="text-xs text-th-text-muted font-mono">
                {doc.source_system ?? 'local'}
                {doc.category_path && ` · ${doc.category_path}`}
              </div>
              <div className="text-sm text-th-text-primary whitespace-pre-wrap border-t border-th-border pt-3">
                {doc.summary || '(无原文摘要)'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function WikiReader() {
  const params = useParams<{ '*'?: string; pageId?: string }>();
  const pageId = params['*'] || params.pageId || '';
  const navigate = useNavigate();
  const { projectId } = useActiveProject();

  const [page, setPage] = useState<WikiPageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [rawDocId, setRawDocId] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    if (!pageId) {
      // 无 pageId 视为非加载态，避免永久 loading
      setLoading(false);
      setPage(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);  // Bug 修复: 切页时清旧错误
    setPage(null);
    fetchWikiPage(pageId, projectId)
      .then((p) => !cancelled && setPage(p))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [pageId, projectId]);

  const processedContent = useMemo(() => {
    if (!page) return '';
    return preprocessMarkdown(page.content);
  }, [page]);

  if (!projectId) {
    return <div className="text-sm text-th-text-muted">加载项目...</div>;
  }
  if (!pageId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-6 space-y-2">
        <div className="text-th-text-primary">未指定 Wiki 页</div>
        <div className="text-sm text-th-text-muted">访问形如 <code className="v15-mono">/v15/read/wiki/&lt;page_id&gt;</code></div>
      </div>
    );
  }
  if (loading) {
    return <div className="text-sm text-th-text-muted">加载 Wiki 页...</div>;
  }
  if (error || !page) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-6 space-y-3">
        <div className="text-th-text-primary">Wiki 页不存在</div>
        <div className="text-sm text-th-text-muted">{pageId}</div>
        {error && <div className="text-xs text-th-error font-mono">{error}</div>}
        <button
          onClick={() => setEditing(true)}
          className="inline-flex items-center gap-2 rounded-btn bg-accent px-4 py-2 text-sm text-white"
        >
          <Edit3 size={14} /> 从空白起草
        </button>
        {editing && (
          <WikiEditorModal
            open
            pageId={pageId}
            projectId={projectId}
            initialTitle={pageId.split('/').pop() ?? pageId}
            onClose={() => setEditing(false)}
            onSaved={(p) => { setPage(p); setError(null); }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="btn-ghost rounded-btn p-1.5 text-th-text-muted hover:text-th-text-primary"
          aria-label="返回"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-th-text-primary truncate">
            {page.title}
          </h1>
          <div className="text-xs text-th-text-muted font-mono truncate">
            {pageId} · v{page.version} · {page.status}
            {page.compiled_at && ` · ${page.compiled_at.slice(0, 16).replace('T', ' ')}`}
          </div>
        </div>
        <button
          onClick={() => setEditing(true)}
          className="inline-flex items-center gap-1.5 rounded-btn border border-th-border px-3 py-1.5 text-sm text-th-text-primary hover:bg-hover"
        >
          <Edit3 size={13} /> 编辑
        </button>
      </div>

      <article className="rounded-card border border-th-border bg-elevated p-6 prose prose-sm max-w-none text-th-text-primary">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children, ...rest }) => {
              if (href?.startsWith('/v15/wiki/')) {
                return (
                  <Link
                    to={href}
                    className="text-accent hover:underline underline-offset-2"
                  >
                    {children}
                  </Link>
                );
              }
              if (href?.startsWith('/v15/raw/')) {
                const id = decodeURIComponent(href.slice('/v15/raw/'.length));
                return (
                  <button
                    type="button"
                    onClick={() => setRawDocId(id)}
                    className="text-accent-secondary hover:underline underline-offset-2 font-mono text-xs"
                  >
                    {children}
                  </button>
                );
              }
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline inline-flex items-center gap-1"
                  {...rest}
                >
                  {children}
                  <ExternalLink size={11} />
                </a>
              );
            },
          }}
        >
          {processedContent}
        </ReactMarkdown>
      </article>

      {page.cross_refs.length > 0 && (
        <div className="rounded-card border border-th-border bg-elevated p-4">
          <div className="text-xs uppercase tracking-wider text-th-text-muted mb-3">
            交叉引用 · {page.cross_refs.length}
          </div>
          <div className="flex flex-wrap gap-2">
            {page.cross_refs.map((ref) => (
              <Link
                key={ref}
                to={`/v15/wiki/${encodeURI(ref)}`}
                className="inline-flex items-center gap-1 rounded-pill border border-th-border bg-hover px-3 py-1 text-xs font-mono text-th-text-primary hover:text-accent hover:border-accent transition"
              >
                {ref}
              </Link>
            ))}
          </div>
        </div>
      )}

      {page.source_doc_ids.length > 0 && (
        <div className="rounded-card border border-th-border bg-elevated p-4">
          <div className="text-xs uppercase tracking-wider text-th-text-muted mb-3">
            源文档 · {page.source_doc_ids.length}
          </div>
          <ul className="space-y-1.5">
            {page.source_doc_ids.map((doc_id) => (
              <li key={doc_id}>
                <button
                  type="button"
                  onClick={() => setRawDocId(doc_id)}
                  className="text-xs font-mono text-accent-secondary hover:underline"
                >
                  ← {doc_id}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {editing && (
        <WikiEditorModal
          open
          pageId={pageId}
          projectId={projectId}
          onClose={() => setEditing(false)}
          onSaved={(p) => setPage(p)}
        />
      )}

      {rawDocId && (
        <RawSourcePopup
          docId={rawDocId}
          projectId={projectId}
          onClose={() => setRawDocId(null)}
        />
      )}
    </div>
  );
}
