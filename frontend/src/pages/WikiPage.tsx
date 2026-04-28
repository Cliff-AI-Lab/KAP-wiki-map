/**
 * @file WikiPage.tsx
 * @description 知识Wiki页面 — V11.2 Karpathy三层Wiki体系
 *
 * 左右分栏:
 * - 左侧: Wiki页面树 (index → domain_overview → source_summary)
 * - 右侧: Markdown 内容渲染
 *
 * V11.2 核心改进:
 * - 用 wiki page 列表自身构建树（不再依赖 domain tree 匹配）
 * - 三层结构: 索引 → 域概览 → 源文档知识卡片
 * - 彻底修复域点击不显示 Wiki 内容的 bug
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  BookMarked, ChevronRight, ChevronDown, FileText, Clock,
  RefreshCw, BookOpen, AlertCircle, Layers, Hash,
  Library, FolderOpen, FileCheck,
} from 'lucide-react';
import { Badge, Button } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { useProject } from '@/contexts/ProjectContext';
import { fetchWikiPages, fetchWikiPage, fetchWikiStats } from '@/services/api';
import type { WikiPageSummary, WikiPageDetail, WikiStats, WikiPageType } from '@/services/api';

/* ── Helpers ── */

function statusVariant(status: string): 'success' | 'warning' | 'info' | 'neutral' {
  switch (status.toLowerCase()) {
    case 'published': return 'success';
    case 'stale': return 'warning';
    case 'draft': return 'info';
    default: return 'neutral';
  }
}

function statusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'published': return '\u5df2\u53d1\u5e03';
    case 'stale': return '\u5f85\u66f4\u65b0';
    case 'draft': return '\u8349\u7a3f';
    default: return status;
  }
}

function pageTypeLabel(type: WikiPageType): string {
  switch (type) {
    case 'index': return '\u7d22\u5f15';
    case 'domain_overview': return '\u57df\u6982\u89c8';
    case 'source_summary': return '\u77e5\u8bc6\u5361\u7247';
    default: return type;
  }
}

function pageTypeIcon(type: WikiPageType) {
  switch (type) {
    case 'index': return <Library size={12} />;
    case 'domain_overview': return <FolderOpen size={12} />;
    case 'source_summary': return <FileCheck size={12} />;
    default: return <FileText size={12} />;
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return '\u672a\u7f16\u8bd1';
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

/* ── Wiki Tree Node ── */

interface WikiTreeNode {
  page: WikiPageSummary;
  children: WikiTreeNode[];
}

/** Build wiki tree from flat page list using parent_page_id relationships */
function buildWikiTree(pages: WikiPageSummary[]): WikiTreeNode[] {
  const nodeMap = new Map<string, WikiTreeNode>();

  // Create nodes for all pages
  for (const p of pages) {
    nodeMap.set(p.page_id, { page: p, children: [] });
  }

  const roots: WikiTreeNode[] = [];

  // Build parent-child relationships
  for (const p of pages) {
    const node = nodeMap.get(p.page_id)!;
    if (p.parent_page_id && nodeMap.has(p.parent_page_id)) {
      nodeMap.get(p.parent_page_id)!.children.push(node);
    } else if (p.page_type === 'index') {
      // Index pages are always roots
      roots.unshift(node);
    } else if (p.page_type === 'domain_overview') {
      // Domain pages without parent go to root
      roots.push(node);
    } else {
      // Orphan source pages — group under their parent_page_id label
      roots.push(node);
    }
  }

  // Sort children: domain_overview first, then source_summary by title
  const sortChildren = (nodes: WikiTreeNode[]) => {
    nodes.sort((a, b) => {
      const typeOrder = { index: 0, domain_overview: 1, source_summary: 2 };
      const ta = typeOrder[a.page.page_type as keyof typeof typeOrder] ?? 3;
      const tb = typeOrder[b.page.page_type as keyof typeof typeOrder] ?? 3;
      if (ta !== tb) return ta - tb;
      return a.page.title.localeCompare(b.page.title, 'zh-CN');
    });
    for (const n of nodes) sortChildren(n.children);
  };
  sortChildren(roots);

  return roots;
}

/* ── Wiki Tree Node Component ── */

interface WikiTreeNodeProps {
  node: WikiTreeNode;
  selectedId: string | null;
  onSelect: (pageId: string) => void;
  depth: number;
}

function WikiTreeNodeItem({ node, selectedId, onSelect, depth }: WikiTreeNodeProps) {
  const [expanded, setExpanded] = useState(
    node.page.page_type === 'index' || node.page.page_type === 'domain_overview',
  );
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.page.page_id;
  const p = node.page;

  return (
    <div>
      <button
        onClick={() => {
          onSelect(p.page_id);
          if (hasChildren) setExpanded((v) => !v);
        }}
        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-btn text-sm transition-all duration-150 text-left ${
          isSelected
            ? 'text-accent font-medium'
            : 'text-th-text-secondary hover:text-th-text-primary'
        }`}
        style={{
          paddingLeft: `${depth * 14 + 8}px`,
          background: isSelected ? 'rgba(85, 179, 255, 0.08)' : 'transparent',
        }}
      >
        {hasChildren ? (
          expanded ? (
            <ChevronDown size={12} className="shrink-0 text-th-text-muted" />
          ) : (
            <ChevronRight size={12} className="shrink-0 text-th-text-muted" />
          )
        ) : (
          <span className="w-3 shrink-0" />
        )}

        {/* Status dot */}
        <div
          className="w-2 h-2 rounded-full shrink-0"
          style={{
            background: p.status === 'published'
              ? 'var(--color-success)'
              : p.status === 'stale'
              ? 'var(--color-warning)'
              : 'var(--color-info)',
          }}
          title={statusLabel(p.status)}
        />

        {/* Type icon */}
        <span className="shrink-0 text-th-text-muted opacity-60">
          {pageTypeIcon(p.page_type)}
        </span>

        {/* Title */}
        <span className="truncate flex-1">
          {p.title}
        </span>

        {/* Source count for domain pages */}
        {p.page_type === 'domain_overview' && p.source_doc_count > 0 && (
          <span className="text-[10px] text-th-text-muted tabular-nums shrink-0">
            {p.source_doc_count}
          </span>
        )}
      </button>

      {hasChildren && expanded && (
        <div>
          {node.children.map((child) => (
            <WikiTreeNodeItem
              key={child.page.page_id}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Content Processor ── */

function preprocessContent(content: string): string {
  let processed = content.replace(
    /\[\[([^\]]+)\]\]/g,
    (_match, id) => `[${id}](#wiki-ref-${id})`,
  );
  processed = processed.replace(
    /\[\u2190\s*([^\]]+)\]/g,
    (_match, docId) => `<span class="wiki-provenance">${docId.trim()}</span>`,
  );
  processed = processed.replace(
    /\[<-\s*([^\]]+)\]/g,
    (_match, docId) => `<span class="wiki-provenance">${docId.trim()}</span>`,
  );
  return processed;
}

/* ── Main Component ── */

export default function WikiPage() {
  const { currentProject } = useProject();
  const projectId = currentProject?.id;

  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [pageDetail, setPageDetail] = useState<WikiPageDetail | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  /* Load wiki page list */
  const { data: wikiPages, loading: pagesLoading, refetch: refetchPages } = useApi<WikiPageSummary[]>(
    () => fetchWikiPages(projectId), [projectId],
  );

  /* Load wiki stats */
  const { data: wikiStats } = useApi<WikiStats>(
    () => fetchWikiStats(projectId), [projectId],
  );

  /* Build wiki tree from page list */
  const wikiTree = useMemo(
    () => buildWikiTree(wikiPages || []),
    [wikiPages],
  );

  /* Load page detail when selected */
  const loadPageDetail = useCallback(async (pageId: string) => {
    setPageLoading(true);
    setPageError(null);
    try {
      const detail = await fetchWikiPage(pageId, projectId);
      setPageDetail(detail);
    } catch (e: any) {
      setPageError(e.message || '\u52a0\u8f7dWiki\u9875\u5185\u5bb9\u5931\u8d25');
      setPageDetail(null);
    } finally {
      setPageLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (selectedPageId) {
      loadPageDetail(selectedPageId);
    } else {
      setPageDetail(null);
      setPageError(null);
    }
  }, [selectedPageId, loadPageDetail]);

  /* Auto-select index page on first load */
  useEffect(() => {
    if (!selectedPageId && wikiPages && wikiPages.length > 0) {
      const indexPage = wikiPages.find((p) => p.page_type === 'index');
      if (indexPage) {
        setSelectedPageId(indexPage.page_id);
      }
    }
  }, [wikiPages, selectedPageId]);

  /* Handle wiki-internal cross-ref navigation */
  const handleCrossRef = useCallback((refId: string) => {
    // Try direct match first, then try with "src/" prefix
    if (wikiPages?.some((p) => p.page_id === refId)) {
      setSelectedPageId(refId);
    } else if (wikiPages?.some((p) => p.page_id === `src/${refId}`)) {
      setSelectedPageId(`src/${refId}`);
    } else {
      setSelectedPageId(refId);
    }
  }, [wikiPages]);

  const processedContent = useMemo(() => {
    if (!pageDetail?.content) return '';
    return preprocessContent(pageDetail.content);
  }, [pageDetail?.content]);

  const pageCount = wikiPages?.length ?? 0;
  const sourceCount = wikiStats?.source_pages ?? wikiPages?.filter((p) => p.page_type === 'source_summary').length ?? 0;
  const domainCount = wikiStats?.domain_pages ?? wikiPages?.filter((p) => p.page_type === 'domain_overview').length ?? 0;

  return (
    <div className="p-6 h-full flex flex-col gap-4 page-enter">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-display flex items-center gap-2">
            <BookMarked className="text-accent" size={22} />
            \u77e5\u8bc6Wiki
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            Karpathy LLM Wiki \u6a21\u5f0f \u2014 \u6bcf\u7bc7\u6587\u6863\u6c89\u6dc0\u4e3a\u77e5\u8bc6\u5361\u7247\uff0c\u57df\u7ea7\u6982\u89c8\u805a\u5408\uff0c\u5168\u5c40\u7d22\u5f15\u4e32\u8054
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={refetchPages} icon={<RefreshCw size={14} />}>
          \u5237\u65b0
        </Button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3 stagger-children">
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full bg-accent" />
            <span className="text-label">Wiki \u603b\u9875\u6570</span>
          </div>
          <div className="text-2xl font-semibold font-display">{pageCount}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <FolderOpen size={11} className="text-th-text-muted" />
            <span className="text-label">\u57df\u6982\u89c8</span>
          </div>
          <div className="text-2xl font-semibold font-display">{domainCount}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <FileCheck size={11} className="text-th-text-muted" />
            <span className="text-label">\u77e5\u8bc6\u5361\u7247</span>
          </div>
          <div className="text-2xl font-semibold font-display">{sourceCount}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--entity-process)' }} />
            <span className="text-label">\u57df\u8986\u76d6</span>
          </div>
          <div className="text-2xl font-semibold font-display">
            {wikiStats?.domain_coverage != null ? `${Math.round(wikiStats.domain_coverage * 100)}%` : '-'}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: Wiki Tree */}
        <div className="w-64 shrink-0 glass-card rounded-card flex flex-col overflow-hidden">
          <div className="px-4 py-3 flex items-center justify-between"
               style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <span className="text-label flex items-center gap-1.5">
              <Layers size={11} /> Wiki \u9875\u9762
            </span>
            <span className="text-[10px] text-th-text-muted tabular-nums">
              {pageCount} \u9875
            </span>
          </div>

          <div className="flex-1 overflow-y-auto py-1 px-1">
            {pagesLoading && (
              <div className="px-3 space-y-2 py-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="skeleton skeleton-text" style={{ width: `${70 + Math.random() * 30}%` }} />
                ))}
              </div>
            )}

            {!pagesLoading && wikiTree.length === 0 && (
              <div className="text-center py-8 text-th-text-muted">
                <BookOpen size={32} className="mx-auto mb-2 opacity-20" />
                <p className="text-xs">\u6682\u65e0Wiki\u9875\u9762</p>
                <p className="text-[10px] mt-1 opacity-60">\u8bf7\u5148\u7070\u5165\u6587\u6863\u89e6\u53d1\u7f16\u8bd1</p>
              </div>
            )}

            {!pagesLoading && wikiTree.map((node) => (
              <WikiTreeNodeItem
                key={node.page.page_id}
                node={node}
                selectedId={selectedPageId}
                onSelect={setSelectedPageId}
                depth={0}
              />
            ))}
          </div>
        </div>

        {/* Right: Wiki Content */}
        <div className="flex-1 glass-card rounded-card overflow-hidden flex flex-col">
          {/* No selection */}
          {!selectedPageId && !pageLoading && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <BookMarked size={48} className="mx-auto mb-4 opacity-10 text-th-text-muted" />
                <p className="text-sm text-th-text-muted">\u9009\u62e9\u5de6\u4fa7Wiki\u9875\u9762\u4ee5\u67e5\u770b\u5185\u5bb9</p>
                <p className="text-xs text-th-text-muted mt-2 opacity-60">
                  \u6bcf\u7bc7\u6587\u6863\u7f16\u8bd1\u4e3a\u72ec\u7acb\u77e5\u8bc6\u5361\u7247\uff0c\u57df\u7ea7\u6982\u89c8\u805a\u5408\u7efc\u8ff0
                </p>
              </div>
            </div>
          )}

          {/* Loading */}
          {pageLoading && (
            <div className="p-6 space-y-4">
              <div className="skeleton" style={{ height: 32, width: '40%' }} />
              <div className="skeleton" style={{ height: 16, width: '60%' }} />
              <div className="skeleton" style={{ height: 200, width: '100%' }} />
              <div className="skeleton" style={{ height: 16, width: '80%' }} />
            </div>
          )}

          {/* Error */}
          {pageError && !pageLoading && (
            <div className="p-6">
              <div className="flex items-center gap-2 text-[var(--color-error)] text-sm">
                <AlertCircle size={16} />
                {pageError}
              </div>
            </div>
          )}

          {/* Page detail */}
          {pageDetail && !pageLoading && (
            <div className="flex-1 overflow-y-auto">
              {/* Page header */}
              <div className="px-6 py-4 flex items-start justify-between gap-4"
                   style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div className="min-w-0">
                  <h2 className="text-title text-th-text-primary truncate">
                    {pageDetail.title}
                  </h2>
                  {pageDetail.summary && (
                    <p className="text-xs text-th-text-muted mt-1 line-clamp-2">
                      {pageDetail.summary}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="info" size="sm">
                    {pageTypeLabel(pageDetail.page_type)}
                  </Badge>
                  <Badge variant={statusVariant(pageDetail.status)} size="sm">
                    {statusLabel(pageDetail.status)}
                  </Badge>
                  <Badge variant="neutral" size="sm">
                    <Hash size={10} className="mr-0.5" />
                    v{pageDetail.version}
                  </Badge>
                  {pageDetail.compiled_at && (
                    <span className="flex items-center gap-1 text-[10px] text-th-text-muted">
                      <Clock size={10} />
                      {formatTime(pageDetail.compiled_at)}
                    </span>
                  )}
                </div>
              </div>

              {/* Source docs */}
              {pageDetail.source_doc_ids.length > 0 && (
                <div className="px-6 py-2 flex items-center gap-2 flex-wrap"
                     style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <span className="text-[10px] text-th-text-muted shrink-0">
                    <FileText size={10} className="inline mr-1" />
                    \u6765\u6e90\u6587\u6863:
                  </span>
                  {pageDetail.source_doc_ids.map((docId) => {
                    // 与后端 wiki_compiler.py 同步的 sanitize 逻辑
                    const safeDocId = docId.replace(/[^a-zA-Z0-9\-_.]/g, '_');
                    return (
                    <button
                      key={docId}
                      onClick={() => handleCrossRef(`src/${safeDocId}`)}
                      className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded text-th-text-muted hover:text-accent transition-colors cursor-pointer"
                      style={{ background: 'rgba(255,255,255,0.03)', boxShadow: 'var(--shadow-ring)' }}
                    >
                      {docId.length > 24 ? docId.slice(0, 24) + '...' : docId}
                    </button>
                    );
                  })}
                </div>
              )}

              {/* Cross refs */}
              {pageDetail.cross_refs.length > 0 && (
                <div className="px-6 py-2 flex items-center gap-2 flex-wrap"
                     style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <span className="text-[10px] text-th-text-muted shrink-0">
                    <BookOpen size={10} className="inline mr-1" />
                    \u4ea4\u53c9\u5f15\u7528:
                  </span>
                  {pageDetail.cross_refs.map((ref) => (
                    <button key={ref}
                      onClick={() => handleCrossRef(ref)}
                      className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded text-accent cursor-pointer hover:opacity-80 transition-opacity"
                      style={{ background: 'rgba(85, 179, 255, 0.06)', boxShadow: '0 0 0 1px rgba(85, 179, 255, 0.15)' }}>
                      {ref}
                    </button>
                  ))}
                </div>
              )}

              {/* Markdown content */}
              <div className="px-6 py-6 wiki-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children, ...props }) => {
                      if (href?.startsWith('#wiki-ref-')) {
                        const refId = href.replace('#wiki-ref-', '');
                        return (
                          <button
                            onClick={() => handleCrossRef(refId)}
                            className="text-accent underline underline-offset-2 hover:opacity-80 transition-opacity cursor-pointer"
                          >
                            {children}
                          </button>
                        );
                      }
                      return <a href={href} {...props}>{children}</a>;
                    },
                    span: ({ className, children, ...props }) => {
                      if (className === 'wiki-provenance') {
                        return (
                          <span
                            className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded mx-0.5 align-middle"
                            style={{
                              background: 'rgba(255,255,255,0.03)',
                              color: 'var(--color-text-muted)',
                              boxShadow: 'var(--shadow-ring)',
                            }}
                            {...props}
                          >
                            <FileText size={9} className="mr-1 opacity-50" />
                            {children}
                          </span>
                        );
                      }
                      return <span className={className} {...props}>{children}</span>;
                    },
                  }}
                >
                  {processedContent}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
