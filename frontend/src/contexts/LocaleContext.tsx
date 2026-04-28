/**
 * LocaleContext — V15 Phase F i18n 上下文
 *
 * 中英双语，localStorage['wikimap-locale'] 持久化。
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { translate, type Locale, type TranslationKey } from '@/lib/i18n';

const STORAGE_KEY = 'wikimap-locale';

interface LocaleContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'zh';
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === 'en' ? 'en' : 'zh';
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN';
  }, [locale]);

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);
  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );

  return <LocaleContext.Provider value={{ locale, setLocale, t }}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale must be used inside <LocaleProvider>');
  return ctx;
}
