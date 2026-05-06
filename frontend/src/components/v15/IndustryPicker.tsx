/**
 * IndustryPicker — 咨询中心前置 · 行业模板选择 (M21 #9)
 *
 * 选完行业才进入对话；选过的行业持久化到 localStorage['kap-consult-industry']。
 */
import { useState } from 'react';
import {
  Factory, Zap, Banknote, HeartPulse, Cpu, ShoppingBag,
  GraduationCap, Building2, Sparkles, ArrowRight, Settings2,
  type LucideIcon,
} from 'lucide-react';

import { useLocale } from '@/contexts/LocaleContext';
import type { TranslationKey } from '@/lib/i18n';

export const INDUSTRY_STORAGE_KEY = 'kap-consult-industry';

export interface IndustryChoice {
  /** 业务 code（与后端 L1 industry_code 对齐） */
  code: string;
  labelKey: TranslationKey;
  descKey: TranslationKey;
  icon: LucideIcon;
}

const INDUSTRIES: IndustryChoice[] = [
  { code: 'manufacturing', labelKey: 'consult.industry.manufacturing', descKey: 'consult.industry.manufacturing.desc', icon: Factory },
  { code: 'energy',        labelKey: 'consult.industry.energy',        descKey: 'consult.industry.energy.desc',        icon: Zap },
  { code: 'finance',       labelKey: 'consult.industry.finance',       descKey: 'consult.industry.finance.desc',       icon: Banknote },
  { code: 'medical',       labelKey: 'consult.industry.medical',       descKey: 'consult.industry.medical.desc',       icon: HeartPulse },
  { code: 'it',            labelKey: 'consult.industry.it',            descKey: 'consult.industry.it.desc',            icon: Cpu },
  { code: 'retail',        labelKey: 'consult.industry.retail',        descKey: 'consult.industry.retail.desc',        icon: ShoppingBag },
  { code: 'education',     labelKey: 'consult.industry.education',     descKey: 'consult.industry.education.desc',     icon: GraduationCap },
  { code: 'gov',           labelKey: 'consult.industry.gov',           descKey: 'consult.industry.gov.desc',           icon: Building2 },
];

const CUSTOM = {
  code: 'custom',
  labelKey: 'consult.industry.custom' as TranslationKey,
  descKey: 'consult.industry.custom.desc' as TranslationKey,
  icon: Settings2,
};


export function loadSavedIndustry(): string | null {
  if (typeof window === 'undefined') return null;
  try { return window.localStorage.getItem(INDUSTRY_STORAGE_KEY); }
  catch { return null; }
}
export function saveIndustry(code: string) {
  if (typeof window === 'undefined') return;
  try { window.localStorage.setItem(INDUSTRY_STORAGE_KEY, code); }
  catch { /* ignore */ }
}
export function clearSavedIndustry() {
  if (typeof window === 'undefined') return;
  try { window.localStorage.removeItem(INDUSTRY_STORAGE_KEY); }
  catch { /* ignore */ }
}


export default function IndustryPicker({
  onConfirm,
}: {
  onConfirm: (code: string, label: string) => void;
}) {
  const { t } = useLocale();
  const [selected, setSelected] = useState<string>('');
  const [customLabel, setCustomLabel] = useState<string>('');

  const isCustom = selected === 'custom';
  const canNext =
    (selected && !isCustom) || (isCustom && customLabel.trim().length > 0);

  const confirm = () => {
    if (!canNext) return;
    if (isCustom) {
      const code = `custom_${customLabel.trim().slice(0, 20).replace(/\s+/g, '_')}`;
      saveIndustry(code);
      onConfirm(code, customLabel.trim());
    } else {
      const choice = INDUSTRIES.find(x => x.code === selected);
      if (!choice) return;
      saveIndustry(choice.code);
      onConfirm(choice.code, t(choice.labelKey));
    }
  };

  return (
    <>
      <header className="kap-anim mb-7">
        <div className="kap-eyebrow">
          <Sparkles size={12} strokeWidth={2} />
          {t('mode.consult')}
        </div>
        <h1 className="kap-headline">{t('consult.industry.title')}</h1>
        <p className="kap-subhead">{t('consult.industry.subtitle')}</p>
      </header>

      <section
        className="kap-stagger grid gap-3 mb-5"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}
      >
        {INDUSTRIES.map((it) => (
          <IndustryCard
            key={it.code}
            spec={it}
            active={selected === it.code}
            onSelect={() => setSelected(it.code)}
            t={t}
          />
        ))}
        <IndustryCard
          spec={CUSTOM}
          active={selected === 'custom'}
          onSelect={() => setSelected('custom')}
          t={t}
        />
      </section>

      {isCustom && (
        <div className="kap-anim mb-5">
          <input
            type="text"
            value={customLabel}
            onChange={(e) => setCustomLabel(e.target.value)}
            placeholder={t('consult.industry.customPlaceholder')}
            className="kap-input"
            autoFocus
          />
        </div>
      )}

      <div className="flex items-center justify-end gap-3 mt-6">
        <button
          type="button"
          onClick={() => onConfirm('default', t('consult.industry.skip'))}
          className="kap-btn kap-btn-ghost"
        >
          {t('consult.industry.skip')}
        </button>
        <button
          type="button"
          onClick={confirm}
          disabled={!canNext}
          className="kap-btn kap-btn-primary"
        >
          {t('consult.industry.next')}
          <ArrowRight size={13} />
        </button>
      </div>
    </>
  );
}


function IndustryCard({
  spec, active, onSelect, t,
}: {
  spec: { code: string; labelKey: TranslationKey; descKey: TranslationKey; icon: LucideIcon };
  active: boolean;
  onSelect: () => void;
  t: (k: TranslationKey) => string;
}) {
  const Icon = spec.icon;
  return (
    <button
      type="button"
      onClick={onSelect}
      className="kap-card text-left transition-all"
      style={{
        padding: '1.1rem 1.2rem',
        cursor: 'pointer',
        borderColor: active ? 'hsl(var(--primary))' : 'hsl(var(--card-border))',
        background: active ? 'hsl(var(--primary) / 0.06)' : 'hsl(var(--card))',
        boxShadow: active ? '0 0 0 1px hsl(var(--primary) / 0.3)' : 'none',
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className="grid place-items-center shrink-0"
          style={{
            width: 36, height: 36,
            background: active
              ? 'hsl(var(--primary) / 0.15)'
              : 'hsl(var(--muted))',
            borderRadius: 'calc(var(--radius) - 4px)',
          }}
        >
          <Icon
            size={16}
            strokeWidth={1.7}
            style={{
              color: active ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))',
            }}
          />
        </div>
        <div className="flex-1">
          <div
            style={{
              fontFamily: 'var(--font-sans)',
              fontWeight: 600,
              fontSize: 14.5,
              letterSpacing: '-0.01em',
              color: 'hsl(var(--foreground))',
            }}
          >
            {t(spec.labelKey)}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-sans)',
              fontWeight: 400,
              fontSize: 12,
              color: 'hsl(var(--muted-foreground))',
              marginTop: 4,
              lineHeight: 1.5,
            }}
          >
            {t(spec.descKey)}
          </div>
        </div>
      </div>
    </button>
  );
}
