/**
 * useCurrentUser — 当前登录用户 id（M13 #2 引入）。
 *
 * 当前 KAP 前端尚无真实 auth 后端集成；用 localStorage 作为
 * fallback。后续 ISS JWT 接通后改为读 token。
 *
 * 同名 hook 在多页复用，让 "我认领的" / 批量决策 / 后续操作日志
 * 等都能拿到一个一致的 user id。
 */
import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'kap-current-user-id';
const DEFAULT_USER = 'admin';

export interface UseCurrentUserResult {
  userId: string;
  setUser: (id: string) => void;
}

export function useCurrentUser(): UseCurrentUserResult {
  const [userId, setUserId] = useState<string>(DEFAULT_USER);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved && saved.trim()) {
        setUserId(saved);
      }
    } catch {
      // ignore (server-side render or storage disabled)
    }
  }, []);

  const setUser = useCallback((id: string) => {
    const trimmed = id.trim() || DEFAULT_USER;
    setUserId(trimmed);
    try {
      window.localStorage.setItem(STORAGE_KEY, trimmed);
    } catch {
      // ignore
    }
  }, []);

  return { userId, setUser };
}
