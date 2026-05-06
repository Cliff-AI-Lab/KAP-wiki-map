/**
 * OverviewHome — 三中心总览页 (M21 #9)
 *
 * 登录后默认进入。介绍三中心能力 + 串联流程 + 各中心入口。
 */
import { Link } from 'react-router-dom';
import {
  Sparkles, Database, Compass, ArrowRight, Check,
  type LucideIcon,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import type { TranslationKey } from '@/lib/i18n';

interface CenterCardSpec {
  to: string;
  icon: LucideIcon;
  accent: string;        // hsl ref
  badgeKey: TranslationKey;
  titleKey: TranslationKey;
  descKey: TranslationKey;
  features: TranslationKey[];
  ctaKey: TranslationKey;
}

const CENTERS: CenterCardSpec[] = [
  {
    to: '/v15/consult',
    icon: Sparkles,
    accent: 'hsl(var(--primary))',
    badgeKey: 'mode.consult',
    titleKey: 'overview.consult.title',
    descKey: 'overview.consult.desc',
    features: [
      'overview.consult.feature1',
      'overview.consult.feature2',
      'overview.consult.feature3',
    ],
    ctaKey: 'overview.consult.cta',
  },
  {
    to: '/v15/manage',
    icon: Database,
    accent: 'hsl(var(--warning))',
    badgeKey: 'mode.manage',
    titleKey: 'overview.manage.title',
    descKey: 'overview.manage.desc',
    features: [
      'overview.manage.feature1',
      'overview.manage.feature2',
      'overview.manage.feature3',
    ],
    ctaKey: 'overview.manage.cta',
  },
  {
    to: '/v15/read',
    icon: Compass,
    accent: 'hsl(var(--success))',
    badgeKey: 'mode.read',
    titleKey: 'overview.read.title',
    descKey: 'overview.read.desc',
    features: [
      'overview.read.feature1',
      'overview.read.feature2',
      'overview.read.feature3',
    ],
    ctaKey: 'overview.read.cta',
  },
];


export default function OverviewHome() {
  const { t } = useLocale();

  return (
    <>
      {/* Hero */}
      <header className="kap-anim mb-10 text-center">
        <div className="kap-eyebrow justify-center" style={{ display: 'inline-flex' }}>
          <Sparkles size={12} strokeWidth={2} />
          {t('overview.eyebrow')}
        </div>
        <h1 className="kap-headline" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', textAlign: 'center' }}>
          {t('overview.title')}
        </h1>
        <p
          className="kap-subhead mx-auto"
          style={{ textAlign: 'center', maxWidth: 760 }}
        >
          {t('overview.subtitle')}
        </p>
      </header>

      {/* 三中心串联流程 */}
      <section
        className="kap-anim mb-8 flex items-center justify-center gap-3 flex-wrap"
        style={{
          padding: '1rem 1.5rem',
          background: 'hsl(var(--muted) / 0.5)',
          border: '1px dashed hsl(var(--border))',
          borderRadius: 'var(--radius)',
        }}
      >
        {CENTERS.map((c, i) => {
          const Icon = c.icon;
          return (
            <div key={c.to} className="flex items-center gap-3">
              <span
                className="inline-flex items-center gap-2 px-3 py-1.5"
                style={{
                  background: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 'calc(var(--radius) - 4px)',
                }}
              >
                <Icon size={13} strokeWidth={1.8} style={{ color: c.accent }} />
                <span
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontWeight: 500,
                    fontSize: 13,
                    color: 'hsl(var(--foreground))',
                  }}
                >
                  {t(c.badgeKey)}
                </span>
              </span>
              {i < CENTERS.length - 1 && (
                <ArrowRight
                  size={14}
                  strokeWidth={1.5}
                  style={{ color: 'hsl(var(--muted-foreground))' }}
                />
              )}
            </div>
          );
        })}
        <span
          className="kap-mono-tag ml-2"
          style={{ color: 'hsl(var(--muted-foreground))' }}
        >
          {t('overview.flow')}
        </span>
      </section>

      {/* 三中心卡片 */}
      <section
        className="kap-stagger grid gap-5"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}
      >
        {CENTERS.map((c) => (
          <CenterCard key={c.to} spec={c} t={t} />
        ))}
      </section>
    </>
  );
}


function CenterCard({
  spec,
  t,
}: {
  spec: CenterCardSpec;
  t: (k: TranslationKey) => string;
}) {
  const Icon = spec.icon;
  return (
    <Link
      to={spec.to}
      className="kap-card group"
      style={{
        padding: '1.6rem',
        textDecoration: 'none',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* accent strip 顶部 */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: spec.accent,
        }}
      />

      <div className="flex items-start justify-between mb-4">
        <div
          className="grid place-items-center"
          style={{
            width: 44,
            height: 44,
            background: `${spec.accent.replace(')', ' / 0.12)')}`,
            border: `1px solid ${spec.accent.replace(')', ' / 0.4)')}`,
            borderRadius: 'calc(var(--radius) - 2px)',
          }}
        >
          <Icon size={20} strokeWidth={1.6} style={{ color: spec.accent }} />
        </div>
        <span
          className="kap-mono-tag"
          style={{
            color: spec.accent,
            border: `1px solid ${spec.accent.replace(')', ' / 0.4)')}`,
            padding: '2px 8px',
            borderRadius: 9999,
            fontSize: 10,
          }}
        >
          {t(spec.badgeKey)}
        </span>
      </div>

      <h3
        style={{
          fontFamily: 'var(--font-sans)',
          fontWeight: 700,
          fontSize: '1.4rem',
          letterSpacing: '-0.02em',
          color: 'hsl(var(--foreground))',
          margin: '0 0 0.5rem',
        }}
      >
        {t(spec.titleKey)}
      </h3>

      <p
        style={{
          fontFamily: 'var(--font-sans)',
          fontWeight: 400,
          fontSize: 13.5,
          color: 'hsl(var(--muted-foreground))',
          lineHeight: 1.6,
          margin: 0,
        }}
      >
        {t(spec.descKey)}
      </p>

      <ul
        className="my-5 space-y-2"
        style={{ listStyle: 'none', padding: 0 }}
      >
        {spec.features.map((f) => (
          <li
            key={f}
            className="flex items-start gap-2"
            style={{
              fontFamily: 'var(--font-sans)',
              fontWeight: 400,
              fontSize: 12.5,
              color: 'hsl(var(--foreground) / 0.85)',
              lineHeight: 1.55,
            }}
          >
            <Check
              size={13}
              strokeWidth={2}
              style={{ color: spec.accent, marginTop: 2, flexShrink: 0 }}
            />
            <span>{t(f)}</span>
          </li>
        ))}
      </ul>

      <div className="flex-1" />

      <div
        className="flex items-center justify-between mt-2 pt-3"
        style={{ borderTop: '1px solid hsl(var(--border))' }}
      >
        <span
          style={{
            fontFamily: 'var(--font-sans)',
            fontWeight: 600,
            fontSize: 13,
            color: spec.accent,
          }}
        >
          {t(spec.ctaKey)}
        </span>
        <ArrowRight
          size={14}
          strokeWidth={2}
          style={{
            color: spec.accent,
            transition: 'transform 200ms ease',
          }}
          className="group-hover:translate-x-1"
        />
      </div>
    </Link>
  );
}
