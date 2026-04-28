/**
 * 统一页面标题组件 (PageHeader)
 *
 * 标准化所有页面的头部区域：图标 + 标题 + 描述 + 可选操作按钮。
 * 使用 page-hero CSS 动画实现入场效果。
 *
 * 设计要点:
 * - 所有页面复用同一布局，保证视觉一致性（间距、字号、图标尺寸）。
 * - actions slot 置于右侧，可传入任意 ReactNode（按钮组、下拉等）。
 * - iconBg 默认为 accent 色的 10% 透明度，各页面可按需覆盖。
 */

import React from 'react';

/** PageHeader 组件的 Props */
interface PageHeaderProps {
  /** 左侧图标，通常传入 lucide-react 图标元素 */
  icon: React.ReactNode;
  /** 图标背景色 class，默认 'bg-accent/10' */
  iconBg?: string;
  /** 页面主标题 */
  title: string;
  /** 标题下方的描述文字（可选） */
  description?: string;
  /** 右侧操作区插槽，可放置按钮组等（可选） */
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  icon,
  iconBg = 'bg-accent/10',
  title,
  description,
  actions,
}) => (
  <div className="flex items-center justify-between page-hero">
    <div className="flex items-center gap-3">
      <div className={`w-12 h-12 rounded-xl ${iconBg} flex items-center justify-center`}>
        {icon}
      </div>
      <div>
        <h1 className="text-display text-th-text-primary">{title}</h1>
        {description && <p className="text-caption text-th-text-muted">{description}</p>}
      </div>
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);

export default PageHeader;
