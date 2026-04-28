/**
 * ProjectLayout — V15 一体化改造 (2026-04-25)
 *
 * 旧: 包 V14 AppLayout (含 sidebar)
 * 新: 包 V15Layout (统一顶栏)
 *
 * 同时把 URL 中的 :projectId 同步到 useActiveProject 的 localStorage,
 * 这样 V14 老页面 (用 useProject) 和 V15 新组件 (用 useActiveProject) 都能拿到同一个项目.
 */
import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ProjectProvider } from '@/contexts/ProjectContext';
import V15Layout from './V15Layout';

const STORAGE_KEY = 'wikimap-active-project';

export default function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>();

  // URL projectId → localStorage, 让 useActiveProject 也认
  useEffect(() => {
    if (projectId) {
      window.localStorage.setItem(STORAGE_KEY, projectId);
    }
  }, [projectId]);

  return (
    <ProjectProvider projectId={projectId}>
      <V15Layout />
    </ProjectProvider>
  );
}
