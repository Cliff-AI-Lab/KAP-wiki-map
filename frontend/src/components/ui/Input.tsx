/**
 * 表单输入组件模块
 *
 * 提供 Input（文本输入）、Textarea（多行文本）、Select（下拉选择）三种表单控件。
 * 统一支持 label、error、hint 属性，基于 glass-surface 风格实现毛玻璃效果。
 */

import React from 'react';

/** 文本输入框属性 */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  hint,
  leftIcon,
  rightIcon,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || `input-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-xs text-muted mb-2">
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted">
            {leftIcon}
          </div>
        )}
        <input
          id={inputId}
          className={`
            w-full glass-surface rounded-lg px-4 py-2.5 text-sm text-th-text-primary
            placeholder:text-th-text-muted focus:outline-none
            disabled:opacity-50 disabled:cursor-not-allowed
            ${leftIcon ? 'pl-10' : ''}
            ${rightIcon ? 'pr-10' : ''}
            ${error ? 'border-red-500/50 focus:border-red-500' : ''}
            ${className}
          `}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted">
            {rightIcon}
          </div>
        )}
      </div>
      {(error || hint) && (
        <p className={`mt-1.5 text-xs ${error ? 'text-red-400' : 'text-muted'}`}>
          {error || hint}
        </p>
      )}
    </div>
  );
};

/** 多行文本输入框属性 */
export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  hint,
  className = '',
  id,
  rows = 3,
  ...props
}) => {
  const textareaId = id || `textarea-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={textareaId} className="block text-xs text-muted mb-2">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        rows={rows}
        className={`
          w-full glass-surface rounded-lg px-4 py-3 text-sm text-th-text-primary resize-none
          placeholder:text-th-text-muted focus:outline-none
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-red-500/50 focus:border-red-500' : ''}
          ${className}
        `}
        {...props}
      />
      {(error || hint) && (
        <p className={`mt-1.5 text-xs ${error ? 'text-red-400' : 'text-muted'}`}>
          {error || hint}
        </p>
      )}
    </div>
  );
};

/** 下拉选择框属性 */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  hint?: string;
  options: { value: string; label: string; disabled?: boolean }[];
}

export const Select: React.FC<SelectProps> = ({
  label,
  error,
  hint,
  options,
  className = '',
  id,
  ...props
}) => {
  const selectId = id || `select-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={selectId} className="block text-xs text-muted mb-2">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`
          w-full glass-surface rounded-lg px-4 py-2.5 text-sm text-th-text-primary
          focus:outline-none bg-transparent
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-red-500/50 focus:border-red-500' : ''}
          ${className}
        `}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      {(error || hint) && (
        <p className={`mt-1.5 text-xs ${error ? 'text-red-400' : 'text-muted'}`}>
          {error || hint}
        </p>
      )}
    </div>
  );
};

export default Input;
