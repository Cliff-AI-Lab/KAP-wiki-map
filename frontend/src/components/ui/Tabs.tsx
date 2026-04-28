/**
 * Tabs 标签切换组件 — Linear 风格
 * 底部线条指示器 + 键盘导航
 */
import { type ReactNode } from 'react';

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  size?: 'sm' | 'md';
}

export function Tabs({ items, active, onChange, size = 'md' }: TabsProps) {
  const isSmall = size === 'sm';

  return (
    <div
      className="flex items-center border-b border-th-border"
      role="tablist"
    >
      {items.map((item) => {
        const isActive = item.id === active;
        return (
          <button
            key={item.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(item.id)}
            className={`relative flex items-center gap-1.5 transition-colors ${
              isSmall ? 'px-3 py-2 text-caption' : 'px-4 py-2.5 text-subheading'
            } ${
              isActive
                ? 'text-th-text-primary'
                : 'text-th-text-muted hover:text-th-text-secondary'
            }`}
          >
            {item.icon}
            {item.label}
            {isActive && (
              <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-accent" />
            )}
          </button>
        );
      })}
    </div>
  );
}
