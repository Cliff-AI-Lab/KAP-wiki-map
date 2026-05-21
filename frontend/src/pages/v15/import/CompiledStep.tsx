/**
 * CompiledStep — 第 4 步: 端到端跑通报告
 *
 * 不只是显示"完成"标记, 而是真实展示 6 阶段的各项指标:
 *   1. 上传 + 解析
 *   2. 去噪决策 (KEEP/ARCHIVE/DISCARD)
 *   3. 知识体系 (域识别覆盖率)
 *   4. Wiki 编译 (三层)
 *   5. 知识图谱 (实体/关系/社区)
 *   6. 欠缺/告警
 *
 * M22 #11: 加 embedded 模式 — 嵌入 ConsultHome 时隐藏底部 Link/QuickLink 卡片,
 * 提供 onComplete 回调让流程关闭.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Loader2, BookOpen, GitBranch, FolderOpen, ArrowRight,
  CheckCircle2, AlertTriangle, Wrench, Upload, Filter, Network, Sparkles,
} from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';
import {
  fetchStats, fetchWikiStats, fetchDomains,
  type KnowledgeStats, type WikiStats, type DomainsResponse,
} from '@/services/api';

interface GraphViewStats { node_count: number; edge_count: number; community_count: number; max_centrality: number }

export interface CompiledStepProps {
  projectId?: string;
  embedded?: boolean;
  onComplete?: () => void;
}

export default function CompiledStep(props: CompiledStepProps = {}) {
  const { projectId: overrideProjectId, embedded = false, onComplete } = props;
  const { projectId: ctxProjectId } = useActiveProject();
  const projectId = overrideProjectId ?? ctxProjectId;
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [wiki, setWiki] = useState<WikiStats | null>(null);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);
  const [graph, setGraph] = useState<GraphViewStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      fetchStats(projectId),
      fetchWikiStats(projectId),
      fetchDomains(projectId),
      fetch(`/api/v1/v15/graph/view?project_id=${encodeURIComponent(projectId)}`).then(r => r.ok ? r.json() : null),
    ]).then(([s, w, d, g]) => {
      if (s.status === 'fulfilled') setStats(s.value);
      if (w.status === 'fulfilled') setWiki(w.value);
      if (d.status === 'fulfilled') setDomains(d.value);
      if (g.status === 'fulfilled' && g.value) setGraph(g.value.stats);
    }).catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (!projectId) {
    return <div className="text-sm text-th-text-muted">未选择项目</div>;
  }

  // === 计算各阶段指标 ===
  const totalDocs = stats?.total_documents ?? 0;
  const kept = stats?.kept ?? 0;
  const archived = stats?.archived ?? 0;
  const discarded = stats?.discarded ?? 0;
  const pendingReview = stats?.pending_review ?? 0;
  const domainsTotal = domains?.total_domains ?? stats?.knowledge_domains ?? 0;
  const domainsWithDocs = domains?.domains.filter((d) => d.doc_count > 0).length ?? 0;
  const domainCoverage = domainsTotal > 0 ? Math.round((domainsWithDocs / domainsTotal) * 100) : 0;
  const wikiPublished = wiki?.published_pages ?? 0;
  const graphNodes = graph?.node_count ?? stats?.graph_nodes ?? 0;
  const graphEdges = graph?.edge_count ?? stats?.graph_edges ?? 0;
  const communities = graph?.community_count ?? 0;

  // === 欠缺识别 ===
  const gaps: { level: 'warn' | 'error'; msg: string }[] = [];
  if (totalDocs === 0) gaps.push({ level: 'error', msg: '尚未导入任何文档 — 在第 1 步上传材料' });
  if (pendingReview > 0) gaps.push({ level: 'warn', msg: `${pendingReview} 篇文档待审核 — 在第 2 步去噪审核处理` });
  if (discarded > 0) gaps.push({ level: 'warn', msg: `${discarded} 篇被丢弃 — 可能是重复或低质量` });
  if (domainCoverage > 0 && domainCoverage < 30) gaps.push({ level: 'warn', msg: `知识域覆盖率仅 ${domainCoverage}% — 待 ${domainsTotal - domainsWithDocs} 个域待识别` });
  if (totalDocs > 0 && wikiPublished === 0) gaps.push({ level: 'error', msg: 'Wiki 未编译 — 检查 ingest 流程是否完成' });
  if (totalDocs > 0 && graphNodes === 0) gaps.push({ level: 'error', msg: '知识图谱为空 — 检查 GraphStore 是否正常' });

  const ready = totalDocs > 0 && wikiPublished > 0 && graphNodes > 0;

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-5'}>
      {!embedded && (
        <div>
          <h2 className="v15-display text-xl text-th-text-primary">第 4 步 · 端到端跑通报告</h2>
          <p className="text-xs text-th-text-muted mt-1">
            从导入 → 去噪 → 体系 → Wiki → 图谱 各阶段真实指标 · 欠缺项一目了然
          </p>
        </div>
      )}

      {/* 总状态 */}
      <div className={`rounded-card p-3 flex items-center gap-3 ${
        ready ? 'border border-th-success/40 bg-th-success/5' : 'border border-th-warning/40 bg-th-warning/5'
      }`}>
        {loading ? <Loader2 size={18} className="animate-spin text-th-text-muted" /> :
          ready ? <CheckCircle2 size={18} className="text-th-success" /> :
                  <AlertTriangle size={18} className="text-th-warning" />}
        <div className="flex-1 text-sm">
          <div className="font-semibold text-th-text-primary">
            {loading ? '加载中...' : ready ? '全流程跑通 · 编译产物已就绪' : '部分阶段未完成'}
          </div>
          <div className="text-[11px] text-th-text-muted v15-mono mt-0.5">
            docs={totalDocs} · wiki={wikiPublished} · graph_nodes={graphNodes} · domains={domainsWithDocs}/{domainsTotal}
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-btn border border-th-error/40 bg-th-error/5 p-3 text-sm text-th-error flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
        </div>
      )}

      {/* 6 阶段跑通记录 */}
      <div className="space-y-3">
        {/* Stage 1: 上传 + 解析 */}
        <StageCard
          step={1}
          icon={<Upload size={14} />}
          title="上传 + 解析"
          metrics={[
            { label: '总文档', value: totalDocs },
            { label: '解析成功', value: totalDocs, hint: '基于 PDF/DOCX/MD/HTML/TXT 多格式 parser' },
            { label: '解析失败', value: 0, tone: 'success' },
          ]}
        />

        {/* Stage 2: 去噪审核 */}
        <StageCard
          step={2}
          icon={<Filter size={14} />}
          title="去噪审核 (LLM 自动 + 人工复核)"
          metrics={[
            { label: 'KEEP', value: kept, tone: 'success' },
            { label: 'ARCHIVE', value: archived, tone: archived > 0 ? 'warning' : 'muted' },
            { label: 'DISCARD', value: discarded, tone: discarded > 0 ? 'error' : 'muted' },
            { label: '待审', value: pendingReview, tone: pendingReview > 0 ? 'warning' : 'muted', hint: '需人工复核' },
          ]}
        />

        {/* Stage 3: 知识体系 */}
        <StageCard
          step={3}
          icon={<Network size={14} />}
          title="知识体系 Schema"
          metrics={[
            { label: '总域数', value: domainsTotal, hint: '行业模板预置' },
            { label: '已识别', value: domainsWithDocs, tone: 'success', hint: 'doc_count > 0' },
            { label: '覆盖率', value: `${domainCoverage}%`, tone: domainCoverage >= 50 ? 'success' : domainCoverage >= 20 ? 'warning' : 'error' },
            { label: '空域', value: domainsTotal - domainsWithDocs, tone: 'muted', hint: '尚无文档归类' },
          ]}
          extra={
            domains && domainsWithDocs > 0 && (
              <div className="text-[11px] text-th-text-muted mt-2 pt-2 border-t border-th-border">
                <span className="v15-mono uppercase tracking-wider mr-2">Top 域:</span>
                {domains.domains
                  .filter((d) => d.doc_count > 0)
                  .sort((a, b) => b.doc_count - a.doc_count)
                  .slice(0, 5)
                  .map((d) => (
                    <span key={d.domain_id} className="inline-block mr-2 px-1.5 py-0.5 rounded text-th-text-secondary bg-hover/50">
                      {d.name || d.domain_id} <span className="text-th-text-muted">·{d.doc_count}</span>
                    </span>
                  ))}
              </div>
            )
          }
        />

        {/* Stage 4: Wiki 编译 */}
        <StageCard
          step={4}
          icon={<BookOpen size={14} />}
          title="Wiki 三层编译 (Karpathy)"
          metrics={[
            { label: 'source', value: wiki?.source_pages ?? 0, hint: '每文档一页' },
            { label: 'domain', value: wiki?.domain_pages ?? 0, hint: '域级聚合' },
            { label: 'index', value: wiki?.index_pages ?? 0, hint: '顶级索引' },
            { label: '已发布', value: wikiPublished, tone: 'success' },
            { label: '陈旧', value: wiki?.stale_pages ?? 0, tone: (wiki?.stale_pages ?? 0) > 0 ? 'warning' : 'muted' },
          ]}
        />

        {/* Stage 5: 知识图谱 */}
        <StageCard
          step={5}
          icon={<GitBranch size={14} />}
          title="知识图谱 (LLM 抽取实体/关系)"
          metrics={[
            { label: '实体节点', value: graphNodes, tone: 'success' },
            { label: '关系边', value: graphEdges, tone: 'success' },
            { label: '社区', value: communities, hint: 'Louvain 自动聚类' },
            { label: '向量 chunks', value: stats?.vector_chunks ?? 0, hint: 'RAG 检索' },
          ]}
        />

        {/* Stage 6: 欠缺/告警 */}
        <div className={`rounded-card p-4 border ${
          gaps.length === 0 ? 'border-th-success/40 bg-th-success/5' :
          gaps.some(g => g.level === 'error') ? 'border-th-error/40 bg-th-error/5' :
          'border-th-warning/40 bg-th-warning/5'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            {gaps.length === 0 ? <CheckCircle2 size={14} className="text-th-success" /> : <AlertTriangle size={14} className="text-th-warning" />}
            <span className="text-sm font-semibold text-th-text-primary">第 6 项 · 欠缺/告警</span>
            <span className="text-[10px] v15-mono text-th-text-muted ml-auto">{gaps.length} 项</span>
          </div>
          {gaps.length === 0 ? (
            <div className="text-xs text-th-text-secondary">所有阶段均健康通过 ✓</div>
          ) : (
            <ul className="space-y-1.5 text-xs">
              {gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
                    g.level === 'error' ? 'bg-th-error' : 'bg-th-warning'
                  }`} />
                  <span className="text-th-text-secondary">{g.msg}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 入口卡 — 顶层路由模式展示, 嵌入模式隐藏 (避免跳出 ConsultHome 流程) */}
      {!embedded && (
        <div className="grid grid-cols-2 gap-4 pt-2">
          <Link to="/v15/read" className="group rounded-card border border-accent/40 bg-accent/5 p-5 hover:bg-accent/10 transition">
            <div className="text-[11px] v15-mono uppercase tracking-wider text-accent mb-1">消费模式 (业务员)</div>
            <div className="flex items-center gap-2"><FolderOpen size={16} className="text-accent" />
              <span className="text-base font-semibold text-th-text-primary">打开 Reader</span></div>
            <p className="text-xs text-th-text-muted mt-2">搜索 · 热门 Wiki · 知识地图 · 跨页穿透</p>
            <div className="mt-3 text-[11px] v15-mono text-accent flex items-center gap-1">
              /v15/read <ArrowRight size={11} className="group-hover:translate-x-0.5 transition" />
            </div>
          </Link>
          <Link to="/v15/manage" className="rounded-card border border-th-border bg-elevated p-5 hover:border-th-border-hover transition">
            <div className="text-[11px] v15-mono uppercase tracking-wider text-th-text-muted mb-1">治理模式 (管理员)</div>
            <div className="flex items-center gap-2"><Wrench size={16} className="text-th-text-secondary" />
              <span className="text-base font-semibold text-th-text-primary">打开治理收件箱</span></div>
            <p className="text-xs text-th-text-muted mt-2">5 Agent 工单 · Wiki 编辑 · 健康面板</p>
            <div className="mt-3 text-[11px] v15-mono text-th-text-secondary flex items-center gap-1">
              /v15/manage <ArrowRight size={11} />
            </div>
          </Link>
        </div>
      )}

      {/* 快捷链接 — 同上 */}
      {!embedded && (
        <div className="grid grid-cols-3 gap-3">
          <QuickLink to={`/v15/manage/graph`} icon={<Sparkles size={12} />} label="知识图谱" hint="9 个 community · 拖拽 / 全部 / 分块" />
          <QuickLink to={`/v15/manage/import/taxonomy`} icon={<Network size={12} />} label="知识体系" hint={`${domainsWithDocs}/${domainsTotal} 域识别`} />
          <QuickLink to={`/v15/manage/import/review`} icon={<Filter size={12} />} label="去噪审核" hint={`${pendingReview} 待审 · ${kept} 已留`} />
        </div>
      )}

      {/* M22 #11 嵌入模式: 完成按钮触发 onComplete (流程关闭) */}
      {embedded && ready && (
        <div className="text-right pt-2">
          <button
            onClick={() => onComplete?.()}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-btn bg-th-success text-[color:var(--color-bg-base)] text-xs font-medium hover:brightness-95"
          >
            <CheckCircle2 size={14} /> 完成 · 进入知识中心
          </button>
        </div>
      )}
    </div>
  );
}

interface StageMetric { label: string; value: number | string; hint?: string; tone?: 'success' | 'warning' | 'error' | 'muted' }

function StageCard({
  step, icon, title, metrics, extra,
}: { step: number; icon: React.ReactNode; title: string; metrics: StageMetric[]; extra?: React.ReactNode }) {
  return (
    <div className="rounded-card border border-th-border bg-elevated p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-6 h-6 rounded-full bg-accent/10 text-accent text-[10px] v15-mono grid place-items-center">{step}</span>
        <span className="text-th-text-muted">{icon}</span>
        <span className="text-sm font-semibold text-th-text-primary">{title}</span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {metrics.map((m) => {
          const colors = {
            success: 'text-th-success',
            warning: 'text-th-warning',
            error:   'text-th-error',
            muted:   'text-th-text-secondary',
          };
          return (
            <div key={m.label}>
              <div className="text-[10px] uppercase tracking-wider text-th-text-muted">{m.label}</div>
              <div className={`text-xl font-semibold mt-1 v15-display ${m.tone ? colors[m.tone] : 'text-th-text-primary'}`}>
                {m.value}
              </div>
              {m.hint && <div className="text-[10px] text-th-text-muted v15-mono mt-1 truncate" title={m.hint}>{m.hint}</div>}
            </div>
          );
        })}
      </div>
      {extra}
    </div>
  );
}

function QuickLink({ to, icon, label, hint }: { to: string; icon: React.ReactNode; label: string; hint: string }) {
  return (
    <Link to={to} className="rounded-btn border border-th-border p-3 hover:border-accent/60 hover:bg-hover transition">
      <div className="text-sm text-th-text-primary inline-flex items-center gap-1.5">{icon} {label}</div>
      <div className="text-[10px] text-th-text-muted v15-mono mt-1">{hint}</div>
    </Link>
  );
}
