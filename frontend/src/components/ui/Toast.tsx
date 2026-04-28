/**
 * Toast 通知组件 + useToast Hook
 *
 * 提供全局级别的轻量级通知，支持 success/error/info/warning 四种变体。
 * 底部居中显示，3 秒自动消失，glass-card 风格。
 *
 * 设计要点:
 * - 通过 React Context 实现全局单例，任意子组件均可调用 showToast()。
 * - 移除采用两阶段动画：先标记 exiting 触发 CSS 退出动画(200ms)，
 *   动画结束后再从 state 中删除 DOM 节点，避免闪烁。
 * - useToast 在 Provider 外部调用时返回 no-op 而非抛异常，方便 Storybook 等隔离环境使用。
 */

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { CheckCircle, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';

/** 通知变体类型，决定图标和左侧边框颜色 */
type ToastVariant = 'success' | 'error' | 'info' | 'warning';

/** 单条 Toast 的内部状态 */
interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  /** 标记为 true 时播放退出动画，200ms 后从列表中移除 */
  exiting?: boolean;
}

/** Context 暴露的 API —— 仅提供 showToast 触发方法 */
interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const variantConfig: Record<ToastVariant, { icon: React.ElementType; borderColor: string }> = {
  success: { icon: CheckCircle, borderColor: 'var(--color-success)' },
  error: { icon: AlertCircle, borderColor: 'var(--color-error)' },
  info: { icon: Info, borderColor: 'var(--color-info)' },
  warning: { icon: AlertTriangle, borderColor: 'var(--color-warning)' },
};

/** Toast 单项渲染 */
const ToastMessage: React.FC<{ item: ToastItem; onClose: (id: number) => void }> = ({ item, onClose }) => {
  const { icon: Icon, borderColor } = variantConfig[item.variant];

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 rounded-xl glass-card shadow-lg max-w-sm ${
        item.exiting ? 'toast-exit' : 'toast-enter'
      }`}
      style={{ borderLeft: `3px solid ${borderColor}` }}
    >
      <Icon size={18} style={{ color: borderColor }} className="shrink-0" />
      <span className="text-sm text-th-text-primary flex-1">{item.message}</span>
      <button
        onClick={() => onClose(item.id)}
        className="text-th-text-muted hover:text-th-text-primary transition-colors shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
};

/** Toast 容器 Provider */
export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  /**
   * 两阶段移除：先设 exiting=true 触发 CSS toast-exit 动画，
   * 等 200ms 动画播完后再真正移除节点。
   */
  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 200);
  }, []);

  const showToast = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => removeToast(id), 3000);
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2">
          {toasts.map((item) => (
            <ToastMessage key={item.id} item={item} onClose={removeToast} />
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
};

/**
 * 消费 Toast 能力的 Hook。
 * 在 ToastProvider 外部调用时返回静默 no-op，不会抛异常。
 */
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return { showToast: (_msg: string, _variant?: ToastVariant) => {} };
  }
  return context;
}
