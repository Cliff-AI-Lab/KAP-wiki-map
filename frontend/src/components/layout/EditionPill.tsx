/**
 * EditionPill — 咨询中心 / 知识中心 / 消费中心 三 tab 切换（M21 #1）
 *
 * AI4S 风：圆角 pill + 激活滑块 + 280ms 缓动
 */
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMode, type Mode } from '@/contexts/ModeContext';
import { useLocale } from '@/contexts/LocaleContext';

/** 路由 path → mode 的映射 */
function inferModeFromPath(pathname: string): Mode {
  if (pathname.startsWith('/v15/consult') || pathname.startsWith('/agent/architect')) return 'consult';
  if (pathname.startsWith('/v15/manage')) return 'manage';
  return 'read';
}

const _ORDER: Mode[] = ['consult', 'manage', 'read'];

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

  const activeIdx = _ORDER.indexOf(mode);

  return (
    <div
      className="relative inline-flex items-center p-1 rounded-pill border border-th-border bg-elevated"
      role="tablist"
      aria-label={t('mode.tablistLabel')}
    >
      <div
        className="absolute top-1 bottom-1 rounded-pill bg-accent shadow-sm"
        style={{
          width: 'calc(33.333% - 3px)',
          left: '4px',
          transform: `translateX(${activeIdx * 100}%)`,
          transition: 'transform 280ms cubic-bezier(.4,0,.2,1)',
        }}
        aria-hidden="true"
      />
      {OPTIONS.map((opt) => {
        const active = mode === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => handleClick(opt.value)}
            className={`relative z-10 px-4 py-1.5 text-sm font-medium rounded-pill transition-colors whitespace-nowrap ${
              active ? 'text-white' : 'text-th-text-muted hover:text-th-text-primary'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
