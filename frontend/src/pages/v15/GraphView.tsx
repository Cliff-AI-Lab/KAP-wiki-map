/**
 * GraphView — 知识图谱 (Nexus 风格)
 *
 * 默认: 全图淡显, 不挤标签.
 * 操作:
 *   • 点击顶部 Community chip → 仅显示该社区节点 + 内部边, 带 label
 *   • 点击节点 → 仅显示该节点 + 1-hop 邻居 + 关联边, 带 label
 *   • 双击节点 / 点击"重置" → 回到全局淡显
 *   • 搜索 → 命中节点高亮, 其余 0.06 透明
 *
 * 物理引擎保持 (节点可拖拽).
 * 边按 inferred 虚线区分 (Inferer Agent 推理关系).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { RefreshCw, Loader2, Search, Tag, FileText, X, Layers, Palette } from 'lucide-react';

import { useActiveProject } from '@/hooks/useActiveProject';

// M2 #3 obsidian 风格染色维度（feedback memory · 节点按维度染色）
type ColorMode = 'community' | 'type' | 'centrality';

interface GraphNode {
  id: string;
  name: string;
  community: number;
  centrality: number;
  size: number;
  type: string;
  doc_count: number;
  // force-graph 运行时
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  inferred: boolean;
}

interface GraphViewData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    community_count: number;
    max_centrality: number;
  };
}

const COMMUNITY_PALETTE = [
  '#88c0d0', '#a3be8c', '#ebcb8b', '#d08770', '#b48ead',
  '#81a1c1', '#bf616a', '#8fbcbb', '#5e81ac', '#c0bfb0',
];
const colorForCommunity = (c: number) => COMMUNITY_PALETTE[c % COMMUNITY_PALETTE.length] ?? '#88c0d0';

// M2 #3 类型染色（中文 type → obsidian 风调色板）
const TYPE_PALETTE: Record<string, string> = {
  人物: '#88c0d0',     // sky
  部门: '#a3be8c',     // green
  项目: '#ebcb8b',     // amber
  制度: '#d08770',     // orange
  产品: '#b48ead',     // purple
  流程: '#81a1c1',     // indigo
  设备: '#bf616a',     // rose
  标准: '#8fbcbb',     // teal
};
const colorForType = (t: string) => TYPE_PALETTE[t] ?? '#a0a0b0';

// M2 #3 中心性染色（绿→黄→红渐变）
function colorForCentrality(c: number, max: number): string {
  if (max <= 0) return '#88c0d0';
  const t = Math.min(1, c / max);
  if (t < 0.33) return '#a3be8c';      // 低 → 绿
  if (t < 0.66) return '#ebcb8b';      // 中 → 黄
  return '#d08770';                     // 高 → 橙红
}

export default function GraphView() {
  const { projectId, loading: projectsLoading } = useActiveProject();
  const [data, setData] = useState<GraphViewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedCommunity, setSelectedCommunity] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  // M2 #3 obsidian 风格：染色维度可切（社区/类型/中心性）
  const [colorMode, setColorMode] = useState<ColorMode>('community');
  const fgRef = useRef<unknown>(null);

  // 节点最终着色函数（按 colorMode 路由）
  const colorForNode = useCallback(
    (n: GraphNode): string => {
      if (colorMode === 'type') return colorForType(n.type);
      if (colorMode === 'centrality') {
        const max = data?.stats.max_centrality ?? 1;
        return colorForCentrality(n.centrality, max);
      }
      return colorForCommunity(n.community);
    },
    [colorMode, data],
  );

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`/api/v1/v15/graph/view?project_id=${encodeURIComponent(projectId)}&max_nodes=200`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d: GraphViewData = await r.json();
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  // 切项目时清选择
  useEffect(() => {
    setSelectedNode(null);
    setSelectedCommunity(null);
    setSearch('');
  }, [projectId]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return {
      nodes: data.nodes,
      links: data.edges.map((e) => ({ ...e })),
    };
  }, [data]);

  // 社区统计 (按 size 排序, 取 top 13)
  const communities = useMemo(() => {
    if (!data) return [] as { id: number; count: number; topNames: string[] }[];
    const m = new Map<number, GraphNode[]>();
    data.nodes.forEach((n) => {
      const arr = m.get(n.community) ?? [];
      arr.push(n);
      m.set(n.community, arr);
    });
    return Array.from(m.entries())
      .map(([id, arr]) => ({
        id,
        count: arr.length,
        topNames: arr.sort((a, b) => b.centrality - a.centrality).slice(0, 3).map((x) => x.name),
      }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  // 1-hop 邻居 ID 集合 (基于 selectedNode)
  const neighborIds = useMemo(() => {
    if (!data || !selectedNode) return new Set<string>();
    const s = new Set<string>([selectedNode.id]);
    data.edges.forEach((e) => {
      const src = typeof e.source === 'string' ? e.source : (e.source as { id: string }).id;
      const tgt = typeof e.target === 'string' ? e.target : (e.target as { id: string }).id;
      if (src === selectedNode.id) s.add(tgt);
      if (tgt === selectedNode.id) s.add(src);
    });
    return s;
  }, [data, selectedNode]);

  // 搜索命中
  const searchHitIds = useMemo(() => {
    if (!data || !search.trim()) return new Set<string>();
    const q = search.trim().toLowerCase();
    return new Set(
      data.nodes
        .filter((n) => n.name.toLowerCase().includes(q) || (n.type ?? '').toLowerCase().includes(q))
        .map((n) => n.id),
    );
  }, [data, search]);

  // 节点可见性: 优先级 search > selectedNode > selectedCommunity > 默认 (全部正常显示)
  const nodeVisibility = useCallback(
    (n: GraphNode): { focused: boolean; alpha: number; showLabel: boolean } => {
      if (search.trim()) {
        const hit = searchHitIds.has(n.id);
        return { focused: hit, alpha: hit ? 1 : 0.06, showLabel: hit };
      }
      if (selectedNode) {
        const hit = neighborIds.has(n.id);
        return { focused: hit, alpha: hit ? 1 : 0.06, showLabel: hit };
      }
      if (selectedCommunity != null) {
        const hit = n.community === selectedCommunity;
        return { focused: hit, alpha: hit ? 1 : 0.08, showLabel: hit };
      }
      // 默认 "全部展示" 模式: 所有节点正常显示 + 都带 label (低 zoom 仅高 centrality 显示, 由 nodeCanvasObject 控制)
      return { focused: true, alpha: 1, showLabel: true };
    },
    [search, selectedNode, selectedCommunity, searchHitIds, neighborIds],
  );

  // 边可见性: 跟节点联动. 默认 (无任何选中) 全部边都焦点
  const edgeFocused = useCallback(
    (e: GraphEdge): boolean => {
      const src = typeof e.source === 'string' ? e.source : (e.source as { id: string }).id;
      const tgt = typeof e.target === 'string' ? e.target : (e.target as { id: string }).id;
      if (search.trim()) return searchHitIds.has(src) || searchHitIds.has(tgt);
      if (selectedNode) return src === selectedNode.id || tgt === selectedNode.id;
      if (selectedCommunity != null) {
        const sNode = data?.nodes.find((n) => n.id === src);
        const tNode = data?.nodes.find((n) => n.id === tgt);
        return sNode?.community === selectedCommunity && tNode?.community === selectedCommunity;
      }
      return true;  // 默认全部边可见
    },
    [search, selectedNode, selectedCommunity, searchHitIds, data],
  );

  const reset = () => {
    setSelectedNode(null);
    setSelectedCommunity(null);
    setSearch('');
  };

  if (projectsLoading) return <div className="text-sm text-th-text-muted">加载项目...</div>;
  if (!projectId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-8 text-center">
        <div className="text-th-text-primary mb-2">还没有项目</div>
      </div>
    );
  }

  return (
    <div className="space-y-4 v15-anim">
      {/* 标题 + stats */}
      <div className="flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-accent" />
        <h1 className="v15-display text-3xl text-th-text-primary">Knowledge Graph</h1>
        <div className="flex items-center gap-3 ml-auto text-xs v15-mono text-th-text-muted">
          {data && (
            <>
              <span>nodes = <span className="text-th-text-primary">{data.stats.node_count}</span></span>
              <span>edges = <span className="text-th-text-primary">{data.stats.edge_count}</span></span>
              <span>communities = <span className="text-accent">{data.stats.community_count}</span></span>
            </>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-btn border border-th-border px-2.5 py-1 hover:text-accent hover:border-accent disabled:opacity-40 transition"
          >
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-th-border bg-elevated p-3 text-sm text-th-error">
          {error}
        </div>
      )}

      {/* 顶部控制栏: 搜索 + 状态 + 重置 */}
      {data && data.nodes.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-btn border border-th-border bg-elevated flex-1 max-w-md">
            <Search size={12} className="text-th-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setSelectedNode(null); setSelectedCommunity(null); }}
              placeholder="搜索节点 (名称 / 类型)..."
              className="flex-1 bg-transparent outline-none text-sm text-th-text-primary placeholder:text-th-text-muted"
            />
          </div>
          <div className="text-[11px] v15-mono text-th-text-muted flex items-center gap-3">
            {selectedNode && <span>聚焦节点: <span className="text-accent">{selectedNode.name}</span> + {neighborIds.size - 1} 邻居</span>}
            {selectedCommunity != null && <span>聚焦社区 <span className="text-accent">#{selectedCommunity}</span></span>}
            {search.trim() && <span>搜索命中 <span className="text-accent">{searchHitIds.size}</span></span>}
            {(selectedNode || selectedCommunity != null || search.trim()) && (
              <button onClick={reset} className="inline-flex items-center gap-1 px-2 py-1 rounded-btn border border-th-border hover:border-accent hover:text-accent transition">
                <X size={11} /> 重置
              </button>
            )}
            {!selectedNode && selectedCommunity == null && !search.trim() && (
              <span>提示: 点击社区 chip 或图中节点聚焦</span>
            )}
          </div>

          {/* M2 #3 obsidian 风格：染色维度切换 */}
          <div className="flex items-center gap-1 ml-auto">
            <Palette size={11} className="text-th-text-muted mr-1" />
            {(['community', 'type', 'centrality'] as ColorMode[]).map((m) => {
              const labels: Record<ColorMode, string> = {
                community: '社区', type: '类型', centrality: '中心性',
              };
              const active = colorMode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setColorMode(m)}
                  className={`px-2 py-1 rounded-pill text-[11px] v15-mono transition border ${
                    active
                      ? 'border-accent bg-accent/15 text-th-text-primary'
                      : 'border-th-border text-th-text-muted hover:border-th-border-hover hover:text-th-text-secondary'
                  }`}
                >
                  {labels[m]}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Community chip bar */}
      {data && communities.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] v15-mono uppercase tracking-wider text-th-text-muted mr-1">
            <Layers size={11} className="inline -mt-0.5 mr-1" />社区
          </span>
          {/* "全部"模式 chip — 显示所有节点和边 */}
          {(() => {
            const isAll = selectedCommunity == null && !selectedNode && !search.trim();
            return (
              <button
                onClick={reset}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-pill text-[11px] v15-mono transition border ${
                  isAll
                    ? 'border-accent bg-accent/15 text-th-text-primary'
                    : 'border-th-border text-th-text-muted hover:border-th-border-hover hover:text-th-text-secondary'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-accent" />
                全部 · {data.stats.node_count}
              </button>
            );
          })()}
          {communities.map((c) => {
            const active = selectedCommunity === c.id;
            return (
              <button
                key={c.id}
                onClick={() => {
                  setSelectedCommunity(active ? null : c.id);
                  setSelectedNode(null);
                  setSearch('');
                }}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-pill text-[11px] v15-mono transition border ${
                  active
                    ? 'border-accent bg-accent/15 text-th-text-primary'
                    : 'border-th-border text-th-text-muted hover:border-th-border-hover hover:text-th-text-secondary'
                }`}
                title={c.topNames.join(' / ')}
              >
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colorForCommunity(c.id) }} />
                #{c.id} · {c.count}
              </button>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-9 relative rounded-card border border-th-border bg-elevated overflow-hidden" style={{ height: 600 }}>
          {loading && !data ? (
            <div className="absolute inset-0 grid place-items-center text-sm text-th-text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : !data || data.nodes.length === 0 ? (
            <div className="absolute inset-0 grid place-items-center text-sm text-th-text-muted">
              无图谱数据（需先灌入文档）
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef as never}
              graphData={graphData}
              nodeRelSize={1}
              nodeLabel={(n) => {
                const nd = n as unknown as GraphNode;
                return `${nd.name}\n类型: ${nd.type}\n关联文档: ${nd.doc_count}\n社区: #${nd.community}\n中心性: ${nd.centrality}`;
              }}
              linkLabel={(l) => {
                const e = l as unknown as GraphEdge;
                return e.relation || (e.inferred ? '推理关系' : '关系');
              }}
              onNodeClick={(n) => {
                setSelectedNode(n as unknown as GraphNode);
                setSelectedCommunity(null);
                setSearch('');
              }}
              onBackgroundClick={reset}
              nodeCanvasObject={(node, ctx, globalScale) => {
                const n = node as unknown as GraphNode;
                const v = nodeVisibility(n);
                const isSel = selectedNode?.id === n.id;
                const r = (n.size ?? 6) / Math.sqrt(globalScale);
                const nodeColor = colorForNode(n);
                ctx.globalAlpha = v.alpha;

                // M2 #3 obsidian 风柔光外发光：选中 / 聚焦节点 shadow blur
                if (isSel) {
                  ctx.shadowColor = nodeColor;
                  ctx.shadowBlur = 22 / Math.sqrt(globalScale);
                } else if (v.focused) {
                  ctx.shadowColor = nodeColor;
                  ctx.shadowBlur = 10 / Math.sqrt(globalScale);
                } else {
                  ctx.shadowBlur = 0;
                }

                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
                ctx.fillStyle = nodeColor;
                ctx.fill();
                ctx.shadowBlur = 0;  // reset，避免污染后续 stroke

                if (isSel) {
                  // 选中节点描白边
                  ctx.strokeStyle = '#eceff4';
                  ctx.lineWidth = 2.5 / globalScale;
                  ctx.stroke();
                } else if (v.focused) {
                  ctx.strokeStyle = 'rgba(236,239,244,0.4)';
                  ctx.lineWidth = 1 / globalScale;
                  ctx.stroke();
                }
                // label 显示策略:
                //   选中/搜索/社区聚焦下 → 全部显示
                //   "全部" 默认模式下 → 按 zoom + centrality 自适应避免拥挤
                const inFocusMode = !!(selectedNode || selectedCommunity != null || search.trim());
                let drawLabel = v.showLabel;
                if (drawLabel && !inFocusMode && !isSel) {
                  // 全部模式 — 低 zoom 仅高 centrality 显示, 高 zoom 全显示
                  if (globalScale < 1.0) drawLabel = n.centrality > 0.18;
                  else if (globalScale < 1.6) drawLabel = n.centrality > 0.08;
                  // else (>=1.6) 全显示
                }
                if (drawLabel) {
                  const fs = Math.max((isSel ? 12 : 10) / globalScale, 7);
                  ctx.font = `${isSel ? 'bold ' : ''}${fs}px 'Inter', sans-serif`;
                  ctx.lineWidth = 3 / globalScale;
                  ctx.strokeStyle = 'rgba(46, 52, 64, 0.85)';
                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'top';
                  const ly = (node.y ?? 0) + r + 2;
                  ctx.strokeText(n.name, node.x ?? 0, ly);
                  ctx.fillStyle = '#eceff4';
                  ctx.fillText(n.name, node.x ?? 0, ly);
                }
                ctx.globalAlpha = 1;
              }}
              linkColor={(link) => {
                const e = link as unknown as GraphEdge;
                const focused = edgeFocused(e);
                if (e.inferred) {
                  return focused ? 'rgba(136, 192, 208, 0.85)' : 'rgba(136, 192, 208, 0.12)';
                }
                return focused ? 'rgba(163, 190, 140, 0.7)' : 'rgba(163, 190, 140, 0.1)';
              }}
              linkLineDash={(link) => {
                const e = link as unknown as GraphEdge;
                return e.inferred ? [4, 4] : null;
              }}
              linkWidth={(link) => (edgeFocused(link as unknown as GraphEdge) ? 1.5 : 0.6)}
              linkCanvasObjectMode={() => 'after'}
              linkCanvasObject={(link, ctx, globalScale) => {
                const e = link as unknown as GraphEdge & { source: { x?: number; y?: number; id?: string }; target: { x?: number; y?: number; id?: string } };
                if (!edgeFocused(e as unknown as GraphEdge)) return;  // 仅聚焦边显示 relation
                const sx = (e.source as { x?: number }).x ?? 0;
                const sy = (e.source as { y?: number }).y ?? 0;
                const tx = (e.target as { x?: number }).x ?? 0;
                const ty = (e.target as { y?: number }).y ?? 0;
                const mx = (sx + tx) / 2;
                const my = (sy + ty) / 2;
                const text = e.relation || (e.inferred ? '推理' : '');
                if (!text) return;
                const fs = Math.max(9 / globalScale, 7);
                ctx.font = `${fs}px 'Inter', sans-serif`;
                ctx.lineWidth = 2.5 / globalScale;
                ctx.strokeStyle = 'rgba(46, 52, 64, 0.9)';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.strokeText(text, mx, my);
                ctx.fillStyle = e.inferred ? 'rgba(136, 192, 208, 1)' : 'rgba(220, 230, 200, 1)';
                ctx.fillText(text, mx, my);
              }}
              backgroundColor="#2e3440"
              cooldownTicks={80}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.25}
              enableNodeDrag={true}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              onNodeDragEnd={(node) => {
                // 拖拽结束后固定节点位置 (设 fx/fy), 让用户拖动后保持
                const n = node as { fx?: number; fy?: number; x?: number; y?: number };
                n.fx = n.x;
                n.fy = n.y;
              }}
            />
          )}
        </div>

        {/* 节点详情面板 */}
        <div className="col-span-3 rounded-card border border-th-border bg-elevated p-4 space-y-3" style={{ height: 600, overflowY: 'auto' }}>
          <div className="flex items-center gap-2">
            <Tag size={14} className="text-accent" />
            <span className="text-sm font-semibold text-th-text-primary">节点详情</span>
          </div>
          {selectedNode ? (
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-th-text-primary v15-mono break-all">{selectedNode.name}</div>
                <div className="text-[10px] text-th-text-muted v15-mono mt-1">{selectedNode.id}</div>
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-th-border">
                <div>
                  <div className="text-[10px] uppercase text-th-text-muted">类型</div>
                  <div className="text-th-text-primary text-xs">{selectedNode.type || '-'}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase text-th-text-muted">关联文档</div>
                  <div className="text-th-text-primary inline-flex items-center gap-1">
                    <FileText size={11} />{selectedNode.doc_count}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase text-th-text-muted">社区</div>
                  <div className="inline-flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colorForNode(selectedNode) }} />
                    <span className="text-th-text-primary text-xs v15-mono">{selectedNode.community}</span>
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase text-th-text-muted">中心性</div>
                  <div className="text-th-text-primary text-xs v15-mono">{selectedNode.centrality}</div>
                </div>
              </div>
              {data && (
                <div className="pt-2 border-t border-th-border">
                  <div className="text-[10px] uppercase text-th-text-muted mb-2">直接关系 ({neighborIds.size - 1})</div>
                  <div className="space-y-1 max-h-72 overflow-y-auto">
                    {data.edges
                      .filter((e) => {
                        const s = typeof e.source === 'string' ? e.source : (e.source as { id: string }).id;
                        const t = typeof e.target === 'string' ? e.target : (e.target as { id: string }).id;
                        return s === selectedNode.id || t === selectedNode.id;
                      })
                      .slice(0, 30)
                      .map((e, i) => {
                        const src = typeof e.source === 'string' ? e.source : (e.source as { id: string }).id;
                        const tgt = typeof e.target === 'string' ? e.target : (e.target as { id: string }).id;
                        const other = src === selectedNode.id ? tgt : src;
                        const direction = src === selectedNode.id ? '→' : '←';
                        return (
                          <div
                            key={i}
                            className="text-xs flex items-center gap-1.5 cursor-pointer hover:bg-hover/40 px-1 py-0.5 rounded"
                            onClick={() => {
                              const node = data.nodes.find((n) => n.id === other);
                              if (node) setSelectedNode(node);
                            }}
                          >
                            <span className="text-th-text-muted v15-mono w-3">{direction}</span>
                            <span className="text-th-text-secondary truncate">{other}</span>
                            <span className={`text-[10px] v15-mono ml-auto ${e.inferred ? 'text-accent' : 'text-th-text-muted'}`}>
                              {e.relation || '关联'}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}
            </div>
          ) : selectedCommunity != null && data ? (
            <div className="space-y-2 text-sm">
              <div className="text-th-text-primary">社区 #{selectedCommunity}</div>
              <div className="text-xs text-th-text-muted">该社区共 {data.nodes.filter((n) => n.community === selectedCommunity).length} 个节点</div>
              <div className="space-y-1 max-h-[480px] overflow-y-auto pt-2 border-t border-th-border">
                {data.nodes
                  .filter((n) => n.community === selectedCommunity)
                  .sort((a, b) => b.centrality - a.centrality)
                  .map((n) => (
                    <div
                      key={n.id}
                      onClick={() => setSelectedNode(n)}
                      className="text-xs flex items-center gap-2 cursor-pointer hover:bg-hover/40 px-1 py-1 rounded"
                    >
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: colorForCommunity(n.community) }} />
                      <span className="text-th-text-primary truncate">{n.name}</span>
                      <span className="text-[10px] v15-mono text-th-text-muted ml-auto">{n.centrality.toFixed(3)}</span>
                    </div>
                  ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-th-text-muted leading-relaxed">
              <div className="mb-2">默认全局淡显</div>
              <div className="text-[11px]">• 上方 chip 选择社区聚焦</div>
              <div className="text-[11px]">• 点击节点 → 仅显示该节点 + 1-hop 邻居</div>
              <div className="text-[11px]">• 搜索节点 → 命中高亮</div>
              <div className="text-[11px]">• 双击空白 / 点重置 → 回全局</div>
            </div>
          )}
        </div>
      </div>

      {/* 底部图例 */}
      <div className="flex items-center gap-4 text-[11px] v15-mono text-th-text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 border-t" style={{ borderColor: 'rgba(163, 190, 140, 0.7)' }} />
          已知关系
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-4 border-t border-dashed" style={{ borderColor: 'rgba(136, 192, 208, 0.85)' }} />
          推理关系 (Inferer Agent)
        </span>
        <span>● 节点大小 = 度中心性</span>
        <span>颜色 = {colorMode === 'community' ? '社区 (Louvain)' : colorMode === 'type' ? '实体类型' : '中心性梯度'}</span>
      </div>
    </div>
  );
}
