/**
 * 树形视图组件
 *
 * 用于展示知识目录的层级结构，支持展开/折叠、路径选中高亮。
 * 每个节点显示名称和文档计数徽章。
 */

import React, { useState } from 'react';
import { ChevronRight, ChevronDown, FolderOpen, Folder } from 'lucide-react';

/** 树节点数据结构（与后端 CatalogNode 对应） */
export interface TreeNode {
  path: string;
  name: string;
  doc_count: number;
  children: TreeNode[];
}

/** 树形视图属性 */
interface TreeViewProps {
  nodes: TreeNode[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

/** 树形视图单个节点（递归渲染子节点，depth 控制缩进） */
const TreeItem: React.FC<{
  node: TreeNode;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  depth: number;
}> = ({ node, selectedPath, onSelect, depth }) => {
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedPath === node.path;

  return (
    <div>
      <button
        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-all duration-150
          ${isSelected ? 'bg-hover text-accent' : 'text-th-text-secondary hover:bg-hover'}
        `}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => {
          onSelect(node.path);
          if (hasChildren) setExpanded(!expanded);
        }}
      >
        {hasChildren ? (
          expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        ) : (
          <span className="w-3.5" />
        )}
        {expanded && hasChildren ? (
          <FolderOpen size={14} className="text-accent" />
        ) : (
          <Folder size={14} />
        )}
        <span className="flex-1 text-left truncate">{node.name}</span>
        <span className="text-xs px-1.5 rounded bg-hover text-th-text-muted">
          {node.doc_count}
        </span>
      </button>
      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const TreeView: React.FC<TreeViewProps> = ({ nodes, selectedPath, onSelect }) => (
  <div className="space-y-0.5">
    {nodes.map((node) => (
      <TreeItem key={node.path} node={node} selectedPath={selectedPath} onSelect={onSelect} depth={0} />
    ))}
  </div>
);

export default TreeView;
