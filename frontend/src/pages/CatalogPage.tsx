/**
 * 知识目录页面（CatalogPage）
 *
 * 书虫智能体的知识分类浏览入口，采用左右分栏布局：
 * - 左侧：分类目录树（TreeView），支持点击节点筛选
 * - 右侧：文档列表表格，支持按标题搜索 + 按分类路径过滤
 *
 * 数据来源：
 * - fetchCatalog —— 获取分类目录树结构
 * - fetchDocuments —— 获取文档列表（最多 200 条）
 *
 * @module pages/CatalogPage
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FolderOpen, FileText, Search } from 'lucide-react';
import { Card, Badge, Button, SkeletonCard, TreeView } from '@/components/ui';
import type { TreeNode } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { fetchCatalog, fetchDocuments } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';
import type { CatalogNode, PaginatedDocuments } from '@/services/api';

/** 将后端返回的 CatalogNode 递归转换为 TreeView 组件所需的 TreeNode 格式 */
function toTreeNodes(catalog: CatalogNode[]): TreeNode[] {
  return catalog.map((c) => ({
    path: c.path,
    name: c.name,
    doc_count: c.doc_count,
    children: toTreeNodes(c.children),
  }));
}

/**
 * 知识目录组件
 *
 * 左侧展示分类目录树，右侧展示过滤后的文档列表，
 * 支持按标题搜索和按分类路径筛选。
 */
export default function CatalogPage() {
  const navigate = useNavigate();
  const { currentProject } = useProject();
  const [selectedPath, setSelectedPath] = useState<string | null>(null); // 当前选中的分类路径（null=全部）
  const [searchTerm, setSearchTerm] = useState('');                      // 文档标题搜索关键词

  // 加载分类目录树
  const { data: catalog, loading: catalogLoading, error: catalogError } = useApi<CatalogNode[]>(
    () => fetchCatalog(currentProject?.id), [currentProject?.id],
  );
  // 加载文档列表（一次性加载最多 200 条，前端过滤）
  const { data: docs, loading: docsLoading, error: docsError, refetch: refetchDocs } = useApi<PaginatedDocuments>(
    () => fetchDocuments({ page_size: 200, projectId: currentProject?.id }), [currentProject?.id],
  );

  const treeNodes = catalog ? toTreeNodes(catalog) : []; // 转换为 TreeView 所需格式

  // 根据搜索关键词和选中分类路径过滤文档
  const filteredDocs = (docs?.documents || []).filter((doc) => {
    const matchSearch = !searchTerm || doc.title.toLowerCase().includes(searchTerm.toLowerCase());
    const matchPath = !selectedPath || doc.category_path.startsWith(selectedPath);
    return matchSearch && matchPath;
  });

  return (
    <div className="p-6 h-full flex flex-col space-y-4 page-enter">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FolderOpen className="text-accent" />
            知识目录
          </h1>
          <p className="text-th-text-muted mt-1">
            浏览分类目录和文档列表
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={refetchDocs}>
          刷新
        </Button>
      </div>

      {/* 搜索栏 */}
      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-th-text-muted" />
        <input
          type="text"
          placeholder="搜索文档标题..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-4 py-2 h-11 rounded-card text-sm bg-transparent shadow-input text-th-text-primary focus:outline-none"
        />
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* 左侧目录树 */}
        <Card padding="sm" className="w-64 overflow-y-auto shrink-0">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-sm font-medium text-th-text-primary">分类目录</span>
            {selectedPath && (
              <Button variant="ghost" size="sm" onClick={() => setSelectedPath(null)}>
                清除
              </Button>
            )}
          </div>

          {catalogLoading && (
            <div className="px-3 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          )}

          {catalogError && <div className="px-3 text-sm text-red-400">{typeof catalogError === 'string' ? catalogError : '加载分类失败'}</div>}

          {treeNodes.length > 0 && (
            <TreeView
              nodes={treeNodes}
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
            />
          )}

          {!catalogLoading && !catalogError && treeNodes.length === 0 && (
            <p className="px-3 text-sm text-th-text-muted">
              暂无分类
            </p>
          )}
        </Card>

        {/* 右侧文档列表 */}
        <Card padding="md" className="flex-1 overflow-y-auto">
          {docsLoading && (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          )}

          {docsError && <div className="text-sm text-red-400">{typeof docsError === 'string' ? docsError : '加载文档失败'}</div>}

          {!docsLoading && filteredDocs.length === 0 && (
            <div className="text-center py-12 text-th-text-muted">
              <FileText size={40} className="mx-auto mb-3 opacity-30" />
              <p>暂无文档</p>
              {(searchTerm || selectedPath) && (
                <p className="text-sm mt-1">尝试修改搜索条件或清除分类筛选</p>
              )}
            </div>
          )}

          {filteredDocs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-th-text-muted">
                  <th className="pb-3 font-medium">标题</th>
                  <th className="pb-3 font-medium">类型</th>
                  <th className="pb-3 font-medium">决策</th>
                  <th className="pb-3 font-medium">来源</th>
                  <th className="pb-3 font-medium">分类</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map((doc) => (
                  <tr
                    key={doc.id}
                    className="border-t cursor-pointer transition-colors border-th-border"
                    onClick={() => navigate(`/documents/${doc.id}`)}
                  >
                    <td className="py-3 max-w-[220px] truncate" title={doc.title}>
                      <div className="flex items-center gap-2">
                        <FileText size={14} className="text-th-text-muted" />
                        {doc.title}
                      </div>
                    </td>
                    <td className="py-3">
                      <Badge variant="neutral" size="sm">{typeof doc.doc_type === 'string' ? doc.doc_type : String(doc.doc_type ?? '未知')}</Badge>
                    </td>
                    <td className="py-3">
                      <Badge
                        variant={doc.decision === 'KEEP' ? 'success' : doc.decision === 'ARCHIVE' ? 'warning' : doc.decision === 'DISCARD' ? 'error' : 'neutral'}
                        size="sm"
                      >
                        {doc.decision}
                      </Badge>
                    </td>
                    <td className="py-3 text-th-text-muted">
                      {doc.source_system}
                    </td>
                    <td className="py-3 text-xs max-w-[150px] truncate text-th-text-muted">
                      {doc.category_path}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
