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

  // M22 #18: 监听跨中心 active project 切换 (ConsultHome ensure-by-industry
  // 写 localStorage 后, 顶栏/知识中心/消费中心 立即拿新 project)
  // 修复用户痛点"金融项目到知识中心变能源" + "消费中心前面知识没保存"
  useEffect(() => {
    const onCustom = () => load();
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) load();
    };
    window.addEventListener('kap:active-project-changed', onCustom);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('kap:active-project-changed', onCustom);
      window.removeEventListener('storage', onStorage);
    };
  }, [load]);

  const setActive = useCallback((id: string) => {
    setProjectId(id);
    window.localStorage.setItem(STORAGE_KEY, id);
    // 通知同 tab 内其他 useActiveProject 实例 (storage event 跨 tab, 同 tab 用自定义)
    window.dispatchEvent(new Event('kap:active-project-changed'));
  }, []);

  return { projectId, projects, loading, error, setActive, refresh: load };
}
