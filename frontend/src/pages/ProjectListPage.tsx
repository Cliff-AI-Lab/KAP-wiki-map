/**
 * 项目列表页面（ProjectListPage）
 *
 * 知识图鉴的项目选择入口页，用户在此页面浏览已有项目或创建新项目。
 *
 * 功能：
 * - 以卡片网格展示所有项目（项目名称、行业标识、描述、知识域/文档数量）
 * - 行业标识使用不同颜色区分（能源=琥珀色、制造=靛蓝色、IT=蓝色等）
 * - 末尾提供"新建项目"虚线卡片入口
 * - 空状态引导：无项目时显示创建引导
 *
 * @module pages/ProjectListPage
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FolderOpen, BookOpen } from 'lucide-react';
import { fetchProjects, type ProjectSummary } from '@/services/projectApi';

/** 行业代码 → 主题颜色映射（用于项目卡片的图标背景和行业名称着色） */
const INDUSTRY_COLORS: Record<string, string> = {
  energy: '#f59e0b',       // 能源 - 琥珀色
  manufacturing: '#6366f1', // 制造业 - 靛蓝色
  it: '#3b82f6',           // IT - 蓝色
  finance: '#10b981',      // 金融 - 绿色
  healthcare: '#ef4444',   // 医疗 - 红色
  generic: '#6b7280',      // 通用 - 灰色
};

/**
 * 项目列表组件
 *
 * 页面加载时自动获取项目列表，以卡片网格形式展示。
 * 点击项目卡片跳转至对应项目的仪表盘页面。
 */
export default function ProjectListPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]); // 项目列表数据
  const [loading, setLoading] = useState(true);                   // 是否正在加载
  const navigate = useNavigate();

  // 组件挂载时从后端获取项目列表
  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div
      className="min-h-screen flex flex-col page-enter bg-base"
    >
      {/* Header */}
      <header
        className="px-8 py-6 bg-elevated border-b border-th-border"
      >
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-btn flex items-center justify-center bg-accent"
            >
              <BookOpen size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-th-text-primary">
                知识图鉴
              </h1>
              <p className="text-xs text-th-text-muted">
                选择一个项目开始知识管理
              </p>
            </div>
          </div>
          <button
            onClick={() => navigate('/projects/new')}
            className="flex items-center gap-2 px-4 py-2 rounded-btn text-sm font-medium text-white transition-colors bg-accent"
          >
            <Plus size={16} />
            新建项目
          </button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 px-8 py-8">
        <div className="max-w-5xl mx-auto">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-40 rounded-card animate-pulse bg-surface"
                />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div className="text-center py-20">
              <FolderOpen
                size={48}
                className="mx-auto mb-4 text-th-text-muted"
              />
              <h2
                className="text-lg font-medium mb-2 text-th-text-primary"
              >
                还没有项目
              </h2>
              <p className="text-sm mb-6 text-th-text-muted">
                创建您的第一个知识管理项目，选择行业模板快速开始
              </p>
              <button
                onClick={() => navigate('/projects/new')}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-btn text-sm font-medium text-white bg-accent"
              >
                <Plus size={16} />
                创建项目
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger-children">
              {projects.map((proj) => {
                const color = INDUSTRY_COLORS[proj.industry_code] || INDUSTRY_COLORS.generic;
                return (
                  <button
                    key={proj.id}
                    onClick={() => navigate(`/projects/${proj.id}`)}
                    className="relative text-left p-5 pl-6 rounded-card glass-card transition-all duration-200 overflow-hidden"
                  >
                    {/* Left vertical accent bar */}
                    <div
                      className="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl"
                      style={{ backgroundColor: color }}
                    />
                    <div className="flex items-start gap-3 mb-3">
                      <div className="min-w-0">
                        <h3
                          className="font-semibold truncate text-th-text-primary"
                        >
                          {proj.name}
                        </h3>
                        <span className="text-xs" style={{ color: color }}>
                          {proj.industry_name}
                        </span>
                      </div>
                    </div>
                    {proj.description && (
                      <p
                        className="text-xs mb-3 line-clamp-2 text-th-text-muted"
                      >
                        {proj.description}
                      </p>
                    )}
                    <div className="flex gap-4 text-xs text-th-text-muted">
                      <span>{proj.domain_count} 个知识域</span>
                      <span>{proj.doc_count} 篇文档</span>
                    </div>
                  </button>
                );
              })}

              {/* New project card */}
              <button
                onClick={() => navigate('/projects/new')}
                className="p-5 rounded-card flex flex-col items-center justify-center gap-3 transition-all min-h-[140px] text-th-text-muted shadow-ring border border-dashed border-th-border-hover"
              >
                <Plus size={28} className="animate-pulse-glow" />
                <span className="text-sm">新建项目</span>
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
