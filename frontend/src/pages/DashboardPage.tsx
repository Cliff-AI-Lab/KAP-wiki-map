/**
 * 知识图鉴仪表盘 (DashboardPage) — V11.2
 *
 * 核心改动: 双引擎从并列展示改为 Tab 切换
 * - Hero Stats: 4 张 Raycast 卡片
 * - BranchFlow: Tab 切换流程图 (Wiki编译 / Skills检索)
 * - BranchCards: 切换式指标卡片
 * - Bottom: 最近文档列表 + 分布图表
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  CheckCircle,
  Upload,
  FolderTree,
  Brain,
  Network,
  AlertCircle,
  Search,
  MessageSquare,
  BookOpen,
  Database,
  BarChart3,
  Check,
  FileSearch,
  ChevronRight,
} from 'lucide-react';
import { SkeletonCard, PageHeader } from '@/components/ui';
import {
  fetchStats,
  fetchDocuments,
  type KnowledgeStats,
  type PaginatedDocuments,
} from '@/services/api';
import { useApi } from '@/hooks/useApi';
import { useProject } from '@/contexts/ProjectContext';

/* ─── doc_type color mapping (CSS variable references) ─── */
const DOC_TYPE_COLORS: Record<string, string> = {
  '技术文档': 'var(--doctype-technical)',
  '会议纪要': 'var(--color-success)',
  '规章制度': 'var(--color-warning)',
  '聊天记录': 'var(--entity-process)',
  '操作规程': 'var(--doctype-technical)',
  '安全规范': 'var(--color-error)',
  '环保标准': 'var(--color-success)',
  '管理制度': 'var(--color-warning)',
};
const DOC_TYPE_DEFAULT_COLOR = 'var(--color-text-quaternary)';

function docTypeColor(t: string): string {
  return DOC_TYPE_COLORS[t] ?? DOC_TYPE_DEFAULT_COLOR;
}

/* ─── relative time helper ─── */
function relativeTime(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return `${Math.floor(days / 30)}月前`;
}

/* ─── SVG Progress Ring (Raycast 精致版) ─── */
function ProgressRing({ percent }: { percent: number }) {
  const r = 18;
  const stroke = 2.5;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (percent / 100) * circumference;
  const size = (r + stroke) * 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="progress-ring shrink-0">
      <circle cx={r + stroke} cy={r + stroke} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
      <circle
        cx={r + stroke} cy={r + stroke} r={r}
        fill="none" stroke="var(--color-accent)" strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset}
        className="progress-ring-transition"
      />
    </svg>
  );
}

/* ─── Horizontal Bar ─── */
function HBar({ widthPct, delay = 0 }: { widthPct: number; delay?: number }) {
  return (
    <div className="flex-1 h-[5px] rounded-full overflow-hidden bar-chart-bar-bg">
      <div
        className="bar-chart-bar bar-chart-bar-fill h-full"
        style={{ width: `${widthPct}%`, animationDelay: `${delay}ms` }}
      />
    </div>
  );
}

/* ─── 双分支步骤定义 (核心: 第一原则双引擎架构) ─── */
const WIKI_STEPS = [
  { path: 'upload', icon: Upload, label: '原始知识导入', desc: '导入→原始库' },
  { path: 'review', icon: CheckCircle, label: '去噪审核', desc: '质量筛选' },
  { path: 'analysis', icon: Brain, label: '智能分析', desc: '蒸馏评估' },
  { path: 'wiki', icon: BookOpen, label: '知识编译Wiki', desc: '域级编译' },
  { path: 'schema', icon: FileSearch, label: 'Schema索引', desc: 'LLM可读层' },
] as const;

const SKILLS_STEPS = [
  { path: 'upload', icon: Upload, label: '知识上传', desc: '导入文档' },
  { path: 'review', icon: CheckCircle, label: '去噪审核', desc: '跳过/保留' },
  { path: 'taxonomy', icon: FolderTree, label: 'Skills体系', desc: '四级域分类' },
  { path: 'graph', icon: Network, label: '知识图谱', desc: '实体关系' },
  { path: 'catalog', icon: FileSearch, label: '知识目录', desc: '浏览管理' },
] as const;

const UNIFIED_STEPS = [
  { path: 'search', icon: Search, label: '知识检索', desc: '双路径搜索' },
  { path: 'qa', icon: MessageSquare, label: '智能问答', desc: '双引擎问答' },
] as const;

/* ─── Branch accent colors (CSS variable references) ─── */
const WIKI_COLORS = [
  'var(--color-info)',
  'var(--color-success)',
  'var(--entity-process)',
  'var(--color-warning)',
  'var(--entity-person)',
];
const SKILLS_COLORS = [
  'var(--color-info)',
  'var(--color-success)',
  'var(--entity-equipment)',
  'var(--entity-person)',
  'var(--entity-standard)',
];

/* ═══════════════════════════════════════════
   Branch Flow — Tab 切换流程图（V11.2）
   Wiki编译 / Skills检索 切换显示 → 统一检索/问答
   ═══════════════════════════════════════════ */
function BranchFlow({
  currentStep,
  onNavigate,
  activeBranch,
  onBranchChange,
}: {
  currentStep: number;
  onNavigate: (path: string) => void;
  activeBranch: 'wiki' | 'skills';
  onBranchChange: (b: 'wiki' | 'skills') => void;
}) {
  const steps = activeBranch === 'wiki' ? WIKI_STEPS : SKILLS_STEPS;
  const colors = activeBranch === 'wiki' ? WIKI_COLORS : SKILLS_COLORS;

  return (
    <div className="glass-card rounded-card p-5">
      {/* Tab 切换头 */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-overline">知识流水线</div>
        <div className="flex gap-1 p-0.5 rounded-btn tab-toggle-container">
          <button
            onClick={() => onBranchChange('wiki')}
            className={`flex items-center gap-2 px-3 py-1 rounded-btn text-xs font-medium transition-all duration-150 ${
              activeBranch === 'wiki' ? 'text-accent tab-toggle-active' : 'text-th-text-muted hover:text-th-text-secondary'
            }`}
          >
            <BookOpen size={12} /> Wiki编译
          </button>
          <button
            onClick={() => onBranchChange('skills')}
            className={`flex items-center gap-2 px-3 py-1 rounded-btn text-xs font-medium transition-all duration-150 ${
              activeBranch === 'skills' ? 'text-accent tab-toggle-active' : 'text-th-text-muted hover:text-th-text-secondary'
            }`}
          >
            <Database size={12} /> Skills检索
          </button>
        </div>
      </div>

      {/* 当前分支步骤 */}
      <div className="space-y-1">
        {steps.map((step, i) => {
          const color = colors[i] || 'var(--color-info)';
          const isCompleted = i < currentStep;
          const isCurrent = i === currentStep;
          return (
            <div
              key={step.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-btn cursor-pointer transition-all duration-150 group ${
                isCurrent ? 'pipeline-step-active' : ''
              }${(!isCompleted && !isCurrent) ? ' pipeline-step-dimmed' : ''}`}
              onClick={() => onNavigate(step.path)}
              style={isCurrent ? { '--step-color': color } as React.CSSProperties : undefined}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 ${
                isCompleted ? 'bg-th-success' : isCurrent ? 'pipeline-step-number-active' : 'pipeline-step-number'
              }`}>
                {isCompleted ? <Check size={11} strokeWidth={3} className="text-white" /> :
                 <span className={isCurrent ? 'text-white' : 'text-th-text-muted'}>{i + 1}</span>}
              </div>
              <div className="min-w-0 flex-1">
                <div className={`text-sm font-medium truncate ${isCurrent ? 'text-th-text-primary' : 'text-th-text-secondary'}`}>{step.label}</div>
                <div className={`text-[10px] truncate ${isCurrent ? 'pipeline-step-desc-active' : 'text-th-text-muted opacity-60'}`}>{step.desc}</div>
              </div>
              <ChevronRight size={14} className="shrink-0 opacity-0 group-hover:opacity-40 transition-opacity text-th-text-muted" />
            </div>
          );
        })}
      </div>

      {/* 底部统一入口 */}
      <div className="mt-4 pt-3 flex gap-3 border-t border-th-border">
        {UNIFIED_STEPS.map((step) => (
          <button
            key={step.path}
            onClick={() => onNavigate(step.path)}
            className="flex-1 flex items-center justify-center gap-2 py-2 rounded-btn text-xs font-medium text-th-text-secondary transition-all hover:text-accent btn-neutral-ring"
          >
            <step.icon size={13} /> {step.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   Branch Metric Cards — 切换式指标卡片（V11.2）
   根据当前分支显示对应指标
   ═══════════════════════════════════════════ */
function BranchCards({
  stats: s,
  onNavigate,
  activeBranch,
}: {
  stats: {
    total_documents: number;
    kept: number;
    archived: number;
    vector_chunks: number;
    knowledge_domains: number;
    doc_cards: number;
    graph_nodes: number;
    graph_edges: number;
  };
  onNavigate: (path: string) => void;
  activeBranch: 'wiki' | 'skills';
}) {
  const retentionPct = s.total_documents > 0 ? Math.round((s.kept / s.total_documents) * 100) : 0;

  const metrics = activeBranch === 'wiki' ? [
    { label: '原始文档', value: `${s.total_documents}`, color: 'var(--color-accent)', path: 'upload' },
    { label: '保留文档', value: `${s.kept}`, sub: `${retentionPct}%`, color: 'var(--color-success)', path: 'review' },
    { label: '知识卡片', value: `${s.doc_cards}`, color: 'var(--entity-process)', path: 'analysis' },
    { label: 'Wiki编译', value: `${s.knowledge_domains}`, sub: '域', color: 'var(--color-warning)', path: 'wiki' },
  ] : [
    { label: '知识域', value: `${s.knowledge_domains}`, color: 'var(--color-accent)', path: 'taxonomy' },
    { label: '图谱节点', value: `${s.graph_nodes}`, sub: `${s.graph_edges}关系`, color: 'var(--entity-person)', path: 'graph' },
    { label: '向量分块', value: `${s.vector_chunks}`, color: 'var(--entity-equipment)', path: 'search' },
    { label: '目录条目', value: `${s.doc_cards}`, color: 'var(--entity-standard)', path: 'catalog' },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
      {metrics.map((m) => (
        <div key={m.label} className="glass-card rounded-card p-4 cursor-pointer transition-all hover:shadow-card-hover group"
             onClick={() => onNavigate(m.path)}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full color-dot" style={{ '--dot-color': m.color } as React.CSSProperties} />
            <span className="text-label">{m.label}</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-semibold font-display">{m.value}</span>
            {m.sub && <span className="text-[10px] text-th-text-muted">{m.sub}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════ */
export default function DashboardPage() {
  const navigate = useNavigate();
  const { currentProject } = useProject();
  const [activeBranch, setActiveBranch] = useState<'wiki' | 'skills'>('wiki');

  const {
    data: stats,
    loading: statsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useApi<KnowledgeStats>(() => fetchStats(currentProject?.id), [currentProject?.id]);

  const {
    data: docsData,
    loading: docsLoading,
    error: docsError,
  } = useApi<PaginatedDocuments>(
    () => fetchDocuments({ page: 1, page_size: 5, projectId: currentProject?.id }),
    [currentProject?.id],
  );

  const loading = statsLoading || docsLoading;
  const error = statsError || docsError;
  const recentDocs = docsData?.documents ?? [];

  /* ─── derived stats ─── */
  const s = stats ?? {
    total_documents: 0,
    kept: 0,
    archived: 0,
    vector_chunks: 0,
    knowledge_domains: 0,
    doc_cards: 0,
    graph_nodes: 0,
    graph_edges: 0,
    by_doc_type: {} as Record<string, number>,
    by_source_system: {} as Record<string, number>,
  };

  const retentionPct = useMemo(
    () => (s.total_documents > 0 ? Math.round((s.kept / s.total_documents) * 100) : 0),
    [s.kept, s.total_documents],
  );

  /* 判断当前工作流进度 */
  const currentStep = useMemo(() => {
    if (s.total_documents === 0) return 0;
    if (s.kept === 0 && s.archived === 0) return 1;
    if (s.knowledge_domains === 0) return 2;
    if (s.doc_cards === 0) return 3;
    if (s.graph_nodes === 0) return 4;
    if (s.graph_edges === 0) return 5;
    if (s.vector_chunks === 0) return 6;
    return 7;
  }, [s]);

  /* Distribution chart helpers */
  const docTypeEntries = useMemo(() => Object.entries(s.by_doc_type), [s.by_doc_type]);
  const sourceEntries = useMemo(() => Object.entries(s.by_source_system), [s.by_source_system]);
  const maxDocType = useMemo(() => Math.max(1, ...docTypeEntries.map(([, c]) => c)), [docTypeEntries]);
  const maxSource = useMemo(() => Math.max(1, ...sourceEntries.map(([, c]) => c)), [sourceEntries]);

  /* ─── Loading ─── */
  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-14 skeleton rounded-card" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (<SkeletonCard key={i} />))}
        </div>
        <div className="h-24 skeleton rounded-card" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (<div key={i} className="h-32 skeleton rounded-card" />))}
        </div>
      </div>
    );
  }

  /* ─── Error ─── */
  if (error) {
    return (
      <div className="p-6 h-full flex items-center justify-center">
        <div className="glass-card rounded-card p-8 text-center max-w-sm">
          <AlertCircle className="mx-auto mb-4 text-th-error" size={36} />
          <p className="text-sm text-secondary mb-5 leading-relaxed">{error}</p>
          <button className="btn-gradient px-5 py-2 rounded-btn text-sm" onClick={() => refetchStats()}>
            重试
          </button>
        </div>
      </div>
    );
  }

  /* ═══════════════════════════════════════════
     Render — 知识治理仪表盘
     ═══════════════════════════════════════════ */
  return (
    <div className="p-6 space-y-5 page-enter">
      {/* ─── Page Header ─── */}
      <PageHeader
        icon={<BookOpen className="text-accent" size={26} />}
        title="知识概览"
        description="知识治理全流程状态与数据统计"
      />

      {/* ─── Hero Stats (4 Raycast cards) ─── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
        {/* 总文档数 */}
        <div className="glass-card rounded-card p-5 relative overflow-hidden">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-label">总文档数</span>
          </div>
          <div className="text-metric animate-countUp">{s.total_documents.toLocaleString()}</div>
          <FileText size={40} className="absolute -bottom-1 -right-1 opacity-[0.03]" />
        </div>

        {/* 保留率 */}
        <div className="glass-card rounded-card p-5 relative overflow-hidden">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-th-success" />
            <span className="text-label">保留率</span>
          </div>
          <div className="flex items-center gap-3">
            <ProgressRing percent={retentionPct} />
            <div className="text-metric animate-countUp">{retentionPct}%</div>
          </div>
        </div>

        {/* 图谱节点 */}
        <div className="glass-card rounded-card p-5 relative overflow-hidden">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full color-dot" style={{ '--dot-color': 'var(--entity-process)' } as React.CSSProperties} />
            <span className="text-label">图谱节点</span>
          </div>
          <div className="text-metric animate-countUp">{s.graph_nodes.toLocaleString()}</div>
          <div className="text-[10px] text-th-text-muted mt-1">{s.graph_edges} 关系连线</div>
        </div>

        {/* 向量分块 */}
        <div className="glass-card rounded-card p-5 relative overflow-hidden">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full bg-th-warning" />
            <span className="text-label">向量分块</span>
          </div>
          <div className="text-metric animate-countUp">{s.vector_chunks.toLocaleString()}</div>
          <div className="text-[10px] text-th-text-muted mt-1">{s.knowledge_domains} 知识域</div>
        </div>
      </div>

      {/* ─── 切换式流程图 (Wiki编译 / Skills检索) ─── */}
      <BranchFlow
        currentStep={currentStep}
        onNavigate={(p) => navigate(p)}
        activeBranch={activeBranch}
        onBranchChange={setActiveBranch}
      />

      {/* ─── 切换式指标卡片 ─── */}
      <BranchCards stats={s} onNavigate={(p) => navigate(p)} activeBranch={activeBranch} />

      {/* ─── Two-Column Bottom ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* ── Recent Documents ── */}
        <div className="glass-card rounded-card p-5">
          <div className="text-overline mb-4">最近文档</div>

          {recentDocs.length > 0 ? (
            <div className="space-y-1">
              {recentDocs.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-btn cursor-pointer transition-all duration-150 hover:bg-hover"
                  onClick={() => navigate('review')}
                >
                  <span className="w-1.5 h-1.5 rounded-full shrink-0 color-dot" style={{ '--dot-color': docTypeColor(doc.doc_type) } as React.CSSProperties} />
                  <span className="text-sm truncate flex-1 text-th-text-primary">{doc.title}</span>
                  <span
                    className="text-[9px] px-2 py-0.5 rounded-pill shrink-0 font-medium doctype-badge"
                    style={{ '--badge-color': docTypeColor(doc.doc_type) } as React.CSSProperties}
                  >
                    {doc.decision || doc.doc_type}
                  </span>
                  <span className="text-[10px] text-th-text-muted shrink-0 tabular-nums">
                    {relativeTime(doc.created_at)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-10 text-th-text-muted">
              <FileText size={28} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm mb-3">暂无文档</p>
              <button className="btn-gradient px-4 py-1 rounded-btn text-xs" onClick={() => navigate('upload')}>
                上传文档
              </button>
            </div>
          )}
        </div>

        {/* ── Distribution Charts ── */}
        <div className="space-y-4">
          {docTypeEntries.length > 0 && (
            <div className="glass-card rounded-card p-5">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={13} className="text-th-text-muted" />
                <span className="text-overline">按文档类型</span>
              </div>
              <div className="space-y-3">
                {docTypeEntries.map(([type, count], idx) => (
                  <div key={type} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-secondary">{type}</span>
                      <span className="text-th-text-muted tabular-nums">{count}</span>
                    </div>
                    <HBar widthPct={(count / maxDocType) * 100} delay={idx * 80} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {sourceEntries.length > 0 && (
            <div className="glass-card rounded-card p-5">
              <div className="flex items-center gap-2 mb-4">
                <Database size={13} className="text-th-text-muted" />
                <span className="text-overline">按来源系统</span>
              </div>
              <div className="space-y-3">
                {sourceEntries.map(([src, count], idx) => (
                  <div key={src} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-secondary">{src}</span>
                      <span className="text-th-text-muted tabular-nums">{count}</span>
                    </div>
                    <HBar widthPct={(count / maxSource) * 100} delay={idx * 80} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {docTypeEntries.length === 0 && sourceEntries.length === 0 && (
            <div className="glass-card rounded-card p-5 text-center text-th-text-muted">
              <BarChart3 size={28} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm">导入文档后显示分布数据</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
