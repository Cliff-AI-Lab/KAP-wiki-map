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
import { useActiveProject } from '@/hooks/useActiveProject';


export default function GovernanceHome() {
  const { t } = useLocale();
  const { projectId } = useActiveProject();

  const [health, setHealth] = useState<GovernanceHealth | null>(null);
  const [queue, setQueue] = useState<GovernanceQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const pid = projectId || 'default';
      const [h, q] = await Promise.all([
        fetchGovernanceHealth(pid).catch(() => null),
        fetchGovernanceQueue(pid, undefined, 'curator').catch(() => []),
      ]);
      setHealth(h);
      setQueue(q || []);
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
