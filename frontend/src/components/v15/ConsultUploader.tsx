/**
 * ConsultUploader — 咨询中心 W2 工位文件上传（M21 #6）
 *
 * 支持：PDF / Word / Excel / Markdown / TXT
 * 调用：POST /api/v1/knowledge/ingest (multipart, 已存在的 API)
 * 完成后展示去噪结果（保留/归档/丢弃）— 与 W3 工位一致
 */
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import {
  Upload, FileText, Loader2, X, Check, AlertCircle,
  FileType2, Sheet, FileCode,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import { ingestFiles, type IngestResult } from '@/services/api';
import { KapCard } from '@/components/v15/CenterShell';

interface Props {
  projectId: string;
  onUploaded?: (result: IngestResult, files: File[]) => void;
}

const ACCEPT =
  '.pdf,.doc,.docx,.xls,.xlsx,.csv,.md,.markdown,.txt,.rtf,' +
  'application/pdf,' +
  'application/msword,' +
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document,' +
  'application/vnd.ms-excel,' +
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,' +
  'text/csv,text/markdown,text/plain';

const MAX_BYTES = 100 * 1024 * 1024;   // 100 MB / file


function fileIcon(name: string) {
  const ext = name.toLowerCase().split('.').pop() || '';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return Sheet;
  if (['doc', 'docx', 'rtf'].includes(ext)) return FileType2;
  if (['md', 'markdown'].includes(ext))     return FileCode;
  return FileText;
}

function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}


export default function ConsultUploader({ projectId, onUploaded }: Props) {
  const { t } = useLocale();
  const inputRef = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResult | null>(null);

  const addFiles = (incoming: FileList | File[]) => {
    setError(null);
    const next: File[] = [];
    for (const f of Array.from(incoming)) {
      if (f.size > MAX_BYTES) {
        setError(`${f.name} > 100MB`);
        continue;
      }
      next.push(f);
    }
    setFiles(prev => [...prev, ...next]);
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = '';
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
  };

  const removeAt = (i: number) => {
    setFiles(prev => prev.filter((_, idx) => idx !== i));
  };

  const upload = async () => {
    if (!files.length || uploading) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const r = await ingestFiles(files, projectId);
      setResult(r);
      onUploaded?.(r, files);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <KapCard
      eyebrow={`▶ ${t('consult.upload.title')}`}
      rightSlot={
        <span className="kap-badge">
          {files.length} files
        </span>
      }
    >
      {/* dropzone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className="cursor-pointer transition-all"
        style={{
          border: `1.5px dashed ${dragOver ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
          background: dragOver ? 'hsl(var(--primary) / 0.05)' : 'hsl(var(--muted) / 0.4)',
          borderRadius: 'calc(var(--radius) - 2px)',
          padding: '2rem 1rem',
          textAlign: 'center',
        }}
      >
        <Upload
          size={28}
          strokeWidth={1.5}
          className="mx-auto mb-2"
          style={{ color: dragOver ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))' }}
        />
        <div
          style={{
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            fontSize: 13.5,
            color: 'hsl(var(--foreground))',
          }}
        >
          {t('consult.upload.dragHint')}
        </div>
        <div
          className="kap-mono-tag mt-1.5"
          style={{ color: 'hsl(var(--muted-foreground))', letterSpacing: '0.06em' }}
        >
          {t('consult.upload.accepted')}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          onChange={onPick}
          className="hidden"
        />
      </div>

      {/* selected files */}
      {files.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {files.map((f, i) => {
            const Icon = fileIcon(f.name);
            return (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center gap-2.5 px-2.5 py-1.5"
                style={{
                  background: 'hsl(var(--muted) / 0.5)',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 'calc(var(--radius) - 4px)',
                }}
              >
                <Icon size={14} style={{ color: 'hsl(var(--primary))' }} />
                <span
                  className="flex-1 truncate"
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: 13,
                    color: 'hsl(var(--foreground))',
                  }}
                >
                  {f.name}
                </span>
                <span
                  className="kap-mono-tag"
                  style={{ color: 'hsl(var(--muted-foreground))' }}
                >
                  {fmtBytes(f.size)}
                </span>
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  className="kap-btn kap-btn-ghost"
                  style={{ padding: '0.2rem' }}
                  aria-label="remove"
                >
                  <X size={12} />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* actions */}
      <div className="flex items-center gap-2 mt-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="kap-btn"
          disabled={uploading}
        >
          <FileText size={13} />
          {t('consult.upload.browse')}
        </button>
        <button
          type="button"
          onClick={upload}
          disabled={!files.length || uploading}
          className="kap-btn kap-btn-primary"
        >
          {uploading
            ? <><Loader2 size={13} className="animate-spin" /> {t('consult.upload.uploading')}</>
            : <><Upload size={13} /> {t('consult.upload.title')} ({files.length})</>}
        </button>
        <div className="flex-1" />
        {result && (
          <span className="kap-badge kap-badge-success">
            <Check size={11} />
            {t('consult.upload.success')}
          </span>
        )}
        {error && (
          <span className="kap-badge kap-badge-danger">
            <AlertCircle size={11} />
            {error}
          </span>
        )}
      </div>

      {/* result tiles */}
      {result?.distillation && (
        <div className="grid grid-cols-3 gap-2 mt-4 pt-4"
             style={{ borderTop: '1px solid hsl(var(--border))' }}>
          <ResultTile labelKey="consult.upload.kept"      value={result.distillation.kept}      tone="good"  />
          <ResultTile labelKey="consult.upload.archived"  value={result.distillation.archived}  tone="warn"  />
          <ResultTile labelKey="consult.upload.discarded" value={result.distillation.discarded} tone="muted" />
        </div>
      )}
    </KapCard>
  );
}


function ResultTile({
  labelKey, value, tone,
}: {
  labelKey: 'consult.upload.kept' | 'consult.upload.archived' | 'consult.upload.discarded';
  value: number;
  tone: 'good' | 'warn' | 'muted';
}) {
  const { t } = useLocale();
  const color =
    tone === 'good' ? 'hsl(var(--success))'
    : tone === 'warn' ? 'hsl(var(--warning))'
    : 'hsl(var(--muted-foreground))';

  return (
    <div
      style={{
        padding: '0.7rem 0.85rem',
        background: 'hsl(var(--muted) / 0.5)',
        border: '1px solid hsl(var(--border))',
        borderRadius: 'calc(var(--radius) - 4px)',
      }}
    >
      <div className="kap-stat-label" style={{ fontSize: 11 }}>
        {t(labelKey)}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-sans)',
          fontWeight: 600,
          fontSize: '1.4rem',
          color,
          marginTop: 4,
          letterSpacing: '-0.02em',
        }}
      >
        {value}
      </div>
    </div>
  );
}
