/**
 * @module router
 * @description 应用路由配置 — 按页面懒加载，减少首屏 JS 体积。
 */
import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import ProjectLayout from '@/components/layout/ProjectLayout';
import V15Layout from '@/components/layout/V15Layout';
import RedirectV14 from '@/components/layout/RedirectV14';

// 懒加载页面组件
const ProjectListPage = lazy(() => import('@/pages/ProjectListPage'));

// V15 双模式页
const ReaderHome = lazy(() => import('@/pages/v15/ReaderHome'));
const GovernanceHome = lazy(() => import('@/pages/v15/GovernanceHome'));
const GovernanceMatrix = lazy(() => import('@/pages/v15/GovernanceMatrix'));
const WikiReader = lazy(() => import('@/pages/v15/WikiReader'));
const GraphView = lazy(() => import('@/pages/v15/GraphView'));
const CodeGraph = lazy(() => import('@/pages/v15/CodeGraph'));
const ObservabilityDashboard = lazy(() => import('@/pages/v15/ObservabilityDashboard'));
const ObservabilityCompare = lazy(() => import('@/pages/v15/ObservabilityCompare'));
const GroundTruthReview = lazy(() => import('@/pages/v15/GroundTruthReview'));
const MyClaimed = lazy(() => import('@/pages/v15/MyClaimed'));
const WikiTree = lazy(() => import('@/pages/v15/WikiTree'));
const ImportLayout = lazy(() => import('@/pages/v15/import/ImportLayout'));
const UploadStep = lazy(() => import('@/pages/v15/import/UploadStep'));
const ReviewStep = lazy(() => import('@/pages/v15/import/ReviewStep'));
const TaxonomyStep = lazy(() => import('@/pages/v15/import/TaxonomyStep'));
const CompiledStep = lazy(() => import('@/pages/v15/import/CompiledStep'));
const ProjectCreatePage = lazy(() => import('@/pages/ProjectCreatePage'));
// V14 老页组件已由 RedirectV14 全部重定向到 V15, 不再 lazy load
// 如需访问 V14 经典版, 保留源文件但不挂路由

/** 页面加载占位 */
function PageFallback() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="animate-pulse text-th-text-muted text-sm">加载中...</div>
    </div>
  );
}

/** 包装懒加载组件 */
function L({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/projects" replace /> },

  // V15 一体化入口 — 所有 V15 页都在同一个 V15Layout 下
  {
    path: '/v15',
    element: <V15Layout />,
    children: [
      { index: true, element: <Navigate to="read" replace /> },

      // 消费模式
      { path: 'read',          element: <L><ReaderHome /></L> },
      { path: 'read/wiki/*',   element: <L><WikiReader /></L> },
      { path: 'read/wiki-tree',element: <L><WikiTree /></L> },     // M16 #4 三层结构总览
      { path: 'read/graph',    element: <L><GraphView /></L> },

      // 治理模式
      { path: 'manage',        element: <L><GovernanceHome /></L> },
      { path: 'manage/matrix', element: <L><GovernanceMatrix /></L> },  // M1 4×6 矩阵审核台
      { path: 'manage/observability', element: <L><ObservabilityDashboard /></L> },  // M10 #3 运营观察仪表盘
      { path: 'manage/observability/compare', element: <L><ObservabilityCompare /></L> },  // M13 #3 多 project 横评
      { path: 'manage/ground-truth',  element: <L><GroundTruthReview /></L> },        // M11 #3 GT 候选审批
      { path: 'manage/my-claimed',    element: <L><MyClaimed /></L> },                // M13 #2 我认领的工单 + 批量决策
      {
        path: 'manage/import',
        element: <L><ImportLayout /></L>,
        children: [
          { index: true, element: <Navigate to="upload" replace /> },
          { path: 'upload',   element: <L><UploadStep /></L> },
          { path: 'review',   element: <L><ReviewStep /></L> },
          { path: 'taxonomy', element: <L><TaxonomyStep /></L> },
          { path: 'compiled', element: <L><CompiledStep /></L> },
        ],
      },
      { path: 'manage/wiki/*',  element: <L><WikiReader /></L> },  // 治理也能看 wiki
      { path: 'manage/graph',   element: <L><GraphView /></L> },
      { path: 'manage/code',    element: <L><CodeGraph /></L> },

      // 兼容旧链接 (短形式) — 用 RedirectV14 保留 splat 段
      { path: 'wiki/*',         element: <RedirectV14 toTemplate="/v15/read/wiki/:*" /> },
      { path: 'graph',          element: <Navigate to="/v15/read/graph" replace /> },
      { path: 'code-graph',     element: <Navigate to="/v15/manage/code" replace /> },
    ],
  },

  { path: '/projects', element: <L><ProjectListPage /></L> },
  { path: '/projects/new', element: <L><ProjectCreatePage /></L> },

  // V14 旧路由 — 全部重定向到 V15 对应页 (保留兼容老书签)
  {
    path: '/projects/:projectId',
    element: <ProjectLayout />,
    children: [
      { index: true,                   element: <RedirectV14 to="/v15/manage" /> },
      { path: 'upload',                element: <RedirectV14 to="/v15/manage/import/upload" /> },
      { path: 'review',                element: <RedirectV14 to="/v15/manage/import/review" /> },
      { path: 'taxonomy',              element: <RedirectV14 to="/v15/manage/import/taxonomy" /> },
      { path: 'schema',                element: <RedirectV14 to="/v15/manage/import/taxonomy" /> },
      { path: 'analysis',              element: <RedirectV14 to="/v15/manage/import/compiled" /> },
      { path: 'graph',                 element: <RedirectV14 to="/v15/manage/graph" /> },
      { path: 'wiki',                  element: <RedirectV14 to="/v15/read" /> },
      { path: 'catalog',               element: <RedirectV14 to="/v15/manage/import/taxonomy" /> },
      { path: 'documents/:docId',      element: <RedirectV14 toTemplate="/v15/read/wiki/src/:docId" /> },
      { path: 'search',                element: <RedirectV14 to="/v15/read" /> },
      { path: 'qa',                    element: <RedirectV14 to="/v15/read" /> },
    ],
  },

  // Legacy route redirects
  { path: '/upload', element: <Navigate to="/projects" replace /> },
  { path: '/review', element: <Navigate to="/projects" replace /> },
  { path: '/taxonomy', element: <Navigate to="/projects" replace /> },
  { path: '/search', element: <Navigate to="/projects" replace /> },
  { path: '/qa', element: <Navigate to="/projects" replace /> },

  // 404 fallback
  { path: '*', element: <Navigate to="/projects" replace /> },
]);
