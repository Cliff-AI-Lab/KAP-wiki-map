/**
 * V15 知识体系建立流程 — 一体化导入向导 (Nord 风, 借鉴 V14 但完全重做)
 *
 * 4 步:
 *   1. 上传文档        UploadStep
 *   2. 去噪审核        ReviewStep
 *   3. 知识体系        TaxonomyStep
 *   4. 编译完成        CompiledStep
 *
 * 左侧 vertical stepper, 右侧 Outlet 渲染当前步骤.
 * 共享 useActiveProject, 不依赖 useParams.
 */
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Upload, Filter, Network, BookOpen, Check } from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';

const STEPS = [
  { id: 'upload',    label: '上传文档',  desc: '飞书/钉钉/企微/本地',     icon: Upload  },
  { id: 'review',    label: '去噪审核',  desc: '保留 / 归档 / 丢弃',       icon: Filter  },
  { id: 'taxonomy',  label: '知识体系',  desc: '四级 Schema 编辑',         icon: Network },
  { id: 'compiled',  label: '编译完成',  desc: 'Wiki + 图谱产出 → 消费',   icon: BookOpen },
];

export default function ImportLayout() {
  const { projectId, projects } = useActiveProject();
  const location = useLocation();
  const current = projects.find((p) => p.id === projectId);

  // 当前步骤 idx
  const currentStepId = STEPS.find((s) => location.pathname.endsWith('/' + s.id))?.id ?? 'upload';
  const currentStepIdx = STEPS.findIndex((s) => s.id === currentStepId);

  return (
    <div className="space-y-6 v15-anim">
      {/* 标题 */}
      <div>
        <div className="text-[11px] v15-mono uppercase tracking-[0.2em] text-th-text-muted mb-2">
          KNOWLEDGE INTAKE · 一体化导入向导
        </div>
        <h1 className="v15-display text-3xl text-th-text-primary">建立知识体系</h1>
        <p className="text-sm text-th-text-muted v15-body-light mt-1">
          {current ? (
            <>项目: <span className="text-th-text-primary">{current.name}</span> · {current.industry_name} · {current.doc_count} 篇文档</>
          ) : (
            <span className="text-th-error">尚未选择项目 — 顶栏切换或新建</span>
          )}
        </p>
      </div>

      {/* Stepper + 内容 */}
      <div className="grid grid-cols-12 gap-6">
        {/* 左侧 vertical stepper */}
        <div className="col-span-3">
          <div className="space-y-2 sticky top-6">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const done = i < currentStepIdx;
              const active = s.id === currentStepId;
              return (
                <NavLink
                  key={s.id}
                  to={s.id}
                  className={({ isActive }) =>
                    `block rounded-card border p-3 transition ${
                      isActive
                        ? 'border-accent bg-hover'
                        : done
                          ? 'border-th-success/30 bg-elevated/60'
                          : 'border-th-border bg-elevated hover:border-th-border-hover'
                    }`
                  }
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-8 h-8 rounded-pill grid place-items-center shrink-0 ${
                        active
                          ? 'bg-accent text-[color:var(--color-bg-base)]'
                          : done
                            ? 'bg-th-success/20 text-th-success'
                            : 'bg-hover text-th-text-muted'
                      }`}
                    >
                      {done ? <Check size={14} /> : <Icon size={14} />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] v15-mono text-th-text-muted">STEP {i + 1}</span>
                        {active && <span className="w-1 h-1 rounded-full bg-accent animate-pulse" />}
                      </div>
                      <div className={`text-sm font-medium mt-0.5 ${active ? 'text-th-text-primary' : 'text-th-text-secondary'}`}>
                        {s.label}
                      </div>
                      <div className="text-[10px] text-th-text-muted mt-0.5">{s.desc}</div>
                    </div>
                  </div>
                </NavLink>
              );
            })}
          </div>
        </div>

        {/* 右侧 Outlet */}
        <div className="col-span-9 v15-glass rounded-card p-6 min-h-[420px]">
          {projectId ? <Outlet /> : <NoProject />}
        </div>
      </div>
    </div>
  );
}

function NoProject() {
  return (
    <div className="grid place-items-center h-full text-center">
      <div>
        <div className="text-th-text-muted text-sm mb-2">未选择项目</div>
        <div className="text-xs text-th-text-muted">顶栏点项目选择器或新建项目</div>
      </div>
    </div>
  );
}
