/**
 * 按钮组件模块
 *
 * 提供 Button（通用按钮）和 IconButton（纯图标按钮）两种组件。
 * 支持 primary/secondary/ghost/danger 四种变体，
 * 以及 sm/md/lg 三种尺寸，内置 loading 状态和图标位置控制。
 */

import React from 'react';
import { Loader2 } from 'lucide-react';

/** 通用按钮属性 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
}

const variantStyles = {
  primary: 'btn-gradient text-white',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'btn-discard',
};

const sizeStyles = {
  sm: 'px-3 py-1.5 text-xs gap-1.5 rounded-btn',
  md: 'px-4 py-2 text-sm gap-2 rounded-btn',
  lg: 'px-5 py-2.5 text-sm gap-2 rounded-btn',
};

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  disabled,
  className = '',
  ...props
}) => {
  const baseClasses = `inline-flex items-center justify-center ${variant === 'primary' ? 'font-semibold' : 'font-medium'} transition-all duration-150`;
  const widthClasses = fullWidth ? 'w-full' : '';
  const disabledClasses = disabled || loading ? 'opacity-50 cursor-not-allowed' : '';

  const iconElement = loading ? (
    <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" />
  ) : icon;

  return (
    <button
      className={`${baseClasses} ${variantStyles[variant]} ${sizeStyles[size]} ${widthClasses} ${disabledClasses} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {iconElement && iconPosition === 'left' && iconElement}
      {children}
      {iconElement && iconPosition === 'right' && iconElement}
    </button>
  );
};

/** 纯图标按钮属性（需提供 label 用于无障碍访问） */
export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon: React.ReactNode;
  label: string;
}

const iconSizeStyles = {
  sm: 'p-1.5',
  md: 'p-2',
  lg: 'p-2.5',
};

export const IconButton: React.FC<IconButtonProps> = ({
  variant = 'ghost',
  size = 'md',
  loading = false,
  icon,
  label,
  disabled,
  className = '',
  ...props
}) => {
  const baseClasses = 'inline-flex items-center justify-center rounded-lg transition-all duration-150';
  const disabledClasses = disabled || loading ? 'opacity-50 cursor-not-allowed' : '';

  return (
    <button
      className={`${baseClasses} ${variantStyles[variant]} ${iconSizeStyles[size]} ${disabledClasses} ${className}`}
      disabled={disabled || loading}
      aria-label={label}
      title={label}
      {...props}
    >
      {loading ? <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" /> : icon}
    </button>
  );
};

export default Button;
