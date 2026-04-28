/**
 * Tailwind CSS 配置 - 知识图鉴 Wiki-Map V14
 *
 * Linear 精工风设计体系，通过 CSS 变量桥接主题切换。
 * Inter Variable cv01/ss03 + 8px 间距基准 + 靛蓝品牌色
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        /* 四层深度 (base → elevated → surface → hover) */
        base: 'var(--color-bg-base)',
        elevated: 'var(--color-bg-elevated)',
        surface: 'var(--color-bg-surface)',
        hover: 'var(--color-bg-hover)',

        /* 品牌靛蓝 */
        accent: {
          DEFAULT: 'var(--color-accent)',
          light: 'var(--color-accent-light)',
          secondary: 'var(--color-accent-secondary)',
        },

        /* 主题感知文字色 */
        'th-text': {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
          quaternary: 'var(--color-text-quaternary)',
        },

        /* 主题感知边框色 */
        'th-border': {
          DEFAULT: 'var(--color-border)',
          hover: 'var(--color-border-hover)',
          accent: 'var(--color-border-accent)',
          solid: 'var(--color-border-solid)',
        },

        /* 语义状态色 */
        'th-success': 'var(--color-success)',
        'th-warning': 'var(--color-warning)',
        'th-error': 'var(--color-error)',
        'th-info': 'var(--color-info)',
      },

      fontFamily: {
        display: ['Inter Variable', 'Inter', 'SF Pro Display', '-apple-system', 'system-ui', 'sans-serif'],
        sans: ['Inter Variable', 'Inter', 'SF Pro Display', '-apple-system', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Berkeley Mono', 'SF Mono', 'ui-monospace', 'monospace'],
      },

      fontWeight: {
        normal: '400',
        medium: '510',    /* Linear 签名字重 */
        semibold: '590',
        bold: '700',
      },

      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        glow: 'var(--shadow-glow)',
        ring: 'var(--shadow-ring)',
        'ring-accent': 'var(--shadow-ring-accent)',
        elevated: 'var(--shadow-elevated)',
        card: 'var(--shadow-card)',
        button: 'var(--shadow-button)',
        input: 'var(--shadow-input)',
        'card-hover': 'var(--shadow-card-hover)',
      },

      borderRadius: {
        /* Linear 三级圆角 */
        btn: 'var(--radius-sm)',     /* 6px */
        card: 'var(--radius-md)',    /* 8px */
        featured: 'var(--radius-lg)', /* 12px */
        pill: 'var(--radius-full)',   /* 9999px */
      },

      letterSpacing: {
        'tight-display': '-0.035em',
        'tight-heading': '-0.02em',
        'tight-body': '-0.01em',
      },

      transitionTimingFunction: {
        linear: 'cubic-bezier(0.21, 0.68, 0.42, 0.98)',
      },
    },
  },
  plugins: [],
};
