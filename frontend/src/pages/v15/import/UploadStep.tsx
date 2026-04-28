/**
 * UploadStep — 第 1 步: 上传文档 (Nord 风, 借鉴 V14 UploadPage 但完全重做)
 *
 * 提供 3 个核心入口:
 *   • 灌入 Demo 数据 (一键 30 篇国标文档, 用于演示)
 *   • 本地文件上传 (拖拽/点击)
 *   • 飞书/钉钉/企微 (mock 模式提示)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileText, Loader2, Check, AlertTriangle,
  Building2, FileUp, ArrowRight, RefreshCw, Boxes,
} from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';
import { fetchDocuments, ingestDemo, ingestFiles, type DocumentSummary } from '@/services/api';

const SOURCE_PRESETS = [
  { key: 'feishu',   label: '飞书',     hint: '云文档 / 企业知识库 (Mock)', icon: '飞' },
  { key: 'dingtalk', label: '钉钉',     hint: '智能文档 (Mock)',            icon: '钉' },
  { key: 'wecom',    label: '企业微信', hint: '微盘 (Mock)',                icon: '企' },
];

export default function UploadStep() {
  const { projectId } = useActiveProject();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [demoIngesting, setDemoIngesting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setLoadingDocs(true);
    try {
      const r = await fetchDocuments({ projectId, page: 1, page_size: 50 });
      setDocs(r.documents);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingDocs(false);
    }
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  async function handleDemo() {
    if (!projectId) return;
    setDemoIngesting(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await ingestDemo(projectId, true);
      setSuccess(`已导入内置知识包 · ${r.message ?? r.status}`);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDemoIngesting(false);
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0 || !projectId) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await ingestFiles(Array.from(files), projectId);
      setSuccess(`已上传 ${files.length} 个文件 · ${r.message ?? r.status}`);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  const goNext = () => navigate('/v15/manage/import/review');

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="v15-display text-xl text-th-text-primary">第 1 步 · 上传文档</h2>
          <p className="text-xs text-th-text-muted mt-1">
            选一种方式把原始资料喂给系统 — 系统会自动去噪 + LLM 蒸馏 + 编译 Wiki
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] v15-mono text-th-text-muted">
          <span>已入库 <span className="text-th-text-primary">{docs.length}</span> 篇</span>
          <button
            onClick={reload}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-btn border border-th-border hover:border-th-border-hover"
          >
            <RefreshCw size={11} /> 刷新
          </button>
        </div>
      </div>

      {/* 三种来源 */}
      <div className="grid grid-cols-3 gap-3">
        {/* Demo 一键灌入 */}
        <button
          onClick={handleDemo}
          disabled={demoIngesting || !projectId}
          className="group rounded-card border border-accent/40 bg-accent/5 p-4 text-left hover:bg-accent/10 disabled:opacity-50 transition"
        >
          <div className="flex items-center gap-2 mb-2">
            <Boxes size={16} className="text-accent" />
            <span className="text-sm font-semibold text-th-text-primary">内置行业知识包</span>
            {demoIngesting && <Loader2 size={12} className="animate-spin text-accent ml-auto" />}
          </div>
          <p className="text-xs text-th-text-muted leading-relaxed">
            30 篇 GB/AQ/SY/T 国标 + 飞书/钉钉/企微样例 · 真 LLM 抽取实体关系 · ≈ 20 分钟
          </p>
          <div className="mt-3 text-[11px] v15-mono text-accent flex items-center gap-1">
            一键导入 <ArrowRight size={11} />
          </div>
        </button>

        {/* 本地拖拽 */}
        <label
          className={`rounded-card border-2 border-dashed p-4 text-left cursor-pointer hover:bg-hover transition ${
            uploading ? 'border-accent bg-accent/5' : 'border-th-border'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".txt,.md,.pdf,.docx,.html"
            onChange={(e) => handleFiles(e.target.files)}
          />
          <div className="flex items-center gap-2 mb-2">
            <FileUp size={16} className="text-th-text-secondary" />
            <span className="text-sm font-semibold text-th-text-primary">本地文件</span>
            {uploading && <Loader2 size={12} className="animate-spin text-accent ml-auto" />}
          </div>
          <p className="text-xs text-th-text-muted leading-relaxed">
            点击或拖拽 · 支持 .txt .md .pdf .docx .html
          </p>
          <div className="mt-3 text-[11px] v15-mono text-th-text-secondary flex items-center gap-1">
            选择文件 <ArrowRight size={11} />
          </div>
        </label>

        {/* 三大平台 */}
        <div className="rounded-card border border-th-border bg-elevated p-4">
          <div className="flex items-center gap-2 mb-2">
            <Building2 size={16} className="text-th-text-secondary" />
            <span className="text-sm font-semibold text-th-text-primary">企业平台</span>
          </div>
          <div className="space-y-1.5">
            {SOURCE_PRESETS.map((s) => (
              <div
                key={s.key}
                className="flex items-center gap-2 px-2 py-1.5 rounded text-xs hover:bg-hover transition"
              >
                <span className="w-5 h-5 rounded grid place-items-center text-[10px] font-bold text-[color:var(--color-bg-base)] bg-th-text-muted">
                  {s.icon}
                </span>
                <span className="text-th-text-secondary">{s.label}</span>
                <span className="text-[10px] text-th-text-muted ml-auto">{s.hint}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-th-text-muted mt-3">
            生产配置: 在设置里填 App ID / Secret 后由后端定时同步
          </p>
        </div>
      </div>

      {/* 提示 */}
      {error && (
        <div className="rounded-btn border border-th-error/40 bg-th-error/5 p-3 text-sm text-th-error flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
        </div>
      )}
      {success && (
        <div className="rounded-btn border border-th-success/40 bg-th-success/5 p-3 text-sm text-th-success flex items-start gap-2">
          <Check size={14} className="shrink-0 mt-0.5" /> {success}
        </div>
      )}

      {/* 已入库文档列表 */}
      <div className="rounded-card border border-th-border bg-elevated/60">
        <div className="flex items-center justify-between px-4 py-3 border-b border-th-border">
          <div className="text-sm font-semibold text-th-text-primary flex items-center gap-2">
            <FileText size={14} className="text-accent" /> 已入库文档
            {loadingDocs && <Loader2 size={11} className="animate-spin text-th-text-muted" />}
          </div>
          {docs.length > 0 && (
            <button
              onClick={goNext}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent text-[color:var(--color-bg-base)] text-xs font-medium hover:brightness-95"
            >
              进入第 2 步 · 去噪审核 <ArrowRight size={12} />
            </button>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto">
          {docs.length === 0 ? (
            <div className="text-xs text-th-text-muted text-center py-10">
              {loadingDocs ? '加载中...' : '暂无文档 — 点上方任一来源开始灌入'}
            </div>
          ) : (
            docs.map((d) => (
              <div
                key={d.id}
                className="flex items-center gap-3 px-4 py-2 border-b border-th-border/50 last:border-b-0 hover:bg-hover/40"
              >
                <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: decisionColor(d.decision) }} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-th-text-primary truncate">{d.title}</div>
                  <div className="text-[10px] text-th-text-muted v15-mono mt-0.5">
                    {d.id} · {d.source_system} · {d.doc_type} · {d.decision}
                  </div>
                </div>
                <Link
                  to={`/v15/read/wiki/src/${encodeURIComponent(d.id)}`}
                  className="text-[11px] text-th-text-muted hover:text-accent v15-mono"
                >
                  查看 →
                </Link>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function decisionColor(d: string): string {
  switch (d) {
    case 'KEEP':    return '#a3be8c';
    case 'ARCHIVE': return '#ebcb8b';
    case 'DISCARD': return '#bf616a';
    default:        return '#a3b1c4';
  }
}
