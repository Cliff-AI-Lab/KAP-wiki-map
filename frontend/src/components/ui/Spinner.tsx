/**
 * Spinner 加载指示器 — Linear 风格
 * SVG 旋转动画 + 靛蓝品牌色
 */
export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZE_MAP = { sm: 14, md: 20, lg: 28 };

export function Spinner({ size = 'md', className = '' }: SpinnerProps) {
  const s = SIZE_MAP[size];
  return (
    <svg
      className={`animate-spin ${className}`}
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle
        cx="12" cy="12" r="10"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        opacity="0.15"
      />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
