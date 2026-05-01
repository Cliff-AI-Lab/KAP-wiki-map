/**
 * LanguageSwitcher — zh/en 语言切换按钮组（M16 #1）。
 *
 * 复用既有 LocaleContext（lib/i18n.ts 字典）。
 */
import { Languages } from 'lucide-react';
import { useLocale } from '@/contexts/LocaleContext';

export default function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();
  const baseClass =
    'inline-flex items-center px-2 py-0.5 text-[11px] rounded-btn border transition';
  return (
    <div className="inline-flex items-center gap-1 text-th-text-muted">
      <Languages size={12} />
      <button
        type="button"
        onClick={() => setLocale('zh')}
        className={`${baseClass} ${
          locale === 'zh'
            ? 'border-accent text-accent bg-accent/10'
            : 'border-th-border hover:border-accent hover:text-accent'
        }`}
        aria-pressed={locale === 'zh'}
      >
        中
      </button>
      <button
        type="button"
        onClick={() => setLocale('en')}
        className={`${baseClass} ${
          locale === 'en'
            ? 'border-accent text-accent bg-accent/10'
            : 'border-th-border hover:border-accent hover:text-accent'
        }`}
        aria-pressed={locale === 'en'}
      >
        EN
      </button>
    </div>
  );
}
