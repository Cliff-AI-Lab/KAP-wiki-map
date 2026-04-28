/**
 * @module useSettings
 * @description LLM 设置管理 Hook。
 * 管理 AI 模型提供商、API Key、Base URL、模型名称和 Embedding 提供商等配置。
 * 设置自动持久化到 localStorage，并提供连接测试和保存到服务端的功能。
 */
import { useState, useEffect, useCallback } from 'react';

/** LLM 设置数据结构 */
export interface LLMSettings {
  /** V15: 加 ruidong = 睿动 iRuidong 平台 (OpenAI 兼容) */
  provider: 'openai' | 'deepseek' | 'anthropic' | 'ruidong' | 'custom';
  apiKey: string;
  baseUrl: string;
  model: string;
  embeddingProvider: 'mock' | 'openai';
}

const STORAGE_KEY = 'bookworm-llm-settings'; // localStorage 键名

/** 默认设置值 — provider 和 model 必须匹配 */
const DEFAULT_SETTINGS: LLMSettings = {
  provider: 'openai',
  apiKey: '',
  baseUrl: '',
  model: 'gpt-4o-mini',
  embeddingProvider: 'mock',
};

/** 各提供商的默认 Base URL 和可选模型列表 */
const PROVIDER_DEFAULTS: Record<string, { baseUrl: string; models: string[] }> = {
  openai: {
    baseUrl: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  },
  deepseek: {
    baseUrl: 'https://api.deepseek.com/v1',
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  anthropic: {
    baseUrl: 'https://api.anthropic.com/v1',
    models: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  },
  ruidong: {
    // V15: 睿动 iRuidong 统一网关，OpenAI 兼容。模型列表留空，点"遍历模型"从 /v1/models 动态拉取
    baseUrl: 'https://iruidong.com/v1',
    models: [],
  },
  custom: {
    baseUrl: '',
    models: [],
  },
};

/** 客户端过滤聊天模型 — 睿动规范 MUST-3（与 scripts/test_ruidong.py 一致） */
const CHAT_HINT = [
  'gpt', 'claude', 'qwen', 'llama', 'mistral', 'yi',
  'glm', 'deepseek', 'ernie', 'moonshot', 'baichuan',
  'kimi', 'minimax', 'ruidong-flash', 'ruidong-pro',
  'chat', 'instruct', '4o', 'sonnet', 'haiku', 'opus',
];
const NON_CHAT = [
  'embedding', 'embed', 'rerank', 'reranker', 'bge', 'm3e',
  'audio', 'whisper', 'tts', 'voice', 'speech',
  'vision-only', 'image', 'dall-e', 'sd', 'flux', 'moderation',
  'ace-step', 'wan-', 't2v', 'i2v', 'ti2v', 'video', 'music',
  'coder-local', 'coder-completion',
];

function looksLikeChatModel(name: string): boolean {
  const n = name.toLowerCase();
  if (NON_CHAT.some((k) => n.includes(k))) return false;
  return CHAT_HINT.some((k) => n.includes(k)) || n.includes('-');
}

/**
 * LLM 设置管理 Hook。
 * 提供设置读写、按提供商获取模型列表/默认URL、连接测试、保存到服务端等功能。
 */
export function useSettings() {
  const [settings, setSettings] = useState<LLMSettings>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      const base = saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
      // 恢复 sessionStorage 中的 API Key
      const savedKey = sessionStorage.getItem(`${STORAGE_KEY}-key`);
      if (savedKey) base.apiKey = savedKey;
      return base;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle'); // 连接测试状态
  const [testMessage, setTestMessage] = useState(''); // 连接测试结果消息
  const [fetchedModels, setFetchedModels] = useState<string[]>([]); // V15: 从 /v1/models 拉取并过滤的模型
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'fetching' | 'success' | 'error'>('idle');
  const [fetchMessage, setFetchMessage] = useState('');

  useEffect(() => {
    try {
      const { apiKey: _omit, ...safeSettings } = settings;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(safeSettings));
      // API Key 仅存于 sessionStorage — 清除时也删除
      if (settings.apiKey) {
        sessionStorage.setItem(`${STORAGE_KEY}-key`, settings.apiKey);
      } else {
        sessionStorage.removeItem(`${STORAGE_KEY}-key`);
      }
    } catch {
      // storage quota / privacy mode — 静默忽略
    }
  }, [settings]);

  // V15 fix: provider 切换时清空已 fetch 的模型列表 (避免 OpenAI→DeepSeek 仍显示旧模型)
  useEffect(() => {
    setFetchedModels([]);
    setFetchStatus('idle');
    setFetchMessage('');
  }, [settings.provider]);

  /** 局部更新设置（合并传入的字段） */
  const updateSettings = useCallback((patch: Partial<LLMSettings>) => {
    setSettings(prev => ({ ...prev, ...patch }));
  }, []);

  /** 根据提供商获取可选模型列表 */
  const getModelsForProvider = useCallback((provider: string) => {
    return PROVIDER_DEFAULTS[provider]?.models || [];
  }, []);

  /** 根据提供商获取默认 Base URL */
  const getDefaultBaseUrl = useCallback((provider: string) => {
    return PROVIDER_DEFAULTS[provider]?.baseUrl || '';
  }, []);

  /** 调用后端接口测试 LLM 连接是否可用 */
  const testConnection = useCallback(async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const resp = await fetch('/api/v1/settings/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: settings.provider,
          api_key: settings.apiKey,
          base_url: settings.baseUrl || getDefaultBaseUrl(settings.provider),
          model: settings.model,
        }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setTestStatus('success');
        setTestMessage(data.message || '连接成功');
      } else {
        setTestStatus('error');
        setTestMessage(data.detail || data.message || '连接失败');
      }
    } catch (err) {
      setTestStatus('error');
      setTestMessage('网络错误，请检查后端是否运行');
    }
  }, [settings, getDefaultBaseUrl]);

  /**
   * V15: 从 {baseUrl}/models 拉取模型列表，客户端按聊天模型过滤
   * (睿动规范 MUST-3: 不硬编码模型列表，客户端过滤非聊天模型)
   */
  const fetchModelsFromEndpoint = useCallback(async (): Promise<string[]> => {
    setFetchStatus('fetching');
    setFetchMessage('');
    try {
      const baseUrl = settings.baseUrl || getDefaultBaseUrl(settings.provider);
      if (!baseUrl) {
        setFetchStatus('error');
        setFetchMessage('请先填写 Base URL');
        return [];
      }
      if (!settings.apiKey) {
        setFetchStatus('error');
        setFetchMessage('请先填写 API Key');
        return [];
      }
      const url = `${baseUrl.replace(/\/$/, '')}/models`;
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${settings.apiKey}` },
      });
      if (!resp.ok) {
        setFetchStatus('error');
        setFetchMessage(`HTTP ${resp.status}`);
        return [];
      }
      const data = await resp.json();
      const raw: unknown[] = Array.isArray(data?.data) ? data.data : Array.isArray(data) ? data : [];
      const ids: string[] = raw
        .map((m) => (typeof m === 'string' ? m : (m as Record<string, unknown>)?.id))
        .filter((x): x is string => typeof x === 'string' && x.length > 0);
      const chat = ids.filter(looksLikeChatModel);
      setFetchedModels(chat);
      setFetchStatus('success');
      setFetchMessage(`${ids.length} → ${chat.length} 聊天模型`);
      return chat;
    } catch (e) {
      setFetchStatus('error');
      setFetchMessage(e instanceof Error ? e.message : String(e));
      return [];
    }
  }, [settings.baseUrl, settings.apiKey, settings.provider, getDefaultBaseUrl]);

  /** 将当前设置保存到后端服务器 */
  const saveToServer = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_provider: settings.provider,
          llm_model: settings.model,
          openai_api_key: settings.apiKey,
          openai_base_url: settings.baseUrl || getDefaultBaseUrl(settings.provider),
          embedding_provider: settings.embeddingProvider,
        }),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }, [settings, getDefaultBaseUrl]);

  return {
    settings,
    updateSettings,
    getModelsForProvider,
    getDefaultBaseUrl,
    testConnection,
    testStatus,
    testMessage,
    saveToServer,
    // V15 Phase F: 模型遍历
    fetchModelsFromEndpoint,
    fetchedModels,
    fetchStatus,
    fetchMessage,
  };
}
