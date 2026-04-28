/**
 * @file DenoiseReviewPage.tsx
 * @description 智能去噪审核页面 — 文档质量审核与入库决策中心
 *
 * 基于文档标签与知识体系对比，提供三级决策（保留/归档/丢弃）：
 * 1. 显示文档标签（类型、领域、关键词）
 * 2. 匹配评分条 + AI 建议（基于 KPI 指标）
 * 3. 一键采纳 AI 建议 / 批量操作
 * 4. 可展开查看文档详情（摘要、关键词、知识域、置信度）
 *
 * 数据来源：后端 review-queue 接口；若无数据则使用内置 Mock 数据。
 */

import { useState, useEffect } from 'react';
import {
  CheckCircle,
  XCircle,
  Sparkles,
  RefreshCw,
  Filter,
  ChevronDown,
  ChevronUp,
  Tag,
  FileText,
  Check,
  X,
  Archive,
  Shield,
} from 'lucide-react';
import { Card, Badge, Button } from '@/components/ui';
import { fetchReviewQueue, resolveReview, type ReviewQueueItem } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';

/**
 * 去噪审核项 — 合并 V2 review-queue 数据 + AI 分析标签
 */
interface DenoiseItem {
  /** 文档唯一标识 */
  doc_id: string;
  /** 文档名称 */
  doc_name: string;
  /** 文档类型（如：制度文档、技术文档、会议纪要） */
  doc_type: string;
  /** AI 提取的关键词列表 */
  keywords: string[];
  /** 关联的知识域列表 */
  domains: string[];
  /** 文档内容摘要 */
  summary: string;
  /** 匹配评分（0~100），基于 KPI 计算 */
  match_score: number;
  /** AI 评分理由说明 */
  match_reason: string;
  /** AI 建议的决策 */
  suggested_decision: 'KEEP' | 'ARCHIVE' | 'DISCARD';
  /** 用户实际决策（null 表示未审核） */
  user_decision: string | null;
  /** AI 分析置信度（0~1） */
  confidence: number;
  /** 保留价值指标（0~1） */
  kpi: number;
}

/** 将后端 ReviewQueueItem 转换为前端 DenoiseItem */
function toDenoiseItem(item: ReviewQueueItem): DenoiseItem {
  const kpi = item.kpi_retain ?? 0.5;
  const score = Math.round(kpi * 100);
  const raw = item.proposed_decision || (kpi >= 0.6 ? 'KEEP' : kpi >= 0.35 ? 'ARCHIVE' : 'DISCARD');
  const suggested = (['KEEP', 'ARCHIVE', 'DISCARD'].includes(raw) ? raw : 'KEEP') as 'KEEP' | 'ARCHIVE' | 'DISCARD';

  return {
    doc_id: item.doc_id,
    doc_name: item.title || item.doc_id,
    doc_type: '文档',
    keywords: [],
    domains: [],
    summary: item.reason || '',
    match_score: score,
    match_reason: item.reason || 'AI 分析完成',
    suggested_decision: suggested,
    user_decision: null,
    confidence: item.confidence ?? 0.5,
    kpi: kpi,
  };
}

// Mock 去噪数据（后端无数据时使用）
const MOCK_ITEMS: DenoiseItem[] = [
  {
    doc_id: 'm1', doc_name: '员工报销管理制度 v3.0', doc_type: '制度文档',
    keywords: ['报销', '财务', '审批流程', '差旅', '发票'],
    domains: ['人力资源', '财务管理'],
    summary: '最新版员工报销管理制度，涵盖差旅报销、日常报销、审批流程等内容。',
    match_score: 92, match_reason: '高质量制度文档，内容完整', suggested_decision: 'KEEP',
    user_decision: null, confidence: 0.95, kpi: 0.92,
  },
  {
    doc_id: 'm2', doc_name: '员工报销管理制度 v2.0', doc_type: '制度文档',
    keywords: ['报销', '财务', '旧版'],
    domains: ['人力资源'],
    summary: '旧版报销制度，已被 v3.0 替代。',
    match_score: 45, match_reason: '已有新版本替代', suggested_decision: 'ARCHIVE',
    user_decision: null, confidence: 0.88, kpi: 0.45,
  },
  {
    doc_id: 'm3', doc_name: '2024Q3 项目周报', doc_type: '会议纪要',
    keywords: ['周报', '项目进展', 'Q3', '里程碑'],
    domains: ['项目管理'],
    summary: '2024年第三季度项目进展汇报，包含各子项目状态。',
    match_score: 68, match_reason: '时效性一般，有参考价值', suggested_decision: 'KEEP',
    user_decision: null, confidence: 0.72, kpi: 0.68,
  },
  {
    doc_id: 'm4', doc_name: '群聊：午饭吃什么', doc_type: '聊天记录',
    keywords: ['聊天', '日常'],
    domains: [],
    summary: '日常闲聊记录，无业务价值。',
    match_score: 8, match_reason: '非业务内容，建议丢弃', suggested_decision: 'DISCARD',
    user_decision: null, confidence: 0.98, kpi: 0.08,
  },
  {
    doc_id: 'm5', doc_name: 'API接口规范 v2.0', doc_type: '技术文档',
    keywords: ['API', 'REST', '接口', '认证', 'JSON'],
    domains: ['产品研发', '技术架构'],
    summary: '系统 API 接口设计规范，包含认证、错误码、数据格式等标准。',
    match_score: 88, match_reason: '核心技术文档', suggested_decision: 'KEEP',
    user_decision: null, confidence: 0.91, kpi: 0.88,
  },
  {
    doc_id: 'm6', doc_name: '过期会议通知 2023-06', doc_type: '通知',
    keywords: ['通知', '过期'],
    domains: [],
    summary: '2023年6月的会议通知，已过期。',
    match_score: 12, match_reason: '过期通知，无保留价值', suggested_decision: 'DISCARD',
    user_decision: null, confidence: 0.96, kpi: 0.12,
  },
];

/**
 * 去噪审核页面组件
 *
 * 展示待审核文档列表，每个文档显示 AI 匹配评分、建议决策和详细标签。
 * 支持单条审核（保留/归档/丢弃）、批量操作和一键采纳 AI 建议。
 */
export default function DenoiseReviewPage() {
  const { currentProject } = useProject();
  const [items, setItems] = useState<DenoiseItem[]>([]); // 审核项列表
  const [loading, setLoading] = useState(true); // 数据加载中
  const [filterType, setFilterType] = useState<'all' | 'keep' | 'archive' | 'discard'>('all'); // 当前筛选条件
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set()); // 已展开详情的文档ID集合
  const [_actionLoading, setActionLoading] = useState<string | null>(null); // 当前正在执行操作的项
  const [toast, setToast] = useState<string | null>(null); // Toast 提示消息

  /** 显示底部 Toast 提示，2.5 秒后自动消失 */
  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  /** 加载审核队列数据（优先从后端获取，失败则使用 Mock 数据） */
  const loadData = async () => {
    setLoading(true);
    try {
      const queue = await fetchReviewQueue('PENDING', currentProject?.id);
      if (queue && queue.length > 0) {
        setItems(queue.map(toDenoiseItem));
      } else {
        setItems(MOCK_ITEMS);
      }
    } catch {
      setItems(MOCK_ITEMS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [currentProject?.id]);

  /** 设置单个文档的审核决策（同时调用后端 resolveReview 接口） */
  const setDecision = async (docId: string, decision: string) => {
    setActionLoading(docId + decision);
    try {
      await resolveReview(docId, decision);
    } catch (e) { console.warn('resolveReview failed (mock mode):', e); }
    setItems(prev => prev.map(item =>
      item.doc_id === docId ? { ...item, user_decision: decision } : item
    ));
    setActionLoading(null);
    const labels: Record<string, string> = { KEEP: '保留', ARCHIVE: '归档', DISCARD: '丢弃' };
    showToast(`已标记为「${labels[decision] || decision}」`);
  };

  /** 批量设置决策（filter='pending' 时仅处理未审核项） */
  const batchDecision = (decision: string, filter?: 'pending') => {
    let count = 0;
    setItems(prev => prev.map(item => {
      if (filter === 'pending' && item.user_decision !== null) return item;
      count++;
      return { ...item, user_decision: decision };
    }));
    const labels: Record<string, string> = { KEEP: '保留', ARCHIVE: '归档', DISCARD: '丢弃' };
    showToast(`已批量标记 ${count} 条为「${labels[decision] || decision}」`);
  };

  /** 一键采纳所有 AI 建议（仅填充未手动审核的项） */
  const acceptAllSuggestions = () => {
    let count = 0;
    setItems(prev => prev.map(item => {
      if (!item.user_decision) count++;
      return { ...item, user_decision: item.user_decision || item.suggested_decision };
    }));
    showToast(`已采纳 ${count} 条 AI 建议`);
  };

  /** 切换文档详情展开/收起 */
  const toggleExpand = (docId: string) => {
    const s = new Set(expandedItems);
    s.has(docId) ? s.delete(docId) : s.add(docId);
    setExpandedItems(s);
  };

  // 过滤
  const filteredItems = items.filter(item => {
    if (filterType === 'all') return true;
    const d = (item.user_decision || item.suggested_decision).toLowerCase();
    return d === filterType;
  });

  // 统计
  const stats = {
    total: items.length,
    keep: items.filter(i => (i.user_decision || i.suggested_decision) === 'KEEP').length,
    archive: items.filter(i => (i.user_decision || i.suggested_decision) === 'ARCHIVE').length,
    discard: items.filter(i => (i.user_decision || i.suggested_decision) === 'DISCARD').length,
    reviewed: items.filter(i => i.user_decision !== null).length,
  };

  const scoreColor = (score: number) => score >= 70 ? 'var(--color-success)' : score >= 40 ? 'var(--color-warning)' : 'var(--color-error)';
  const decisionBadge = (d: string) => d === 'KEEP' ? 'success' : d === 'ARCHIVE' ? 'warning' : 'error';

  return (
    <div className="p-8 space-y-8 page-enter">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-metric flex items-center gap-2">
            <Shield className="text-accent" />
            去噪审核
          </h1>
          <p className="text-th-text-muted mt-1">AI 智能分析 + 人工审核，确保知识库质量</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={loadData} icon={<RefreshCw size={14} />}>刷新</Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-5 gap-3">
        <Card className="p-3 text-center">
          <div className="text-metric">{stats.total}</div>
          <div className="text-xs text-th-text-muted">总数</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full" style={{ background: 'var(--color-success)' }} />
            <div className="text-metric" style={{ color: 'var(--color-success)' }}>{stats.keep}</div>
          </div>
          <div className="text-xs text-th-text-muted">保留</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full" style={{ background: 'var(--color-warning)' }} />
            <div className="text-metric" style={{ color: 'var(--color-warning)' }}>{stats.archive}</div>
          </div>
          <div className="text-xs text-th-text-muted">归档</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full" style={{ background: 'var(--color-error)' }} />
            <div className="text-metric" style={{ color: 'var(--color-error)' }}>{stats.discard}</div>
          </div>
          <div className="text-xs text-th-text-muted">丢弃</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full" style={{ background: 'var(--color-info)' }} />
            <div className="text-metric" style={{ color: 'var(--color-info)' }}>{stats.reviewed}</div>
          </div>
          <div className="text-xs text-th-text-muted">已审核</div>
        </Card>
      </div>

      {/* 批量操作栏 */}
      <div className="flex items-center justify-between p-3 bg-hover rounded-btn">
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={acceptAllSuggestions} icon={<Sparkles size={14} />}>
            采纳 AI 建议
          </Button>
          <Button variant="secondary" size="sm" onClick={() => batchDecision('KEEP', 'pending')}>
            <Check size={14} className="mr-1" />全部保留
          </Button>
          <Button variant="secondary" size="sm" onClick={() => batchDecision('DISCARD', 'pending')}>
            <X size={14} className="mr-1" />全部丢弃
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-th-text-muted" />
          {(['all', 'keep', 'archive', 'discard'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilterType(f)}
              className={`text-xs px-2 py-1 rounded transition-all ${filterType === f ? 'font-medium bg-surface text-accent' : 'text-th-text-muted'}`}
            >
              {f === 'all' ? '全部' : f === 'keep' ? '保留' : f === 'archive' ? '归档' : '丢弃'}
            </button>
          ))}
        </div>
      </div>

      {/* 文档列表 */}
      {loading ? (
        <div className="text-center py-12 text-th-text-muted">加载中...</div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map(item => {
            const decision = item.user_decision || item.suggested_decision;
            const isExpanded = expandedItems.has(item.doc_id);
            const isReviewed = item.user_decision !== null;

            return (
              <Card key={item.doc_id} className="p-4 transition-all">

                {/* 主行 */}
                <div className="flex items-center gap-4">
                  {/* 状态点 */}
                  {isReviewed && (
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: decision === 'KEEP' ? 'var(--color-success)' : decision === 'ARCHIVE' ? 'var(--color-warning)' : 'var(--color-error)' }} />
                  )}

                  {/* 评分 */}
                  <div className="w-14 text-center shrink-0">
                    <div className="text-lg font-bold" style={{ color: scoreColor(item.match_score) }}>{item.match_score}</div>
                    <div className="text-[10px] text-th-text-muted">匹配分</div>
                  </div>

                  {/* 评分条 */}
                  <div className="w-16 shrink-0">
                    <div className="h-2 bg-hover rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${item.match_score}%`, backgroundColor: scoreColor(item.match_score) }} />
                    </div>
                  </div>

                  {/* 文档信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <FileText size={16} className="text-th-text-muted shrink-0" />
                      <span className="font-medium truncate">{item.doc_name}</span>
                      <Badge variant="neutral" size="sm">{item.doc_type}</Badge>
                    </div>
                    <div className="text-xs text-th-text-muted mt-1 truncate">{item.match_reason}</div>
                  </div>

                  {/* AI 建议 + 已审核标记 */}
                  {isReviewed && (
                    <Badge variant={decisionBadge(decision) as any} size="sm" className="ring-1 ring-current font-bold">
                      {decision === 'KEEP' ? '已保留' : decision === 'ARCHIVE' ? '已归档' : '已丢弃'}
                    </Badge>
                  )}
                  {!isReviewed && (
                    <Badge variant={decisionBadge(item.suggested_decision) as any} size="sm">
                      AI: {item.suggested_decision}
                    </Badge>
                  )}

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => setDecision(item.doc_id, 'KEEP')}
                      className={`p-2 rounded-btn transition-all duration-200 ${decision === 'KEEP' ? 'btn-keep active scale-110' : 'text-th-text-muted hover:text-th-success hover:scale-105 bg-hover'}`}
                      title="保留"><CheckCircle size={18} /></button>
                    <button onClick={() => setDecision(item.doc_id, 'ARCHIVE')}
                      className={`p-2 rounded-btn transition-all duration-200 ${decision === 'ARCHIVE' ? 'btn-archive active scale-110' : 'text-th-text-muted hover:text-[var(--color-warning)] hover:scale-105 bg-hover'}`}
                      title="归档"><Archive size={18} /></button>
                    <button onClick={() => setDecision(item.doc_id, 'DISCARD')}
                      className={`p-2 rounded-btn transition-all duration-200 ${decision === 'DISCARD' ? 'btn-discard active scale-110' : 'text-th-text-muted hover:text-th-error hover:scale-105 bg-hover'}`}
                      title="丢弃"><XCircle size={18} /></button>
                  </div>

                  {/* 展开 */}
                  <button onClick={() => toggleExpand(item.doc_id)} className="p-1 rounded hover:bg-hover">
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="mt-4 pt-4 border-t space-y-3 border-th-border">
                    {/* 关键词标签 */}
                    {item.keywords.length > 0 && (
                      <div>
                        <div className="text-xs font-medium mb-2 flex items-center gap-1 text-th-text-muted">
                          <Tag size={12} />关键词
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {item.keywords.map(kw => (
                            <span key={kw} className="badge-neutral text-xs px-2 py-0.5 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 知识域 */}
                    {item.domains.length > 0 && (
                      <div>
                        <div className="text-xs font-medium mb-2 text-th-text-muted">关联知识域</div>
                        <div className="flex flex-wrap gap-1">
                          {item.domains.map(d => (
                            <span key={d} className="badge-active text-xs px-2 py-0.5 rounded">{d}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 摘要 */}
                    {item.summary && (
                      <div>
                        <div className="text-xs font-medium mb-1 text-th-text-muted">内容摘要</div>
                        <p className="text-sm text-th-text-secondary">{item.summary}</p>
                      </div>
                    )}

                    {/* 置信度 */}
                    <div className="flex items-center gap-4 text-xs text-th-text-muted">
                      <span>AI 置信度: {(item.confidence * 100).toFixed(0)}%</span>
                      <span>KPI: {(item.kpi * 100).toFixed(0)}</span>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Toast 提示 */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-btn shadow-xl text-white text-sm font-medium animate-slideUp backdrop-blur"
          style={{ backgroundColor: 'rgba(34,197,94,0.9)' }}>
          {toast}
        </div>
      )}
    </div>
  );
}
