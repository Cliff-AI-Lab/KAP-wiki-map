/**
 * @file GraphPage.tsx
 * @description 知识图谱页面 — V10 Raycast 深暗精工风 + 深度美化
 *
 * 核心理念：按知识体系分支逐层展开，图谱沿体系分支生长。
 * 图谱是知识治理的核心可视化——实体关系清晰展示是产品价值体现。
 *
 * V10 美化:
 * - 4层节点渲染: 外发光环 + 渐变主体 + 内高光 + 清晰标签
 * - 渐变连线: 源色→目标色 + 动态宽度 + 实心箭头
 * - 交互增强: 点击发光轨迹 + 选中脉冲 + 30fps动画
 * - Raycast UI: 控制面板全面升级
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  Network, ArrowRight, Maximize2, ZoomIn, ZoomOut,
  RefreshCw, FolderTree, FileText, GitBranch, Eye, EyeOff,
} from 'lucide-react';
import { Badge, Button, SkeletonCard } from '@/components/ui';
import { fetchGraphOverview, fetchDomains } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';
import type { GraphOverview, GraphNode, DomainInfo } from '@/services/api';

/* ── 实体类型颜色 (统一 CSS 变量, V11.2) ── */
const _css = getComputedStyle(document.documentElement);
const _cv = (v: string, fb: string) => _css.getPropertyValue(v).trim() || fb;
const TYPE_COLORS: Record<string, string> = {
  Person: _cv('--entity-person', '#f472b6'),
  Department: _cv('--entity-department', '#55b3ff'),
  Project: _cv('--entity-project', '#ffbc33'),
  Product: _cv('--entity-product', '#5fc992'),
  Process: _cv('--entity-process', '#c084fc'),
  Regulation: _cv('--entity-regulation', '#929799'),
  Equipment: _cv('--entity-equipment', '#fb923c'),
  Material: _cv('--entity-material', '#FF6363'),
  Standard: _cv('--entity-standard', '#818cf8'),
  Location: _cv('--entity-location', '#34d399'),
  Entity: _cv('--entity-default', '#55b3ff'),
};

const TYPE_LABELS: Record<string, string> = {
  Person: '人物', Department: '部门', Project: '项目', Product: '产品',
  Process: '流程工艺', Regulation: '制度法规', Equipment: '设备装置',
  Material: '物料', Standard: '标准规范', Location: '位置区域', Entity: '实体',
};

function getColor(type: string): string {
  return TYPE_COLORS[type] || '#55b3ff';
}

/** 辅助: 给颜色加 alpha */
function colorAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** 辅助: 提亮颜色 */
function lighten(hex: string, pct: number): string {
  const r = Math.min(255, parseInt(hex.slice(1, 3), 16) + pct);
  const g = Math.min(255, parseInt(hex.slice(3, 5), 16) + pct);
  const b = Math.min(255, parseInt(hex.slice(5, 7), 16) + pct);
  return `rgb(${r},${g},${b})`;
}

type ViewMode = 'entity' | 'document';

interface ForceNode extends GraphNode {
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  doc_count?: number;
  doc_ids?: string[];
  entity_count?: number;
}

/** V8: 获取文档视角图谱数据 */
async function fetchGraphDocView(projectId?: string, domainId?: string) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (domainId) params.set('domain_id', domainId);
  const resp = await fetch(`/api/v1/knowledge/graph-doc-view?${params}`);
  if (!resp.ok) throw new Error('加载文档视角失败');
  return resp.json();
}

/**
 * 知识图谱页面组件 — V10 深度美化版
 */
export default function GraphPage() {
  const { currentProject } = useProject();
  const [rawData, setRawData] = useState<GraphOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<ForceNode | null>(null);
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set());
  const [highlightEdges, setHighlightEdges] = useState<Set<string>>(new Set());
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [viewMode, setViewMode] = useState<ViewMode>('entity');
  const [branches, setBranches] = useState<DomainInfo[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const animFrameRef = useRef<number>(0);
  const tickRef = useRef(0);

  /* 加载知识体系分支 */
  useEffect(() => {
    if (!currentProject?.id) return;
    fetchDomains(currentProject.id)
      .then((resp) => {
        const roots = resp.domains.filter((d: DomainInfo) => !d.parent_id);
        const secondLevel = resp.domains.filter((d: DomainInfo) =>
          roots.some((r: DomainInfo) => r.domain_id === d.parent_id)
        );
        setBranches(secondLevel.length > 0 ? secondLevel : roots);
      })
      .catch(() => {});
  }, [currentProject?.id]);

  /** 加载图谱数据 */
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setHighlightNodes(new Set());
    setHighlightEdges(new Set());
    try {
      if (viewMode === 'entity') {
        const data = await fetchGraphOverview(undefined, currentProject?.id, selectedBranch || undefined);
        setRawData(data);
      } else {
        const data = await fetchGraphDocView(currentProject?.id, selectedBranch || undefined);
        setRawData(data);
      }
    } catch (e: any) {
      setError(e.message || '加载失败');
      setRawData({ node_count: 0, edge_count: 0, nodes: [], edges: [] });
    } finally {
      setLoading(false);
    }
  }, [currentProject?.id, selectedBranch, viewMode]);

  useEffect(() => { loadData(); }, [loadData]);

  /* 画布尺寸监听 */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setDimensions({ width: Math.max(width, 400), height: Math.max(height, 300) });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  /* 选中节点时的 30fps 动画循环 (脉冲效果) */
  useEffect(() => {
    if (!selectedNode) {
      cancelAnimationFrame(animFrameRef.current);
      return;
    }
    let lastTime = 0;
    const animate = (time: number) => {
      if (time - lastTime > 33) { // ~30fps
        tickRef.current++;
        graphRef.current?.refresh();
        lastTime = time;
      }
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animFrameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [selectedNode]);

  /* 数据转换 (带类型过滤) */
  const graphData = useMemo(() => {
    if (!rawData) return { nodes: [], links: [] };
    const filteredNodes = rawData.nodes
      .filter((n: any) => !hiddenTypes.has(n.type))
      .map((n: any) => ({ ...n }));
    const nodeIds = new Set(filteredNodes.map((n: any) => n.id));
    return {
      nodes: filteredNodes,
      links: rawData.edges
        .filter((e: any) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e: any) => ({
          source: e.source,
          target: e.target,
          relation: e.relation || '',
          weight: e.weight || 1,
          shared_entities: e.shared_entities || [],
        })),
    };
  }, [rawData, hiddenTypes]);

  /* 类型统计 */
  const typeDistribution = useMemo(() => {
    if (viewMode === 'document' || !rawData) return {};
    const counts: Record<string, number> = {};
    for (const n of rawData.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
    return counts;
  }, [rawData, viewMode]);

  /** 节点点击 */
  const handleNodeClick = useCallback(
    (node: ForceNode) => {
      if (selectedNode?.id === node.id) {
        setSelectedNode(null);
        setHighlightNodes(new Set());
        setHighlightEdges(new Set());
        return;
      }
      setSelectedNode(node);
      const hn = new Set<string>([node.id]);
      const he = new Set<string>();
      for (const link of graphData.links) {
        const s = typeof link.source === 'object' ? (link.source as any).id : link.source;
        const t = typeof link.target === 'object' ? (link.target as any).id : link.target;
        if (s === node.id || t === node.id) {
          hn.add(s);
          hn.add(t);
          he.add(`${s}-${t}`);
        }
      }
      setHighlightNodes(hn);
      setHighlightEdges(he);
    },
    [selectedNode, graphData]
  );

  /** ═══ V10: 4层节点渲染 ═══ */
  const paintNode = useCallback(
    (node: ForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.label || node.id;
      const x = node.x || 0;
      const y = node.y || 0;
      const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id);
      const isSelected = selectedNode?.id === node.id;
      const alpha = isHighlighted ? 1 : 0.12;

      if (viewMode === 'document') {
        /* 文档视角: 圆角矩形 */
        const entityCount = (node as any).entity_count || 1;
        const w = Math.max(20, Math.min(40, entityCount * 4)) / globalScale;
        const h = w * 0.65;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = isSelected ? '#55b3ff' : '#3b82f6';
        const rx = 3 / globalScale;
        ctx.beginPath();
        ctx.roundRect(x - w / 2, y - h / 2, w, h, rx);
        ctx.fill();
        if (globalScale > 0.5) {
          ctx.font = `${Math.max(10 / globalScale, 2)}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillStyle = isHighlighted ? '#eeeeee' : '#555a5e';
          ctx.fillText(label.length > 10 ? label.slice(0, 10) + '…' : label, x, y + h / 2 + 3 / globalScale);
        }
        ctx.globalAlpha = 1;
        return;
      }

      /* ── 实体视角: V10 4层渲染 ── */
      const docCount = (node as any).doc_count || 0;
      const r = Math.max(5, Math.min(14, 5 + docCount * 1.5)) / globalScale;
      const color = getColor(node.type);

      ctx.globalAlpha = alpha;

      /* Layer 1: 外发光环 (仅 zoom > 0.4 且高亮时) */
      if (isHighlighted && globalScale > 0.4) {
        const glow = ctx.createRadialGradient(x, y, r, x, y, r * 2.5);
        glow.addColorStop(0, colorAlpha(color, 0.20));
        glow.addColorStop(1, colorAlpha(color, 0));
        ctx.beginPath();
        ctx.arc(x, y, r * 2.5, 0, 2 * Math.PI);
        ctx.fillStyle = glow;
        ctx.fill();
      }

      /* Layer 2: 渐变主体 (中心亮→边缘暗, 3D质感) */
      const bodyGrad = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, 0, x, y, r);
      bodyGrad.addColorStop(0, lighten(color, 50));
      bodyGrad.addColorStop(1, color);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = bodyGrad;
      ctx.fill();

      /* Layer 3: 内高光环 (白色描边, 80%半径) */
      ctx.beginPath();
      ctx.arc(x, y, r * 0.8, 0, 2 * Math.PI);
      ctx.strokeStyle = 'rgba(255,255,255,0.12)';
      ctx.lineWidth = 0.5 / globalScale;
      ctx.stroke();

      /* 选中节点: 脉冲光环 */
      if (isSelected) {
        const pulse = Math.sin(tickRef.current * 0.15) * 2 / globalScale;
        ctx.beginPath();
        ctx.arc(x, y, r + 3 / globalScale + pulse, 0, 2 * Math.PI);
        ctx.strokeStyle = colorAlpha(color, 0.5);
        ctx.lineWidth = 1.5 / globalScale;
        ctx.stroke();
      }

      /* Layer 4: 标签 (缩放 > 0.5 才显示) */
      if (globalScale > 0.5) {
        const fontSize = Math.max(10 / globalScale, 2);
        ctx.font = `500 ${fontSize}px "DM Sans", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        /* 暗色阴影提升可读性 */
        ctx.shadowColor = 'rgba(7,8,10,0.8)';
        ctx.shadowBlur = 3 / globalScale;
        ctx.fillStyle = isHighlighted ? '#eeeeee' : '#555a5e';

        const displayLabel = label.length > 10 ? label.slice(0, 10) + '…' : label;
        ctx.fillText(displayLabel, x, y + r + 3 / globalScale);

        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
      }

      ctx.globalAlpha = 1;
    },
    [highlightNodes, selectedNode, viewMode]
  );

  /** ═══ V10: 渐变连线 + 实心箭头 + 药丸标签 ═══ */
  const paintLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const s = typeof link.source === 'object' ? link.source : { x: 0, y: 0, id: link.source, type: '' };
      const t = typeof link.target === 'object' ? link.target : { x: 0, y: 0, id: link.target, type: '' };
      const key = `${s.id}-${t.id}`;
      const isHighlighted = highlightEdges.size === 0 || highlightEdges.has(key);
      const weight = link.weight || 1;

      /* 动态宽度: 0.5px(弱) → 3px(强) */
      const minW = 0.5 / globalScale;
      const maxW = 3 / globalScale;
      const baseWidth = minW + (maxW - minW) * Math.min(weight / 8, 1);
      const lineWidth = isHighlighted ? baseWidth * 1.4 : baseWidth;

      /* 渐变连线: 源色 → 目标色 */
      const sColor = getColor(s.type || 'Entity');
      const tColor = getColor(t.type || 'Entity');
      const baseAlpha = isHighlighted ? 0.7 : 0.25;

      const grad = ctx.createLinearGradient(s.x, s.y, t.x, t.y);
      grad.addColorStop(0, colorAlpha(sColor, baseAlpha));
      grad.addColorStop(1, colorAlpha(tColor, baseAlpha));

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = grad;
      ctx.lineWidth = lineWidth;
      ctx.stroke();

      /* 高亮时的发光轨迹 */
      if (isHighlighted && highlightEdges.size > 0) {
        ctx.save();
        ctx.shadowColor = sColor;
        ctx.shadowBlur = 6 / globalScale;
        ctx.lineWidth = lineWidth * 2;
        ctx.globalAlpha = 0.15;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.stroke();
        ctx.restore();
      }

      /* 实心三角箭头 (实体视角, 2/3 位置) */
      if (viewMode === 'entity') {
        const angle = Math.atan2(t.y - s.y, t.x - s.x);
        const arrowSize = 4 / globalScale;
        const tipX = s.x + (t.x - s.x) * 0.65;
        const tipY = s.y + (t.y - s.y) * 0.65;

        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - arrowSize * Math.cos(angle - 0.4), tipY - arrowSize * Math.sin(angle - 0.4));
        ctx.lineTo(tipX - arrowSize * Math.cos(angle + 0.4), tipY - arrowSize * Math.sin(angle + 0.4));
        ctx.closePath();
        ctx.fillStyle = colorAlpha(sColor, isHighlighted ? 0.6 : 0.25);
        ctx.fill();
      }

      /* 关系标签 — 暗色药丸背景 (缩放 > 0.8) */
      if (globalScale > 0.8 && isHighlighted) {
        const mx = (s.x + t.x) / 2;
        const my = (s.y + t.y) / 2;
        const fontSize = Math.max(8 / globalScale, 1.5);
        const labelText = viewMode === 'document'
          ? (weight > 1 ? `共享${weight}实体` : '共享')
          : (link.relation || '');

        if (labelText) {
          ctx.font = `500 ${fontSize}px "DM Sans", sans-serif`;
          const tw = ctx.measureText(labelText).width;
          const padX = 4 / globalScale;
          const padY = 2 / globalScale;

          /* 药丸背景 */
          ctx.fillStyle = 'rgba(7, 8, 10, 0.85)';
          ctx.beginPath();
          ctx.roundRect(mx - tw / 2 - padX, my - fontSize / 2 - padY, tw + padX * 2, fontSize + padY * 2, 3 / globalScale);
          ctx.fill();

          /* 文字 */
          ctx.fillStyle = isHighlighted ? '#eeeeee' : '#929799';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(labelText, mx, my);
        }
      }
    },
    [highlightEdges, viewMode]
  );

  /* 缩放控制 */
  const zoomIn = () => graphRef.current?.zoom(graphRef.current.zoom() * 1.3, 300);
  const zoomOut = () => graphRef.current?.zoom(graphRef.current.zoom() * 0.7, 300);
  const zoomFit = () => graphRef.current?.zoomToFit(400, 60);

  /* 类型过滤切换 */
  const toggleType = (type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleAllTypes = () => {
    if (hiddenTypes.size > 0) setHiddenTypes(new Set());
    else setHiddenTypes(new Set(Object.keys(typeDistribution)));
  };

  /* 选中节点的邻接边 */
  const selectedEdges = useMemo(() => {
    if (!selectedNode) return [];
    return graphData.links.filter((l: any) => {
      const s = typeof l.source === 'object' ? (l.source as any).id : l.source;
      const t = typeof l.target === 'object' ? (l.target as any).id : l.target;
      return s === selectedNode.id || t === selectedNode.id;
    });
  }, [selectedNode, graphData]);

  /* ═══ Render ═══ */
  return (
    <div className="p-6 h-full flex flex-col gap-4 page-enter">
      {/* 页头 — Raycast 风格 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-display flex items-center gap-2">
            <Network className="text-accent" size={22} />
            知识图谱
          </h1>
          <p className="text-sm text-th-text-muted mt-1">
            {viewMode === 'entity' ? '按知识体系分支浏览实体关系网络' : '按文档关联查看共享实体网络'}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadData} icon={<RefreshCw size={14} />}>
          刷新
        </Button>
      </div>

      {/* 统计行 — Raycast 卡片 */}
      <div className="grid grid-cols-3 gap-3 stagger-children">
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full bg-accent" />
            <span className="text-label">{viewMode === 'entity' ? '实体节点' : '文档节点'}</span>
          </div>
          <div className="text-2xl font-semibold font-display">{graphData.nodes.length}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#5fc992' }} />
            <span className="text-label">{viewMode === 'entity' ? '关系连线' : '文档关联'}</span>
          </div>
          <div className="text-2xl font-semibold font-display">{graphData.links.length}</div>
        </div>
        <div className="glass-card rounded-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#c084fc' }} />
            <span className="text-label">{viewMode === 'entity' ? '实体类型' : '文档总数'}</span>
          </div>
          <div className="text-2xl font-semibold font-display">
            {viewMode === 'entity' ? Object.keys(typeDistribution).length : graphData.nodes.length}
          </div>
        </div>
      </div>

      {loading && (
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, i) => (<SkeletonCard key={i} />))}
        </div>
      )}
      {error && <div className="text-sm text-[var(--color-error)]">{error}</div>}

      {/* 图谱主区域 */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* ── 左侧控制面板 ── */}
        <div className="w-60 shrink-0 space-y-3 overflow-y-auto">
          {/* 视角切换 */}
          <div className="glass-card rounded-card p-4">
            <div className="text-label mb-2 flex items-center gap-1">
              <GitBranch size={11} /> 图谱视角
            </div>
            <div className="flex gap-1">
              <button onClick={() => setViewMode('entity')}
                className={`pill-tab flex-1 justify-center ${viewMode === 'entity' ? 'active' : ''}`}>
                <Network size={11} /> 实体
              </button>
              <button onClick={() => setViewMode('document')}
                className={`pill-tab flex-1 justify-center ${viewMode === 'document' ? 'active' : ''}`}>
                <FileText size={11} /> 文档
              </button>
            </div>
          </div>

          {/* 知识体系分支 */}
          {branches.length > 0 && (
            <div className="glass-card rounded-card p-4">
              <div className="text-label mb-2 flex items-center gap-1">
                <FolderTree size={11} /> 知识体系分支
              </div>
              <div className="space-y-0.5">
                <button onClick={() => setSelectedBranch('')}
                  className={`pill-tab w-full text-left text-xs ${!selectedBranch ? 'active' : ''}`}>
                  全部分支
                </button>
                {branches.map((b) => (
                  <button key={b.domain_id}
                    onClick={() => setSelectedBranch(b.domain_id === selectedBranch ? '' : b.domain_id)}
                    className={`pill-tab w-full text-left text-xs ${selectedBranch === b.domain_id ? 'active' : ''}`}>
                    {b.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 类型图例 (可切换显隐) */}
          {viewMode === 'entity' && Object.keys(typeDistribution).length > 0 && (
            <div className="glass-card rounded-card p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-label">实体类型</span>
                <button onClick={toggleAllTypes} className="text-[9px] text-th-text-muted hover:text-th-text-primary transition-colors">
                  {hiddenTypes.size > 0 ? '显示全部' : '隐藏全部'}
                </button>
              </div>
              <div className="space-y-1">
                {Object.entries(typeDistribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => {
                    const isHidden = hiddenTypes.has(type);
                    return (
                      <button key={type}
                        onClick={() => toggleType(type)}
                        className={`flex items-center gap-2 w-full text-left py-0.5 px-1 rounded transition-opacity ${isHidden ? 'opacity-30' : 'opacity-100'}`}>
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: getColor(type) }} />
                        <span className="text-xs flex-1 text-th-text-secondary">
                          {TYPE_LABELS[type] || type}
                        </span>
                        <span className="text-[10px] text-th-text-muted tabular-nums">{count}</span>
                        {isHidden ? <EyeOff size={10} className="text-th-text-muted" /> : <Eye size={10} className="text-th-text-muted" />}
                      </button>
                    );
                  })}
              </div>
              {/* 可见数统计 */}
              <div className="mt-2 pt-2 text-[10px] text-th-text-muted" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                {graphData.nodes.length} / {rawData?.nodes.length ?? 0} 节点可见
              </div>
            </div>
          )}

          {/* 缩放控制 */}
          <div className="glass-card rounded-card p-3">
            <div className="flex items-center justify-center gap-1">
              <button onClick={zoomOut} className="p-1.5 rounded-btn hover:bg-hover transition-colors">
                <ZoomOut size={14} className="text-th-text-muted" />
              </button>
              <button onClick={zoomFit} className="p-1.5 rounded-btn hover:bg-hover transition-colors">
                <Maximize2 size={14} className="text-th-text-muted" />
              </button>
              <button onClick={zoomIn} className="p-1.5 rounded-btn hover:bg-hover transition-colors">
                <ZoomIn size={14} className="text-th-text-muted" />
              </button>
            </div>
          </div>

          {/* 选中节点详情 */}
          {selectedNode && (
            <div className="glass-card rounded-card p-4">
              <div className="text-label mb-2">
                {viewMode === 'entity' ? '选中实体' : '选中文档'}
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  {viewMode === 'entity' && (
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: getColor(selectedNode.type), boxShadow: `0 0 6px ${colorAlpha(getColor(selectedNode.type), 0.4)}` }} />
                  )}
                  {viewMode === 'document' && <FileText size={14} className="text-accent" />}
                  <span className="text-sm font-medium text-th-text-primary truncate">
                    {selectedNode.label}
                  </span>
                </div>

                {viewMode === 'entity' && (
                  <>
                    <Badge variant="info" size="sm">{TYPE_LABELS[selectedNode.type] || selectedNode.type}</Badge>

                    {(selectedNode as any).doc_ids && (selectedNode as any).doc_ids.length > 0 && (
                      <div className="pt-2 mt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                        <div className="text-[10px] mb-1 flex items-center gap-1 text-th-text-muted">
                          <FileText size={9} /> 关联文档 ({(selectedNode as any).doc_ids.length})
                        </div>
                        <div className="space-y-0.5 max-h-28 overflow-auto">
                          {((selectedNode as any).doc_ids as string[]).map((docId: string) => (
                            <a key={docId}
                              href={`/projects/${currentProject?.id}/documents/${docId}`}
                              className="block text-[10px] px-2 py-1 rounded-btn hover:bg-hover truncate text-th-text-secondary">
                              {docId}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {viewMode === 'document' && (selectedNode as any).entity_count > 0 && (
                  <div className="text-xs text-th-text-muted">包含 {(selectedNode as any).entity_count} 个实体</div>
                )}

                {selectedEdges.length > 0 && (
                  <div className="pt-2 mt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <div className="text-[10px] mb-1 text-th-text-muted">
                      {viewMode === 'entity' ? `关联关系 (${selectedEdges.length})` : `关联文档 (${selectedEdges.length})`}
                    </div>
                    <div className="space-y-0.5 max-h-36 overflow-auto">
                      {selectedEdges.map((e: any, i: number) => {
                        const src = typeof e.source === 'object' ? e.source : { id: e.source, label: e.source };
                        const tgt = typeof e.target === 'object' ? e.target : { id: e.target, label: e.target };
                        const other = src.id === selectedNode.id ? tgt : src;
                        const direction = src.id === selectedNode.id ? '→' : '←';
                        return (
                          <div key={i} className="text-[10px] flex items-center gap-1 text-th-text-secondary">
                            <ArrowRight size={9} className="shrink-0 text-th-text-muted" />
                            <span className="truncate">
                              {direction} {viewMode === 'document' ? '' : `${e.relation}: `}{other.label || other.id}
                            </span>
                            {viewMode === 'document' && <span className="text-th-text-muted shrink-0">({e.weight})</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── 力导向图画布 ── */}
        <div className="flex-1 relative overflow-hidden rounded-card" style={{ boxShadow: 'var(--shadow-card)' }}>
          <div ref={containerRef} className="absolute inset-0" style={{ background: 'rgba(7,8,10,0.5)' }}>
            {!loading && graphData.nodes.length > 0 && (
              <ForceGraph2D
                ref={graphRef}
                graphData={graphData}
                width={dimensions.width}
                height={dimensions.height}
                backgroundColor="transparent"
                nodeCanvasObject={paintNode}
                nodePointerAreaPaint={(node: ForceNode, color: string, ctx: CanvasRenderingContext2D) => {
                  ctx.beginPath();
                  ctx.arc(node.x || 0, node.y || 0, 10, 0, 2 * Math.PI);
                  ctx.fillStyle = color;
                  ctx.fill();
                }}
                linkCanvasObject={paintLink}
                onNodeClick={handleNodeClick}
                onBackgroundClick={() => {
                  setSelectedNode(null);
                  setHighlightNodes(new Set());
                  setHighlightEdges(new Set());
                }}
                cooldownTicks={80}
                d3AlphaDecay={0.02}
                d3VelocityDecay={0.25}
                enableNodeDrag={true}
                enableZoomInteraction={true}
              />
            )}
            {!loading && graphData.nodes.length === 0 && (
              <div className="flex items-center justify-center h-full text-th-text-muted">
                <div className="text-center">
                  <Network size={48} className="mx-auto mb-4 opacity-20" />
                  <p className="text-sm">暂无图谱数据</p>
                  <p className="text-xs mt-2 text-th-text-muted">
                    {selectedBranch ? '该分支下暂无数据，请先导入相关文档' : '请先导入文档以构建知识图谱'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
