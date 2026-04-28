/**
 * @module UnifiedSettings
 * @description 统一设置弹窗组件。
 * 以模态对话框形式展示三个选项卡：
 * - AI 配置：LLM 提供商、API Key、Base URL、模型选择、Embedding 提供商、连接测试
 * - 主题外观：亮/暗模式切换、多种预设主题选择
 * - 关于：版本信息、技术栈、核心能力介绍
 */
import React, { useState } from 'react';
import {
  X,
  Brain,
  Palette,
  Info,
  Key,
  Globe,
  Cpu,
  Plug,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Sun,
  Moon,
  Monitor,
  Languages,
  RefreshCw,
  Activity,
  Database,
  Server,
  Network,
} from 'lucide-react';
import { themes, applyTheme, loadSavedTheme, type Theme } from '@/lib/themes';
import { useSettings } from '@/hooks/useSettings';
import { useLocale } from '@/contexts/LocaleContext';
import type { Locale } from '@/lib/i18n';

interface Props {
  onClose: () => void;
}

type Tab = 'ai' | 'theme' | 'locale' | 'system' | 'about';

export const UnifiedSettings: React.FC<Props> = ({ onClose }) => {
  const { locale, setLocale, t } = useLocale();
  const [activeTab, setActiveTab] = useState<Tab>('ai');
  const [currentTheme, setCurrentTheme] = useState(loadSavedTheme);
  const [showSecret, setShowSecret] = useState(false);
  const {
    settings,
    updateSettings,
    getModelsForProvider,
    getDefaultBaseUrl,
    testConnection,
    testStatus,
    testMessage,
    saveToServer,
    fetchModelsFromEndpoint,
    fetchedModels,
    fetchStatus,
    fetchMessage,
  } = useSettings();

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'ai', label: t('settings.tabAI'), icon: <Brain size={16} /> },
    { id: 'theme', label: t('settings.tabTheme'), icon: <Palette size={16} /> },
    { id: 'locale', label: t('settings.tabLocale'), icon: <Languages size={16} /> },
    { id: 'system', label: t('settings.tabSystem'), icon: <Activity size={16} /> },
    { id: 'about', label: t('settings.tabAbout'), icon: <Info size={16} /> },
  ];

  const [saveError, setSaveError] = useState<string | null>(null);
  const handleSave = async () => {
    setSaveError(null);
    const ok = await saveToServer();
    if (ok) {
      onClose();
    } else {
      setSaveError('保存到服务端失败 · 请检查网络或后端日志');
    }
  };

  const handleThemeSelect = (theme: Theme) => {
    applyTheme(theme);
    setCurrentTheme(theme);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />

      <div
        className="relative w-[720px] max-h-[85vh] rounded-xl overflow-hidden flex animate-fadeIn bg-elevated border border-th-border"
        onClick={e => e.stopPropagation()}
      >
        {/* Left Tabs */}
        <div className="w-48 shrink-0 border-r flex flex-col border-th-border bg-surface">
          <div className="p-4 border-b border-th-border">
            <h2 className="text-lg font-semibold text-th-text-primary">{t('settings.title')}</h2>
          </div>
          <nav className="flex-1 p-2 space-y-1">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                  activeTab === tab.id
                    ? 'text-accent bg-hover border-l-2 border-accent'
                    : 'text-th-text-secondary border-l-2 border-transparent hover:bg-hover'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Right Content */}
        <div className="flex-1 flex flex-col">
          <div className="flex items-center justify-between p-4 border-b border-th-border">
            <h3 className="font-medium text-th-text-primary">
              {tabs.find(t => t.id === activeTab)?.label}
            </h3>
            <button onClick={onClose} className="btn-ghost rounded-lg p-1.5">
              <X size={18} className="text-th-text-muted" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {activeTab === 'ai' && <AITab
              settings={settings}
              updateSettings={updateSettings}
              getModelsForProvider={getModelsForProvider}
              getDefaultBaseUrl={getDefaultBaseUrl}
              testConnection={testConnection}
              testStatus={testStatus}
              testMessage={testMessage}
              showSecret={showSecret}
              setShowSecret={setShowSecret}
              fetchModelsFromEndpoint={fetchModelsFromEndpoint}
              fetchedModels={fetchedModels}
              fetchStatus={fetchStatus}
              fetchMessage={fetchMessage}
            />}
            {activeTab === 'theme' && <ThemeTab
              currentTheme={currentTheme}
              onSelect={handleThemeSelect}
            />}
            {activeTab === 'locale' && <LocaleTab
              locale={locale}
              onSelect={setLocale}
              t={t}
            />}
            {activeTab === 'system' && <SystemTab />}
            {activeTab === 'about' && <AboutTab />}
          </div>

          <div className="flex items-center justify-end gap-3 p-4 border-t border-th-border">
            {saveError && (
              <span className="text-xs text-th-error mr-auto inline-flex items-center gap-1">
                <AlertTriangle size={12} /> {saveError}
              </span>
            )}
            <button onClick={onClose} className="btn-secondary rounded-lg px-4 py-2 text-sm">
              {t('settings.cancel')}
            </button>
            <button onClick={handleSave} className="btn-gradient rounded-lg px-4 py-2 text-sm">
              {t('settings.save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ========== AI Configuration Tab ========== */
function AITab({
  settings, updateSettings, getModelsForProvider, getDefaultBaseUrl,
  testConnection, testStatus, testMessage, showSecret, setShowSecret,
  fetchModelsFromEndpoint, fetchedModels, fetchStatus, fetchMessage,
}: any) {
  const providers = [
    { id: 'ruidong',  name: '睿动 iRuidong', desc: '统一 AI 网关 · 多模型可切' },
    { id: 'openai',   name: 'OpenAI',        desc: 'GPT-4o / GPT-4 系列' },
    { id: 'deepseek', name: 'DeepSeek',      desc: 'DeepSeek-Chat / Reasoner' },
    { id: 'anthropic',name: 'Anthropic',     desc: 'Claude 系列' },
    { id: 'custom',   name: '自定义 (OpenAI 兼容)', desc: '任何兼容 OpenAI API 的服务' },
  ];

  const staticModels: string[] = getModelsForProvider(settings.provider);
  // 睿动 / custom 优先用遍历结果；其他 provider 用静态清单
  const dynamicModels: string[] = Array.isArray(fetchedModels) ? fetchedModels : [];
  const models: string[] = dynamicModels.length > 0 ? dynamicModels : staticModels;
  const canFetch = settings.provider === 'ruidong' || settings.provider === 'custom' || settings.provider === 'openai';

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium mb-2 text-th-text-primary">
          <Cpu size={14} className="inline mr-2" />
          模型提供商
        </label>
        <div className="grid grid-cols-2 gap-2">
          {providers.map(p => (
            <button
              key={p.id}
              onClick={() => {
                updateSettings({
                  provider: p.id,
                  baseUrl: getDefaultBaseUrl(p.id),
                  model: getModelsForProvider(p.id)[0] || '',
                });
              }}
              className={`glass-surface rounded-lg p-3 text-left transition-all ${
                settings.provider === p.id ? 'border-accent shadow-ring-accent' : ''
              }`}
            >
              <div className="text-sm font-medium text-th-text-primary">{p.name}</div>
              <div className="text-xs mt-0.5 text-th-text-muted">{p.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2 text-th-text-primary">
          <Key size={14} className="inline mr-2" />
          API Key
        </label>
        <div className="relative">
          <input
            type={showSecret ? 'text' : 'password'}
            value={settings.apiKey}
            onChange={e => updateSettings({ apiKey: e.target.value })}
            placeholder={settings.provider === 'openai' ? 'sk-...' : settings.provider === 'anthropic' ? 'sk-ant-...' : '输入 API Key'}
            className="glass-surface w-full rounded-lg px-3 py-2.5 text-sm pr-16 text-th-text-primary"
          />
          <button
            onClick={() => setShowSecret(!showSecret)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs px-2 py-1 rounded text-th-text-muted"
          >
            {showSecret ? '隐藏' : '显示'}
          </button>
        </div>
        <p className="text-xs mt-1.5 text-th-text-muted">
          API Key 仅存储在本地浏览器和服务端配置中
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2 text-th-text-primary">
          <Globe size={14} className="inline mr-2" />
          API 端点 (Base URL)
        </label>
        <input
          type="text"
          value={settings.baseUrl}
          onChange={e => updateSettings({ baseUrl: e.target.value })}
          placeholder={getDefaultBaseUrl(settings.provider) || 'https://your-api.com/v1'}
          className="glass-surface w-full rounded-lg px-3 py-2.5 text-sm text-th-text-primary"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-th-text-primary">
            <Brain size={14} className="inline mr-2" />
            模型
            {dynamicModels.length > 0 && (
              <span className="ml-2 text-xs text-th-text-muted font-mono">
                (已从 /v1/models 过滤 · {dynamicModels.length} 个聊天模型)
              </span>
            )}
          </label>
          {canFetch && (
            <button
              type="button"
              onClick={fetchModelsFromEndpoint}
              disabled={fetchStatus === 'fetching' || !settings.apiKey}
              className="btn-secondary rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5 disabled:opacity-40"
              title="调 /v1/models 遍历，客户端过滤聊天模型"
            >
              {fetchStatus === 'fetching' ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              遍历模型
            </button>
          )}
        </div>
        {fetchStatus === 'success' && (
          <div className="text-xs text-th-success mb-2 font-mono inline-flex items-center gap-1"><CheckCircle size={11}/> {fetchMessage}</div>
        )}
        {fetchStatus === 'error' && (
          <div className="text-xs text-th-error mb-2 font-mono inline-flex items-center gap-1"><AlertTriangle size={11}/> {fetchMessage}</div>
        )}
        {models.length > 0 ? (
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {models.map((m: string) => (
              <button
                key={m}
                onClick={() => updateSettings({ model: m })}
                className={`w-full glass-surface rounded-lg px-3 py-2 text-sm text-left flex items-center justify-between transition-all text-th-text-primary ${
                  settings.model === m ? 'border-accent' : ''
                }`}
              >
                {m}
                {settings.model === m && <CheckCircle size={16} className="text-th-success" />}
              </button>
            ))}
          </div>
        ) : (
          <input
            type="text"
            value={settings.model}
            onChange={e => updateSettings({ model: e.target.value })}
            placeholder="输入模型名称 (或点右上角遍历模型)"
            className="glass-surface w-full rounded-lg px-3 py-2.5 text-sm text-th-text-primary"
          />
        )}
      </div>

      <div>
        <label className="block text-sm font-medium mb-2 text-th-text-primary">
          Embedding 提供商
        </label>
        <select
          value={settings.embeddingProvider}
          onChange={e => updateSettings({ embeddingProvider: e.target.value })}
          className="glass-surface w-full rounded-lg px-3 py-2.5 text-sm text-th-text-primary"
        >
          <option value="mock">Mock (离线模式)</option>
          <option value="openai">OpenAI Embeddings</option>
        </select>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={testConnection}
          disabled={testStatus === 'testing' || !settings.apiKey}
          className="btn-secondary rounded-lg px-4 py-2 text-sm flex items-center gap-2"
        >
          {testStatus === 'testing' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Plug size={14} />
          )}
          测试连接
        </button>
        {testStatus === 'success' && (
          <span className="text-sm flex items-center gap-1 text-th-success">
            <CheckCircle size={14} /> {testMessage}
          </span>
        )}
        {testStatus === 'error' && (
          <span className="text-sm flex items-center gap-1 text-th-error">
            <AlertTriangle size={14} /> {testMessage}
          </span>
        )}
      </div>
    </div>
  );
}

/* ========== Theme Tab ========== */
function ThemeTab({ currentTheme, onSelect }: { currentTheme: Theme; onSelect: (t: Theme) => void }) {
  const darkThemes = themes.filter(t => t.colorScheme === 'dark');
  const lightThemes = themes.filter(t => t.colorScheme === 'light');

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium mb-3 text-th-text-primary">外观模式</label>
        <div className="flex gap-2">
          {[
            { mode: 'dark', icon: <Moon size={16} />, label: '暗色' },
            { mode: 'light', icon: <Sun size={16} />, label: '亮色' },
            { mode: 'system', icon: <Monitor size={16} />, label: '跟随系统' },
          ].map(({ mode, icon, label }) => (
            <button
              key={mode}
              onClick={() => {
                if (mode === 'system') {
                  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                  const theme = themes.find(t => t.colorScheme === (prefersDark ? 'dark' : 'light')) ?? themes[0]!;
                  onSelect(theme);
                } else {
                  const theme = themes.find(t => t.colorScheme === mode) ?? themes[0]!;
                  onSelect(theme);
                }
              }}
              className={`glass-surface flex-1 rounded-lg p-3 flex flex-col items-center gap-2 transition-all ${
                (mode === 'dark' && currentTheme.colorScheme === 'dark') ||
                (mode === 'light' && currentTheme.colorScheme === 'light')
                  ? 'border-accent' : ''
              }`}
            >
              {icon}
              <span className="text-xs text-th-text-secondary">{label}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-3 text-th-text-primary">暗色主题</label>
        <div className="grid grid-cols-2 gap-2">
          {darkThemes.map(theme => (
            <ThemeCard key={theme.id} theme={theme} isActive={currentTheme.id === theme.id} onSelect={onSelect} />
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-3 text-th-text-primary">亮色主题</label>
        <div className="grid grid-cols-2 gap-2">
          {lightThemes.map(theme => (
            <ThemeCard key={theme.id} theme={theme} isActive={currentTheme.id === theme.id} onSelect={onSelect} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** 单个主题预览卡片 - 使用主题自身颜色渲染（保留 inline style） */
function ThemeCard({ theme, isActive, onSelect }: { theme: Theme; isActive: boolean; onSelect: (t: Theme) => void }) {
  return (
    <button
      onClick={() => onSelect(theme)}
      className="rounded-lg p-3 text-left transition-all border"
      style={{
        backgroundColor: theme.colors.bgElevated,
        borderColor: isActive ? theme.colors.accent : theme.colors.border,
        boxShadow: isActive ? `0 0 0 2px ${theme.colors.accent}40` : undefined,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div className="flex gap-1">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.accent }} />
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.success }} />
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: theme.colors.info }} />
        </div>
        {isActive && <CheckCircle size={14} style={{ color: theme.colors.accent }} />}
      </div>
      <div className="text-sm font-medium" style={{ color: theme.colors.textPrimary }}>{theme.name}</div>
      <div className="flex gap-1 mt-1.5">
        <div className="flex-1 h-1 rounded" style={{ backgroundColor: theme.colors.bgBase }} />
        <div className="flex-1 h-1 rounded" style={{ backgroundColor: theme.colors.bgSurface }} />
        <div className="flex-1 h-1 rounded" style={{ backgroundColor: theme.colors.bgHover }} />
      </div>
    </button>
  );
}

/* ========== Locale Tab — V15 Phase F ========== */
function LocaleTab({
  locale,
  onSelect,
  t,
}: {
  locale: Locale;
  onSelect: (l: Locale) => void;
  t: (k: any) => string;
}) {
  const options: { id: Locale; label: string; native: string; code: string }[] = [
    { id: 'zh', label: t('settings.localeZh'), native: '中文',    code: 'CN' },
    { id: 'en', label: t('settings.localeEn'), native: 'English', code: 'EN' },
  ];
  return (
    <div className="space-y-4">
      <p className="text-sm text-th-text-muted">{t('settings.localeDesc')}</p>
      <div className="grid grid-cols-2 gap-3">
        {options.map((opt) => {
          const active = locale === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => onSelect(opt.id)}
              className={`glass-surface rounded-lg p-4 text-left transition-all ${
                active ? 'border-accent shadow-ring-accent' : ''
              }`}
            >
              <div className="flex items-center gap-3 mb-1">
                <span
                  className={`w-10 h-10 grid place-items-center rounded-btn font-mono text-xs font-bold ${
                    active ? 'bg-accent text-[color:var(--color-bg-base)]' : 'bg-hover text-th-text-secondary'
                  }`}
                >
                  {opt.code}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium text-th-text-primary">{opt.native}</div>
                  <div className="text-xs text-th-text-muted font-mono uppercase">{opt.id}</div>
                </div>
                {active && <CheckCircle size={16} className="text-th-success" />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ========== System Tab — 组件状态可视化 ========== */
interface InfraItem { key: string; name: string; status: string; addr: string; required: boolean; optional: boolean }
interface StoreItem { name: string; category: string; desc?: string; mode?: string; depends?: string; count?: number; status?: string; error?: string }
interface ComponentsResp {
  infra: InfraItem[];
  stores: StoreItem[];
  summary: {
    infra_total: number;
    infra_ok: number;
    infra_unavailable: number;
    store_total: number;
    store_persistent?: number;
    store_pg_mode: number;
    store_memory_mode: number;
    total: number;
  };
}

function SystemTab() {
  const [data, setData] = React.useState<ComponentsResp | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/v1/system/components');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-th-text-primary">组件状态</div>
          <div className="text-xs text-th-text-muted mt-1">
            重组件 (Milvus / Neo4j / MinIO) 可选 · 不可用时自动 fallback memory
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-btn border border-th-border text-[11px] v15-mono text-th-text-muted hover:text-th-text-primary disabled:opacity-50"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          刷新
        </button>
      </div>

      {error && (
        <div className="rounded-btn border border-th-error/40 bg-th-error/5 p-3 text-sm text-th-error inline-flex items-center gap-2">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {data && (
        <>
          {/* 汇总 */}
          <div className="grid grid-cols-4 gap-2">
            <SysStat label="基础设施" value={`${data.summary.infra_ok}/${data.summary.infra_total}`} hint="ok / 总" tone={data.summary.infra_ok === data.summary.infra_total ? 'success' : 'warning'} />
            <SysStat label="持久化 Store" value={`${data.summary.store_persistent ?? data.summary.store_pg_mode}`} hint="真后端 (pg/neo4j/...)" tone="success" />
            <SysStat label="Memory 模式" value={`${data.summary.store_memory_mode}`} hint="降级运行" tone="warning" />
            <SysStat label="组件总数" value={`${data.summary.total}`} hint="infra + stores" tone="info" />
          </div>

          {/* 基础设施 */}
          <div className="rounded-card border border-th-border bg-elevated/60 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-th-border">
              <Server size={14} className="text-accent" />
              <span className="text-sm font-semibold text-th-text-primary">基础设施</span>
            </div>
            {data.infra.map((x) => {
              const ok = x.status === 'ok';
              return (
                <div key={x.key} className="flex items-center gap-3 px-4 py-2 border-b border-th-border/40 last:border-b-0">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${ok ? 'bg-th-success' : x.required ? 'bg-th-error' : 'bg-th-warning'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-th-text-primary inline-flex items-center gap-2">
                      {x.name}
                      {x.required ? (
                        <span className="text-[9px] v15-mono px-1 rounded bg-th-error/20 text-th-error">必选</span>
                      ) : (
                        <span className="text-[9px] v15-mono px-1 rounded bg-hover text-th-text-muted">可选</span>
                      )}
                    </div>
                    <div className="text-[10px] text-th-text-muted v15-mono truncate">{x.addr}</div>
                  </div>
                  <span className={`text-[10px] v15-mono px-2 py-0.5 rounded-pill ${ok ? 'bg-th-success/20 text-th-success' : 'bg-th-warning/20 text-th-warning'}`}>
                    {ok ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Stores */}
          <div className="rounded-card border border-th-border bg-elevated/60 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-th-border">
              <Database size={14} className="text-accent" />
              <span className="text-sm font-semibold text-th-text-primary">Store 层</span>
            </div>
            {data.stores.map((s) => (
              <div key={s.name} className="flex items-center gap-3 px-4 py-2 border-b border-th-border/40 last:border-b-0">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  s.mode === 'pg' ? 'bg-th-success' : s.mode === 'memory' ? 'bg-th-warning' : 'bg-th-error'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-th-text-primary inline-flex items-center gap-2">
                    {s.name}
                    {s.count != null && (
                      <span className="text-[10px] v15-mono text-th-text-muted">· {s.count}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-th-text-muted truncate">{s.desc} · 依赖 {s.depends}</div>
                </div>
                <span className={`text-[10px] v15-mono px-2 py-0.5 rounded-pill ${
                  s.mode === 'pg' ? 'bg-th-success/20 text-th-success' :
                  s.mode === 'memory' ? 'bg-th-warning/20 text-th-warning' :
                  'bg-th-error/20 text-th-error'
                }`}>
                  {s.mode?.toUpperCase() ?? 'N/A'}
                </span>
              </div>
            ))}
          </div>

          {/* 启用提示 */}
          {data.summary.store_memory_mode > 0 && (
            <div className="rounded-btn border border-th-warning/30 bg-th-warning/5 p-3 text-xs text-th-text-secondary">
              <div className="font-semibold text-th-warning inline-flex items-center gap-1.5 mb-1">
                <Network size={12} /> 启用持久化重组件
              </div>
              <div className="text-[11px] text-th-text-muted">
                运行 <code className="v15-mono text-accent">docker-compose up -d</code> 启动 Neo4j / Milvus / Redis / MinIO,
                然后 <code className="v15-mono text-accent">python run_dev.py</code> 重启后端,
                4 个 memory 组件将切换到对应真后端, 数据持久化不丢.
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SysStat({ label, value, hint, tone }: { label: string; value: string; hint: string; tone: 'success' | 'warning' | 'info' | 'error' }) {
  const colors = {
    success: 'text-th-success',
    warning: 'text-th-warning',
    info:    'text-accent',
    error:   'text-th-error',
  };
  return (
    <div className="rounded-card border border-th-border bg-elevated p-3">
      <div className="text-[10px] uppercase tracking-wider text-th-text-muted">{label}</div>
      <div className={`text-2xl font-semibold mt-1 v15-display ${colors[tone]}`}>{value}</div>
      <div className="text-[10px] text-th-text-muted v15-mono mt-1">{hint}</div>
    </div>
  );
}

/* ========== About Tab ========== */
function AboutTab() {
  return (
    <div className="space-y-6">
      <div className="glass-card rounded-card p-6 text-center">
        <div className="text-3xl font-bold mb-2 text-accent">知识图鉴</div>
        <div className="text-sm text-th-text-muted">Wiki-Map · 企业知识编译与治理平台</div>
        <div className="mt-4 text-sm text-th-text-secondary">Version 11.0</div>
      </div>

      <div className="space-y-3">
        <div className="glass-surface rounded-lg p-4">
          <div className="text-xs font-medium mb-2 text-th-text-muted">技术栈</div>
          <div className="flex flex-wrap gap-2">
            {['Python 3.11', 'FastAPI', 'React 19', 'Vite', 'Tailwind CSS', 'PostgreSQL', 'Neo4j', 'Milvus', 'Redis'].map(tech => (
              <span key={tech} className="badge-neutral text-xs px-2 py-1 rounded">{tech}</span>
            ))}
          </div>
        </div>

        <div className="glass-surface rounded-lg p-4">
          <div className="text-xs font-medium mb-2 text-th-text-muted">核心能力</div>
          <ul className="text-sm space-y-1 text-th-text-secondary">
            <li>- 飞书/钉钉/企微文档自动采集</li>
            <li>- AI 智能去噪与质量评分</li>
            <li>- 多维知识蒸馏 (Librarian / Judge / Refiner)</li>
            <li>- 混合检索 (向量 + 图谱 + BM25 + 目录)</li>
            <li>- Skills 知识体系路由与分支激活检索</li>
            <li>- 智能问答与知识缺口分析</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default UnifiedSettings;
