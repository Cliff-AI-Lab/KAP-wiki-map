/**
 * EditionPill — 三中心切换（M21 #5 · shadcn 风 .kap-nav）
 */
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMode, type Mode } from '@/contexts/ModeContext';
import { useLocale } from '@/contexts/LocaleContext';

function inferModeFromPath(pathname: string): Mode {
  if (pathname.startsWith('/v15/consult') || pathname.startsWith('/agent/architect')) return 'consult';
  if (pathname.startsWith('/v15/manage')) return 'manage';
  return 'read';
}

export function EditionPill() {
  const { mode, setMode } = useMode();
  const { t } = useLocale();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const inferred = inferModeFromPath(location.pathname);
    if (inferred !== mode) setMode(inferred);
  }, [location.pathname, mode, setMode]);

  const handleClick = (value: Mode) => {
    setMode(value);
    if (value === 'consult') navigate('/v15/consult');
    else if (value === 'manage') navigate('/v15/manage');
    else navigate('/v15/read');
  };

  const OPTIONS: { value: Mode; label: string }[] = [
    { value: 'consult', label: t('mode.consult') },
    { value: 'manage',  label: t('mode.manage') },
    { value: 'read',    label: t('mode.read') },
  ];

  return (
    <div className="kap-nav" role="tablist" aria-label={t('mode.tablistLabel')}>
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={mode === opt.value}
          data-active={mode === opt.value}
          onClick={() => handleClick(opt.value)}
          className="kap-nav-item"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
