/**
 * GroundTruthReview — Ground truth 候选审批页（M11 #3）。
 *
 * 工作流：
 *   1. 拉 GET /observability/ground-truth/auto-construct 取候选列表
 *   2. SME 在每个候选上 inline-edit expected_doc_ids（基于 proposed_doc_ids）
 *   3. Confirm → POST /observability/ground-truth 入库（候选行从列表移除）
 *   4. Skip → 本地隐藏，不入库
 *   5. 旁边显示已入库的 GroundTruthQuery 列表（可删除）
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Check, X, Loader2, Plus, Trash2, RefreshCw, ListChecks, Sparkles,
} from 'lucide-react';

import {
  fetchGroundTruthCandidates,
  fetchGroundTruthList,
  addGroundTruth,
  deleteGroundTruth,
  type GroundTruthCandidate,
  type GroundTruthQuery,
} from '@/services/observabilityApi';
import { useActiveProject } from '@/hooks/useActiveProject';
import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';

interface DraftCandidate extends GroundTruthCandidate {
  draftDocIds: string;   // 文本框内容（逗号分隔），允许 SME 修改
  note: string;
  saving: boolean;
  hidden: boolean;
}

function CandidateCard({
  draft, onConfirm, onSkip, onChange,
}: {
  draft: DraftCandidate;
  onConfirm: () => void;
  onSkip: () => void;
  onChange: (patch: Partial<DraftCandidate>) => void;
}) {
  return (
    <div className="rounded-card border border-th-border p-4 bg-elevated hover:shadow-card-hover transition">
      <div className="flex items-start gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-th-text-muted">
              {draft.project_id || '（无 project）'}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent">
              useful_rate {(draft.useful_rate * 100).toFixed(0)}%
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-th-border text-th-text-muted">
              {draft.sample_size} 样本
            </span>
          </div>
          <p className="text-sm text-th-text-primary font-medium">
            {draft.query_text}
          </p>
          <p className="text-xs text-th-text-muted mt-1">{draft.reasoning}</p>
        </div>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-th-text-muted">
          expected_doc_ids（逗号分隔；M11 #1 自动算交集预填）
        </label>
        <textarea
          value={draft.draftDocIds}
          onChange={(e) => onChange({ draftDocIds: e.target.value })}
          rows={2}
          placeholder="doc1, doc2, doc3"
          className="w-full text-xs font-mono px-2 py-1 rounded border border-th-border bg-elevated focus:outline-none focus:border-accent"
        />

        <label className="block text-xs text-th-text-muted">备注（可选）</label>
        <input
          type="text"
          value={draft.note}
          onChange={(e) => onChange({ note: e.target.value })}
          maxLength={200}
          placeholder="审批备注..."
          className="w-full text-xs px-2 py-1 rounded border border-th-border bg-elevated focus:outline-none focus:border-accent"
        />
      </div>

      <div className="flex items-center justify-end gap-2 mt-3">
        <button
          type="button"
          onClick={onSkip}
          disabled={draft.saving}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-btn text-xs font-medium border border-th-border text-th-text-secondary hover:bg-hover transition disabled:opacity-40"
        >
          <X size={12} /> 跳过
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={draft.saving || draft.draftDocIds.trim() === ''}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-btn text-xs font-medium border border-emerald-500/40 text-emerald-700 hover:bg-emerald-500/10 transition disabled:opacity-40"
        >
          {draft.saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          {draft.saving ? '保存中' : '确认入库'}
        </button>
      </div>
    </div>
  );
}

function ExistingGtRow({
  gt, onDelete,
}: {
  gt: GroundTruthQuery;
  onDelete: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-start gap-2 py-2 border-t border-th-border first:border-t-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm text-th-text-primary truncate">
          {gt.query_text}
        </div>
        <div className="text-xs text-th-text-muted truncate font-mono">
          {gt.expected_doc_ids.length} doc(s):{' '}
          {gt.expected_doc_ids.slice(0, 3).join(', ')}
          {gt.expected_doc_ids.length > 3 && '...'}
        </div>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onDelete();
          } finally {
            setBusy(false);
          }
        }}
        className="text-th-text-muted hover:text-rose-600 transition disabled:opacity-40"
        title="删除"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
      </button>
    </div>
  );
}

export default function GroundTruthReview() {
  const { projectId: activeProjectId } = useActiveProject();
  const { t } = useLocale();
  const projectId = activeProjectId || undefined;

  const [drafts, setDrafts] = useState<DraftCandidate[]>([]);
  const [existing, setExisting] = useState<GroundTruthQuery[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState<string | null>(null);

  // 配置：阈值
  const [minUseful, setMinUseful] = useState(0.8);
  const [minSamples, setMinSamples] = useState(2);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [candRes, gtRes] = await Promise.all([
        fetchGroundTruthCandidates({
          projectId, minUsefulRate: minUseful, minSamples,
          maxResults: 50,
        }),
        fetchGroundTruthList(projectId),
      ]);
      setDrafts(candRes.map(c => ({
        ...c,
        draftDocIds: c.proposed_doc_ids.join(', '),
        note: '',
        saving: false,
        hidden: false,
      })));
      setExisting(gtRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, minUseful, minSamples]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const updateDraft = (idx: number, patch: Partial<DraftCandidate>) => {
    setDrafts(prev => prev.map((d, i) => (i === idx ? { ...d, ...patch } : d)));
  };

  const handleConfirm = async (idx: number) => {
    const draft = drafts[idx];
    if (!draft) return;
    const docIds = draft.draftDocIds
      .split(',').map(s => s.trim()).filter(Boolean);
    if (docIds.length === 0) return;

    updateDraft(idx, { saving: true });
    try {
      const gt = await addGroundTruth({
        project_id: draft.project_id,
        query_text: draft.query_text,
        expected_doc_ids: docIds,
        note: draft.note,
      });
      setExisting(prev => [gt, ...prev]);
      updateDraft(idx, { hidden: true, saving: false });
      setSavedFlash(`入库成功：${draft.query_text.slice(0, 30)}`);
      setTimeout(() => setSavedFlash(null), 2500);
    } catch (e) {
      updateDraft(idx, { saving: false });
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSkip = (idx: number) => {
    updateDraft(idx, { hidden: true });
  };

  const handleDelete = async (gtId: string) => {
    try {
      await deleteGroundTruth(gtId);
      setExisting(prev => prev.filter(g => g.gt_id !== gtId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const visibleDrafts = drafts.filter(d => !d.hidden);

  return (
    <div className="p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-th-text-primary flex items-center gap-2">
            <Sparkles size={20} className="text-accent" />
            {t('gtreview.title')}
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            {t('gtreview.subtitleClean')}
            {projectId && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-mono">
                {projectId}
              </span>
            )}
          </p>
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

      {/* 阈值控件 */}
      <div className="flex items-center gap-4 mb-4 p-3 rounded-card bg-elevated border border-th-border">
        <label className="text-xs text-th-text-muted flex items-center gap-2">
          min useful_rate:
          <input
            type="number"
            step="0.05" min="0" max="1"
            value={minUseful}
            onChange={(e) => setMinUseful(Number(e.target.value))}
            className="w-16 text-xs px-2 py-1 rounded border border-th-border bg-elevated focus:outline-none focus:border-accent"
          />
        </label>
        <label className="text-xs text-th-text-muted flex items-center gap-2">
          min samples:
          <input
            type="number"
            step="1" min="1" max="100"
            value={minSamples}
            onChange={(e) => setMinSamples(Number(e.target.value))}
            className="w-16 text-xs px-2 py-1 rounded border border-th-border bg-elevated focus:outline-none focus:border-accent"
          />
        </label>
        <span className="ml-auto text-xs text-th-text-muted">
          {visibleDrafts.length} 待审批 · {existing.length} 已入库
        </span>
      </div>

      {savedFlash && (
        <div className="mb-3 p-2 rounded text-xs bg-emerald-500/10 text-emerald-700 border border-emerald-500/40">
          <Check size={12} className="inline mr-1" /> {savedFlash}
        </div>
      )}
      {error && (
        <div className="mb-3 p-2 rounded text-xs bg-rose-500/10 text-rose-700 border border-rose-500/40">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 左 2/3：候选列表 */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-mono text-th-text-muted flex items-center gap-2">
            <Plus size={14} /> {t('gtreview.candidates')}
          </h2>
          {loading && drafts.length === 0 && (
            <div className="text-xs text-th-text-muted py-6 text-center">
              <Loader2 size={14} className="inline animate-spin mr-2" /> {t('observ.loading')}
            </div>
          )}
          {!loading && visibleDrafts.length === 0 && (
            <div className="text-xs text-th-text-muted py-6 text-center border border-dashed border-th-border rounded-card">
              {t('gtreview.empty')}（useful_rate ≥ {minUseful}, samples ≥ {minSamples}）
            </div>
          )}
          {visibleDrafts.map((draft, vIdx) => {
            const realIdx = drafts.findIndex(d => d.candidate_id === draft.candidate_id);
            return (
              <CandidateCard
                key={draft.candidate_id || vIdx}
                draft={draft}
                onConfirm={() => handleConfirm(realIdx)}
                onSkip={() => handleSkip(realIdx)}
                onChange={(patch) => updateDraft(realIdx, patch)}
              />
            );
          })}
        </div>

        {/* 右 1/3：已入库 */}
        <div>
          <h2 className="text-sm font-mono text-th-text-muted flex items-center gap-2 mb-3">
            <ListChecks size={14} /> 已入库 ({existing.length})
          </h2>
          <div className="rounded-card border border-th-border bg-elevated p-3 max-h-[600px] overflow-y-auto">
            {existing.length === 0 && (
              <div className="text-xs text-th-text-muted py-3 text-center">
                尚无 ground truth
              </div>
            )}
            {existing.map(gt => (
              <ExistingGtRow
                key={gt.gt_id}
                gt={gt}
                onDelete={() => handleDelete(gt.gt_id)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
