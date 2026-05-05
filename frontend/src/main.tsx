/**
 * @module main
 * @description 应用入口文件。
 * 在挂载 React 应用之前先恢复用户保存的主题设置，
 * 然后以 StrictMode 模式渲染根组件到 DOM。
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ToastProvider } from './components/ui/Toast';
import { ModeProvider } from './contexts/ModeContext';
import { LocaleProvider } from './contexts/LocaleContext';
import { applyTheme, loadSavedTheme } from './lib/themes';
import './index.css';
import './styles/distinctive.css';   // M21 #4 · 三中心统一设计系统

// 在渲染前恢复用户上次保存的主题（含 data-theme 切换 hsl）
applyTheme(loadSavedTheme());
// 兜底：若 applyTheme 未触发 dataset.theme（如旧缓存），按 colorScheme 设
if (!document.documentElement.dataset.theme) {
  document.documentElement.dataset.theme =
    document.documentElement.style.colorScheme === 'light' ? 'light' : 'dark';
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LocaleProvider>
      <ModeProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ModeProvider>
    </LocaleProvider>
  </React.StrictMode>,
);
