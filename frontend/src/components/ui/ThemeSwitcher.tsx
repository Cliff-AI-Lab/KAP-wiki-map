/**
 * 主题切换器组件 (ThemeSwitcher)
 *
 * 从 V7 的循环切换(cycle toggle)重写为下拉选择器，
 * 分暗色/亮色两组显示全部可用主题。
 *
 * 设计要点:
 * - 每个选项用 3 个色彩圆点(accent / accentSecondary / success)预览主题配色，
 *   让用户无需切换即可直观辨别主题。
 * - 触发按钮显示 Sun(暗色时，暗示可切到亮色) / Moon(亮色时)，
 *   沿用常见的"对立图标"惯例。
 * - 点击外部区域自动关闭下拉，通过 mousedown 事件监听实现。
 */

import React, { useState, useRef, useEffect } from 'react';
import { Sun, Moon, Check } from 'lucide-react';
import { themes, applyTheme, loadSavedTheme, type Theme } from '@/lib/themes';

export const ThemeSwitcher: React.FC = () => {
  const [current, setCurrent] = useState<Theme>(loadSavedTheme);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 点击组件外部时关闭下拉面板（使用 mousedown 而非 click，
  // 因为 mousedown 在 blur 之前触发，时序更可靠）
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const darkThemes = themes.filter((t) => t.colorScheme === 'dark');
  const lightThemes = themes.filter((t) => t.colorScheme === 'light');

  const selectTheme = (theme: Theme) => {
    applyTheme(theme);
    setCurrent(theme);
    setOpen(false);
  };

  /** 单个主题选项行：3 色圆点预览 + 主题名 + 选中对勾 */
  const ThemeOption: React.FC<{ theme: Theme }> = ({ theme }) => (
    <button
      onClick={() => selectTheme(theme)}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors rounded-md
        ${current.id === theme.id ? 'bg-hover' : 'hover:bg-hover'}
      `}
    >
      <div className="flex gap-1">
        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.accent }} />
        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.accentSecondary }} />
        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.success }} />
      </div>
      <span className="flex-1 text-left text-th-text-primary">{theme.name}</span>
      {current.id === theme.id && <Check size={14} className="text-accent" />}
    </button>
  );

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="btn-ghost rounded-lg p-2 transition-all duration-150"
        aria-label="切换主题"
        title={`当前: ${current.name}`}
      >
        {current.colorScheme === 'dark' ? (
          <Sun size={16} className="text-th-text-secondary" />
        ) : (
          <Moon size={16} className="text-th-text-secondary" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-52 rounded-xl border bg-elevated shadow-lg z-50 p-1.5 border-th-border">
          <div className="text-overline px-3 py-1.5 text-th-text-muted">暗色</div>
          {darkThemes.map((t) => <ThemeOption key={t.id} theme={t} />)}
          <div className="border-t border-th-border my-1" />
          <div className="text-overline px-3 py-1.5 text-th-text-muted">亮色</div>
          {lightThemes.map((t) => <ThemeOption key={t.id} theme={t} />)}
        </div>
      )}
    </div>
  );
};

export default ThemeSwitcher;
