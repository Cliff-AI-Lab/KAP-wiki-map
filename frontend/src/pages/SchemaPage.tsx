/**
 * Schema 索引页 — Karpathy 架构最顶层: LLM 可直接消费的知识目录。
 *
 * 将所有 Wiki 编译页的摘要压缩为结构化索引，是双引擎 QueryRouter 的决策依据。
 * 对应核心理念第一原则: 双引擎架构的 Schema 层(LLM可读目录)。
 *
 * @module pages/SchemaPage
 */

import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  FileCode2,
  BookMarked,
  RefreshCw,
  Layers,
  FileText,
  ArrowRight,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';
import { PageHeader, SkeletonCard } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { useProject } from '@/contexts/ProjectContext';

/* ── API types (inline, matches backend WikiSchema) ── */
interface WikiSchema {
  schema_text: string;
  page_count: number;
  domain_coverage: number;
  compiled_domains: string[];
}

interface WikiStatsData {
  total_pages: number;
  published_pages: number;
  stale_pages: number;
  total_source_docs: number;
  domain_coverage: number;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function fetchSchema(projectId?: string): Promise<WikiSchema> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  const resp = await fetch(`${API_BASE}/api/v1/wiki/schema?${params}`);
  if (!resp.ok) throw new Error('加载 Schema 索引失败');
  return resp.json();
}

async function fetchWikiStats(projectId?: string): Promise<WikiStatsData> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  const resp = await fetch(`${API_BASE}/api/v1/wiki/stats?${params}`);
  if (!resp.ok) throw new Error('加载统计失败');
  return resp.json();
}

export default function SchemaPage() {
  const navigate = useNavigate();
  const { currentProject } = useProject();

  const { data: schema, loading: schemaLoading, error: schemaError, refetch } =
    useApi<WikiSchema>(() => fetchSchema(currentProject?.id), [currentProject?.id]);

  const { data: stats, loading: statsLoading } =
    useApi<WikiStatsData>(() => fetchWikiStats(currentProject?.id), [currentProject?.id]);

  const loading = schemaLoading || statsLoading;

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-14 skeleton rounded-card" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
        </div>
        <div className="h-96 skeleton rounded-card" />
      </div>
    );
  }

  if (schemaError) {
    return (
      <div className="p-6 h-full flex items-center justify-center">
        <div className="glass-card rounded-card p-8 text-center max-w-sm">
          <AlertCircle className="mx-auto mb-4 text-[var(--color-error)]" size={36} />
          <p className="text-sm text-secondary mb-5">{schemaError}</p>
          <button className="btn-gradient px-5 py-2 rounded-btn text-sm" onClick={() => refetch()}>
            重试
          </button>
        </div>
      </div>
    );
  }

  const s = stats ?? { total_pages: 0, published_pages: 0, stale_pages: 0, total_source_docs: 0, domain_coverage: 0 };
  const sc = schema ?? { schema_text: '', page_count: 0, domain_coverage: 0, compiled_domains: [] };

  return (
    <div className="p-6 space-y-5 page-enter">
      {/* Header */}
      <PageHeader
        icon={<FileCode2 className="text-accent" size={24} />}
        title="Schema 索引"
        description="LLM 可直接消费的知识目录 — Karpathy 架构最顶层"
      />

      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#55b3ff' }} />
            <span className="text-label">编译域数</span>
          </div>
          <div className="text-2xl font-semibold font-display">{sc.page_count}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#5fc992' }} />
            <span className="text-label">域覆盖率</span>
          </div>
          <div className="text-2xl font-semibold font-display">{Math.round(sc.domain_coverage * 100)}%</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#ffbc33' }} />
            <span className="text-label">源文档数</span>
          </div>
          <div className="text-2xl font-semibold font-display">{s.total_source_docs}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.stale_pages > 0 ? '#FF6363' : '#5fc992' }} />
            <span className="text-label">新鲜度</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-2xl font-semibold font-display">
              {s.stale_pages > 0 ? `${s.stale_pages}过时` : '全部新鲜'}
            </div>
            {s.stale_pages === 0 && <CheckCircle size={16} className="text-[var(--color-success)]" />}
          </div>
        </div>
      </div>

      {/* Schema 索引目录 */}
      <div className="glass-card rounded-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-accent" />
            <span className="text-heading">Schema 知识索引</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('../wiki')}
              className="btn-secondary px-3 py-1.5 rounded-btn text-xs flex items-center gap-1.5"
            >
              <BookMarked size={12} /> 查看 Wiki 编译页
            </button>
            <button
              onClick={() => refetch()}
              className="btn-ghost px-2 py-1.5 rounded-btn"
            >
              <RefreshCw size={13} className="text-th-text-muted" />
            </button>
          </div>
        </div>

        {sc.schema_text ? (
          <div className="wiki-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {sc.schema_text}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="text-center py-16 text-th-text-muted">
            <FileCode2 size={48} className="mx-auto mb-4 opacity-20" />
            <p className="text-sm mb-2">暂无 Schema 索引</p>
            <p className="text-xs text-th-text-muted mb-4">请先通过 Wiki 编译分支灌入并编译文档</p>
            <button
              onClick={() => navigate('../upload')}
              className="btn-gradient px-4 py-1.5 rounded-btn text-xs"
            >
              开始导入文档
            </button>
          </div>
        )}
      </div>

      {/* 编译域列表 */}
      {sc.compiled_domains.length > 0 && (
        <div className="glass-card rounded-card p-5">
          <div className="text-overline mb-3">已编译知识域 ({sc.compiled_domains.length})</div>
          <div className="flex flex-wrap gap-2">
            {sc.compiled_domains.map((domain) => (
              <button
                key={domain}
                onClick={() => navigate('../wiki')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-btn text-xs text-th-text-secondary transition-all hover:text-accent"
                style={{ background: 'rgba(255,255,255,0.03)', boxShadow: 'var(--shadow-ring)' }}
              >
                <FileText size={11} />
                {domain}
                <ArrowRight size={10} className="opacity-40" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
