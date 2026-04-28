/**
 * useActiveProject — V15 消费/治理模式下自动选中一个项目
 *
 * 跨项目的全局入口需要一个隐式 projectId：
 *   1. 优先用 localStorage['wikimap-active-project']
 *   2. 否则取 fetchProjects() 的第一个
 *   3. 都没有返回 null（调用者需要处理"无项目"状态）
 */
import { useEffect, useState, useCallback } from 'react';
import { fetchProjects, type ProjectSummary } from '@/services/projectApi';

const STORAGE_KEY = 'wikimap-active-project';

export interface UseActiveProjectResult {
  projectId: string | null;
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  setActive: (id: string) => void;
  refresh: () => void;
}

export function useActiveProject(): UseActiveProjectResult {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchProjects();
      setProjects(list);

      const saved = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null;
      const valid = saved && list.some((p) => p.id === saved);
      const picked = valid ? saved : list[0]?.id ?? null;
      setProjectId(picked);
      if (picked && picked !== saved) {
        window.localStorage.setItem(STORAGE_KEY, picked);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setActive = useCallback((id: string) => {
    setProjectId(id);
    window.localStorage.setItem(STORAGE_KEY, id);
  }, []);

  return { projectId, projects, loading, error, setActive, refresh: load };
}
