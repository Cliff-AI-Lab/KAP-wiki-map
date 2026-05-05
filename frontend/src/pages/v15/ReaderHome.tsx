/**
 * 消费中心 — 三中心统一设计 (M21 #4)
 *
 * 严格按 distinctive.css Nordic Minimalism 系统渲染。
 * 共享 CenterShell + CenterHero + Pipeline + StatTile + KapCard。
 *
 * 业务定位：渐进式三路召回（Wiki 快路径 → RAG 深检索 → 图谱跨域）
 */
import { useEffect, useState, type FormEvent } from 'react';
import { Search, Clock, BookOpen, Layers, Network } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import {
  askQuestion,
  fetchWikiPages,
  fetchDomains,
  type QAResponse,
  type WikiPageSummary,
  type DomainInfo,
} from '@/services/api';
import {
  CenterShell, CenterHero, Pipeline, KapCard, StatTile, type Station,
} from '@/components/v15/CenterShell';


const RECENT_KEY = 'wikimap-recent-questions';
const MAX_RECENT = 5;

function loadRecent(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch { return []; }
}
function saveRecent(q: string): string[] {
  const prev = loadRecent().filter(x => x !== q);
  const next = [q, ...prev].slice(0, MAX_RECENT);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  return next;
}


export default function ReaderHome() {
  const { t } = useLocale();
  const { projectId } = useActiveProject();

  const [query, setQuery] = useState('');
  const [resp, setResp] = useState<QAResponse | null>(null);
  const [lastQ, setLastQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [wikiPages, setWikiPages] = useState<WikiPageSummary[]>([]);
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [recent, setRecent] = useState<string[]>(loadRecent());

  useEffect(() => {
    fetchWikiPages(projectId || undefined).then(setWikiPages).catch(() => {});
    fetchDomains(projectId || undefined)
      .then(r => setDomains(r?.domains || []))
      .catch(() => {});
  }, [projectId]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true); setError(null); setResp(null); setLastQ(q);
    try {
      const r = await askQuestion(q, 5, projectId || undefined);
      setResp(r);
      setRecent(saveRecent(q));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // 三路 stations（消费中心的 pipeline 是渐进式召回路径）
  const stations: Station[] = [
    { id: 'P1', icon: BookOpen, labelKey: 'read.path.wiki',  hintKey: 'read.path.wiki.hint',
      state: resp?.route_path === 'wiki' ? 'active' : 'pending' },
    { id: 'P2', icon: Layers,   labelKey: 'read.path.rag',   hintKey: 'read.path.rag.hint',
      state: resp?.route_path === 'rag'  ? 'active' : resp?.route_path === 'hybrid' ? 'active' : 'pending' },
    { id: 'P3', icon: Network,  labelKey: 'read.path.graph', hintKey: 'read.path.graph.hint',
      state: 'pending' },
  ];

  return (
    <CenterShell>
      <CenterHero
        kind="read"
        titleKey="read.heroTitle"
        subtitleKey="read.heroSub"
      />

      <Pipeline labelKey="kap.tagFlow" stations={stations} />

      {/* 搜索框 */}
      <KapCard frost className="mb-8">
        <form onSubmit={onSubmit} className="flex items-center gap-3">
          <Search size={18} style={{ color: 'var(--kap-frost)' }} />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={t('reader.searchPlaceholder')}
            className="kap-input"
            style={{ background: 'transparent', border: 'none', fontSize: '1.1rem', fontWeight: 200, padding: '0.4rem 0' }}
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="kap-btn kap-btn-primary"
          >
            {loading ? t('reader.searching') : t('reader.searchBtn')}
          </button>
        </form>
      </KapCard>

      {error && (
        <div className="kap-card mb-6" style={{
          padding: '0.8rem 1rem', borderColor: 'var(--kap-aurora-red)',
          background: 'rgba(191,97,106,0.08)',
        }}>
          <span className="kap-mono-tag" style={{ color: 'var(--kap-aurora-red)' }}>
            ERR · {error}
          </span>
        </div>
      )}

      {resp && <AnswerCard resp={resp} q={lastQ} t={t} />}

      {/* 4 张统计 */}
      <section className="kap-stagger kap-grid-3 my-8" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatTile labelKey="kap.statWiki"    value={wikiPages.length} />
        <StatTile labelKey="kap.statDomains" value={domains.length} />
        <StatTile labelKey="kap.statQueries" value={recent.length} />
        <StatTile
          labelKey="reader.routeShown"
          value={resp?.route_path?.toUpperCase() ?? '—'}
          state={resp ? 'good' : 'normal'}
        />
      </section>

      {/* 三卡：热门 Wiki / 知识地图 / 最近问答 */}
      <div className="kap-stagger kap-grid-3">
        <KapCard eyebrow={`▶ ${t('reader.cardHotWiki')}`}>
          {wikiPages.length === 0 ? (
            <Empty text={t('reader.emptyWiki')} />
          ) : (
            <ul className="space-y-2">
              {wikiPages.slice(0, 6).map(p => (
                <li key={p.page_id}
                    className="flex items-center justify-between gap-3 py-1.5"
                    style={{ borderBottom: '1px dashed rgba(216,222,233,0.06)' }}>
                  <span style={{ fontFamily: 'var(--kap-font-display)', fontWeight: 500, fontSize: 14 }}>
                    {p.title}
                  </span>
                  <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
                    {p.source_doc_count ?? 0}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </KapCard>

        <KapCard eyebrow={`▶ ${t('reader.cardDomainMap')}`}>
          {domains.length === 0 ? (
            <Empty text={t('reader.emptyDomain')} />
          ) : (
            <ul className="space-y-2">
              {domains.slice(0, 6).map(d => (
                <li key={d.domain_id}
                    className="flex items-center justify-between gap-3 py-1.5"
                    style={{ borderBottom: '1px dashed rgba(216,222,233,0.06)' }}>
                  <span style={{ fontFamily: 'var(--kap-font-display)', fontWeight: 500, fontSize: 14 }}>
                    {d.name}
                  </span>
                  <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
                    {d.doc_count ?? 0}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </KapCard>

        <KapCard eyebrow={`▶ ${t('reader.cardRecent')}`}>
          {recent.length === 0 ? (
            <Empty text={t('reader.emptyRecent')} />
          ) : (
            <ul className="space-y-1.5">
              {recent.map((q, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => { setQuery(q); }}
                    className="w-full text-left flex items-baseline gap-2 py-1"
                    style={{ fontFamily: 'var(--kap-font-body)', fontSize: 13 }}
                  >
                    <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="truncate" style={{ color: 'var(--kap-snow-2)' }}>{q}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </KapCard>
      </div>
    </CenterShell>
  );
}


function Empty({ text }: { text: string }) {
  return (
    <div className="py-6 text-center kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
      ○ {text}
    </div>
  );
}


function AnswerCard({
  resp, q, t,
}: {
  resp: QAResponse;
  q: string;
  t: (k: string, vars?: Record<string, string | number>) => string;
}) {
  const routeLabel: Record<string, string> = {
    wiki:   t('reader.routeWiki'),
    rag:    t('reader.routeRag'),
    hybrid: t('reader.routeHybrid'),
  };

  return (
    <KapCard frost className="mb-8">
      <div className="flex items-center flex-wrap gap-3 mb-3">
        {resp.route_path && (
          <span
            className="kap-mono-tag px-2 py-1"
            style={{
              border: '1px solid var(--kap-frost)',
              color: 'var(--kap-frost)',
              background: 'rgba(136,192,208,0.08)',
            }}
          >
            {t('reader.routeShown')} · {routeLabel[resp.route_path] ?? resp.route_path}
          </span>
        )}
        {resp.latency_ms !== undefined && (
          <span className="kap-mono-tag" style={{ color: 'var(--kap-snow-4)' }}>
            <Clock size={10} className="inline mr-1" />
            {resp.latency_ms}ms
          </span>
        )}
      </div>

      <div className="kap-mono-tag mb-3" style={{ color: 'var(--kap-snow-4)' }}>
        Q · {q}
      </div>

      <div className="prose prose-sm max-w-none"
           style={{
             fontFamily: 'var(--kap-font-body)', fontWeight: 400, fontSize: 14.5,
             color: 'var(--kap-snow-1)', lineHeight: 1.7,
           }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{resp.answer}</ReactMarkdown>
      </div>

      {resp.sources && resp.sources.length > 0 && (
        <div className="mt-5 pt-3" style={{ borderTop: '1px solid rgba(216,222,233,0.08)' }}>
          <div className="kap-mono-tag mb-2" style={{ color: 'var(--kap-snow-4)' }}>
            ▶ {t('reader.sources')} · {resp.sources.length}
          </div>
          <ul className="space-y-1.5">
            {resp.sources.slice(0, 5).map((s, i) => (
              <li key={i} className="kap-mono-tag flex items-baseline gap-2"
                  style={{ color: 'var(--kap-snow-3)', letterSpacing: '0.06em' }}>
                <span style={{ color: 'var(--kap-frost)' }}>#{String(i + 1).padStart(2, '0')}</span>
                <span>{s.title || s.doc_id}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </KapCard>
  );
}
