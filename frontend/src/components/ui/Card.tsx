/**
 * 卡片组件模块
 *
 * 提供 Card 容器及其子组件（CardHeader / CardTitle / CardContent / CardFooter）。
 * 支持 flat/elevated/bordered 三种变体和可交互状态（hover 抬升效果）。
 */

import React from 'react';

/** 卡片容器属性 */
export interface CardProps {
  children: React.ReactNode;
  variant?: 'flat' | 'elevated' | 'bordered';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  interactive?: boolean;
  className?: string;
  onClick?: () => void;
}

const variantClasses = {
  flat: 'bg-surface',
  elevated: 'glass-card',
  bordered: 'bg-transparent shadow-ring',
};

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
};

export const Card: React.FC<CardProps> = ({
  children,
  variant = 'elevated',
  padding = 'md',
  interactive = false,
  className = '',
  onClick,
}) => {
  const baseClasses = 'rounded-card transition-all duration-200';
  const interactiveClasses = interactive
    ? 'cursor-pointer hover:shadow-card-hover active:scale-[0.99]'
    : '';

  return (
    <div
      className={`${baseClasses} ${variantClasses[variant]} ${paddingStyles[padding]} ${interactiveClasses} ${className}`}
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
    >
      {children}
    </div>
  );
};

/** 卡片头部区域（flex 布局，两端对齐） */
export const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`flex items-center justify-between mb-4 ${className}`}>
    {children}
  </div>
);

/** 卡片标题（可附带图标和徽章） */
export const CardTitle: React.FC<{
  children: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}> = ({ children, icon, badge, className = '' }) => (
  <div className={`flex items-center gap-3 ${className}`}>
    {icon && (
      <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-hover">
        {icon}
      </div>
    )}
    <div className="flex-1">
      <h3 className="font-medium text-th-text-primary">
        {children}
      </h3>
    </div>
    {badge}
  </div>
);

/** 卡片内容区域 */
export const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <div className={className}>{children}</div>;

/** 卡片底部区域（带顶部分隔线） */
export const CardFooter: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`mt-4 pt-4 border-t border-th-border ${className}`}>
    {children}
  </div>
);

export default Card;
