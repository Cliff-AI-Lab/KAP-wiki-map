/**
 * 知识中心 — 三中心统一设计 (M21 #4)
 *
 * 严格按 distinctive.css Nordic Minimalism 系统渲染。
 * 共享 CenterShell + CenterHero + Pipeline + StatTile + KapCard。
 *
 * 业务定位：存储 + 向量化 + 图谱化（拿咨询中心产物 → 入库 → 检索）
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FolderPlus, Database, Cpu, GitBranch, ShieldCheck, Send,
  Inbox, LayoutGrid, RefreshCw, AlertCircle,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import {
  CenterShell, CenterHero, Pipeline, KapCard, StatTile, type Station,
} from '@/components/v15/CenterShell';
import {
  fetchGovernanceHealth, fetchGovernanceQueue,
  type GovernanceHealth, type GovernanceQueueItem,
} from '@/services/governanceApi';
import {
  fetchStats, fetchWikiStats, fetchDocuments,
  type KnowledgeStats, type WikiStats, type DocumentSummary,
} from '@/services/api';
import { useActiveProject } from '@/hooks/useActiveProject';


export default function GovernanceHome() {
  const { t } = useLocale();
  const { projectId } = useActiveProject();

  const [health, setHealth] = useState<GovernanceHealth | null>(null);
  const [queue, setQueue] = useState<GovernanceQueueItem[]>([]);
  // M22 #17: 入库进度可视化 + 文档清单
  const [kStats, setKStats] = useState<KnowledgeStats | null>(null);
  const [wStats, setWStats] = useState<WikiStats | null>(null);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const pid = projectId || 'default';
      const [h, q, ks, ws, ds] = await Promise.all([
        fetchGovernanceHealth(pid).catch(() => null),
        fetchGovernanceQueue(pid, undefined, 'curator').catch(() => []),
        fetchStats(pid).catch(() => null),
        fetchWikiStats(pid).catch(() => null),
        fetchDocuments({ projectId: pid, page: 1, page_size: 20 }).catch(() => null),
      ]);
      setHealth(h);
      setQueue(q || []);
      setKStats(ks);
      setWStats(ws);
      setDocs(ds?.documents || []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [projectId]);

  // 6 工位 — 知识中心视角的工位（存储 / 向量化 / 图谱化为核心）
  const stations: Station[] = [
    { id: 'W1', icon: FolderPlus,  labelKey: 'manage.station.w1', hintKey: 'manage.station.w1.hint', state: 'done' },
    { id: 'W2', icon: Database,    labelKey: 'manage.station.w2', hintKey: 'manage.station.w2.hint', state: 'done' },
    { id: 'W3', icon: Cpu,         labelKey: 'manage.station.w3', hintKey: 'manage.station.w3.hint', state: 'active' },
    { id: 'W4', icon: GitBranch,   labelKey: 'manage.station.w4', hintKey: 'manage.station.w4.hint', state: 'pending' },
    { id: 'W5', icon: ShieldCheck, labelKey: 'manage.station.w5', hintKey: 'manage.station.w5.hint', state: 'pending' },
    { id: 'W6', icon: Send,        labelKey: 'manage.station.w6', hintKey: 'manage.station.w6.hint', state: 'pending' },
  ];

  // 后端 health 字段已是百分整数（0-100）；做防御兼容 0-1 小数也能跑
  const toPctNumber = (v: number | undefined): number => {
    const x = v ?? 0;
    return x <= 1 ? x * 100 : x;
  };
  const wikiCoverage = `${Math.round(toPctNumber(health?.wiki_coverage))}%`;
  const ragFallback  = `${Math.round(toPctNumber(health?.rag_fallback_rate))}%`;
  const provenance   = `${Math.round(toPctNumber(health?.provenance_score))}%`;

  return (
    <CenterShell>
      <CenterHero
        kind="manage"
        titleKey="manage.heroTitle"
        subtitleKey="manage.heroSub"
        rightSlot={
          <>
            <Link to="/v15/manage/matrix" className="kap-btn">
              <LayoutGrid size={13} />
              {t('kap.viewMatrix')}
            </Link>
            <button
              type="button"
              onClick={() => { setRefreshing(true); load(); }}
              className="kap-btn"
              disabled={refreshing}
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
              {t('observ.refresh')}
            </button>
          </>
        }
      />

      <Pipeline labelKey="kap.tagPipeline" stations={stations} />

      {/* M22 #17: 入库进度面板 - 解决用户痛点"看不到归档/向量化/图谱化进度" */}
      <KapCard
        eyebrow="▶ 入库进度（归档 / 向量化 / 图谱化 / Wiki 编织）"
        rightSlot={
          <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
            project: {projectId || 'default'}
          </span>
        }
      >
        <div className="kap-grid-3" style={{ gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px' }}>
          <ProgressTile
            label="① 归档落库"
            value={kStats?.kept ?? 0}
            total={kStats?.total_documents ?? 0}
            subtext={`${kStats?.archived ?? 0} 归档 · ${kStats?.discarded ?? 0} 丢弃 · ${kStats?.pending_review ?? 0} 待审`}
            done={(kStats?.total_documents ?? 0) > 0}
          />
          <ProgressTile
            label="② 向量化"
            value={kStats?.vector_chunks ?? 0}
            unit=" chunks"
            subtext={(kStats?.vector_chunks ?? 0) > 0 ? '已向量化, RAG 可召回' : '尚未向量化'}
            done={(kStats?.vector_chunks ?? 0) > 0}
          />
          <ProgressTile
            label="③ 图谱化"
            value={kStats?.graph_nodes ?? 0}
            unit=" 节点"
            subtext={`${kStats?.graph_edges ?? 0} 条关系边`}
            done={(kStats?.graph_nodes ?? 0) > 0}
          />
          <ProgressTile
            label="④ Wiki 编织"
            value={wStats?.published_pages ?? 0}
            unit=" 页"
            subtext={`source ${wStats?.source_pages ?? 0} · domain ${wStats?.domain_pages ?? 0} · index ${wStats?.index_pages ?? 0}`}
            done={(wStats?.published_pages ?? 0) > 0}
          />
          <ProgressTile
            label="⑤ 知识域识别"
            value={kStats?.knowledge_domains ?? 0}
            unit=" 域"
            subtext={`${kStats?.doc_cards ?? 0} 个 doc 卡片已建`}
            done={(kStats?.knowledge_domains ?? 0) > 0}
          />
        </div>
        {/* 重建入口 - 人工调整进程 */}
        <div className="mt-4 pt-3 flex flex-wrap gap-2"
             style={{ borderTop: '1px solid rgba(216,222,233,0.08)' }}>
          <Link to="/v15/manage/import/review" className="kap-btn">
            <ShieldCheck size={12} />
            去噪审核 ({kStats?.pending_review ?? 0} 待审)
          </Link>
          <Link to="/v15/manage/import/taxonomy" className="kap-btn">
            <GitBranch size={12} />
            知识体系 ({kStats?.knowledge_domains ?? 0} 域)
          </Link>
          <Link to="/v15/manage/graph" className="kap-btn">
            <GitBranch size={12} />
            查看图谱 ({kStats?.graph_nodes ?? 0}/{kStats?.graph_edges ?? 0})
          </Link>
          <Link to="/v15/read/wiki-tree" className="kap-btn">
            <Database size={12} />
            Wiki 三层 ({wStats?.published_pages ?? 0})
          </Link>
          <Link to="/v15/manage/import/compiled" className="kap-btn kap-btn-primary">
            <RefreshCw size={12} />
            端到端报告 + 重建入口
          </Link>
        </div>
      </KapCard>

      <div style={{ height: 16 }} />

      {/* M22 #17: 已上传文档清单 - 用户痛点"上传了哪些文档要能看到" */}
      <KapCard
        eyebrow="▶ 已上传文档"
        rightSlot={
          <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
            共 {docs.length} 篇 (最近 20)
          </span>
        }
      >
        {docs.length === 0 ? (
          <div className="py-8 text-center" style={{
            fontFamily: 'var(--kap-font-mono)', fontSize: 12,
            color: 'var(--kap-snow-4)',
          }}>
            <Inbox size={24} className="inline-block mb-2" style={{ opacity: 0.5 }} />
            <div>暂无文档 (从咨询中心上传或调用 /knowledge/ingest)</div>
          </div>
        ) : (
          <ul className="space-y-1.5">
            {docs.slice(0, 12).map(d => {
              const tone = d.decision === 'KEEP'    ? 'hsl(var(--success))'
                         : d.decision === 'ARCHIVE' ? 'hsl(var(--warning))'
                         : d.decision === 'DISCARD' ? 'hsl(var(--destructive))'
                         : 'hsl(var(--muted-foreground))';
              return (
                <li key={d.id} className="flex items-center gap-2"
                    style={{
                      padding: '0.45rem 0.6rem',
                      background: 'hsl(var(--muted) / 0.3)',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: 'calc(var(--radius) - 4px)',
                      fontSize: 11.5, lineHeight: 1.5,
                    }}>
                  <span className="kap-badge"
                        style={{ color: tone, borderColor: tone, fontSize: 10 }}>
                    {d.decision || '?'}
                  </span>
                  <span className="flex-1 truncate" style={{ fontWeight: 500 }}>
                    {d.title || d.id}
                  </span>
                  {d.doc_type && (
                    <span className="kap-mono-tag" style={{ fontSize: 9.5, color: 'hsl(var(--muted-foreground))' }}>
                      {d.doc_type}
                    </span>
                  )}
                  {d.category_path && (
                    <span className="kap-mono-tag truncate"
                          style={{ fontSize: 9.5, color: 'hsl(var(--primary))', maxWidth: 220 }}>
                      ◆ {d.category_path}
                    </span>
                  )}
                  <Link to={`/v15/manage/import/review`} className="kap-btn"
                        style={{ fontSize: 10, padding: '2px 8px' }}>
                    ✎ 调整
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {docs.length > 12 && (
          <div className="mt-2 text-right">
            <Link to="/v15/manage/import/review" className="kap-mono-tag"
                  style={{ fontSize: 11, color: 'hsl(var(--primary))' }}>
              查看全部 {docs.length} 篇 →
            </Link>
          </div>
        )}
      </KapCard>

      <div style={{ height: 20 }} />

      {error && (
        <div className="kap-card mb-6" style={{
          padding: '0.8rem 1rem', borderColor: 'var(--kap-aurora-red)',
          background: 'rgba(191,97,106,0.08)',
        }}>
          <span className="kap-mono-tag" style={{ color: 'var(--kap-aurora-red)' }}>
            <AlertCircle size={11} className="inline mr-1.5" /> {error}
          </span>
        </div>
      )}

      {/* 4 张统计 */}
      <section className="kap-stagger kap-grid-3 mb-8" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatTile labelKey="gov.metricCoverage" value={wikiCoverage} state="good" />
        <StatTile
          labelKey="gov.metricFallback"
          value={ragFallback}
          state={toPctNumber(health?.rag_fallback_rate) > 40 ? 'alert' : 'normal'}
        />
        <StatTile labelKey="gov.metricProvenance" value={provenance} state="good" />
        <StatTile labelKey="kap.statDecisions" value={queue.length} suffix="待审" />
      </section>

      {/* 主区：左工单 / 右健康 */}
      <div className="kap-grid-2" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)' }}>
        <KapCard
          eyebrow={`▶ ${t('gov.queueDetail')}`}
          frost
          rightSlot={
            <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
              {t('gov.countTotal', { n: queue.length })}
            </span>
          }
        >
          {queue.length === 0 ? (
            <div className="py-12 text-center" style={{
              fontFamily: 'var(--kap-font-mono)', fontSize: 12,
              color: 'var(--kap-snow-4)', letterSpacing: '0.08em',
            }}>
              <Inbox size={28} className="inline-block mb-3" style={{ color: 'var(--kap-snow-4)', opacity: 0.5 }} />
              <div>{t('gov.emptyQueue')}</div>
            </div>
          ) : (
            <ul className="kap-stagger space-y-2.5">
              {queue.slice(0, 12).map(it => <QueueRow key={it.id} item={it} t={t} />)}
            </ul>
          )}
        </KapCard>

        <KapCard eyebrow={`▶ ${t('gov.health')}`}>
          <div className="space-y-5">
            <HealthBar label={t('gov.metricCoverage')} value={health?.wiki_coverage ?? 0} hint={t('gov.hintCoverage')} accent="var(--kap-frost)" />
            <HealthBar label={t('gov.metricFallback')} value={health?.rag_fallback_rate ?? 0} hint={t('gov.hintFallback')} accent="var(--kap-aurora-orange)" inverted />
            <HealthBar label={t('gov.metricProvenance')} value={health?.provenance_score ?? 0} hint={t('gov.hintProvenance')} accent="var(--kap-aurora-green)" />
          </div>
          <div className="mt-6 pt-4" style={{ borderTop: '1px solid rgba(216,222,233,0.08)' }}>
            <div className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
              {t('gov.healthSub')}
            </div>
          </div>
        </KapCard>
      </div>
    </CenterShell>
  );
}


// M22 #17 · 入库进度单格 (5 阶段)
function ProgressTile({
  label, value, total, unit = '', subtext, done,
}: {
  label: string;
  value: number;
  total?: number;
  unit?: string;
  subtext?: string;
  done?: boolean;
}) {
  const display = total !== undefined && total > 0
    ? `${value} / ${total}`
    : `${value}${unit}`;
  return (
    <div className="kap-card" style={{
      padding: '0.7rem 0.85rem',
      background: done ? 'hsl(var(--success) / 0.08)' : 'hsl(var(--muted) / 0.4)',
      border: `1px solid ${done ? 'hsl(var(--success) / 0.4)' : 'hsl(var(--border))'}`,
    }}>
      <div className="kap-mono-tag mb-1"
           style={{
             color: done ? 'hsl(var(--success))' : 'hsl(var(--muted-foreground))',
             fontSize: 10, letterSpacing: '0.04em',
           }}>
        {label} {done ? '✓' : '○'}
      </div>
      <div style={{
        fontFamily: 'var(--kap-font-display)',
        fontWeight: 700, fontSize: 22,
        color: 'hsl(var(--foreground))',
        letterSpacing: '-0.02em',
      }}>
        {display}
      </div>
      {subtext && (
        <div className="kap-mono-tag" style={{
          fontSize: 10, color: 'hsl(var(--muted-foreground))', marginTop: 4,
        }}>
          {subtext}
        </div>
      )}
    </div>
  );
}


function QueueRow({ item, t }: { item: GovernanceQueueItem; t: (k: string) => string }) {
  void t;
  return (
    <li
      className="flex items-center gap-4 py-2.5 px-3"
      style={{
        borderLeft: '2px solid var(--kap-frost)',
        background: 'rgba(67,76,94,0.35)',
        transition: 'all var(--kap-dur-fast) var(--kap-ease)',
      }}
    >
      <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
        #{(item.id || '').slice(-6).toUpperCase()}
      </span>
      <div className="flex-1 truncate" style={{
        fontFamily: 'var(--kap-font-body)', fontWeight: 400, fontSize: 14,
      }}>
        {item.title || item.description || '(no title)'}
      </div>
      <span className="kap-mono-tag" style={{ color: 'var(--kap-aurora-yellow)' }}>
        {item.kind?.toUpperCase()}
      </span>
    </li>
  );
}


function HealthBar({
  label, value, hint, accent, inverted,
}: {
  label: string; value: number; hint: string; accent: string; inverted?: boolean;
}) {
  // 兼容：value 可能是 0-1 小数也可能是 0-100 整数
  const pct = Math.round(value <= 1 ? value * 100 : value);
  const fillPct = inverted ? Math.max(0, 100 - pct) : pct;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span style={{ fontFamily: 'var(--kap-font-display)', fontWeight: 500, fontSize: 13 }}>
          {label}
        </span>
        <span className="kap-mono-tag" style={{ color: accent }}>
          {pct}%
        </span>
      </div>
      <div className="relative h-1.5 mb-1" style={{ background: 'rgba(216,222,233,0.08)' }}>
        <div
          className="absolute inset-y-0 left-0"
          style={{
            width: `${fillPct}%`,
            background: accent,
            transition: 'width 800ms var(--kap-ease)',
          }}
        />
      </div>
      <div className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)', letterSpacing: '0.10em' }}>
        {hint}
      </div>
    </div>
  );
}
