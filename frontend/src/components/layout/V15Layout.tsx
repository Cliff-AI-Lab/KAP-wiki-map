/**
 * V15Layout — 全局入口（M21 #5 · 三中心统一 shadcn 风）
 *
 * 顶栏 + 页面共享同一套 design tokens（slate dark），无第二风格。
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
    <div className="flex h-screen flex-col overflow-hidden">
      {/* 顶栏 */}
      <header
        className="h-16 shrink-0 sticky top-0 z-20 flex items-center gap-5 px-6 border-b backdrop-blur-md"
        style={{
          background: 'hsl(var(--background) / 0.85)',
          borderColor: 'hsl(var(--border))',
        }}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 grid place-items-center font-bold text-sm"
            style={{
              background: 'hsl(var(--primary))',
              color: 'hsl(var(--primary-foreground))',
              borderRadius: 'calc(var(--radius) - 2px)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            K
          </div>
          <div className="flex flex-col leading-tight">
            <span
              style={{
                fontFamily: 'var(--font-sans)',
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: '-0.01em',
                color: 'hsl(var(--foreground))',
              }}
            >
              {t('brand.name')}
            </span>
            <span
              className="kap-mono-tag"
              style={{ color: 'hsl(var(--muted-foreground))' }}
            >
              {t('brand.tagline')}
            </span>
          </div>
        </div>

        <div
          className="w-px h-5"
          style={{ background: 'hsl(var(--border))' }}
        />

        <V15ProjectSelector />

        <div className="flex-1" />

        <EditionPill />

        <button
          onClick={() => setSettingsOpen(true)}
          className="kap-btn kap-btn-ghost"
          style={{ padding: '0.45rem' }}
          aria-label={t('topbar.settings')}
          title={t('topbar.settings')}
        >
          <Settings size={15} />
        </button>
      </header>

      {/* 主区 */}
      <main
        className="flex-1 overflow-y-auto kap-page"
        style={{ background: 'hsl(var(--background))' }}
      >
        <div className="kap-content">
          <Outlet />
        </div>
      </main>

      {settingsOpen && <UnifiedSettings onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
