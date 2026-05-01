/**
 * WikiTree — Wiki 三层结构总览页（M16 #4）。
 *
 * 把 WikiHierarchyTree 组件挂成独立页，方便 SME 整体看 Wiki 编译产出。
 * 点节点 → 跳转到 /v15/read/wiki/<page_id>
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen } from 'lucide-react';

import WikiHierarchyTree from '@/components/v15/WikiHierarchyTree';
import { useActiveProject } from '@/hooks/useActiveProject';

export default function WikiTree() {
  const navigate = useNavigate();
  const { projectId } = useActiveProject();

  const handleSelect = (pageId: string) => {
    navigate(`/v15/read/wiki/${encodeURIComponent(pageId)}`);
  };

  return (
    <div className="p-6 max-w-screen-md mx-auto space-y-4">
      <div className="flex items-center gap-3">
        <Link
          to="/v15/read"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-btn text-xs text-th-text-muted hover:text-th-text-primary hover:bg-hover"
        >
          <ArrowLeft size={12} /> 消费首页
        </Link>
        <h1 className="text-2xl font-semibold text-th-text-primary flex items-center gap-2">
          <BookOpen size={20} className="text-accent" />
          Wiki 三层结构总览
        </h1>
        <span className="text-xs text-th-text-muted font-mono">
          决策书 §6 · Karpathy 三层
        </span>
      </div>

      <p className="text-sm text-th-text-muted">
        index → domain_overview → source_summary 三级编译产出。点节点跳转到详情页。
      </p>

      <WikiHierarchyTree
        projectId={projectId || undefined}
        onSelectPage={handleSelect}
      />
    </div>
  );
}
