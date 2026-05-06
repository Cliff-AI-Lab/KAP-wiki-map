/**
 * ModeContext — V15 三中心模式（咨询 / 知识 / 消费）全局状态（M21 #1）
 *
 * 咨询中心 (consult): 块① 知识咨询智能体 — AI 对话式建知识体系
 * 知识中心 (manage):  块② 知识管理 + 存储 — 6 工位 + 4×6 矩阵 + 双层本体
 * 消费中心 (read):    块③ 渐进式消费门户 — Wiki / RAG / 图谱三路召回
 *
 * 状态持久化到 localStorage['wikimap-mode']，默认 'read'（消费中心）。
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Mode = 'overview' | 'consult' | 'manage' | 'read';

const STORAGE_KEY = 'wikimap-mode';

interface ModeContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  toggleMode: () => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

function readInitialMode(): Mode {
  if (typeof window === 'undefined') return 'overview';
  const v = window.localStorage.getItem(STORAGE_KEY);
  if (v === 'overview' || v === 'consult' || v === 'manage' || v === 'read') return v;
  return 'overview';
}

const _MODE_ORDER: Mode[] = ['overview', 'consult', 'manage', 'read'];

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readInitialMode);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const setMode = (m: Mode) => setModeState(m);
  const toggleMode = () => setModeState((m) => {
    const idx = _MODE_ORDER.indexOf(m);
    return _MODE_ORDER[(idx + 1) % _MODE_ORDER.length];
  });

  return (
    <ModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode(): ModeContextValue {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error('useMode must be used inside <ModeProvider>');
  return ctx;
}
