/**
 * EditionPill — 消费 / 治理 模式切换控件
 *
 * AI4S 风：圆角 pill + 暖橙激活滑块 + 280ms 缓动
 */
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMode, type Mode } from '@/contexts/ModeContext';
import { useLocale } from '@/contexts/LocaleContext';

/** 路由 path → mode 的映射 */
function inferModeFromPath(pathname: string): Mode {
  if (pathname.startsWith('/v15/manage')) return 'manage';
  return 'read'; // /v15/read 及其他默认消费
}

export function EditionPill() {
  const { mode, setMode } = useMode();
  const { t } = useLocale();
  const navigate = useNavigate();
  const location = useLocation();

  // 路由变化时同步 mode（保持 Pill 视觉状态正确）
  useEffect(() => {
    const inferred = inferModeFromPath(location.pathname);
    if (inferred !== mode) setMode(inferred);
  }, [location.pathname, mode, setMode]);

  const handleClick = (value: Mode) => {
    setMode(value);
    // 真实切页面: 治理 → /v15/manage / 消费 → /v15/read
    navigate(value === 'manage' ? '/v15/manage' : '/v15/read');
  };

  const OPTIONS: { value: Mode; label: string }[] = [
    { value: 'read',   label: t('mode.read') },
    { value: 'manage', label: t('mode.manage') },
  ];

  return (
    <div
      className="relative inline-flex items-center p-1 rounded-pill border border-th-border bg-elevated"
      role="tablist"
      aria-label="模式切换"
    >
      <div
        className="absolute top-1 bottom-1 rounded-pill bg-accent shadow-sm"
        style={{
          width: 'calc(50% - 4px)',
          transform: mode === 'read' ? 'translateX(0)' : 'translateX(100%)',
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
            className={`relative z-10 px-5 py-1.5 text-sm font-medium rounded-pill transition-colors ${
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
