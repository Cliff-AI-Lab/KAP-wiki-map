/**
 * 主题配置模块 — 知识图鉴 Wiki-Map V14
 *
 * 通过 CSS 变量实现运行时主题切换。
 * Linear Dark (默认) / Raycast Dark / Classic Gold Dark / GitHub Light / Nord Dark / Warm Light
 *
 * V14: Linear 精工风为默认主题 — 靛蓝品牌色 + 透明卡片 + Inter Variable
 */

/** 主题定义接口 */
export interface Theme {
  id: string;
  name: string;
  colorScheme: 'dark' | 'light';
  colors: {
    bgBase: string;
    bgElevated: string;
    bgSurface: string;
    bgHover: string;
    accent: string;
    accentLight: string;
    accentSecondary: string;
    success: string;
    warning: string;
    error: string;
    info: string;
    textPrimary: string;
    textSecondary: string;
    textMuted: string;
    border: string;
    borderHover: string;
    borderAccent: string;
  };
  shadows: {
    sm: string;
    md: string;
    lg: string;
    glow: string;
    ring: string;
    ringAccent: string;
    elevated: string;
    /** Raycast 多层 inset 卡片阴影 */
    card: string;
    /** Raycast 按钮 inset 高光阴影 */
    button: string;
    /** Raycast 输入框内凹阴影 */
    input: string;
    /** 卡片 hover 状态阴影 */
    cardHover: string;
  };
  gradients: [string, string, string];
}

/** 内置主题列表，第一个为默认主题 */
export const themes: Theme[] = [
  /* --- Nordic Minimalism: Nord 色板 (V15 新默认, distinctive-frontend skill) --- */
  {
    id: 'nordic-v15',
    name: 'Nordic V15',
    colorScheme: 'dark',
    colors: {
      bgBase: '#2e3440',
      bgElevated: '#3b4252',
      bgSurface: '#434c5e',
      bgHover: '#4c566a',
      accent: '#88c0d0',
      accentLight: '#8fbcbb',
      accentSecondary: '#81a1c1',
      success: '#a3be8c',
      warning: '#ebcb8b',
      error: '#bf616a',
      info: '#88c0d0',
      textPrimary: '#eceff4',
      textSecondary: '#d8dee9',
      textMuted: '#a3b1c4',
      border: 'rgba(236, 239, 244, 0.08)',
      borderHover: 'rgba(236, 239, 244, 0.16)',
      borderAccent: 'rgba(136, 192, 208, 0.5)',
    },
    shadows: {
      sm: '0 1px 2px rgba(0, 0, 0, 0.3)',
      md: '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(236, 239, 244, 0.05)',
      lg: '0 8px 24px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(236, 239, 244, 0.08)',
      glow: '0 0 24px rgba(136, 192, 208, 0.18)',
      ring: '0px 0px 0px 1px rgba(236, 239, 244, 0.08)',
      ringAccent: '0px 0px 0px 1px rgba(136, 192, 208, 0.5)',
      elevated: '0px 0px 0px 1px rgba(236, 239, 244, 0.06), 0 2px 8px rgba(0, 0, 0, 0.3)',
      card: '0px 0px 0px 1px rgba(236, 239, 244, 0.06)',
      button: 'inset 0 1px 0 rgba(236, 239, 244, 0.06), 0 0 0 1px rgba(236, 239, 244, 0.08)',
      input: '0px 0px 0px 1px rgba(236, 239, 244, 0.08), inset 0 1px 2px rgba(0, 0, 0, 0.2)',
      cardHover: '0px 0px 0px 1px rgba(136, 192, 208, 0.4), 0 4px 16px rgba(0, 0, 0, 0.4)',
    },
    gradients: ['rgba(136, 192, 208, 0.18)', 'rgba(163, 190, 140, 0.10)', 'rgba(191, 97, 106, 0.08)'],
  },
  /* --- AI4S Warm: 暖橙浅色 (V15 旧默认, 可切换回退) --- */
  {
    id: 'ai4s-warm',
    name: 'AI4S Warm',
    colorScheme: 'light',
    colors: {
      bgBase: '#fafaf7',
      bgElevated: '#ffffff',
      bgSurface: '#f5f3ee',
      bgHover: '#f0ece4',
      accent: '#d97757',
      accentLight: '#e69377',
      accentSecondary: '#b85c41',
      success: '#16a34a',
      warning: '#ca8a04',
      error: '#dc2626',
      info: '#d97757',
      textPrimary: '#2a2a28',
      textSecondary: '#57544e',
      textMuted: '#8a847c',
      border: 'rgba(0, 0, 0, 0.08)',
      borderHover: 'rgba(0, 0, 0, 0.12)',
      borderAccent: 'rgba(217, 119, 87, 0.35)',
    },
    shadows: {
      sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
      md: '0 2px 8px rgba(0, 0, 0, 0.06), 0 0 0 1px rgba(0, 0, 0, 0.04)',
      lg: '0 8px 24px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.05)',
      glow: '0 0 20px rgba(217, 119, 87, 0.12)',
      ring: '0px 0px 0px 1px rgba(0, 0, 0, 0.06)',
      ringAccent: '0px 0px 0px 1px rgba(217, 119, 87, 0.35)',
      elevated: '0px 0px 0px 1px rgba(0, 0, 0, 0.06), 0 2px 8px rgba(0, 0, 0, 0.04)',
      card: '0px 0px 0px 1px rgba(0, 0, 0, 0.06)',
      button: 'inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 0 0 1px rgba(0, 0, 0, 0.08)',
      input: '0px 0px 0px 1px rgba(0, 0, 0, 0.08), inset 0 1px 2px rgba(0, 0, 0, 0.03)',
      cardHover: '0px 0px 0px 1px rgba(217, 119, 87, 0.25), 0 4px 16px rgba(0, 0, 0, 0.06)',
    },
    gradients: ['rgba(217, 119, 87, 0.05)', 'rgba(247, 231, 223, 0.6)', 'rgba(217, 119, 87, 0.02)'],
  },
  /* --- Wiki-Map Gold: 金色精工风 (V14 旧默认, 保留) --- */
  {
    id: 'linear-dark',
    name: 'Wiki-Map Gold',
    colorScheme: 'dark',
    colors: {
      bgBase: '#08090a',
      bgElevated: '#0f1011',
      bgSurface: '#191a1b',
      bgHover: '#28282c',
      accent: '#d4a656',
      accentLight: '#e6be7a',
      accentSecondary: '#c99a45',
      success: '#3fb950',
      warning: '#d29922',
      error: '#f85149',
      info: '#d4a656',
      textPrimary: '#f7f8f8',
      textSecondary: '#d0d6e0',
      textMuted: '#8a8f98',
      border: 'rgba(255, 255, 255, 0.05)',
      borderHover: 'rgba(255, 255, 255, 0.08)',
      borderAccent: 'rgba(212, 166, 86, 0.35)',
    },
    shadows: {
      sm: 'rgba(0, 0, 0, 0.2) 0px 1px 2px',
      md: 'rgba(0, 0, 0, 0.2) 0px 0px 0px 1px, rgba(0, 0, 0, 0.2) 0px 2px 8px',
      lg: 'rgba(0, 0, 0, 0.2) 0px 0px 0px 1px, rgba(0, 0, 0, 0.3) 0px 8px 32px',
      glow: '0 0 20px rgba(212, 166, 86, 0.10)',
      ring: '0px 0px 0px 1px rgba(255, 255, 255, 0.05)',
      ringAccent: '0px 0px 0px 1px rgba(212, 166, 86, 0.35)',
      elevated: 'rgba(0, 0, 0, 0.2) 0px 0px 0px 1px',
      card: 'rgba(0, 0, 0, 0.2) 0px 0px 0px 1px',
      button: 'rgba(255, 255, 255, 0.03) 0px 1px 0px 0px inset, rgba(255, 255, 255, 0.08) 0px 0px 0px 1px',
      input: 'rgba(255, 255, 255, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.2) 0px 2px 4px 0px inset',
      cardHover: 'rgba(255, 255, 255, 0.08) 0px 0px 0px 1px, 0 0 20px rgba(212, 166, 86, 0.06)',
    },
    gradients: ['rgba(212, 166, 86, 0.04)', 'rgba(74, 158, 255, 0.02)', 'rgba(212, 166, 86, 0.02)'],
  },
  /* --- Raycast Dark: 冷蓝精工风 (V10-V13 旧默认) --- */
  {
    id: 'raycast-dark',
    name: 'Raycast Dark',
    colorScheme: 'dark',
    colors: {
      bgBase: '#07080a',
      bgElevated: '#101111',
      bgSurface: '#1b1c1e',
      bgHover: '#252829',
      accent: '#55b3ff',
      accentLight: '#7cc4ff',
      accentSecondary: '#5fc992',
      success: '#5fc992',
      warning: '#ffbc33',
      error: '#FF6363',
      info: '#55b3ff',
      textPrimary: '#eeeeee',
      textSecondary: '#929799',
      textMuted: '#555a5e',
      border: 'rgba(255, 255, 255, 0.06)',
      borderHover: 'rgba(255, 255, 255, 0.10)',
      borderAccent: 'rgba(85, 179, 255, 0.30)',
    },
    shadows: {
      sm: 'rgba(0, 0, 0, 0.28) 0px 1px 2px',
      md: 'rgb(27, 28, 30) 0px 0px 0px 1px, rgba(0, 0, 0, 0.3) 0px 2px 8px',
      lg: 'rgb(27, 28, 30) 0px 0px 0px 1px, rgba(0, 0, 0, 0.4) 0px 8px 32px',
      glow: '0 0 20px rgba(85, 179, 255, 0.10)',
      ring: '0px 0px 0px 1px rgba(255, 255, 255, 0.06)',
      ringAccent: '0px 0px 0px 1px rgba(85, 179, 255, 0.30)',
      elevated: 'rgb(27, 28, 30) 0px 0px 0px 1px, rgb(7, 8, 10) 0px 0px 0px 1px inset',
      card: 'rgb(27, 28, 30) 0px 0px 0px 1px, rgb(7, 8, 10) 0px 0px 0px 1px inset',
      button: 'rgba(255, 255, 255, 0.05) 0px 1px 0px 0px inset, rgba(255, 255, 255, 0.25) 0px 0px 0px 1px',
      input: 'rgb(27, 28, 30) 0px 0px 0px 1px, rgb(21, 21, 23) 0px 0px 0px 1px inset, rgba(0, 0, 0, 0.3) 0px 2px 4px 0px inset',
      cardHover: 'rgb(37, 40, 41) 0px 0px 0px 1px, rgb(7, 8, 10) 0px 0px 0px 1px inset, 0 0 20px rgba(85, 179, 255, 0.06)',
    },
    gradients: ['rgba(85, 179, 255, 0.04)', 'rgba(95, 201, 146, 0.03)', 'rgba(85, 179, 255, 0.02)'],
  },
  /* --- Classic Gold Dark: V9 金色暖调 (保留兼容) --- */
  {
    id: 'classic-gold-dark',
    name: 'Classic Gold',
    colorScheme: 'dark',
    colors: {
      bgBase: '#08090a',
      bgElevated: '#111214',
      bgSurface: '#191a1c',
      bgHover: '#1f2123',
      accent: '#d4a656',
      accentLight: '#e6be7a',
      accentSecondary: '#4a9eff',
      success: '#3fb950',
      warning: '#d29922',
      error: '#f85149',
      info: '#58a6ff',
      textPrimary: '#f0f2f4',
      textSecondary: '#9ca3af',
      textMuted: '#6b7280',
      border: 'rgba(255, 255, 255, 0.08)',
      borderHover: 'rgba(255, 255, 255, 0.14)',
      borderAccent: 'rgba(212, 166, 86, 0.35)',
    },
    shadows: {
      sm: '0 1px 3px rgba(0, 0, 0, 0.6)',
      md: '0 4px 16px rgba(0, 0, 0, 0.5)',
      lg: '0 8px 32px rgba(0, 0, 0, 0.6)',
      glow: '0 0 40px rgba(212, 166, 86, 0.12)',
      ring: '0px 0px 0px 1px rgba(255, 255, 255, 0.08)',
      ringAccent: '0px 0px 0px 1px rgba(212, 166, 86, 0.35)',
      elevated: '0px 0px 0px 1px rgba(255, 255, 255, 0.08), 0 4px 16px rgba(0, 0, 0, 0.4)',
      card: '0px 0px 0px 1px rgba(255, 255, 255, 0.08)',
      button: '0px 0px 0px 1px rgba(212, 166, 86, 0.35)',
      input: '0px 0px 0px 1px rgba(255, 255, 255, 0.08), inset 0 2px 4px rgba(0, 0, 0, 0.3)',
      cardHover: '0px 0px 0px 1px rgba(255, 255, 255, 0.14), 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 40px rgba(212, 166, 86, 0.06)',
    },
    gradients: ['rgba(212, 166, 86, 0.10)', 'rgba(74, 158, 255, 0.07)', 'rgba(212, 166, 86, 0.04)'],
  },
  /* --- GitHub Light --- */
  {
    id: 'github-light',
    name: 'GitHub Light',
    colorScheme: 'light',
    colors: {
      bgBase: '#fafaf9',
      bgElevated: '#ffffff',
      bgSurface: '#f4f4f2',
      bgHover: '#eae8e4',
      accent: '#0969da',
      accentLight: '#218bff',
      accentSecondary: '#1a7f37',
      success: '#1a7f37',
      warning: '#9a6700',
      error: '#cf222e',
      info: '#0969da',
      textPrimary: '#1f2328',
      textSecondary: '#656d76',
      textMuted: '#8b949e',
      border: 'rgba(28, 25, 23, 0.12)',
      borderHover: 'rgba(28, 25, 23, 0.25)',
      borderAccent: 'rgba(9, 105, 218, 0.35)',
    },
    shadows: {
      sm: '0 1px 2px rgba(0, 0, 0, 0.06)',
      md: '0 4px 12px rgba(0, 0, 0, 0.08)',
      lg: '0 8px 24px rgba(0, 0, 0, 0.1)',
      glow: '0 0 20px rgba(9, 105, 218, 0.06)',
      ring: '0px 0px 0px 1px rgba(28, 25, 23, 0.12)',
      ringAccent: '0px 0px 0px 1px rgba(9, 105, 218, 0.35)',
      elevated: '0px 0px 0px 1px rgba(28, 25, 23, 0.12), 0 4px 12px rgba(0, 0, 0, 0.06)',
      card: '0px 0px 0px 1px rgba(28, 25, 23, 0.12)',
      button: '0px 0px 0px 1px rgba(28, 25, 23, 0.20), 0 1px 2px rgba(0, 0, 0, 0.06)',
      input: '0px 0px 0px 1px rgba(28, 25, 23, 0.12), inset 0 1px 2px rgba(0, 0, 0, 0.04)',
      cardHover: '0px 0px 0px 1px rgba(28, 25, 23, 0.20), 0 4px 16px rgba(0, 0, 0, 0.08)',
    },
    gradients: ['rgba(9, 105, 218, 0.03)', 'rgba(26, 127, 55, 0.02)', 'rgba(9, 105, 218, 0.01)'],
  },
  /* --- Nord Dark --- */
  {
    id: 'nord-dark',
    name: 'Nord Dark',
    colorScheme: 'dark',
    colors: {
      bgBase: '#242933',
      bgElevated: '#2e3440',
      bgSurface: '#3b4252',
      bgHover: '#434c5e',
      accent: '#88c0d0',
      accentLight: '#8fbcbb',
      accentSecondary: '#81a1c1',
      success: '#a3be8c',
      warning: '#ebcb8b',
      error: '#bf616a',
      info: '#5e81ac',
      textPrimary: '#eceff4',
      textSecondary: '#d8dee9',
      textMuted: '#7b88a1',
      border: 'rgba(255, 255, 255, 0.07)',
      borderHover: 'rgba(255, 255, 255, 0.13)',
      borderAccent: 'rgba(136, 192, 208, 0.30)',
    },
    shadows: {
      sm: '0 1px 3px rgba(0, 0, 0, 0.5)',
      md: '0 4px 16px rgba(0, 0, 0, 0.4)',
      lg: '0 8px 32px rgba(0, 0, 0, 0.5)',
      glow: '0 0 40px rgba(136, 192, 208, 0.10)',
      ring: '0px 0px 0px 1px rgba(255, 255, 255, 0.07)',
      ringAccent: '0px 0px 0px 1px rgba(136, 192, 208, 0.30)',
      elevated: '0px 0px 0px 1px rgba(255, 255, 255, 0.07), 0 4px 16px rgba(0, 0, 0, 0.3)',
      card: '0px 0px 0px 1px rgba(255, 255, 255, 0.07)',
      button: '0px 0px 0px 1px rgba(136, 192, 208, 0.30)',
      input: '0px 0px 0px 1px rgba(255, 255, 255, 0.07), inset 0 2px 4px rgba(0, 0, 0, 0.2)',
      cardHover: '0px 0px 0px 1px rgba(255, 255, 255, 0.13), 0 4px 16px rgba(0, 0, 0, 0.3)',
    },
    gradients: ['rgba(136, 192, 208, 0.08)', 'rgba(129, 161, 193, 0.06)', 'rgba(136, 192, 208, 0.03)'],
  },
  /* --- Warm Light --- */
  {
    id: 'warm-light',
    name: 'Warm Light',
    colorScheme: 'light',
    colors: {
      bgBase: '#faf8f5',
      bgElevated: '#ffffff',
      bgSurface: '#f3f0eb',
      bgHover: '#ebe7e0',
      accent: '#b8860b',
      accentLight: '#daa520',
      accentSecondary: '#2563eb',
      success: '#16a34a',
      warning: '#ca8a04',
      error: '#dc2626',
      info: '#2563eb',
      textPrimary: '#1c1917',
      textSecondary: '#57534e',
      textMuted: '#a8a29e',
      border: 'rgba(28, 25, 23, 0.1)',
      borderHover: 'rgba(28, 25, 23, 0.2)',
      borderAccent: 'rgba(184, 134, 11, 0.3)',
    },
    shadows: {
      sm: '0 1px 2px rgba(0, 0, 0, 0.06)',
      md: '0 4px 12px rgba(0, 0, 0, 0.08)',
      lg: '0 8px 24px rgba(0, 0, 0, 0.1)',
      glow: '0 0 20px rgba(184, 134, 11, 0.08)',
      ring: '0px 0px 0px 1px rgba(28, 25, 23, 0.1)',
      ringAccent: '0px 0px 0px 1px rgba(184, 134, 11, 0.3)',
      elevated: '0px 0px 0px 1px rgba(28, 25, 23, 0.1), 0 4px 12px rgba(0, 0, 0, 0.05)',
      card: '0px 0px 0px 1px rgba(28, 25, 23, 0.1)',
      button: '0px 0px 0px 1px rgba(28, 25, 23, 0.15), 0 1px 2px rgba(0, 0, 0, 0.05)',
      input: '0px 0px 0px 1px rgba(28, 25, 23, 0.1), inset 0 1px 2px rgba(0, 0, 0, 0.03)',
      cardHover: '0px 0px 0px 1px rgba(28, 25, 23, 0.2), 0 4px 16px rgba(0, 0, 0, 0.06)',
    },
    gradients: ['rgba(184, 134, 11, 0.04)', 'rgba(37, 99, 235, 0.03)', 'rgba(184, 134, 11, 0.02)'],
  },
];

const STORAGE_KEY = 'bookworm-theme';

/**
 * 应用主题到页面 — 设置所有 CSS 变量
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;

  /* 背景层级 */
  root.style.setProperty('--color-bg-base', theme.colors.bgBase);
  root.style.setProperty('--color-bg-elevated', theme.colors.bgElevated);
  root.style.setProperty('--color-bg-surface', theme.colors.bgSurface);
  root.style.setProperty('--color-bg-hover', theme.colors.bgHover);

  /* 品牌色 */
  root.style.setProperty('--color-accent', theme.colors.accent);
  root.style.setProperty('--color-accent-light', theme.colors.accentLight);
  root.style.setProperty('--color-accent-secondary', theme.colors.accentSecondary);

  /* 语义色 */
  root.style.setProperty('--color-success', theme.colors.success);
  root.style.setProperty('--color-warning', theme.colors.warning);
  root.style.setProperty('--color-error', theme.colors.error);
  root.style.setProperty('--color-info', theme.colors.info);

  /* 文字层级 */
  root.style.setProperty('--color-text-primary', theme.colors.textPrimary);
  root.style.setProperty('--color-text-secondary', theme.colors.textSecondary);
  root.style.setProperty('--color-text-muted', theme.colors.textMuted);

  /* 边框 */
  root.style.setProperty('--color-border', theme.colors.border);
  root.style.setProperty('--color-border-hover', theme.colors.borderHover);
  root.style.setProperty('--color-border-accent', theme.colors.borderAccent);

  /* 基础阴影 */
  root.style.setProperty('--shadow-sm', theme.shadows.sm);
  root.style.setProperty('--shadow-md', theme.shadows.md);
  root.style.setProperty('--shadow-lg', theme.shadows.lg);
  root.style.setProperty('--shadow-glow', theme.shadows.glow);
  root.style.setProperty('--shadow-ring', theme.shadows.ring);
  root.style.setProperty('--shadow-ring-accent', theme.shadows.ringAccent);
  root.style.setProperty('--shadow-elevated', theme.shadows.elevated);

  /* V10 新增: 组件专属阴影 */
  root.style.setProperty('--shadow-card', theme.shadows.card);
  root.style.setProperty('--shadow-button', theme.shadows.button);
  root.style.setProperty('--shadow-input', theme.shadows.input);
  root.style.setProperty('--shadow-card-hover', theme.shadows.cardHover);

  /* 颜色方案 */
  root.style.colorScheme = theme.colorScheme;

  /* M21 #6 · shadcn distinctive.css 按 data-theme 切换 hsl 变量 */
  root.dataset.theme = theme.colorScheme;

  /* 背景辉光渐变 */
  const [gradA, gradB, gradC] = theme.gradients;
  root.style.setProperty('--color-bg-gradient-a', gradA);
  root.style.setProperty('--color-bg-gradient-b', gradB);
  root.style.setProperty('--color-bg-gradient-c', gradC);

  localStorage.setItem(STORAGE_KEY, theme.id);
}

/**
 * 从 localStorage 加载已保存的主题，兼容旧 ID
 */
export function loadSavedTheme(): Theme {
  const savedId = localStorage.getItem(STORAGE_KEY);
  /* 兼容 V9 的 palantir-dark ID → 映射到 classic-gold-dark */
  const mappedId = savedId === 'palantir-dark' ? 'classic-gold-dark' : savedId;
  const found = themes.find((t) => t.id === mappedId);
  return found ?? themes[0]!;
}
