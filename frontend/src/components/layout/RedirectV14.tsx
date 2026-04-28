/**
 * RedirectV14 — V14 老路径 → V15 新路径的桥接器.
 *
 * 同时:
 *   1. 读 URL 中 :projectId, 同步到 localStorage['wikimap-active-project']
 *   2. 用 replace 跳转到 V15 新路径 (可注入 :docId)
 *
 * 使用:
 *   { path: 'wiki', element: <RedirectV14 to="/v15/read/wiki/domain" /> }
 *   { path: 'documents/:docId', element: <RedirectV14 toTemplate="/v15/read/wiki/src/:docId" /> }
 */
import { useEffect } from 'react';
import { Navigate, useParams } from 'react-router-dom';

interface Props {
  to?: string;
  toTemplate?: string;   // 支持 ':docId' 等模板替换
}

const STORAGE_KEY = 'wikimap-active-project';

export default function RedirectV14({ to, toTemplate }: Props) {
  const params = useParams();
  const { projectId } = params;

  useEffect(() => {
    if (projectId) {
      window.localStorage.setItem(STORAGE_KEY, projectId);
    }
  }, [projectId]);

  let target = to ?? '/v15/read';
  if (toTemplate) {
    target = toTemplate.replace(/:(\w+|\*)/g, (_, k) => {
      const v = params[k as keyof typeof params];
      return v ? v : '';   // splat 不能 encodeURIComponent (会丢 / 分隔)
    });
  }
  return <Navigate to={target} replace />;
}
