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

// 在渲染前恢复用户上次保存的主题
applyTheme(loadSavedTheme());

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
