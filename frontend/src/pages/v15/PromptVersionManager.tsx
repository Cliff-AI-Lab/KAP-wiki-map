/**
 * PromptVersionManager — Prompt 版本管理 UI（M18 #3）。
 *
 * 后端在位：
 *   GET    /observability/prompt-versions          M11 #4
 *   POST   /observability/prompt-versions          M11 #4 + M12 #1 + M15 #3
 *   POST   /prompt-versions/{id}/deactivate        M11 #4
 *   GET    /prompt-versions/ab                     M11 #4 + M12 #1
 *   POST   /prompt-versions/auto-tune              M16 #2
 *
 * 三块：
 *   1. 顶部过滤（condition_type / language）+ 操作（新建 / auto-tune）
 *   2. 版本列表（list / activate=true 高亮 / deactivate 按钮）
 *   3. AB 比较表（每版本 sample_size + approve_rate）
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Activity, CheckCircle2, Loader2, Play, Plus, RefreshCw, X,
} from 'lucide-react';

import {
  autoTunePrompt, createPromptVersion, deactivatePromptVersion,
  fetchPromptABScores, fetchPromptVersions,
  type AutoTuneResult, type ConditionType,
  type PromptABScore, type PromptVersion,
} from '@/services/observabilityApi';
import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';

const CONDITIONS: ConditionType[] = [
  'new_entity_type',
  'relation_solidification',
  'relation_split',
  'standard_upgrade',
];
const LANGUAGES = ['zh', 'en'];


export default function PromptVersionManager() {
  const { t } = useLocale();

  const [conditionFilter, setConditionFilter] = useState<ConditionType | ''>('');
  const [languageFilter, setLanguageFilter] = useState<string>('');
  const [tab, setTab] = useState<'list' | 'ab' | 'diff'>('list');
  const [diffLeftId, setDiffLeftId] = useState<string>('');
  const [diffRightId, setDiffRightId] = useState<string>('');

  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [abScores, setAbScores] = useState<PromptABScore[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [autoTuneResult, setAutoTuneResult] = useState<AutoTuneResult | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [vs, ab] = await Promise.all([
        fetchPromptVersions({
          conditionType: conditionFilter || undefined,
          language: languageFilter || undefined,
        }),
        fetchPromptABScores({
          conditionType: conditionFilter || undefined,
        }),
      ]);
      setVersions(vs);
      setAbScores(ab);
    } catch (e) {
      setError((e as Error).message || 'load failed');
    } finally {
      setLoading(false);
    }
  }, [conditionFilter, languageFilter]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const onDeactivate = async (versionId: string) => {
    if (!window.confirm(t('pv.confirmDeactivate', { id: versionId }))) return;
    try {
      await deactivatePromptVersion(versionId);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onAutoTune = async () => {
    if (!conditionFilter) {
      setError('请先选择 condition_type');
      return;
    }
    try {
      const result = await autoTunePrompt({
        condition_type: conditionFilter,
        language: languageFilter || 'zh',
      });
      setAutoTuneResult(result);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary">
            {t('pv.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">{t('pv.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={loadAll}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-btn border border-th-border px-3 py-1.5 text-sm text-th-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('observ.refresh')}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-card border border-rose-500/40 bg-rose-50/40 text-rose-700 text-sm">
          {error}
        </div>
      )}

      {autoTuneResult && (
        <AutoTuneBanner
          result={autoTuneResult}
          onDismiss={() => setAutoTuneResult(null)}
          t={t}
        />
      )}

      {/* 过滤 + 操作 */}
      <div className="flex flex-wrap items-center gap-3 mb-4 p-3 bg-th-bg-subtle rounded-card border border-th-border">
        <label className="flex items-center gap-2 text-xs text-th-text-muted">
          {t('pv.filterCondition')}
          <select
            value={conditionFilter}
            onChange={e => setConditionFilter(e.target.value as ConditionType | '')}
            className="px-2 py-1 rounded-btn border border-th-border bg-elevated text-sm font-mono"
          >
            <option value="">{t('pv.filterAll')}</option>
            {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-th-text-muted">
          {t('pv.filterLanguage')}
          <select
            value={languageFilter}
            onChange={e => setLanguageFilter(e.target.value)}
            className="px-2 py-1 rounded-btn border border-th-border bg-elevated text-sm font-mono"
          >
            <option value="">{t('pv.filterAll')}</option>
            {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowCreate(v => !v)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn bg-accent text-white text-sm hover:bg-accent/90"
          >
            <Plus size={14} />
            {t('pv.create')}
          </button>
          <button
            type="button"
            onClick={onAutoTune}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn border border-accent text-accent text-sm hover:bg-accent/10"
          >
            <Play size={14} />
            {t('pv.autoTune')}
          </button>
        </div>
      </div>

      {showCreate && (
        <CreateForm
          defaultCondition={conditionFilter || 'new_entity_type'}
          defaultLanguage={languageFilter || 'zh'}
          onCancel={() => setShowCreate(false)}
          onCreated={async () => {
            setShowCreate(false);
            await loadAll();
          }}
          onError={msg => setError(msg)}
          t={t}
        />
      )}

      {/* tabs */}
      <div className="flex border-b border-th-border mb-4 text-sm">
        <button
          type="button"
          onClick={() => setTab('list')}
          className={`px-4 py-2 -mb-px border-b-2 ${
            tab === 'list'
              ? 'border-accent text-accent'
              : 'border-transparent text-th-text-muted hover:text-th-text-primary'
          }`}
        >
          {t('pv.tabList')}
        </button>
        <button
          type="button"
          onClick={() => setTab('ab')}
          className={`px-4 py-2 -mb-px border-b-2 ${
            tab === 'ab'
              ? 'border-accent text-accent'
              : 'border-transparent text-th-text-muted hover:text-th-text-primary'
          }`}
        >
          {t('pv.tabAB')}
        </button>
        <button
          type="button"
          onClick={() => setTab('diff')}
          className={`px-4 py-2 -mb-px border-b-2 ${
            tab === 'diff'
              ? 'border-accent text-accent'
              : 'border-transparent text-th-text-muted hover:text-th-text-primary'
          }`}
        >
          {t('pv.tabDiff')}
        </button>
      </div>

      {tab === 'list' && (
        <VersionList versions={versions} onDeactivate={onDeactivate} t={t} />
      )}
      {tab === 'ab' && <ABTable scores={abScores} t={t} />}
      {tab === 'diff' && (
        <DiffView
          versions={versions}
          leftId={diffLeftId} rightId={diffRightId}
          onChangeLeft={setDiffLeftId}
          onChangeRight={setDiffRightId}
          t={t}
        />
      )}
    </div>
  );
}


function AutoTuneBanner({
  result, onDismiss, t,
}: {
  result: AutoTuneResult;
  onDismiss: () => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const isAction = result.action !== 'noop';
  return (
    <div
      className={`mb-4 p-3 rounded-card border flex items-start gap-3 text-sm ${
        isAction
          ? 'border-emerald-500/40 bg-emerald-50/40 text-emerald-800'
          : 'border-th-border bg-th-bg-subtle text-th-text-muted'
      }`}
    >
      {isAction ? <CheckCircle2 size={16} /> : <Activity size={16} />}
      <div className="flex-1">
        <div className="font-medium">
          {isAction
            ? t('pv.autoTuneAction', { action: result.action })
            : t('pv.autoTuneNoop')}
        </div>
        <div className="text-xs mt-1">
          {t('pv.autoTuneReason')}: {result.reason}
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-th-text-muted hover:text-th-text-primary"
      >
        <X size={14} />
      </button>
    </div>
  );
}


function VersionList({
  versions, onDeactivate, t,
}: {
  versions: PromptVersion[];
  onDeactivate: (id: string) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  if (versions.length === 0) {
    return (
      <div className="p-6 text-center text-th-text-muted text-sm rounded-card border border-th-border">
        {t('pv.empty')}
      </div>
    );
  }
  return (
    <div className="rounded-card border border-th-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-th-bg-subtle text-th-text-muted text-xs">
          <tr>
            <th className="text-left p-2 font-mono">{t('pv.col.versionId')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.condition')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.language')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.activatedAt')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.status')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.note')}</th>
            <th className="text-right p-2 font-mono">{t('pv.col.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {versions.map(v => {
            const isActive = v.deactivated_at == null;
            return (
              <tr
                key={v.version_id}
                className={`border-t border-th-border ${
                  isActive ? 'bg-emerald-50/30' : ''
                }`}
              >
                <td className="p-2 font-mono text-xs">{v.version_id}</td>
                <td className="p-2 text-xs">{v.condition_type}</td>
                <td className="p-2 text-xs">{v.language}</td>
                <td className="p-2 text-xs text-th-text-muted">
                  {new Date(v.activated_at).toLocaleString()}
                </td>
                <td className="p-2 text-xs">
                  {isActive ? (
                    <span className="text-emerald-700 font-medium">
                      {t('pv.statusActive')}
                    </span>
                  ) : (
                    <span className="text-th-text-muted">
                      {t('pv.statusInactive')}
                    </span>
                  )}
                </td>
                <td className="p-2 text-xs text-th-text-muted">{v.note || '—'}</td>
                <td className="p-2 text-right">
                  {isActive && (
                    <button
                      type="button"
                      onClick={() => onDeactivate(v.version_id)}
                      className="px-2 py-1 rounded-btn border border-rose-400 text-rose-600 text-xs hover:bg-rose-50"
                    >
                      {t('pv.deactivate')}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


function ABTable({
  scores, t,
}: {
  scores: PromptABScore[];
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  if (scores.length === 0) {
    return (
      <div className="p-6 text-center text-th-text-muted text-sm rounded-card border border-th-border">
        {t('observ.empty')}
      </div>
    );
  }
  return (
    <div className="rounded-card border border-th-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-th-bg-subtle text-th-text-muted text-xs">
          <tr>
            <th className="text-left p-2 font-mono">{t('pv.col.versionId')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.condition')}</th>
            <th className="text-left p-2 font-mono">{t('pv.col.status')}</th>
            <th className="text-right p-2 font-mono">{t('pv.col.sampleSize')}</th>
            <th className="text-right p-2 font-mono">{t('pv.col.approveRate')}</th>
          </tr>
        </thead>
        <tbody>
          {scores.map(s => (
            <tr
              key={s.version_id}
              className={`border-t border-th-border ${
                s.is_active ? 'bg-emerald-50/30' : ''
              }`}
            >
              <td className="p-2 font-mono text-xs">{s.version_id}</td>
              <td className="p-2 text-xs">{s.condition_type}</td>
              <td className="p-2 text-xs">
                {s.is_active
                  ? <span className="text-emerald-700">{t('pv.statusActive')}</span>
                  : <span className="text-th-text-muted">{t('pv.statusInactive')}</span>
                }
              </td>
              <td className="p-2 text-xs text-right tabular-nums">{s.sample_size}</td>
              <td className="p-2 text-xs text-right tabular-nums font-medium">
                {(s.approve_rate * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════
//  M19 #3 · 版本对比 (DiffView)
// ════════════════════════════════════════════════════════════════════════

type DiffLine = { kind: 'common' | 'added' | 'removed'; text: string };

/** 简化 LCS 行级 diff（O(n*m)，足够 system_prompt 几十行）。*/
function computeLineDiff(left: string, right: string): DiffLine[] {
  const a = left.split('\n');
  const b = right.split('\n');
  const m = a.length;
  const n = b.length;
  // dp[i][j] = LCS length
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    Array(n + 1).fill(0),
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
      else dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = m, j = n;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      out.push({ kind: 'common', text: a[i - 1] });
      i--; j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      out.push({ kind: 'removed', text: a[i - 1] });
      i--;
    } else {
      out.push({ kind: 'added', text: b[j - 1] });
      j--;
    }
  }
  while (i > 0) { out.push({ kind: 'removed', text: a[i - 1] }); i--; }
  while (j > 0) { out.push({ kind: 'added', text: b[j - 1] }); j--; }
  return out.reverse();
}


function DiffView({
  versions, leftId, rightId, onChangeLeft, onChangeRight, t,
}: {
  versions: PromptVersion[];
  leftId: string; rightId: string;
  onChangeLeft: (id: string) => void;
  onChangeRight: (id: string) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const left = versions.find(v => v.version_id === leftId);
  const right = versions.find(v => v.version_id === rightId);

  const diff = left && right
    ? computeLineDiff(left.system_prompt, right.system_prompt)
    : [];
  const added = diff.filter(d => d.kind === 'added').length;
  const removed = diff.filter(d => d.kind === 'removed').length;
  const noChanges = left && right && added === 0 && removed === 0;

  return (
    <div className="rounded-card border border-th-border p-4 bg-elevated space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-th-text-muted">
          {t('pv.diffSelectLeft')}
          <select
            value={leftId}
            onChange={e => onChangeLeft(e.target.value)}
            className="px-2 py-1 rounded-btn border border-th-border font-mono text-sm"
          >
            <option value="">—</option>
            {versions.map(v => (
              <option key={v.version_id} value={v.version_id}>
                {v.version_id} · {v.condition_type} · {v.language}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-th-text-muted">
          {t('pv.diffSelectRight')}
          <select
            value={rightId}
            onChange={e => onChangeRight(e.target.value)}
            className="px-2 py-1 rounded-btn border border-th-border font-mono text-sm"
          >
            <option value="">—</option>
            {versions.map(v => (
              <option key={v.version_id} value={v.version_id}>
                {v.version_id} · {v.condition_type} · {v.language}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!left || !right ? (
        <div className="p-6 text-center text-th-text-muted text-sm">
          {t('pv.diffEmpty')}
        </div>
      ) : noChanges ? (
        <div className="p-6 text-center text-th-text-muted text-sm">
          {t('pv.diffNoChanges')}
        </div>
      ) : (
        <>
          <div className="text-xs text-th-text-muted">
            {t('pv.diffStats', { added, removed })}
          </div>
          <div className="rounded-card border border-th-border bg-th-bg-subtle font-mono text-xs overflow-x-auto">
            {diff.map((line, idx) => (
              <div
                key={idx}
                className={`px-2 py-0.5 whitespace-pre ${
                  line.kind === 'added'
                    ? 'bg-emerald-50/60 text-emerald-800'
                    : line.kind === 'removed'
                    ? 'bg-rose-50/60 text-rose-800'
                    : ''
                }`}
              >
                <span className="inline-block w-4 select-none text-th-text-muted">
                  {line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : ' '}
                </span>
                {line.text || ' '}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export { computeLineDiff };


function CreateForm({
  defaultCondition, defaultLanguage,
  onCancel, onCreated, onError, t,
}: {
  defaultCondition: ConditionType;
  defaultLanguage: string;
  onCancel: () => void;
  onCreated: () => void;
  onError: (msg: string) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
}) {
  const [condition, setCondition] = useState<ConditionType>(defaultCondition);
  const [language, setLanguage] = useState(defaultLanguage);
  const [excerpt, setExcerpt] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await createPromptVersion({
        condition_type: condition,
        language,
        prompt_text_excerpt: excerpt,
        system_prompt: systemPrompt,
        note,
      });
      onCreated();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="mb-4 p-4 rounded-card border border-accent/40 bg-elevated grid grid-cols-2 gap-3 text-sm"
    >
      <label className="flex flex-col gap-1">
        <span className="text-xs text-th-text-muted">{t('pv.col.condition')}</span>
        <select
          value={condition}
          onChange={e => setCondition(e.target.value as ConditionType)}
          className="px-2 py-1 rounded-btn border border-th-border font-mono"
        >
          {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-th-text-muted">{t('pv.col.language')}</span>
        <select
          value={language}
          onChange={e => setLanguage(e.target.value)}
          className="px-2 py-1 rounded-btn border border-th-border font-mono"
        >
          {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </label>
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-th-text-muted">prompt_text_excerpt</span>
        <input
          value={excerpt}
          onChange={e => setExcerpt(e.target.value)}
          maxLength={200}
          className="px-2 py-1 rounded-btn border border-th-border"
        />
      </label>
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-th-text-muted">system_prompt</span>
        <textarea
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          maxLength={8000}
          rows={4}
          className="px-2 py-1 rounded-btn border border-th-border font-mono text-xs"
        />
      </label>
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-th-text-muted">{t('pv.col.note')}</span>
        <input
          value={note}
          onChange={e => setNote(e.target.value)}
          maxLength={200}
          className="px-2 py-1 rounded-btn border border-th-border"
        />
      </label>
      <div className="col-span-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-btn border border-th-border text-sm"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="px-3 py-1.5 rounded-btn bg-accent text-white text-sm disabled:opacity-40"
        >
          {submitting ? '...' : t('pv.create')}
        </button>
      </div>
    </form>
  );
}
