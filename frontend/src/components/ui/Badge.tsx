/**
 * 徽章组件模块
 *
 * 提供状态/标签徽章，支持 success/warning/error/info/neutral 五种变体。
 * 附带 decisionVariant 和 statusVariant 工具函数，用于将后端枚举映射为徽章变体。
 */

import React from 'react';

/** 徽章属性 */
export interface BadgeProps {
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  size?: 'sm' | 'md';
  children: React.ReactNode;
  className?: string;
}

/** 变体对应的 CSS 类名映射 */
const variantStyles = {
  success: 'badge-keep',
  warning: 'badge-archive',
  error: 'badge-discard',
  info: 'badge-pending',
  neutral: 'badge-neutral',
};

/** 尺寸对应的 Tailwind 类名映射 */
const sizeStyles = {
  sm: 'px-1.5 py-0.5 text-[10px]',
  md: 'px-2 py-0.5 text-xs',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'md',
  children,
  className = '',
}) => (
  <span
    className={`inline-flex items-center font-medium rounded-md ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
  >
    {children}
  </span>
);

/** Decision -> Badge variant mapping */
export function decisionVariant(decision: string): BadgeProps['variant'] {
  switch (decision) {
    case 'KEEP': return 'success';
    case 'ARCHIVE': return 'warning';
    case 'DISCARD': return 'error';
    default: return 'neutral';
  }
}

/** DocStatus -> Badge variant mapping */
export function statusVariant(status: string): BadgeProps['variant'] {
  switch (status) {
    case 'ACTIVE': return 'success';
    case 'PENDING_REVIEW': return 'info';
    case 'ARCHIVED': return 'warning';
    case 'DISCARDED': return 'error';
    default: return 'neutral';
  }
}

export default Badge;
