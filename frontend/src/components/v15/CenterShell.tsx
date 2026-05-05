/**
 * CenterShell + CenterHero + Pipeline + StatTile + KapCard — 三中心共享组件
 * (M21 #5 · shadcn slate 体系，与 V15Layout 顶栏完全同语言)
 */
import { type ReactNode } from 'react';
import { Sparkles, Database, Compass, ChevronRight } from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import LanguageSwitcher from '@/components/v15/LanguageSwitcher';
import type { TranslationKey } from '@/lib/i18n';

export type CenterKind = 'consult' | 'manage' | 'read';

const CENTER_META: Record<CenterKind, {
  badgeKey: TranslationKey;
  icon: typeof Sparkles;
}> = {
  consult: { badgeKey: 'mode.consult', icon: Sparkles },
  manage:  { badgeKey: 'mode.manage',  icon: Database },
  read:    { badgeKey: 'mode.read',    icon: Compass  },
};


export function CenterShell({ children }: { children: ReactNode }) {
  // V15Layout 已提供 .kap-page / .kap-content；此处仅 fragment
  return <>{children}</>;
}


export function CenterHero({
  kind,
  titleKey,
  subtitleKey,
  rightSlot,
}: {
  kind: CenterKind;
  titleKey: TranslationKey;
  subtitleKey?: TranslationKey;
  rightSlot?: ReactNode;
}) {
  const { t } = useLocale();
  const meta = CENTER_META[kind];
  const Icon = meta.icon;

  return (
    <header className="kap-anim flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-7">
      <div>
        <div className="kap-eyebrow">
          <Icon size={12} strokeWidth={2} />
          {t(meta.badgeKey)}
        </div>
        <h1 className="kap-headline">{t(titleKey)}</h1>
        {subtitleKey && <p className="kap-subhead">{t(subtitleKey)}</p>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {rightSlot}
        <LanguageSwitcher />
      </div>
    </header>
  );
}


export interface Station {
  id: string;
  labelKey: TranslationKey;
  hintKey?: TranslationKey;
  icon?: typeof Sparkles;
  state?: 'pending' | 'active' | 'done';
}

export function Pipeline({
  labelKey,
  stations,
  onClickStation,
}: {
  labelKey: TranslationKey;
  stations: Station[];
  onClickStation?: (id: string) => void;
}) {
  const { t } = useLocale();

  return (
    <section className="kap-anim mb-6">
      <div className="flex items-center gap-2 mb-2.5">
        <div
          className="kap-mono-tag"
          style={{ color: 'hsl(var(--muted-foreground))' }}
        >
          {t(labelKey)}
        </div>
        <div
          className="flex-1 h-px"
          style={{ background: 'hsl(var(--border))' }}
        />
      </div>
      <div className="kap-stagger flex gap-2 overflow-x-auto items-stretch">
        {stations.map((s, i) => {
          const Icon = s.icon ?? Sparkles;
          const state = s.state ?? 'pending';
          const stateClass =
            state === 'active' ? 'kap-badge-primary'
            : state === 'done' ? 'kap-badge-success'
            : 'kap-badge';

          return (
            <div key={s.id} className="flex items-center flex-1 min-w-[140px]">
              <button
                type="button"
                data-state={state}
                className="kap-station w-full"
                onClick={() => onClickStation?.(s.id)}
              >
                <div className="flex items-center gap-2 mb-1">
                  <Icon
                    size={12}
                    strokeWidth={1.8}
                    style={{ color: 'hsl(var(--muted-foreground))' }}
                  />
                  <span
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontWeight: 600,
                      fontSize: 13,
                      color: 'hsl(var(--foreground))',
                      letterSpacing: '-0.01em',
                    }}
                  >
                    {t(s.labelKey)}
                  </span>
                  {state === 'active' && (
                    <span className={`${stateClass} ml-auto`} style={{ fontSize: 9.5 }}>
                      <span
                        className="kap-pulse w-1.5 h-1.5 rounded-full"
                        style={{ background: 'currentColor' }}
                      />
                      ACTIVE
                    </span>
                  )}
                  {state === 'done' && (
                    <span className={`${stateClass} ml-auto`} style={{ fontSize: 9.5 }}>
                      DONE
                    </span>
                  )}
                </div>
                {s.hintKey && (
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontWeight: 400,
                      fontSize: 11.5,
                      color: 'hsl(var(--muted-foreground))',
                    }}
                  >
                    {t(s.hintKey)}
                  </div>
                )}
              </button>
              {i < stations.length - 1 && (
                <ChevronRight
                  size={14}
                  strokeWidth={1.5}
                  className="shrink-0 mx-1"
                  style={{ color: 'hsl(var(--muted-foreground) / 0.5)' }}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}


export function StatTile({
  labelKey,
  value,
  suffix,
  state = 'normal',
}: {
  labelKey: TranslationKey;
  value: ReactNode;
  suffix?: string;
  state?: 'normal' | 'alert' | 'good';
}) {
  const { t } = useLocale();
  const valueColor =
    state === 'alert' ? 'hsl(var(--destructive))'
    : state === 'good'  ? 'hsl(var(--success))'
    : 'hsl(var(--foreground))';

  return (
    <div className="kap-card" style={{ padding: '1.1rem 1.2rem' }}>
      <div className="kap-stat-label">{t(labelKey)}</div>
      <div className="kap-stat-value" style={{ color: valueColor }}>
        {value}
        {suffix && <span className="kap-stat-suffix">{suffix}</span>}
      </div>
    </div>
  );
}


export function KapCard({
  titleKey,
  eyebrow,
  children,
  className = '',
  frost = false,
  rightSlot,
  padding = '1.25rem',
}: {
  titleKey?: TranslationKey;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
  frost?: boolean;
  rightSlot?: ReactNode;
  padding?: string;
}) {
  const { t } = useLocale();
  return (
    <section
      className={`kap-card ${frost ? 'kap-card-frost' : ''} ${className}`}
      style={{ padding }}
    >
      {(titleKey || eyebrow) && (
        <header className="flex items-center justify-between mb-3.5">
          <div>
            {eyebrow && (
              <div
                className="kap-mono-tag mb-1"
                style={{ color: 'hsl(var(--muted-foreground))' }}
              >
                {eyebrow}
              </div>
            )}
            {titleKey && (
              <h3 className="kap-section-title">{t(titleKey)}</h3>
            )}
          </div>
          {rightSlot}
        </header>
      )}
      {children}
    </section>
  );
}
