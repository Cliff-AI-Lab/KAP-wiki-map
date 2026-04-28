/**
 * 骨架屏组件模块
 *
 * 提供 Skeleton（基础占位块）、SkeletonText（多行文本占位）、
 * SkeletonCard（卡片占位）三种加载态占位组件。
 */

import React from 'react';

/** 基础骨架属性 */
interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className = '', width, height }) => (
  <div className={`skeleton ${className}`} style={{ width, height }} />
);

/** 多行文本骨架（最后一行宽度为 60%，模拟自然段落效果） */
export const SkeletonText: React.FC<{ lines?: number; className?: string }> = ({
  lines = 3,
  className = '',
}) => (
  <div className={className}>
    {Array.from({ length: lines }).map((_, i) => (
      <div
        key={i}
        className="skeleton skeleton-text"
        style={{ width: i === lines - 1 ? '60%' : '100%' }}
      />
    ))}
  </div>
);

/** 卡片骨架（含图标占位 + 三行文本占位） */
export const SkeletonCard: React.FC = () => (
  <div className="glass-card rounded-xl p-5">
    <div className="flex items-center gap-3 mb-4">
      <Skeleton className="w-9 h-9 rounded-lg" />
      <Skeleton className="skeleton-text" width="40%" />
    </div>
    <SkeletonText lines={3} />
  </div>
);

export default Skeleton;
