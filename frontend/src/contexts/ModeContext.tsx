/**
 * ModeContext — V15 双模式（消费 / 治理）全局状态
 *
 * 消费模式 (read)  : 业务/新员工视角 — 读 Wiki、搜索、问答
 * 治理模式 (manage): 管理员/专家视角 — 编译、审核、配置
 *
 * 状态持久化到 localStorage['wikimap-mode']，默认 'read'。
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Mode = 'read' | 'manage';

const STORAGE_KEY = 'wikimap-mode';

interface ModeContextValue {
  mode: Mode;
  setMode: (m: Mode) => void;
  toggleMode: () => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

function readInitialMode(): Mode {
  if (typeof window === 'undefined') return 'read';
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === 'manage' ? 'manage' : 'read';
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readInitialMode);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const setMode = (m: Mode) => setModeState(m);
  const toggleMode = () => setModeState((m) => (m === 'read' ? 'manage' : 'read'));

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
