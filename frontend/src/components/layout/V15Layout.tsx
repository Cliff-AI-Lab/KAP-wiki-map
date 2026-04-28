/**
 * V15Layout — 全局入口布局（消费 / 治理模式）
 *
 * 不挂 ProjectContext（V15 双模式是跨项目的全局体验）。
 * 顶栏：Logo + 品牌名 + EditionPill + 设置。
 */
import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Settings } from 'lucide-react';
import { EditionPill } from './EditionPill';
import { V15ProjectSelector } from './V15ProjectSelector';
import { UnifiedSettings } from '@/components/settings/UnifiedSettings';
import { useLocale } from '@/contexts/LocaleContext';

export default function V15Layout() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { t } = useLocale();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-base v15-bg-mesh">
      <header className="h-16 shrink-0 flex items-center gap-6 px-8 border-b border-th-border bg-elevated/70 backdrop-blur sticky top-0 z-20">
        {/* Logo + 品牌 — Space Grotesk 900 */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-btn bg-accent grid place-items-center text-[color:var(--color-bg-base)] font-bold text-sm v15-display">
            图
          </div>
          <span className="v15-display text-[17px] uppercase tracking-[0.02em] text-th-text-primary">
            {t('brand.name')}
          </span>
          <span className="text-[11px] v15-mono text-th-text-muted uppercase tracking-[0.15em]">
            {t('brand.tagline')}
          </span>
        </div>

        <div className="w-px h-5 bg-th-border" />

        <V15ProjectSelector />

        <div className="flex-1" />

        <EditionPill />

        <button
          onClick={() => setSettingsOpen(true)}
          className="btn-ghost rounded-btn p-2 transition-all duration-150"
          aria-label={t('topbar.settings')}
          title={t('topbar.settings')}
        >
          <Settings size={15} className="text-th-text-secondary" />
        </button>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1600px] mx-auto w-full px-6 py-8">
          <Outlet />
        </div>
      </main>

      {settingsOpen && <UnifiedSettings onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
