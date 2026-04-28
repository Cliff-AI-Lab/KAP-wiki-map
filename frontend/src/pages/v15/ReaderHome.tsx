/**
 * ReaderHome — 消费模式首页（Phase B: 接真实 API）
 *
 * 设计：
 *   - 顶部标题 + 项目选择器（全局入口自动选中首个项目）
 *   - 搜索框 → askQuestion → 答案卡（路由徽章 / 耗时 / Markdown / 溯源）
 *   - 三卡片：热门Wiki / 知识地图 / 最近问答（本地历史）
 *
 * 睿动 glm-5.1 驱动后端 call_llm，前端只经 /api/v1/qa/ask 代理。
 */
import { useEffect, useState, type FormEvent } from 'react';
import { Search, Clock, FileText, ChevronDown } from 'lucide-react';
import { Link } from 'react-router-dom';
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

const RECENT_KEY = 'wikimap-recent-questions';
const MAX_RECENT = 5;

function loadRecent(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function saveRecent(q: string): string[] {
  const prev = loadRecent().filter((x) => x !== q);
  const next = [q, ...prev].slice(0, MAX_RECENT);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  return next;
}

function RouteBadge({ path }: { path?: string }) {
  const { t } = useLocale();
  if (!path) return null;
  const label: Record<string, string> = {
    wiki: t('reader.routeWiki'),
    rag: t('reader.routeRag'),
    hybrid: t('reader.routeHybrid'),
  };
  return (
    <span className="px-2 py-0.5 rounded-pill text-xs font-mono bg-hover text-accent-secondary border border-th-border">
      {label[path] ?? path}
    </span>
  );
}

function AnswerCard({ resp, q }: { resp: QAResponse; q: string }) {
  const { t } = useLocale();
  const [expandedSources, setExpandedSources] = useState(false);
  return (
    <div className="rounded-card border border-th-border bg-elevated p-5 space-y-4">
      <div className="flex items-center gap-2 text-xs text-th-text-muted">
        <RouteBadge path={resp.route_path} />
        {resp.latency_ms !== undefined && (
          <span className="flex items-center gap-1 font-mono">
            <Clock size={11} /> {resp.latency_ms} ms
          </span>
        )}
        {resp.routed_domains && resp.routed_domains.length > 0 && (
          <span className="font-mono">· 域: {resp.routed_domains.slice(0, 3).join(', ')}</span>
        )}
      </div>

      <div className="text-xs text-th-text-muted font-mono">Q: {q}</div>

      <div className="text-th-text-primary prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{resp.answer}</ReactMarkdown>
      </div>

      {resp.sources && resp.sources.length > 0 && (
        <div className="pt-3 border-t border-th-border">
          <button
            type="button"
            onClick={() => setExpandedSources((v) => !v)}
            className="flex items-center gap-2 text-xs text-th-text-muted hover:text-th-text-primary"
          >
            <ChevronDown
              size={14}
              style={{
                transform: expandedSources ? 'rotate(0)' : 'rotate(-90deg)',
                transition: 'transform 150ms',
              }}
            />
            <FileText size={12} />
            {t('reader.sources')} · {resp.sources.length}
          </button>
          {expandedSources && (
            <ul className="mt-3 space-y-2">
              {resp.sources.map((s, i) => (
                <li key={`${s.doc_id}-${i}`} className="text-xs flex items-start gap-2">
                  <span className="text-th-text-muted font-mono w-6 text-right">#{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-th-text-primary truncate">{s.title}</div>
                    <div className="text-th-text-muted truncate">{s.content}</div>
                  </div>
                  <span className="text-th-text-muted font-mono">{(s.score * 100).toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function WikiHotCard({ projectId }: { projectId: string }) {
  const { t } = useLocale();
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchWikiPages(projectId)
      .then((list) => {
        if (!cancelled) setPages(list.slice(0, 5));
      })
      .catch(() => {
        if (!cancelled) setPages([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <div className="rounded-card border border-th-border bg-elevated p-4 hover:shadow-card-hover transition-shadow">
      <div className="text-xs uppercase tracking-wider text-th-text-muted mb-3">{t('reader.cardHotWiki')}</div>
      {loading ? (
        <div className="text-xs text-th-text-muted">...</div>
      ) : pages.length === 0 ? (
        <div className="text-xs text-th-text-muted">{t('reader.emptyWiki')}</div>
      ) : (
        <ul className="space-y-2 text-sm text-th-text-primary">
          {pages.map((p) => (
            <li key={p.page_id}>
              <Link
                to={`/v15/wiki/${encodeURI(p.page_id)}`}
                className="flex items-center gap-2 truncate hover:text-accent transition-colors"
              >
                <span className="w-1 h-1 rounded-full bg-accent opacity-60 shrink-0" />
                <span className="truncate">{p.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DomainMapCard({ projectId }: { projectId: string }) {
  const { t } = useLocale();
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDomains(projectId)
      .then((r) => {
        if (!cancelled) {
          // 取前 5 个有文档的域
          const top = r.domains
            .filter((d) => d.doc_count > 0)
            .sort((a, b) => b.doc_count - a.doc_count)
            .slice(0, 5);
          setDomains(top);
        }
      })
      .catch(() => {
        if (!cancelled) setDomains([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <div className="rounded-card border border-th-border bg-elevated p-4 hover:shadow-card-hover transition-shadow">
      <div className="text-xs uppercase tracking-wider text-th-text-muted mb-3">{t('reader.cardDomainMap')}</div>
      {loading ? (
        <div className="text-xs text-th-text-muted">...</div>
      ) : domains.length === 0 ? (
        <div className="text-xs text-th-text-muted">{t('reader.emptyDomain')}</div>
      ) : (
        <ul className="space-y-2 text-sm text-th-text-primary">
          {domains.map((d) => (
            <li key={d.domain_id} className="flex items-center gap-2 truncate">
              <span className="w-1 h-1 rounded-full bg-accent opacity-60 shrink-0" />
              <span className="truncate flex-1">{d.name}</span>
              <span className="text-xs text-th-text-muted font-mono">{d.doc_count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RecentCard({
  items,
  onPick,
}: {
  items: string[];
  onPick: (q: string) => void;
}) {
  const { t } = useLocale();
  return (
    <div className="rounded-card border border-th-border bg-elevated p-4 hover:shadow-card-hover transition-shadow">
      <div className="text-xs uppercase tracking-wider text-th-text-muted mb-3">{t('reader.cardRecent')}</div>
      {items.length === 0 ? (
        <div className="text-xs text-th-text-muted">{t('reader.emptyRecent')}</div>
      ) : (
        <ul className="space-y-2 text-sm">
          {items.map((q, i) => (
            <li key={`${i}-${q}`}>
              <button
                type="button"
                onClick={() => onPick(q)}
                className="flex items-center gap-2 truncate w-full text-left text-th-text-primary hover:text-accent"
              >
                <span className="w-1 h-1 rounded-full bg-accent opacity-60 shrink-0" />
                <span className="truncate">{q}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ReaderHome() {
  const { t } = useLocale();
  const { projectId, projects, loading: projectsLoading } = useActiveProject();

  const [query, setQuery] = useState('');
  const [answering, setAnswering] = useState(false);
  const [answer, setAnswer] = useState<{ resp: QAResponse; q: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>(() => loadRecent());

  async function doAsk(q: string) {
    if (!q.trim() || !projectId) return;
    setAnswering(true);
    setError(null);
    try {
      const resp = await askQuestion(q.trim(), 5, projectId);
      setAnswer({ resp, q });
      setRecent(saveRecent(q.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnswering(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    doAsk(query);
  }

  if (projectsLoading) {
    return <div className="text-sm text-th-text-muted">{t('reader.loadingProject')}</div>;
  }

  if (!projectId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-8 text-center">
        <div className="text-th-text-primary mb-2">{t('reader.emptyProject')}</div>
        <div className="text-sm text-th-text-muted">{t('reader.emptyProjectHint')}</div>
      </div>
    );
  }

  const currentProjectName = projects.find((p) => p.id === projectId)?.name ?? projectId;

  return (
    <div className="space-y-8">
      <div className="space-y-2 pt-4">
        <div className="v15-anim v15-stagger-1 text-[10px] v15-mono uppercase tracking-[0.3em] text-accent">
          Knowledge Atlas · Reader
        </div>
        <h1 className="v15-anim v15-stagger-2 v15-display text-5xl md:text-6xl text-th-text-primary">
          {t('reader.title')}
        </h1>
        <div className="v15-anim v15-stagger-3 v15-body-light text-sm text-th-text-muted v15-mono">
          · {currentProjectName}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="v15-anim v15-stagger-4 v15-glass p-4">
        <div className="flex items-center gap-3">
          <Search size={18} className="text-th-text-muted shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={answering}
            placeholder={t('reader.searchPlaceholder')}
            className="flex-1 bg-transparent outline-none text-th-text-primary placeholder:text-th-text-muted disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={answering || !query.trim()}
            className="v15-cta text-sm"
          >
            {answering ? t('reader.searching') : t('reader.searchBtn')}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-card border border-th-border bg-elevated p-4 text-sm text-th-error">
          {error}
        </div>
      )}

      {answer && <AnswerCard resp={answer.resp} q={answer.q} />}

      <div className="grid grid-cols-3 gap-4">
        <div className="v15-anim v15-stagger-5"><WikiHotCard projectId={projectId} /></div>
        <div className="v15-anim v15-stagger-5"><DomainMapCard projectId={projectId} /></div>
        <div className="v15-anim v15-stagger-6"><RecentCard items={recent} onPick={(q) => { setQuery(q); doAsk(q); }} /></div>
      </div>
    </div>
  );
}
