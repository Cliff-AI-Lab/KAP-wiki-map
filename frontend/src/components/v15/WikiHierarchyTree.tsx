/**
 * WikiHierarchyTree — V11.2 三层 Wiki 体系可视化（M16 #4）。
 *
 * 决策书 §6 Karpathy 三层 Wiki 体系：
 *   index (根索引)
 *     └─ domain_overview (领域概览，多个)
 *           └─ source_summary (源文档摘要，多个)
 *
 * 拉 GET /api/v1/wiki/pages 后按 page_type + parent_page_id 构造树形展示，
 * 让 SME 直观看 Wiki 编译结构 + 各层级 page 数。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ChevronRight, ChevronDown, BookOpen, Layers, FileText,
  Loader2, RefreshCw, AlertCircle,
} from 'lucide-react';

import {
  fetchWikiPages, type WikiPageSummary,
} from '@/services/api';
import { useLocale } from '@/contexts/LocaleContext';

interface Props {
  projectId?: string;
  /** 点 page 时调用（可选；不传则不可点击） */
  onSelectPage?: (pageId: string) => void;
}

interface TreeNode {
  page: WikiPageSummary;
  children: TreeNode[];
}

function buildTree(pages: WikiPageSummary[]): TreeNode[] {
  const byParent: Record<string, WikiPageSummary[]> = {};
  for (const p of pages) {
    const parent = p.parent_page_id || '';
    (byParent[parent] = byParent[parent] || []).push(p);
  }
  // 根：parent_page_id 为空
  const roots = byParent[''] || [];
  // 优先 index 类型在前
  roots.sort((a, b) => {
    if (a.page_type === 'index' && b.page_type !== 'index') return -1;
    if (b.page_type === 'index' && a.page_type !== 'index') return 1;
    return a.title.localeCompare(b.title);
  });

  function attach(p: WikiPageSummary): TreeNode {
    const children = (byParent[p.page_id] || []).map(attach);
    return { page: p, children };
  }
  return roots.map(attach);
}


function TypeIcon({ type }: { type: string }) {
  const cls = 'shrink-0';
  if (type === 'index') return <Layers size={14} className={`${cls} text-accent`} />;
  if (type === 'domain_overview') return <BookOpen size={14} className={`${cls} text-emerald-600`} />;
  return <FileText size={14} className={`${cls} text-th-text-muted`} />;
}


function NodeRow({
  node, depth, onSelectPage,
}: {
  node: TreeNode;
  depth: number;
  onSelectPage?: (pageId: string) => void;
}) {
  const [open, setOpen] = useState(depth < 2);    // 默认展开前 2 层
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1 px-2 rounded text-xs hover:bg-hover/40 transition ${
          onSelectPage ? 'cursor-pointer' : ''
        }`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => {
          if (hasChildren) setOpen((o) => !o);
          if (onSelectPage) onSelectPage(node.page.page_id);
        }}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown size={12} className="text-th-text-muted shrink-0" />
          ) : (
            <ChevronRight size={12} className="text-th-text-muted shrink-0" />
          )
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <TypeIcon type={node.page.page_type} />
        <span className="text-th-text-primary truncate flex-1">
          {node.page.title}
        </span>
        {node.page.source_doc_count > 0 && (
          <span className="text-[10px] text-th-text-muted font-mono shrink-0">
            {node.page.source_doc_count} src
          </span>
        )}
        {node.page.cross_ref_count > 0 && (
          <span className="text-[10px] text-th-text-muted font-mono shrink-0">
            ↔ {node.page.cross_ref_count}
          </span>
        )}
      </div>
      {open && node.children.map((c) => (
        <NodeRow
          key={c.page.page_id}
          node={c}
          depth={depth + 1}
          onSelectPage={onSelectPage}
        />
      ))}
    </div>
  );
}


export default function WikiHierarchyTree({
  projectId, onSelectPage,
}: Props) {
  const { t } = useLocale();
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchWikiPages(projectId);
      setPages(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const tree = buildTree(pages);
  const counts = {
    index: pages.filter((p) => p.page_type === 'index').length,
    domain: pages.filter((p) => p.page_type === 'domain_overview').length,
    source: pages.filter((p) => p.page_type === 'source_summary').length,
  };

  return (
    <div className="rounded-card border border-th-border bg-elevated p-3">
      <div className="flex items-center gap-2 mb-2">
        <Layers size={14} className="text-accent" />
        <span className="text-sm font-mono text-th-text-muted">
          Wiki 三层结构
        </span>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-btn border border-th-border text-[11px] text-th-text-muted hover:text-accent hover:border-accent disabled:opacity-40"
        >
          {loading ? (
            <Loader2 size={10} className="animate-spin" />
          ) : (
            <RefreshCw size={10} />
          )}
          刷新
        </button>
      </div>

      {/* 各层计数 */}
      <div className="grid grid-cols-3 gap-2 mb-3 text-[11px]">
        <div className="rounded p-2 border border-th-border">
          <div className="flex items-center gap-1 text-th-text-muted">
            <Layers size={10} /> {t('wiki.layer.index')}
            <span className="ml-auto font-mono text-[10px]">index</span>
          </div>
          <div className="text-base font-semibold text-accent mt-0.5">
            {counts.index}
          </div>
        </div>
        <div className="rounded p-2 border border-th-border">
          <div className="flex items-center gap-1 text-th-text-muted">
            <BookOpen size={10} /> {t('wiki.layer.domain_overview')}
            <span className="ml-auto font-mono text-[10px]">domain</span>
          </div>
          <div className="text-base font-semibold text-emerald-700 mt-0.5">
            {counts.domain}
          </div>
        </div>
        <div className="rounded p-2 border border-th-border">
          <div className="flex items-center gap-1 text-th-text-muted">
            <FileText size={10} /> {t('wiki.layer.source_summary')}
            <span className="ml-auto font-mono text-[10px]">source</span>
          </div>
          <div className="text-base font-semibold text-th-text-primary mt-0.5">
            {counts.source}
          </div>
        </div>
      </div>

      {error && (
        <div className="text-xs text-rose-600 py-2 flex items-center gap-1">
          <AlertCircle size={12} /> {error}
        </div>
      )}

      {!loading && pages.length === 0 && !error && (
        <div className="text-xs text-th-text-muted py-4 text-center border border-dashed border-th-border rounded">
          暂无 Wiki 页面（先在 W6 工位编译）
        </div>
      )}

      {tree.length > 0 && (
        <div className="max-h-[400px] overflow-y-auto">
          {tree.map((root) => (
            <NodeRow
              key={root.page.page_id}
              node={root}
              depth={0}
              onSelectPage={onSelectPage}
            />
          ))}
        </div>
      )}
    </div>
  );
}
