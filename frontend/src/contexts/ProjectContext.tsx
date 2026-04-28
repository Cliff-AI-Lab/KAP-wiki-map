/**
 * @module ProjectContext
 * @description 项目上下文模块。
 * 提供 ProjectProvider 和 useProject Hook，用于在全局维护当前项目、
 * 项目列表、加载状态，以及项目切换和刷新逻辑。
 * 项目 ID 持久化到 localStorage，刷新页面后可恢复上次选择。
 */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

/** 项目数据模型 */
export interface Project {
  id: string;
  name: string;
  industry_code: string;
  industry_name: string;
  description: string;
  status: string;
  doc_count: number;
  domain_count: number;
  created_at: string | null;
}

/** 项目上下文对外暴露的值 */
interface ProjectContextValue {
  currentProject: Project | null;
  projects: Project[];
  loading: boolean;
  switchProject: (id: string) => void;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue>({
  currentProject: null,
  projects: [],
  loading: true,
  switchProject: () => {},
  refreshProjects: async () => {},
});

/** 便捷 Hook：获取当前项目上下文 */
export function useProject() {
  return useContext(ProjectContext);
}

const API_BASE = import.meta.env.VITE_API_BASE ?? ''; // API 基础路径，可通过环境变量覆盖
const STORAGE_KEY = 'bookworm_current_project_id'; // 本地存储键名，记住上次选中的项目

/**
 * 项目上下文提供者。
 * 初始化时从后端拉取项目列表，根据 URL 中的 projectId 或 localStorage
 * 中的缓存 ID 确定当前项目。
 */
export function ProjectProvider({
  children,
  projectId,
}: {
  children: React.ReactNode;
  projectId?: string;
}) {
  const [projects, setProjects] = useState<Project[]>([]); // 全部项目列表
  const [currentProject, setCurrentProject] = useState<Project | null>(null); // 当前选中项目
  const [loading, setLoading] = useState(true); // 是否正在加载

  /** 从后端获取项目列表 */
  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/projects`);
      if (res.ok) {
        const data: Project[] = await res.json();
        setProjects(data);
        return data;
      }
    } catch {
      // ignore
    }
    return [];
  }, []);

  /** 供外部调用的刷新项目列表方法 */
  const refreshProjects = useCallback(async () => {
    await fetchProjects();
  }, [fetchProjects]);

  /** 切换当前项目并持久化到 localStorage */
  const switchProject = useCallback(
    (id: string) => {
      const proj = projects.find((p) => p.id === id);
      if (proj) {
        setCurrentProject(proj);
        localStorage.setItem(STORAGE_KEY, id);
      }
    },
    [projects]
  );

  useEffect(() => {
    (async () => {
      setLoading(true);
      const data = await fetchProjects();
      // Determine current project
      const targetId = projectId || localStorage.getItem(STORAGE_KEY);
      const match = data.find((p) => p.id === targetId);
      if (match) {
        setCurrentProject(match ?? null);
        localStorage.setItem(STORAGE_KEY, match.id);
      } else if (data.length > 0) {
        setCurrentProject(data[0] ?? null);
        localStorage.setItem(STORAGE_KEY, data[0]!.id);
      }
      setLoading(false);
    })();
  }, [fetchProjects, projectId]);

  return (
    <ProjectContext.Provider
      value={{ currentProject, projects, loading, switchProject, refreshProjects }}
    >
      {children}
    </ProjectContext.Provider>
  );
}
