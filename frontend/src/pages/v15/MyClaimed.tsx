/**
 * MyClaimed — "我认领的"工单列表 + 批量决策（M13 #2）。
 *
 * 视图：
 *  - 顶部切换 user_id（默认 admin；走 useCurrentUser localStorage 兜底）
 *  - 列表：fetchGovernanceQueue + claimed_by === userId 客户端过滤
 *  - 多选 checkbox + bulk approve / reject 一键批量决策
 *  - 单条操作：通过 / 打回（同 GovernanceMatrix drawer）
 *
 * 后端 fetchGovernanceQueue 暂不支持 claimed_by 服务器侧过滤，前端过滤足够。
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check, X, Loader2, ArrowLeft, RefreshCw, AlertCircle, Inbox,
  Square, CheckSquare, UserCircle,
} from 'lucide-react';

import { useActiveProject } from '@/hooks/useActiveProject';
import { useCurrentUser } from '@/hooks/useCurrentUser';
import {
  decideGovernanceItem,
  fetchGovernanceQueue,
  type GovernanceQueueItem,
} from '@/services/governanceApi';

export default function MyClaimed() {
  const { projectId, loading: projectsLoading } = useActiveProject();
  const { userId, setUser } = useCurrentUser();

  const [items, setItems] = useState<GovernanceQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyAll, setBusyAll] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      // 默认拉所有 status；对方过滤 claimed_by === userId
      const all = await fetchGovernanceQueue(projectId);
      const mine = all.filter(
        (it) => it.claimed_by === userId
          && (it.status === 'reviewing' || it.status === 'pending'),
      );
      setItems(mine);
      // 清掉已不再属于我的选择
      setSelected((prev) => {
        const valid = new Set(mine.map((m) => m.id));
        return new Set([...prev].filter((id) => valid.has(id)));
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, userId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((it) => it.id)));
    }
  };

  const flashOK = (msg: string) => {
    setFlash(msg);
    setTimeout(() => setFlash(null), 2500);
  };

  const handleBulk = async (decision: 'approve' | 'reject') => {
    if (selected.size === 0) return;
    setBusyAll(true);
    setError(null);
    let okCount = 0;
    let failCount = 0;
    const tasks = [...selected].map(async (id) => {
      try {
        await decideGovernanceItem(id, decision);
        okCount += 1;
      } catch (e) {
        failCount += 1;
        // 单条失败不阻断其他
      }
    });
    await Promise.all(tasks);
    setBusyAll(false);
    flashOK(
      `批量${decision === 'approve' ? '通过' : '驳回'} 完成：` +
      `成功 ${okCount} / 失败 ${failCount}`,
    );
    setSelected(new Set());
    await load();
  };

  const allSelected = items.length > 0 && selected.size === items.length;

  if (projectsLoading) {
    return <div className="text-sm text-th-text-muted">项目加载中...</div>;
  }
  if (!projectId) {
    return (
      <div className="rounded-card border border-th-border bg-elevated p-8 text-center">
        <div className="text-th-text-primary mb-2">尚未选择项目</div>
        <Link to="/projects" className="text-sm text-accent hover:underline">
          去项目列表
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6 max-w-screen-2xl mx-auto">
      <div className="flex items-center gap-3">
        <Link
          to="/v15/manage"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-btn text-xs text-th-text-muted hover:text-th-text-primary hover:bg-hover"
        >
          <ArrowLeft size={12} /> 治理首页
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-th-text-primary">
          我认领的工单
        </h1>
        <span className="text-xs text-th-text-muted font-mono">
          claimed_by · 批量决策
        </span>

        <div className="ml-auto flex items-center gap-3">
          <UserCircle size={14} className="text-th-text-muted" />
          <input
            type="text"
            value={userId}
            onChange={(e) => setUser(e.target.value)}
            className="text-xs px-2 py-1 rounded border border-th-border bg-elevated focus:outline-none focus:border-accent w-32"
            placeholder="user_id"
          />
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn border border-th-border text-xs text-th-text-secondary hover:text-th-text-primary hover:bg-hover disabled:opacity-50 transition"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          <AlertCircle className="inline mr-2" size={14} /> {error}
        </div>
      )}
      {flash && (
        <div className="rounded-card border border-emerald-500/40 bg-emerald-500/10 p-2 text-xs text-emerald-700">
          <Check className="inline mr-1" size={12} /> {flash}
        </div>
      )}

      {/* 批量操作工具栏 */}
      <div className="flex items-center gap-2 p-3 rounded-card border border-th-border bg-elevated">
        <button
          type="button"
          onClick={toggleAll}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-btn border border-th-border text-xs hover:bg-hover"
          disabled={items.length === 0}
        >
          {allSelected ? <CheckSquare size={12} /> : <Square size={12} />}
          {allSelected ? '取消全选' : '全选'}
        </button>
        <span className="text-xs text-th-text-muted">
          已选 {selected.size} / {items.length}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            disabled={selected.size === 0 || busyAll}
            onClick={() => handleBulk('approve')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-btn border border-emerald-500/40 text-xs text-emerald-700 hover:bg-emerald-500/10 disabled:opacity-40"
          >
            {busyAll ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
            批量通过
          </button>
          <button
            type="button"
            disabled={selected.size === 0 || busyAll}
            onClick={() => handleBulk('reject')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-btn border border-rose-500/40 text-xs text-rose-700 hover:bg-rose-500/10 disabled:opacity-40"
          >
            {busyAll ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
            批量打回
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="rounded-card border border-th-border bg-elevated">
        {loading && items.length === 0 ? (
          <div className="p-8 text-center text-sm text-th-text-muted">
            <Loader2 className="inline animate-spin mr-2" size={14} /> 加载中...
          </div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-th-text-muted">
            <Inbox className="inline mr-2" size={16} />
            未找到 {userId} 认领的工单（{projectId}）
          </div>
        ) : (
          <ul className="divide-y divide-th-border">
            {items.map((it) => {
              const isSel = selected.has(it.id);
              return (
                <li
                  key={it.id}
                  className="p-3 flex items-start gap-3 hover:bg-hover/40 transition"
                >
                  <button
                    type="button"
                    onClick={() => toggleOne(it.id)}
                    className="mt-0.5 text-th-text-muted hover:text-accent"
                  >
                    {isSel ? <CheckSquare size={14} className="text-accent" /> : <Square size={14} />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-th-text-primary truncate">
                      {it.title}
                    </div>
                    <div className="text-xs text-th-text-muted mt-0.5 truncate">
                      {it.description}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] font-mono text-th-text-muted">
                      <span>{it.workstation || '-'}</span>
                      <span>{it.assigned_role || '-'}</span>
                      <span>状态 {it.status}</span>
                      <span>优先级 {it.priority}</span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
