/**
 * CenterShell + CenterHero + Pipeline + StatTile + KapCard
 *
 * 三中心（咨询 / 知识 / 消费）共用的页面骨架。
 * 严格按 distinctive.css 的 Nordic 设计 token 渲染，三中心保持视觉一致。
 *
 * 用法：
 *   <CenterShell>
 *     <CenterHero kind="consult" titleKey="..." />
 *     <Pipeline stations={...} active="W2" />
 *     <KapCard>...</KapCard>
 *   </CenterShell>
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
  accent: string;        // Nordic accent ref
}> = {
  consult: { badgeKey: 'mode.consult', icon: Sparkles, accent: 'var(--kap-frost)' },
  manage:  { badgeKey: 'mode.manage',  icon: Database, accent: 'var(--kap-aurora-yellow)' },
  read:    { badgeKey: 'mode.read',    icon: Compass,  accent: 'var(--kap-aurora-green)' },
};


// ════════════════════════════════════════════════════════════
//  Shell
// ════════════════════════════════════════════════════════════
export function CenterShell({ children }: { children: ReactNode }) {
  return (
    <div className="kap-page">
      <div className="kap-content">{children}</div>
    </div>
  );
}


// ════════════════════════════════════════════════════════════
//  Hero — 顶部品牌区（三中心唯一变量是 kind）
// ════════════════════════════════════════════════════════════
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
    <header className="kap-anim flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-10">
      <div>
        {/* Eyebrow */}
        <div className="kap-eyebrow" style={{ color: meta.accent }}>
          <Icon size={12} strokeWidth={1.6} />
          KAP · {t(meta.badgeKey).toUpperCase()}
        </div>

        {/* Title */}
        <h1 className="kap-headline kap-headline-cn">
          {t(titleKey)}
        </h1>

        {/* Subtitle */}
        {subtitleKey && (
          <p className="kap-subhead">{t(subtitleKey)}</p>
        )}
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {rightSlot}
        <LanguageSwitcher />
      </div>
    </header>
  );
}


// ════════════════════════════════════════════════════════════
//  Pipeline — 工位/流程横条；3 中心都用，仅 stations 不同
// ════════════════════════════════════════════════════════════
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
    <section className="kap-anim relative kap-strip mb-8">
      {/* corners */}
      <span className="kap-strip-corner" style={{ top: 0, left: 0, borderRight: 'none', borderBottom: 'none' }} />
      <span className="kap-strip-corner" style={{ top: 0, right: 0, borderLeft: 'none', borderBottom: 'none' }} />
      <span className="kap-strip-corner" style={{ bottom: 0, left: 0, borderRight: 'none', borderTop: 'none' }} />
      <span className="kap-strip-corner" style={{ bottom: 0, right: 0, borderLeft: 'none', borderTop: 'none' }} />

      <div className="absolute -top-3 left-5 px-2 bg-[var(--kap-bg)] kap-mono-tag" style={{ color: 'var(--kap-frost)' }}>
        ▶ {t(labelKey)}
      </div>

      <div className="kap-stagger flex gap-2 overflow-x-auto items-stretch w-full">
        {stations.map((s, i) => {
          const Icon = s.icon ?? Sparkles;
          const state = s.state ?? 'pending';
          const stateColor =
            state === 'active' ? 'var(--kap-aurora-yellow)'
            : state === 'done'  ? 'var(--kap-aurora-green)'
            : 'var(--kap-snow-4)';
          return (
            <div key={s.id} className="flex items-center flex-1 min-w-[140px]">
              <button
                type="button"
                data-state={state}
                className="kap-station w-full"
                onClick={() => onClickStation?.(s.id)}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span
                    className="kap-mono-tag px-1.5 py-0.5 border"
                    style={{ color: stateColor, borderColor: stateColor }}
                  >
                    {s.id}
                  </span>
                  <Icon size={13} strokeWidth={1.5} style={{ color: 'var(--kap-snow-3)' }} />
                  {state === 'active' && (
                    <span className="ml-auto inline-flex items-center gap-1.5 kap-mono-tag" style={{ color: 'var(--kap-aurora-yellow)' }}>
                      <span className="kap-pulse inline-block w-1.5 h-1.5 rounded-full" style={{ background: 'var(--kap-aurora-yellow)' }} />
                      ACTIVE
                    </span>
                  )}
                  {state === 'done' && (
                    <span className="ml-auto kap-mono-tag" style={{ color: 'var(--kap-aurora-green)' }}>DONE</span>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--kap-font-display)',
                    fontWeight: state === 'active' ? 700 : 500,
                    fontSize: '14px',
                    color: state === 'pending' ? 'var(--kap-snow-4)' : 'var(--kap-snow-1)',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {t(s.labelKey)}
                </div>
                {s.hintKey && (
                  <div
                    className="mt-0.5"
                    style={{
                      fontFamily: 'var(--kap-font-body)',
                      fontWeight: 200,
                      fontSize: '11px',
                      color: 'var(--kap-snow-4)',
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
                  className="shrink-0 mx-1.5"
                  style={{ color: state === 'done' ? 'var(--kap-aurora-green)' : 'rgba(216,222,233,0.25)' }}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}


// ════════════════════════════════════════════════════════════
//  StatTile — 三中心通用统计单元
// ════════════════════════════════════════════════════════════
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
    state === 'alert' ? 'var(--kap-aurora-red)'
    : state === 'good'  ? 'var(--kap-aurora-green)'
    : 'var(--kap-snow-1)';

  return (
    <div className="kap-card kap-card-strip kap-stat">
      <div className="kap-stat-label">{t(labelKey)}</div>
      <div className="kap-stat-value" style={{ color: valueColor }}>
        {value}
        {suffix && <span className="kap-stat-suffix">{suffix}</span>}
      </div>
    </div>
  );
}


// ════════════════════════════════════════════════════════════
//  KapCard — 通用卡片
// ════════════════════════════════════════════════════════════
export function KapCard({
  titleKey,
  eyebrow,
  children,
  className = '',
  frost = false,
  rightSlot,
}: {
  titleKey?: TranslationKey;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
  frost?: boolean;
  rightSlot?: ReactNode;
}) {
  const { t } = useLocale();
  return (
    <section className={`kap-card ${frost ? 'kap-card-frost' : ''} ${className}`} style={{ padding: '1.4rem' }}>
      {(titleKey || eyebrow) && (
        <header className="flex items-center justify-between mb-4">
          <div>
            {eyebrow && (
              <div className="kap-mono-tag mb-1" style={{ color: 'var(--kap-snow-4)' }}>
                {eyebrow}
              </div>
            )}
            {titleKey && (
              <h3 className="kap-section-title" style={{ fontSize: '1.05rem' }}>
                {t(titleKey)}
              </h3>
            )}
          </div>
          {rightSlot}
        </header>
      )}
      {children}
    </section>
  );
}
