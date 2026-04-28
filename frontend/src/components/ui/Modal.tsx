/**
 * Modal 对话框组件 — Linear 风格
 * 透明背景遮罩 + 居中面板 + Escape 关闭 + 焦点陷阱
 */
import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

const SIZE_MAP = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' };

export function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        ref={panelRef}
        tabIndex={-1}
        className={`relative ${SIZE_MAP[size]} w-full mx-4 rounded-featured bg-elevated shadow-lg border border-th-border animate-in`}
        style={{ animationDuration: '200ms' }}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-th-border">
            <h3 className="text-heading text-th-text-primary">{title}</h3>
            <button
              onClick={onClose}
              className="p-1 rounded-btn text-th-text-muted hover:text-th-text-primary hover:bg-hover transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
