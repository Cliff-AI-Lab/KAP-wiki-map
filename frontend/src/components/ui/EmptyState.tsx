/**
 * 空状态占位组件
 *
 * 当列表/页面无数据时展示，包含图标、标题、描述和可选的操作按钮。
 */

import React from 'react';
import { Inbox } from 'lucide-react';

/** 空状态属性 */
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
}) => (
  <div className="flex flex-col items-center justify-center py-16 text-center animate-fadeIn">
    <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4 bg-hover text-th-text-muted">
      {icon ?? <Inbox size={28} />}
    </div>
    <h3 className="text-heading mb-1 text-th-text-secondary">
      {title}
    </h3>
    {description && (
      <p className="text-caption max-w-sm text-th-text-muted">
        {description}
      </p>
    )}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export default EmptyState;
