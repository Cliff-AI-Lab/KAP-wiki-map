/**
 * V15 项目选择器 — 顶栏下拉 (Nord 风)
 *
 * 与 V14 ProjectSelector 的区别:
 *   - 用 useActiveProject hook 统一项目上下文
 *   - 极简下拉 + 暖橙(or Frost) 行业徽章
 *   - 内置 "新建项目" 入口
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Plus, FolderOpen } from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';

const INDUSTRY_COLORS: Record<string, string> = {
  energy:        '#d08770',   // aurora orange
  manufacturing: '#88c0d0',   // frost
  it:            '#81a1c1',
  finance:       '#a3be8c',
  healthcare:    '#bf616a',
  generic:       '#a3b1c4',
};

export function V15ProjectSelector() {
  const { projectId, projects, setActive, loading } = useActiveProject();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const current = projects.find((p) => p.id === projectId);

  if (loading) {
    return <div className="text-xs text-th-text-muted v15-mono px-3">loading...</div>;
  }

  if (!current && projects.length === 0) {
    return (
      <Link
        to="/projects/new"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn border border-dashed border-th-border text-xs text-th-text-muted hover:text-accent hover:border-accent transition"
      >
        <Plus size={12} /> 新建项目
      </Link>
    );
  }

  const color = current ? (INDUSTRY_COLORS[current.industry_code] ?? INDUSTRY_COLORS.generic) : INDUSTRY_COLORS.generic;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-btn border border-th-border bg-elevated hover:border-th-border-hover text-sm transition"
      >
        <span
          className="w-5 h-5 rounded grid place-items-center text-[10px] font-bold text-th-text-primary"
          style={{ backgroundColor: color, color: '#2e3440' }}
        >
          {current?.industry_name?.charAt(0) ?? '·'}
        </span>
        <span className="text-th-text-primary truncate max-w-[180px]">
          {current?.name ?? '选择项目'}
        </span>
        <ChevronDown size={12} className="text-th-text-muted" />
      </button>

      {open && (
        <div className="absolute left-0 mt-1 w-72 rounded-card border border-th-border bg-elevated shadow-lg overflow-hidden z-30 v15-anim-scale">
          <div className="text-[10px] uppercase tracking-wider text-th-text-muted px-3 py-2 border-b border-th-border v15-mono">
            项目 · {projects.length}
          </div>
          <div className="max-h-72 overflow-y-auto">
            {projects.map((p) => {
              const c = INDUSTRY_COLORS[p.industry_code] ?? INDUSTRY_COLORS.generic;
              const active = p.id === projectId;
              return (
                <button
                  key={p.id}
                  onClick={() => { setActive(p.id); setOpen(false); }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition hover:bg-hover ${
                    active ? 'bg-hover' : ''
                  }`}
                >
                  <span
                    className="w-5 h-5 rounded grid place-items-center text-[10px] font-bold shrink-0"
                    style={{ backgroundColor: c, color: '#2e3440' }}
                  >
                    {p.industry_name?.charAt(0) ?? '·'}
                  </span>
                  <span className="flex-1 truncate text-th-text-primary">{p.name}</span>
                  <span className="text-[10px] v15-mono text-th-text-muted">{p.doc_count} doc</span>
                </button>
              );
            })}
          </div>
          <div className="border-t border-th-border">
            <Link
              to="/projects/new"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-th-text-secondary hover:text-accent hover:bg-hover transition"
            >
              <Plus size={14} /> 新建项目
            </Link>
            <Link
              to="/projects"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-th-text-secondary hover:text-accent hover:bg-hover transition border-t border-th-border"
            >
              <FolderOpen size={14} /> 项目管理
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
