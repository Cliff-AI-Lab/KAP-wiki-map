/**
 * V15 Phase M: 代码知识图谱 (借鉴 GitNexus).
 *
 * 扫 packages/ + api/ 模块级 import 关系, 让用户:
 *   • 看 V15 自身的代码架构 (community 染色)
 *   • 找 dead code (入度=0 的孤岛)
 *   • blast radius: 改一处, 谁会受影响
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Loader2, RefreshCw, AlertTriangle, Target, Code2 } from 'lucide-react';

interface CodeNode {
  id: string;
  package: string;
  subpackage: string;
  file: string;
  classes: string[];
  functions: string[];
  loc: number;
  in_degree: number;
  out_degree: number;
  color: string;
  size: number;
  is_entry: boolean;
  is_dead: boolean;
}

interface CodeEdge {
  source: string;
  target: string;
  kind: string;
}

interface CodeGraphData {
  nodes: CodeNode[];
  edges: CodeEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    dead_code_count: number;
    package_count: number;
    total_loc: number;
  };
  package_colors: Record<string, string>;
}

interface BlastRadiusResult {
  target: string;
  max_hops: number;
  affected: { module: string; hops: number }[];
  stats: { count: number; by_hop: Record<string, number> };
}

const FALLBACK = '#a3b1c4';

export default function CodeGraph() {
  const [data, setData] = useState<CodeGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<CodeNode | null>(null);
  const [blast, setBlast] = useState<BlastRadiusResult | null>(null);
  const [blastLoading, setBlastLoading] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const fgRef = useRef<any>(null);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`/api/v1/v15/code-graph${force ? '?force=true' : ''}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 计算 blast radius
  const fetchBlast = useCallback(async (target: string) => {
    setBlastLoading(true);
    try {
      const r = await fetch(`/api/v1/v15/code-graph/blast-radius?target=${encodeURIComponent(target)}&max_hops=3`);
      if (!r.ok) {
        setBlast(null);
      } else {
        setBlast(await r.json());
      }
    } finally {
      setBlastLoading(false);
    }
  }, []);

  // 点击节点 → 选中 + 跑 blast radius
  const onNodeClick = useCallback((node: any) => {
    setSelectedNode(node as CodeNode);
    fetchBlast(node.id);
  }, [fetchBlast]);

  // 染色: 选中态 + blast radius hop 高亮
  const blastSet = blast ? new Set(blast.affected.map(a => a.module)) : null;

  const graphData = data ? {
    nodes: data.nodes.map(n => ({ ...n, _fade: blastSet ? !(blastSet.has(n.id) || n.id === blast?.target) : false })),
    links: data.edges,
  } : { nodes: [], links: [] };

  return (
    <div className="space-y-4 v15-anim">
      {/* 标题 + stats */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] v15-mono uppercase tracking-[0.2em] text-th-text-muted mb-2">
            CODE INTELLIGENCE · 模块依赖与影响分析
          </div>
          <h1 className="v15-display text-3xl text-th-text-primary">代码图谱</h1>
          <p className="text-sm text-th-text-muted v15-body-light mt-1">
            扫 packages/ + api/ Python AST · 模块级 import 关系 · 点节点查看 blast radius
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] v15-mono text-th-text-muted">
          {data && (
            <>
              <span>nodes = <span className="text-th-text-primary">{data.stats.node_count}</span></span>
              <span>·</span>
              <span>edges = <span className="text-th-text-primary">{data.stats.edge_count}</span></span>
              <span>·</span>
              <span>dead = <span className="text-th-error">{data.stats.dead_code_count}</span></span>
              <span>·</span>
              <span>LOC = <span className="text-th-text-primary">{data.stats.total_loc}</span></span>
            </>
          )}
          <button
            onClick={() => load(true)}
            className="ml-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-btn border border-th-border hover:border-th-border-hover text-th-text-secondary"
            title="重新扫描"
          >
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-btn border border-th-error/30 bg-th-error/5 p-3 text-sm text-th-error flex items-center gap-2">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* 主图谱 */}
        <div className="col-span-8 v15-glass rounded-card p-3 h-[640px] relative overflow-hidden">
          {loading ? (
            <div className="h-full grid place-items-center text-th-text-muted text-sm">
              <Loader2 size={20} className="animate-spin mb-2" />
              扫描代码中...
            </div>
          ) : data && data.nodes.length > 0 ? (
            <ForceGraph2D
              ref={fgRef}
              graphData={graphData as any}
              nodeId="id"
              nodeRelSize={1}
              backgroundColor="rgba(0,0,0,0)"
              linkColor={(l: any) => {
                if (blastSet && (blastSet.has(typeof l.source === 'string' ? l.source : l.source.id) || blastSet.has(typeof l.target === 'string' ? l.target : l.target.id))) {
                  return 'rgba(191, 97, 106, 0.5)';
                }
                return 'rgba(236, 239, 244, 0.12)';
              }}
              linkDirectionalArrowLength={3.5}
              linkDirectionalArrowRelPos={1}
              onNodeClick={onNodeClick}
              onNodeHover={(node: any) => setHoveredId(node?.id ?? null)}
              nodeCanvasObject={(node: any, ctx, scale) => {
                const r = (node.size ?? 6) / Math.max(scale * 0.5, 1);
                const isSel = selectedNode?.id === node.id;
                const isHover = hoveredId === node.id;
                const isAffected = blastSet?.has(node.id);
                const isTarget = blast?.target === node.id;
                ctx.globalAlpha = node._fade && !isTarget && !isHover ? 0.18 : 1;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
                ctx.fillStyle = node.is_dead ? '#bf616a' : (node.color ?? FALLBACK);
                ctx.fill();
                if (isTarget) {
                  ctx.strokeStyle = '#bf616a';
                  ctx.lineWidth = 3 / scale;
                  ctx.stroke();
                } else if (isAffected) {
                  ctx.strokeStyle = '#ebcb8b';
                  ctx.lineWidth = 2 / scale;
                  ctx.stroke();
                } else if (isSel || isHover) {
                  ctx.strokeStyle = '#88c0d0';
                  ctx.lineWidth = 2 / scale;
                  ctx.stroke();
                }
                // 大节点显示模块名
                if (r * scale > 8 || isHover || isSel) {
                  const label = node.id.split('.').slice(-2).join('.');
                  ctx.font = `${10 / scale}px Inter, sans-serif`;
                  ctx.fillStyle = '#eceff4';
                  ctx.textAlign = 'center';
                  ctx.fillText(label, node.x, node.y + r + 8 / scale);
                }
                ctx.globalAlpha = 1;
              }}
            />
          ) : (
            <div className="h-full grid place-items-center text-th-text-muted text-sm">
              暂无代码数据
            </div>
          )}
        </div>

        {/* 右侧详情 */}
        <div className="col-span-4 space-y-4">
          {/* 节点详情 */}
          <div className="v15-glass rounded-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Code2 size={14} className="text-accent" />
              <span className="text-sm font-semibold text-th-text-primary">模块详情</span>
            </div>
            {selectedNode ? (
              <div className="space-y-2 text-sm">
                <div className="text-th-text-primary v15-mono text-[12px] break-all">{selectedNode.id}</div>
                <div className="text-xs text-th-text-muted">
                  {selectedNode.file} · {selectedNode.loc} 行
                </div>
                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-th-border">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-th-text-muted">In</div>
                    <div className="text-th-text-primary">{selectedNode.in_degree}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-th-text-muted">Out</div>
                    <div className="text-th-text-primary">{selectedNode.out_degree}</div>
                  </div>
                </div>
                {selectedNode.is_entry && (
                  <span className="inline-block px-2 py-0.5 rounded-pill text-[10px] bg-accent/20 text-accent border border-accent/40">入口</span>
                )}
                {selectedNode.is_dead && (
                  <span className="inline-block px-2 py-0.5 rounded-pill text-[10px] bg-th-error/20 text-th-error border border-th-error/40 ml-2">dead code</span>
                )}
                {selectedNode.classes.length > 0 && (
                  <div className="pt-2 border-t border-th-border">
                    <div className="text-[10px] uppercase tracking-wider text-th-text-muted mb-1">Classes</div>
                    <div className="text-xs text-th-text-secondary v15-mono">
                      {selectedNode.classes.join(', ')}
                    </div>
                  </div>
                )}
                {selectedNode.functions.length > 0 && (
                  <div className="pt-2 border-t border-th-border">
                    <div className="text-[10px] uppercase tracking-wider text-th-text-muted mb-1">Functions</div>
                    <div className="text-xs text-th-text-secondary v15-mono leading-relaxed">
                      {selectedNode.functions.join(', ')}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-th-text-muted">点图中节点查看详情</div>
            )}
          </div>

          {/* Blast Radius */}
          <div className="v15-glass rounded-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Target size={14} className="text-th-error" />
              <span className="text-sm font-semibold text-th-text-primary">Blast Radius</span>
              {blastLoading && <Loader2 size={12} className="animate-spin text-th-text-muted ml-auto" />}
            </div>
            {blast ? (
              <div className="space-y-2 text-sm">
                <div className="text-xs text-th-text-muted">
                  改 <span className="v15-mono text-th-error">{blast.target.split('.').slice(-2).join('.')}</span> 影响 <span className="text-th-text-primary font-semibold">{blast.stats.count}</span> 个上游模块
                </div>
                <div className="flex gap-2 text-[10px] v15-mono">
                  {Object.entries(blast.stats.by_hop).map(([hop, cnt]) => (
                    <span key={hop} className="px-2 py-0.5 rounded-pill border border-th-border text-th-text-muted">
                      hop {hop}: {cnt}
                    </span>
                  ))}
                </div>
                <div className="max-h-64 overflow-y-auto pt-2 border-t border-th-border">
                  {blast.affected.slice(0, 30).map(a => (
                    <div key={a.module} className="text-xs py-1 flex items-center gap-2">
                      <span className={`v15-mono w-12 text-[10px] ${a.hops === 1 ? 'text-th-error' : a.hops === 2 ? 'text-th-warning' : 'text-th-text-muted'}`}>
                        hop {a.hops}
                      </span>
                      <span className="text-th-text-secondary truncate">{a.module}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-xs text-th-text-muted">点图中节点自动计算</div>
            )}
          </div>
        </div>
      </div>

      {/* 图例 */}
      <div className="flex flex-wrap items-center gap-4 text-[11px] v15-mono text-th-text-muted">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-th-error" /> dead code (入度=0)</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full ring-2 ring-th-error" /> Blast 目标</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full ring-2 ring-th-warning" /> 受影响 (上游)</span>
        <span className="flex items-center gap-1.5">● 节点大小 = (in + out) degree</span>
        <span className="flex items-center gap-1.5">颜色 = 二级包 (packages.governance / api.routers / ...)</span>
      </div>
    </div>
  );
}
