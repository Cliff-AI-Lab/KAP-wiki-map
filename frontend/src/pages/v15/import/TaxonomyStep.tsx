/**
 * TaxonomyStep — 第 3 步: 知识体系 (Nord 风, 借鉴 V14 但完全重做)
 *
 * 展示项目的四级知识体系树:
 *   根 → 一级域 → 二级域 → 叶子域
 * 每个域显示 doc_count, 点击高亮.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Loader2, Network, ArrowRight, RefreshCw, AlertTriangle, ChevronRight,
} from 'lucide-react';
import { useActiveProject } from '@/hooks/useActiveProject';
import { fetchDomains, type DomainInfo } from '@/services/api';

interface TreeNode extends DomainInfo {
  children: TreeNode[];
  level: number;
}

function buildTree(domains: DomainInfo[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  domains.forEach((d) => map.set(d.domain_id, { ...d, children: [], level: 0 }));
  const roots: TreeNode[] = [];
  domains.forEach((d) => {
    const node = map.get(d.domain_id)!;
    if (d.parent_id && map.has(d.parent_id)) {
      const parent = map.get(d.parent_id)!;
      parent.children.push(node);
      node.level = parent.level + 1;
    } else {
      roots.push(node);
    }
  });
  // 递归 fix levels
  function fixLevel(node: TreeNode, level: number) {
    node.level = level;
    node.children.sort((a, b) => b.doc_count - a.doc_count);
    node.children.forEach((c) => fixLevel(c, level + 1));
  }
  roots.sort((a, b) => b.doc_count - a.doc_count);
  roots.forEach((r) => fixLevel(r, 0));
  return roots;
}

export default function TaxonomyStep() {
  const { projectId } = useActiveProject();
  const navigate = useNavigate();
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const reload = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetchDomains(projectId);
      setDomains(r.domains);
      // 默认展开 level 0
      const top = new Set<string>();
      r.domains.filter((d) => !d.parent_id).forEach((d) => top.add(d.domain_id));
      setExpanded(top);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  const tree = useMemo(() => buildTree(domains), [domains]);

  const stats = useMemo(() => {
    const lvls: Record<number, number> = {};
    function walk(node: TreeNode) {
      lvls[node.level] = (lvls[node.level] ?? 0) + 1;
      node.children.forEach(walk);
    }
    tree.forEach(walk);
    return {
      total: domains.length,
      levels: lvls,
      with_docs: domains.filter((d) => d.doc_count > 0).length,
      total_docs: domains.reduce((sum, d) => sum + d.doc_count, 0),
    };
  }, [domains, tree]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="v15-display text-xl text-th-text-primary">第 3 步 · 知识体系</h2>
          <p className="text-xs text-th-text-muted mt-1">
            Schema 四级分类 · LLM 自动归类 + 可人工编辑 · 这里是项目模板的实例
          </p>
        </div>
        <button
          onClick={reload}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-btn border border-th-border text-[11px] v15-mono text-th-text-muted hover:text-th-text-primary"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          刷新
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="域总数"    value={stats.total} hint="Schema 全部节点" />
        <StatCard label="L0 根域"   value={stats.levels[0] ?? 0} hint="顶级类目" />
        <StatCard label="已识别域"  value={stats.with_docs} hint="doc_count>0" />
        <StatCard label="总文档"    value={stats.total_docs} hint="跨所有域" />
      </div>

      {error && (
        <div className="rounded-btn border border-th-error/40 bg-th-error/5 p-3 text-sm text-th-error flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
        </div>
      )}

      {/* Tree */}
      <div className="rounded-card border border-th-border bg-elevated/60">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-th-border">
          <Network size={14} className="text-accent" />
          <span className="text-sm font-semibold text-th-text-primary">体系树</span>
          <span className="text-[10px] text-th-text-muted v15-mono ml-auto">
            shift + 点击 全部展开（暂未实现）
          </span>
        </div>
        <div className="max-h-[440px] overflow-y-auto p-2">
          {tree.length === 0 ? (
            <div className="text-xs text-th-text-muted text-center py-8">
              {loading ? '加载中...' : '暂无体系数据'}
            </div>
          ) : (
            tree.map((root) => <TreeRow key={root.domain_id} node={root} expanded={expanded} onToggle={toggle} />)
          )}
        </div>
      </div>

      <div className="text-right">
        <button
          onClick={() => navigate('/v15/manage/import/compiled')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent text-[color:var(--color-bg-base)] text-xs font-medium hover:brightness-95"
        >
          进入第 4 步 · 编译完成 <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
}

function TreeRow({
  node, expanded, onToggle,
}: { node: TreeNode; expanded: Set<string>; onToggle: (id: string) => void }) {
  const isOpen = expanded.has(node.domain_id);
  const hasChildren = node.children.length > 0;
  const indent = node.level * 18;
  const heat = Math.min(1, node.doc_count / 8); // 0~1 doc 热度
  const bgOpacity = 0.04 + heat * 0.12;

  return (
    <>
      <div
        className="flex items-center gap-2 px-2 py-1.5 rounded text-sm hover:bg-hover/40 transition cursor-pointer"
        style={{ paddingLeft: `${8 + indent}px` }}
        onClick={() => hasChildren && onToggle(node.domain_id)}
      >
        <ChevronRight
          size={12}
          className={`text-th-text-muted transition-transform ${isOpen ? 'rotate-90' : ''} ${hasChildren ? '' : 'opacity-0'}`}
        />
        <span
          className="w-1 h-1 rounded-full shrink-0"
          style={{
            backgroundColor: heat > 0.5 ? 'var(--color-accent)' : 'var(--color-text-muted)',
            boxShadow: heat > 0.7 ? `0 0 6px var(--color-accent)` : undefined,
          }}
        />
        <span className="text-th-text-primary truncate">{node.name || node.domain_id}</span>
        <span className="text-[10px] text-th-text-muted v15-mono ml-auto shrink-0">
          {node.doc_count} doc
        </span>
        <span
          className="ml-2 px-1.5 py-0.5 rounded-pill text-[10px] v15-mono shrink-0"
          style={{
            backgroundColor: `rgba(136, 192, 208, ${bgOpacity})`,
            color: 'var(--color-text-muted)',
          }}
        >
          L{node.level}
        </span>
      </div>
      {isOpen && node.children.map((c) => (
        <TreeRow key={c.domain_id} node={c} expanded={expanded} onToggle={onToggle} />
      ))}
    </>
  );
}

function StatCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-card border border-th-border bg-elevated p-3">
      <div className="text-[10px] uppercase tracking-wider text-th-text-muted">{label}</div>
      <div className="text-2xl font-semibold text-th-text-primary mt-1 v15-display">{value}</div>
      {hint && <div className="text-[10px] text-th-text-muted v15-mono mt-1">{hint}</div>}
    </div>
  );
}
