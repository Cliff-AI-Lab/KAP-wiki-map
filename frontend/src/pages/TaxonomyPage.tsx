/**
 * @file TaxonomyPage.tsx
 * @description 知识体系管理页面 — 思维导图风格的四级知识分类树
 *
 * 主要功能：
 * - 以缩进树形结构展示 L0~L3 四级知识体系（部门/大领域 -> 业务子领域 -> 知识分类 -> 知识条目）
 * - 支持展开/折叠、全部展开/折叠操作
 * - 节点可选中、可编辑名称（双击编辑）
 * - 统计卡片展示各层级节点数和关联文档数
 * - 数据来源：fetchDomains(projectId) 后端接口
 *
 * V6: 纯粹展示项目行业模板的四级知识体系，移除全局 Skills 面板。
 */

import { useState, useEffect } from 'react';
import {
  FolderTree,
  ChevronRight,
  ChevronDown,
  Plus,
  Edit2,
  Trash2,
  FileText,
  Download,
  Sparkles,
} from 'lucide-react';
import { Card, Badge, Button } from '@/components/ui';
import { fetchDomains } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';

/** 知识体系树节点 */
interface TaxonomyNode {
  /** 节点唯一标识（对应 domain_id） */
  id: string;
  /** 节点显示名称 */
  name: string;
  /** 层级标识：L0=部门/大领域, L1=业务子领域, L2=知识分类, L3=知识条目 */
  level: 'L0' | 'L1' | 'L2' | 'L3';
  /** 该节点下关联的文档数量 */
  doc_count: number;
  /** 子节点列表 */
  children?: TaxonomyNode[];
  /** 节点颜色（仅 L0 层级分配） */
  color?: string;
}

/** 各层级的展示配置（缩进、字体、连线粗细）— Linear 克制风 */
const LEVEL_CONFIG = {
  L0: { label: '部门/大领域', indent: 0, nodeClass: 'text-[15px] font-[590]', lineWidth: 2 },
  L1: { label: '业务子领域', indent: 48, nodeClass: 'text-[14px] font-[510]', lineWidth: 1 },
  L2: { label: '知识分类', indent: 96, nodeClass: 'text-[13px] font-[400]', lineWidth: 1 },
  L3: { label: '知识条目', indent: 144, nodeClass: 'text-[13px] font-[400]', lineWidth: 1 },
};

/* 金色单色系 — 主色+灰阶层次，克制不花哨 */
const DEFAULT_COLORS = [
  'var(--color-accent)',          // 金色
  'var(--color-text-muted)',      // 灰
  'var(--color-accent-light)',    // 浅金
  'var(--color-text-quaternary)', // 深灰
  'var(--color-accent)',          // 金色循环
  'var(--color-text-muted)',
  'var(--color-accent-light)',
];

/** 将后端扁平的 DomainInfo[] 列表转换为带层级的 TaxonomyNode[] 树结构 */
function domainToTree(domains: any[]): TaxonomyNode[] {
  if (!domains || domains.length === 0) return [];
  const levels = ['L0', 'L1', 'L2', 'L3'] as const;
  const map = new Map<string, TaxonomyNode>();
  const roots: TaxonomyNode[] = [];

  for (const d of domains) {
    map.set(d.domain_id, {
      id: d.domain_id,
      name: d.name,
      level: 'L1',
      doc_count: d.doc_count || 0,
      children: [],
    });
  }

  // Build tree
  for (const d of domains) {
    const node = map.get(d.domain_id)!;
    if (d.parent_id && map.has(d.parent_id)) {
      map.get(d.parent_id)!.children!.push(node);
    } else {
      roots.push(node);
    }
  }

  // Assign levels and colors by depth
  function assignDepth(nodes: TaxonomyNode[], depth: number) {
    nodes.forEach((n, i) => {
      n.level = levels[Math.min(depth, 3)] ?? 'L3';
      if (depth === 0) n.color = DEFAULT_COLORS[i % DEFAULT_COLORS.length];
      if (n.children && n.children.length > 0) {
        assignDepth(n.children, depth + 1);
      }
    });
  }
  assignDepth(roots, 0);
  return roots;
}

/**
 * 知识体系管理页面组件
 *
 * 以思维导图风格展示项目的四级知识分类树（L0~L3），支持节点展开/折叠、
 * 选中查看详情、编辑名称等操作。顶部统计卡片汇总各层级节点数和关联文档数。
 */
export default function TaxonomyPage() {
  const { currentProject } = useProject();
  const [taxonomy, setTaxonomy] = useState<TaxonomyNode[]>([]); // 知识体系树数据
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set()); // 已展开节点ID集合
  const [selectedNode, setSelectedNode] = useState<string | null>(null); // 当前选中节点ID
  const [editingNode, setEditingNode] = useState<string | null>(null); // 当前编辑中的节点ID
  const [editingName, setEditingName] = useState(''); // 编辑中的节点名称
  const [loading, setLoading] = useState(true); // 数据加载中

  /** 从后端加载知识体系数据并构建树结构 */
  const loadData = async () => {
    setLoading(true);
    try {
      const resp = await fetchDomains(currentProject?.id);
      const tree = domainToTree(resp.domains);
      setTaxonomy(tree);
      if (tree.length > 0) {
        setExpandedNodes(new Set(tree.map((n) => n.id)));
      }
    } catch {
      setTaxonomy([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentProject?.id]);

  /** 切换节点展开/折叠 */
  const toggleExpand = (nodeId: string) => {
    const s = new Set(expandedNodes);
    s.has(nodeId) ? s.delete(nodeId) : s.add(nodeId);
    setExpandedNodes(s);
  };

  /** 展开所有节点 */
  const expandAll = () => {
    const all = new Set<string>();
    const collect = (nodes: TaxonomyNode[]) =>
      nodes.forEach((n) => {
        all.add(n.id);
        if (n.children) collect(n.children);
      });
    collect(taxonomy);
    setExpandedNodes(all);
  };

  /** 折叠所有节点 */
  const collapseAll = () => setExpandedNodes(new Set());

  /** 开始编辑节点名称 */
  const startEdit = (node: TaxonomyNode) => {
    setEditingNode(node.id);
    setEditingName(node.name);
  };
  /** 保存编辑（当前仅关闭编辑状态） */
  const saveEdit = () => setEditingNode(null);

  /** 递归渲染知识体系树节点（含缩进连线、展开/折叠、编辑、文档计数） */
  const renderNode = (node: TaxonomyNode, parentColor?: string, _isLast = false) => {
    const config = LEVEL_CONFIG[node.level];
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const isSelected = selectedNode === node.id;
    const isEditing = editingNode === node.id;
    const nodeColor = node.color || parentColor || DEFAULT_COLORS[0];

    return (
      <div key={node.id} className="relative">
        {node.level !== 'L0' && (
          <div
            className="absolute top-4 bg-th-border"
            style={{ left: config.indent - 30, width: 25, height: 2 }}
          />
        )}
        <div
          className="relative flex items-center gap-2 py-2 group"
          style={{ paddingLeft: config.indent }}
        >
          {hasChildren ? (
            <button
              onClick={() => toggleExpand(node.id)}
              className="w-5 h-5 flex items-center justify-center rounded hover:bg-hover text-th-text-muted"
            >
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          ) : (
            <div className="w-5 h-5 flex items-center justify-center">
              <div className="w-1.5 h-1.5 rounded-full bg-th-text-muted opacity-40" />
            </div>
          )}
          <div
            className={`flex items-center gap-3 px-3 py-1.5 rounded-btn cursor-pointer transition-all border-l-2 ${
              isSelected
                ? 'border-l-accent bg-[rgba(94,106,210,0.06)]'
                : 'border-l-transparent hover:bg-hover hover:border-l-[rgba(255,255,255,0.08)]'
            }`}
            onClick={() => setSelectedNode(isSelected ? null : node.id)}
          >
            {isEditing ? (
              <input
                type="text"
                value={editingName}
                onChange={(e) => setEditingName(e.target.value)}
                onBlur={saveEdit}
                onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
                autoFocus
                className="px-2 py-1 rounded border bg-base border-th-border text-sm"
              />
            ) : (
              <span
                className={`${config.nodeClass} ${
                  node.level === 'L0' ? 'text-th-text-primary' : 'text-th-text-secondary'
                }`}
              >
                {node.name}
              </span>
            )}
            <Badge variant="neutral" size="sm" className="opacity-70">
              <FileText size={12} className="mr-1" />
              {node.doc_count}
            </Badge>
            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 ml-2 transition-opacity">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  startEdit(node);
                }}
                className="p-1 rounded hover:bg-hover"
              >
                <Edit2 size={14} className="text-th-text-muted" />
              </button>
              {hasChildren && (
                <button
                  onClick={(e) => e.stopPropagation()}
                  className="p-1 rounded hover:bg-hover"
                >
                  <Plus size={14} className="text-th-text-muted" />
                </button>
              )}
            </div>
          </div>
        </div>
        {hasChildren && isExpanded && (
          <div className="relative">
            <div
              className="absolute bg-th-border"
              style={{
                left:
                  config.indent +
                  (node.children?.[0] ? LEVEL_CONFIG[node.children[0].level].indent : 60) -
                  30,
                top: 0,
                bottom: 16,
                width: 2,
              }}
            />
            {node.children!.map((child, idx) =>
              renderNode(child, nodeColor, idx === node.children!.length - 1)
            )}
          </div>
        )}
      </div>
    );
  };

  /** 递归统计树中所有节点总数 */
  const countNodes = (nodes: TaxonomyNode[]): number =>
    nodes.reduce((s, n) => s + 1 + (n.children ? countNodes(n.children) : 0), 0);
  const totalNodes = countNodes(taxonomy);
  const totalDocs = taxonomy.reduce((s, n) => s + n.doc_count, 0);

  /** 在树中递归查找指定ID的节点 */
  const findNode = (nodes: TaxonomyNode[], id: string): TaxonomyNode | null => {
    for (const n of nodes) {
      if (n.id === id) return n;
      if (n.children) {
        const f = findNode(n.children, id);
        if (f) return f;
      }
    }
    return null;
  };

  return (
    <div className="p-6 h-full flex flex-col page-enter">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-display flex items-center gap-2 text-th-text-primary">
            <FolderTree size={20} className="text-th-text-muted" />
            知识体系
          </h1>
          <p className="text-caption text-th-text-muted mt-1">
            {currentProject?.industry_name
              ? `${currentProject.industry_name}行业四级知识体系`
              : '四层知识分类体系'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={loadData}>
            刷新
          </Button>
          <Button variant="secondary" size="sm" onClick={expandAll}>
            全部展开
          </Button>
          <Button variant="secondary" size="sm" onClick={collapseAll}>
            全部折叠
          </Button>
          <Button variant="secondary" icon={<Download size={16} />}>
            导出
          </Button>
          <Button variant="secondary" icon={<Sparkles size={16} />}>AI优化</Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-4">
        <Card className="p-4">
          <div className="text-2xl font-[510] text-th-text-primary">{taxonomy.length}</div>
          <div className="text-caption text-th-text-muted mt-1">L0 部门/大领域</div>
        </Card>
        <Card className="p-4">
          <div className="text-2xl font-[510] text-th-text-primary">
            {taxonomy.reduce((s, n) => s + (n.children?.length || 0), 0)}
          </div>
          <div className="text-caption text-th-text-muted mt-1">L1 业务子领域</div>
        </Card>
        <Card className="p-4">
          <div className="text-2xl font-[510] text-th-text-primary">{totalNodes}</div>
          <div className="text-caption text-th-text-muted mt-1">总节点数</div>
        </Card>
        <Card className="p-4">
          <div className="text-2xl font-[510] text-th-text-primary">{totalDocs}</div>
          <div className="text-caption text-th-text-muted mt-1">关联文档</div>
        </Card>
      </div>

      <div className="flex items-center gap-6 mb-4 px-4 py-2 rounded-card border border-th-border">
        <span className="text-caption text-th-text-muted">层级:</span>
        {Object.entries(LEVEL_CONFIG).map(([level, config]) => (
          <div key={level} className="flex items-center gap-1.5">
            <span className="text-caption font-[510] text-th-text-secondary">{level}</span>
            <span className="text-caption text-th-text-muted">{config.label}</span>
          </div>
        ))}
      </div>

      <Card className="flex-1 p-4 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="text-th-text-muted">加载中...</div>
          </div>
        ) : taxonomy.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-th-text-muted">
            <FolderTree size={48} className="mb-4 opacity-30" />
            <p className="text-base font-medium mb-1">暂无知识体系</p>
            <p className="text-sm">请先创建项目并选择行业模板，系统将自动生成四级知识体系</p>
          </div>
        ) : (
          <div className="min-w-[600px]">
            {taxonomy.map((node, idx) =>
              renderNode(node, undefined, idx === taxonomy.length - 1)
            )}
          </div>
        )}
      </Card>

      {selectedNode && (
        <Card className="mt-4 p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">
              已选择: {findNode(taxonomy, selectedNode)?.name}
            </h3>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" icon={<Plus size={14} />}>
                添加子节点
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<Trash2 size={14} />}
                className="text-red-500"
              >
                删除
              </Button>
            </div>
          </div>
          <p className="text-sm text-th-text-muted">
            点击查看该分类下的文档，或进行编辑操作
          </p>
        </Card>
      )}
    </div>
  );
}
