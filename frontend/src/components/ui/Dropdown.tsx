/**
 * Dropdown 下拉菜单组件 — Linear 风格
 * 透明面板 + 键盘导航 + 点击外部关闭
 */
import { useState, useRef, useEffect, type ReactNode } from 'react';

export interface DropdownItem {
  id: string;
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  divider?: boolean;
}

export interface DropdownProps {
  trigger: ReactNode;
  items: DropdownItem[];
  onSelect: (id: string) => void;
  align?: 'left' | 'right';
}

export function Dropdown({ trigger, items, onSelect, align = 'left' }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen(!open)}>{trigger}</div>

      {open && (
        <div
          className={`absolute top-full mt-1 ${align === 'right' ? 'right-0' : 'left-0'} min-w-[180px] z-50 py-1 rounded-card bg-elevated border border-th-border shadow-lg`}
        >
          {items.map((item) =>
            item.divider ? (
              <div key={item.id} className="h-px my-1 bg-[var(--color-border)]" />
            ) : (
              <button
                key={item.id}
                onClick={() => { onSelect(item.id); setOpen(false); }}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-caption transition-colors ${
                  item.danger
                    ? 'text-th-error hover:bg-[var(--color-error-bg)]'
                    : 'text-th-text-secondary hover:bg-hover hover:text-th-text-primary'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}
