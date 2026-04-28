/**
 * @file SearchPage.tsx
 * @description 知识检索页面 — 左侧知识域目录树 + 右侧搜索栏与结果列表
 *
 * 主要功能：
 * - 左侧面板：按知识域（Domain）树形筛选搜索结果
 * - 右侧面板：关键词搜索输入、Top-K 结果数量选择、搜索结果卡片列表
 * - 搜索结果展示：标题、内容摘要、相关性评分、文档类型、来源系统、分类路径
 * - 支持按选中的知识域过滤搜索结果
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Search,
  FileText,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Card, Badge } from '@/components/ui';
import {
  searchDocs,
  fetchDomains,
  type SearchResponse,
  type SearchHit,
  type DomainsResponse,
  type DomainInfo,
} from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';

/* ---------- domain tree helpers ---------- */

/** 知识域树节点（扩展 DomainInfo 增加 children） */
interface DomainTreeNode extends DomainInfo {
  children: DomainTreeNode[];
}

/** 将后端扁平的 DomainInfo 列表构建为嵌套的树结构 */
function buildDomainTree(domains: DomainInfo[]): DomainTreeNode[] {
  const map = new Map<string, DomainTreeNode>();
  const roots: DomainTreeNode[] = [];

  for (const d of domains) {
    map.set(d.domain_id, { ...d, children: [] });
  }
  for (const node of map.values()) {
    if (node.parent_id && map.has(node.parent_id)) {
      map.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

/* ---------- component ---------- */

/**
 * 知识检索页面组件
 *
 * 左右两栏布局：左侧为知识域目录树（可按域筛选结果），
 * 右侧为搜索栏和结果列表（支持 Top-K 配置和相关性评分展示）。
 */
export default function SearchPage() {
  const { currentProject } = useProject();

  // ── 知识域目录树相关状态 ──
  const [domainTree, setDomainTree] = useState<DomainTreeNode[]>([]); // 知识域树结构
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set()); // 展开的域节点ID
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null); // 当前选中的域（用于筛选结果）
  const [domainsLoading, setDomainsLoading] = useState(true); // 域数据加载中
  const [domainsError, setDomainsError] = useState<string | null>(null); // 域加载错误
  const [totalDocCards, setTotalDocCards] = useState(0); // 文档卡片总数

  // ── 搜索相关状态 ──
  const [query, setQuery] = useState(''); // 搜索关键词
  const [topK, setTopK] = useState(10); // 返回结果数量上限
  const [results, setResults] = useState<SearchHit[]>([]); // 搜索结果列表
  const [totalHits, setTotalHits] = useState(0); // 后端返回的总命中数
  const [searching, setSearching] = useState(false); // 搜索进行中
  const [searchError, setSearchError] = useState<string | null>(null); // 搜索错误信息
  const [searched, setSearched] = useState(false); // 是否已执行过搜索（控制空状态展示）

  // 页面加载时获取知识域数据并构建树结构（默认展开第一层）
  useEffect(() => {
    (async () => {
      setDomainsLoading(true);
      setDomainsError(null);
      try {
        const data: DomainsResponse = await fetchDomains(currentProject?.id);
        const tree = buildDomainTree(data.domains);
        setDomainTree(tree);
        setTotalDocCards(data.total_doc_cards);
        // expand first level by default
        const first = new Set<string>(tree.map((n) => n.domain_id));
        setExpandedNodes(first);
      } catch (err) {
        setDomainsError(err instanceof Error ? err.message : '加载域信息失败');
      } finally {
        setDomainsLoading(false);
      }
    })();
  }, [currentProject?.id]);

  /** 执行搜索 — 调用后端 searchDocs 接口获取结果 */
  const handleSearch = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      const q = query.trim();
      if (!q) return;
      setSearching(true);
      setSearchError(null);
      setSearched(true);
      try {
        const data: SearchResponse = await searchDocs(q, topK, currentProject?.id);
        setResults(data.results);
        setTotalHits(data.total_hits);
      } catch (err) {
        setSearchError(err instanceof Error ? err.message : '搜索失败');
        setResults([]);
        setTotalHits(0);
      } finally {
        setSearching(false);
      }
    },
    [query, topK, currentProject?.id],
  );

  // 按选中的知识域过滤搜索结果（未选中则显示全部）
  const displayResults = selectedDomain
    ? results.filter((r) => r.category_path?.includes(selectedDomain))
    : results;

  /* ---------- tree rendering ---------- */

  /** 切换知识域节点展开/折叠 */
  const toggleExpand = (id: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  /** 递归渲染知识域树节点（含缩进、展开/折叠、选中高亮、文档计数） */
  const renderTreeNode = (node: DomainTreeNode, depth = 0) => {
    const isExpanded = expandedNodes.has(node.domain_id);
    const isSelected = selectedDomain === node.domain_id;
    const hasChildren = node.children.length > 0;

    return (
      <div key={node.domain_id}>
        <div
          className={`flex items-center gap-2 px-3 py-2 cursor-pointer rounded-btn transition-colors ${
            isSelected ? 'bg-accent/10 text-accent' : 'hover:bg-hover'
          }`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          onClick={() => {
            if (hasChildren) toggleExpand(node.domain_id);
            setSelectedDomain(isSelected ? null : node.domain_id);
          }}
        >
          {hasChildren ? (
            <span className="w-4 h-4 flex items-center justify-center text-th-text-muted">
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          ) : (
            <span className="w-4" />
          )}
          <FolderOpen
            size={16}
            className={isSelected ? 'text-accent' : 'text-th-text-muted'}
          />
          <span className="flex-1 text-sm truncate">{node.name}</span>
          {node.doc_count > 0 && (
            <Badge variant="neutral" className="text-xs">
              {node.doc_count}
            </Badge>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div>
            {node.children.map((child) => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  /* ---------- 评分颜色辅助函数 ---------- */

  /** 根据相关性评分返回对应的颜色类名（绿/黄/灰） */
  const scoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.5) return 'text-yellow-600';
    return 'text-th-text-secondary';
  };

  /* ---------- render ---------- */

  return (
    <div className="p-6 h-full flex flex-col page-enter">
      {/* Header */}
      <div className="mb-6 page-hero">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Search className="text-accent" size={22} />
          知识检索
        </h1>
        <p className="text-sm text-th-text-secondary mt-1">
          在知识库中搜索文档，按知识域筛选结果
        </p>
      </div>

      {/* Body: left + right */}
      <div className="flex-1 flex gap-6 min-h-0">
        {/* Left panel: domain tree */}
        <Card className="w-72 flex-shrink-0 flex flex-col bg-[var(--color-bg-elevated)]">
          <div className="p-4 border-b border-th-border">
            <h3 className="font-medium text-th-text-primary">知识域</h3>
            <p className="text-xs text-th-text-muted mt-1">
              共 {totalDocCards} 份文档卡片
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {domainsLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="animate-spin text-th-text-muted" size={20} />
              </div>
            ) : domainsError ? (
              <div className="text-center py-8 text-sm text-red-500">
                <AlertCircle className="mx-auto mb-2" size={20} />
                {domainsError}
              </div>
            ) : (
              <>
                {/* "All" option */}
                <div
                  className={`flex items-center gap-2 px-3 py-2 cursor-pointer rounded-btn transition-colors ${
                    !selectedDomain ? 'bg-accent/10 text-accent' : 'hover:bg-hover'
                  }`}
                  onClick={() => setSelectedDomain(null)}
                >
                  <span className="w-4" />
                  <FileText
                    size={16}
                    className={!selectedDomain ? 'text-accent' : 'text-th-text-muted'}
                  />
                  <span className="flex-1 text-sm">全部</span>
                </div>
                <div className="h-px bg-hover my-2" />
                {domainTree.map((node) => renderTreeNode(node))}
              </>
            )}
          </div>
        </Card>

        {/* Right panel: search + results */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Search bar */}
          <form onSubmit={handleSearch} className="flex items-center gap-3 mb-4">
            <div className="flex-1 relative shadow-input rounded-featured">
              <Search
                size={18}
                className="absolute left-4 top-1/2 -translate-y-1/2 text-th-text-muted"
              />
              <input
                type="text"
                placeholder="输入关键词搜索知识库..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-11 pr-4 h-12 text-base bg-transparent border-none focus:outline-none rounded-featured text-th-text-primary placeholder:text-th-text-muted"
              />
            </div>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="rounded-btn text-sm py-2 px-3 bg-transparent shadow-input text-th-text-primary focus:outline-none"
            >
              {[5, 10, 20, 50].map((n) => (
                <option key={n} value={n}>
                  Top {n}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={searching || !query.trim()}
              className="btn-gradient px-4 py-2 rounded-btn text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {searching ? (
                <RefreshCw className="animate-spin" size={14} />
              ) : (
                <Search size={14} />
              )}
              搜索
            </button>
          </form>

          {/* Result count */}
          {searched && !searchError && (
            <div className="text-sm text-th-text-secondary mb-3">
              共 {totalHits} 条结果
              {selectedDomain && (
                <span>
                  ，当前筛选显示 {displayResults.length} 条
                </span>
              )}
            </div>
          )}

          {/* Error */}
          {searchError && (
            <div className="flex items-center gap-2 text-red-500 text-sm mb-3">
              <AlertCircle size={16} />
              {searchError}
            </div>
          )}

          {/* Results list */}
          <Card className="flex-1 overflow-hidden flex flex-col">
            <div className="flex-1 overflow-y-auto">
              {!searched ? (
                <div className="h-full flex items-center justify-center text-th-text-muted">
                  <div className="text-center">
                    <Search size={40} className="mx-auto mb-3 opacity-50" />
                    <p>输入关键词开始搜索</p>
                  </div>
                </div>
              ) : searching ? (
                <div className="h-full flex items-center justify-center">
                  <RefreshCw className="animate-spin text-th-text-muted" size={28} />
                </div>
              ) : displayResults.length === 0 ? (
                <div className="h-full flex items-center justify-center text-th-text-muted">
                  <div className="text-center">
                    <FileText size={40} className="mx-auto mb-3 opacity-50" />
                    <p>没有找到匹配的结果</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 p-3">
                  {displayResults.map((hit) => (
                    <div
                      key={`${hit.doc_id}-${hit.chunk_id}`}
                      className="glass-card rounded-card p-4"
                    >
                      <div className="flex items-start gap-3">
                        <FileText
                          size={18}
                          className="text-th-text-muted mt-0.5 flex-shrink-0"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-medium text-th-text-primary truncate">
                              {hit.title}
                            </h4>
                            <div className="flex items-center gap-2 ml-auto flex-shrink-0">
                              <div className="w-16 h-1.5 rounded-full bg-white/5 overflow-hidden">
                                <div
                                  className={`h-full rounded-full bar-chart-bar ${
                                    hit.score >= 0.8 ? 'bg-th-success' : hit.score >= 0.5 ? 'bg-th-warning' : 'bg-th-text-muted'
                                  }`}
                                  style={{ width: `${hit.score * 100}%` }}
                                />
                              </div>
                              <span
                                className={`text-xs font-mono ${scoreColor(hit.score)}`}
                              >
                                {hit.score.toFixed(3)}
                              </span>
                            </div>
                          </div>
                          <p className="text-sm text-th-text-secondary line-clamp-3 mb-2">
                            {hit.content}
                          </p>
                          <div className="flex items-center gap-2 flex-wrap">
                            {hit.doc_type && (
                              <Badge variant="neutral" className="text-xs">
                                {hit.doc_type}
                              </Badge>
                            )}
                            {hit.source_system && (
                              <Badge variant="neutral" className="text-xs">
                                {hit.source_system}
                              </Badge>
                            )}
                            {hit.category_path && (
                              <span className="text-xs text-th-text-muted">
                                {hit.category_path}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
