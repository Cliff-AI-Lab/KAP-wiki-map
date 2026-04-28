/**
 * 智能问答页面（QAPage）
 *
 * 书虫智能体的 RAG（检索增强生成）问答界面，采用 Chat 风格交互。
 *
 * 核心功能：
 * - 用户在底部输入栏提问，消息列表自动向上滚动
 * - 调用后端 /api/v1/qa/ask 接口，基于知识库文档生成回答
 * - 每条 AI 回答下方可展开查看引用来源卡片（文档标题、相关度评分、内容摘要）
 * - 支持调节 topK（参考文档数量）参数
 * - 展示意图分类（intentCategory）和响应延迟（latencyMs）等元信息
 *
 * @module pages/QAPage
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  MessageSquare,
  Send,
  User,
  Bot,
  ChevronDown,
  ChevronRight,
  FileText,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Card, Badge } from '@/components/ui';
import { askQuestion, type QAResponse, type QASource } from '@/services/api';
import { useProject } from '@/contexts/ProjectContext';

/* ---------- types ---------- */

/** 聊天消息数据结构 */
interface ChatMessage {
  /** 消息唯一标识（前端生成，格式：role-timestamp） */
  id: string;
  /** 消息角色：user=用户提问, assistant=AI回答 */
  role: 'user' | 'assistant';
  /** 消息文本内容 */
  content: string;
  /** AI 回答引用的知识来源列表 */
  sources?: QASource[];
  /** AI 识别的意图分类（如"设备操作"、"安全规范"等） */
  intentCategory?: string;
  /** V11: 双引擎路径标识 (wiki/rag/hybrid) */
  routePath?: string;
  /** 后端响应延迟（毫秒） */
  latencyMs?: number;
  /** 错误信息（请求失败时填充） */
  error?: string;
}

/* ---------- component ---------- */

/**
 * 智能问答组件
 *
 * 提供 Chat 风格的问答界面，用户输入问题后调用 RAG 接口获取基于文档的回答。
 */
export default function QAPage() {
  const { currentProject } = useProject();
  const [messages, setMessages] = useState<ChatMessage[]>([]);          // 聊天消息列表
  const [input, setInput] = useState('');                               // 当前输入框内容
  const [topK, setTopK] = useState(5);                                  // 检索参考文档数量
  const [loading, setLoading] = useState(false);                        // 是否正在等待 AI 回答
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set()); // 已展开来源的消息 ID 集合

  const scrollRef = useRef<HTMLDivElement>(null);   // 消息列表滚动容器引用
  const inputRef = useRef<HTMLInputElement>(null);  // 输入框引用（用于自动聚焦）

  // 消息变化或加载状态变化时，自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // 组件挂载时自动聚焦输入框
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /** 切换某条消息的来源卡片展开/折叠状态 */
  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      next.has(msgId) ? next.delete(msgId) : next.add(msgId);
      return next;
    });
  };

  /** 提交问题：将用户消息加入列表，调用后端 QA 接口，将 AI 回答追加到列表 */
  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      const question = input.trim();
      if (!question || loading) return;

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: question,
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setLoading(true);

      try {
        const data: QAResponse = await askQuestion(question, topK, currentProject?.id);
        const assistantMsg: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          intentCategory: data.intent_category,
          routePath: data.route_path || 'rag',
          latencyMs: data.latency_ms,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMsg: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: '抱歉，回答失败，请稍后重试。',
          error: err instanceof Error ? err.message : '未知错误',
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [input, topK, loading, currentProject?.id],
  );

  /* ---------- render ---------- */

  return (
    <div className="p-6 h-full flex flex-col page-enter">
      {/* Header */}
      <div className="mb-4 page-hero">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <MessageSquare className="text-accent" size={22} />
          智能问答
        </h1>
        <p className="text-sm text-th-text-secondary mt-1">
          向知识库提问，获取基于文档的回答
        </p>
      </div>

      {/* Chat area */}
      <Card className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && !loading && (
            <div className="h-full flex items-center justify-center text-th-text-muted">
              <div className="text-center">
                <MessageSquare size={40} className="mx-auto mb-3 opacity-50" />
                <p className="mb-1">暂无对话</p>
                <p className="text-xs">在下方输入问题开始提问</p>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className="flex gap-3">
              {/* Avatar */}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.role === 'user'
                    ? 'bg-accent/20 text-accent'
                    : 'bg-hover text-th-text-secondary'
                }`}
              >
                {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div
                  className={`rounded-card px-4 py-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'text-th-text-primary bg-[var(--color-info-bg)] shadow-[0px_0px_0px_1px_rgba(94,106,210,0.25)]'
                      : 'glass-card text-th-text-primary'
                  }`}
                >
                  {msg.content}
                </div>

                {/* Error detail */}
                {msg.error && (
                  <div className="flex items-center gap-1 mt-1 text-xs text-red-500">
                    <AlertCircle size={12} />
                    {msg.error}
                  </div>
                )}

                {/* Meta info */}
                {msg.role === 'assistant' && !msg.error && (
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-th-text-muted">
                    {/* V11: 双引擎路径 badge */}
                    {msg.routePath && (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-pill text-[10px] font-medium ${
                        msg.routePath === 'wiki'
                          ? 'badge-active'
                          : msg.routePath === 'hybrid'
                          ? 'bg-[var(--color-purple-bg)] text-[#c084fc] shadow-[0_0_0_1px_rgba(167,139,250,0.25)]'
                          : 'badge-pending'
                      }`}
                      >
                        {msg.routePath === 'wiki' ? '📖 Wiki路径' : msg.routePath === 'hybrid' ? '🔀 双路径' : '⚡ RAG路径'}
                      </span>
                    )}
                    {msg.intentCategory && (
                      <Badge variant="neutral" className="text-xs">
                        {msg.intentCategory}
                      </Badge>
                    )}
                    {msg.latencyMs !== undefined && (
                      <span>{msg.latencyMs}ms</span>
                    )}
                  </div>
                )}

                {/* Sources toggle */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2">
                    <button
                      className="flex items-center gap-1 text-xs text-accent hover:text-accent-light transition-colors"
                      onClick={() => toggleSources(msg.id)}
                    >
                      {expandedSources.has(msg.id) ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                      查看来源 ({msg.sources.length})
                    </button>

                    {expandedSources.has(msg.id) && (
                      <div className="mt-2 space-y-2">
                        {msg.sources.map((src, idx) => (
                          <div
                            key={`${src.doc_id}-${idx}`}
                            className="glass-card rounded-card p-3"
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <FileText size={14} className="text-th-text-muted" />
                              <span className="text-sm font-medium text-th-text-primary truncate">
                                {src.title}
                              </span>
                              <span className="text-xs font-mono text-green-600 ml-auto flex-shrink-0">
                                {src.score.toFixed(3)}
                              </span>
                            </div>
                            <p className="text-xs text-th-text-secondary line-clamp-3 mb-1.5">
                              {src.content}
                            </p>
                            <div className="flex items-center gap-2 flex-wrap">
                              {src.source_system && (
                                <Badge variant="neutral" className="text-xs">
                                  {src.source_system}
                                </Badge>
                              )}
                              {src.category_path && (
                                <span className="text-xs text-th-text-muted">
                                  {src.category_path}
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-hover text-th-text-secondary">
                <Bot size={16} />
              </div>
              <div className="glass-card rounded-card px-4 py-3 text-sm text-th-text-muted flex items-center gap-2">
                <RefreshCw className="animate-spin" size={14} />
                正在思考...
              </div>
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-th-border">
          <form onSubmit={handleSubmit} className="flex items-center gap-3">
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="rounded-btn text-sm h-12 px-3 focus:outline-none bg-transparent shadow-input text-th-text-primary"
              title="参考文档数量"
            >
              {[3, 5, 10, 20].map((n) => (
                <option key={n} value={n}>
                  Top {n}
                </option>
              ))}
            </select>
            <div className="flex-1 relative shadow-input rounded-featured">
              <input
                ref={inputRef}
                type="text"
                placeholder="输入你的问题..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
                className="w-full px-4 h-12 text-base bg-transparent border-none focus:outline-none rounded-featured text-th-text-primary placeholder:text-th-text-muted disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="btn-gradient px-5 h-12 rounded-btn text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all"
            >
              <Send size={14} />
              发送
            </button>
          </form>
        </div>
      </Card>
    </div>
  );
}
