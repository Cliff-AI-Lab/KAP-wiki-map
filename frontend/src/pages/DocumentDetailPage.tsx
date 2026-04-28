/**
 * 文档详情页面（DocumentDetailPage）
 *
 * 根据路由参数 docId 加载并展示单篇文档的完整信息。
 *
 * 页面布局：
 * - 顶栏：文档标题、分类路径、决策标签（KEEP/ARCHIVE/DISCARD）、处理状态
 * - 左侧（2/3 宽度）：摘要、关键词标签、识别实体、相关文档链接
 * - 右侧（1/3 宽度）：保留置信度 KPI、基本信息表（ID/类型/来源/部门等）、时间信息
 *
 * 数据来源：fetchDocument（对接后端 /api/v1/knowledge/documents/:id）
 *
 * @module pages/DocumentDetailPage
 */

import { useParams, useNavigate } from 'react-router-dom';
import { FileText, ArrowLeft, Tag, FolderTree, Link2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Badge, Button, SkeletonCard } from '@/components/ui';
import { decisionVariant, statusVariant } from '@/components/ui/Badge';
import { useApi } from '@/hooks/useApi';
import { fetchDocument } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';
import type { DocumentDetail } from '@/services/api';

/**
 * 文档详情组件
 *
 * 从路由参数获取 docId，通过 useApi 异步加载文档数据，
 * 分左右两栏展示文档的摘要、关键词、实体、KPI 及基本信息。
 */
export default function DocumentDetailPage() {
  const { docId } = useParams<{ docId: string }>();  // 从 URL 路由获取文档 ID
  const navigate = useNavigate();
  const { currentProject: _currentProject } = useProject();

  // 根据 docId 异步加载文档详情数据
  const { data: doc, loading, error } = useApi<DocumentDetail>(
    () => fetchDocument(docId!),
    [docId],
  );

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-400 mb-4">{error}</div>
        <Button variant="secondary" onClick={() => navigate(-1)}>返回</Button>
      </div>
    );
  }

  if (!doc) return null;

  return (
    <div className="p-6 space-y-6">
      {/* 顶栏 */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft size={18} />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold flex items-center gap-2 truncate">
            <FileText size={22} />
            {doc.title}
          </h1>
          <p className="text-sm mt-1 text-th-text-muted">
            {doc.category_path || '未分类'}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={decisionVariant(doc.decision)}>{doc.decision}</Badge>
          <Badge variant={statusVariant(doc.status)}>{doc.status}</Badge>
        </div>
      </div>

      {/* 主内容 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 左 2/3 */}
        <div className="md:col-span-2 space-y-6">
          {/* 摘要 */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>摘要</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-th-text-secondary">
                {doc.summary || '暂无摘要'}
              </p>
            </CardContent>
          </Card>

          {/* 关键词 */}
          {doc.keywords && doc.keywords.length > 0 && (
            <Card padding="lg">
              <CardHeader>
                <CardTitle icon={<Tag size={16} />}>关键词</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {doc.keywords.map((kw, i) => (
                    <Badge key={i} variant="neutral">{kw}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* 实体 */}
          {doc.entities && doc.entities.length > 0 && (
            <Card padding="lg">
              <CardHeader>
                <CardTitle icon={<FolderTree size={16} />}>识别实体</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {doc.entities.map((ent, i) => (
                    <Badge key={i} variant="info">{ent}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* 相关文档 */}
          {doc.related_doc_ids && doc.related_doc_ids.length > 0 && (
            <Card padding="lg">
              <CardHeader>
                <CardTitle icon={<Link2 size={16} />}>相关文档</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {doc.related_doc_ids.map((rid) => (
                    <button
                      key={rid}
                      className="block text-sm hover:underline truncate w-full text-left text-accent"
                      onClick={() => navigate(`/documents/${rid}`)}
                    >
                      {rid}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* 右 1/3 */}
        <div className="space-y-4">
          {/* KPI */}
          <Card padding="lg" className="text-center">
            <div className="text-4xl font-bold text-accent">
              {doc.kpi_retain != null ? `${(doc.kpi_retain * 100).toFixed(0)}%` : '-'}
            </div>
            <div className="text-xs mt-1 text-th-text-muted">保留置信度</div>
          </Card>

          {/* 基本信息 */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>基本信息</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm">
                <InfoRow label="文档ID" value={doc.id} />
                <InfoRow label="文档类型" value={doc.doc_type} />
                <InfoRow label="来源系统" value={doc.source_system} />
                <InfoRow label="分类路径" value={doc.category_path || '-'} />
                <InfoRow label="部门" value={doc.department_id || '-'} />
                <InfoRow label="访问级别" value={doc.access_level || '-'} />
              </div>
            </CardContent>
          </Card>

          {/* 时间 */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>时间信息</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                {doc.created_at && (
                  <InfoRow label="创建" value={new Date(doc.created_at).toLocaleString('zh-CN')} />
                )}
                {doc.updated_at && (
                  <InfoRow label="更新" value={new Date(doc.updated_at).toLocaleString('zh-CN')} />
                )}
                {doc.ingested_at && (
                  <InfoRow label="入库" value={new Date(doc.ingested_at).toLocaleString('zh-CN')} />
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** 信息行组件 —— 左侧标签、右侧值，用于展示文档的键值对属性 */
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-th-text-muted">{label}</span>
      <span className="text-right truncate max-w-[180px] text-th-text-primary" title={value}>
        {value}
      </span>
    </div>
  );
}
