/**
 * PromptVersionManager smoke test（M18 #3）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import PromptVersionManager from './PromptVersionManager';

vi.mock('@/services/observabilityApi', () => ({
  fetchPromptVersions: vi.fn(),
  fetchPromptABScores: vi.fn(),
  createPromptVersion: vi.fn(),
  deactivatePromptVersion: vi.fn(),
  autoTunePrompt: vi.fn(),
}));

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string, vars?: Record<string, string | number>) => {
      const map: Record<string, string> = {
        'pv.title': 'Prompt 版本管理',
        'pv.subtitle': '自学习闭环',
        'pv.tabList': '版本列表',
        'pv.tabAB': 'AB 比较',
        'pv.create': '新建版本',
        'pv.deactivate': '停用',
        'pv.autoTune': '触发 auto-tune',
        'pv.col.versionId': '版本 ID',
        'pv.col.condition': '监测条件',
        'pv.col.language': '语言',
        'pv.col.activatedAt': '激活时间',
        'pv.col.status': '状态',
        'pv.col.note': '备注',
        'pv.col.actions': '操作',
        'pv.col.sampleSize': '样本数',
        'pv.col.approveRate': '批准率',
        'pv.statusActive': '激活中',
        'pv.statusInactive': '已停用',
        'pv.empty': '暂无版本',
        'pv.filterCondition': '条件',
        'pv.filterLanguage': '语言',
        'pv.filterAll': '全部',
        'pv.confirmDeactivate': '确认停用 {id}?',
        'pv.autoTuneAction': '动作: {action}',
        'pv.autoTuneNoop': 'auto-tune 无变化',
        'pv.autoTuneReason': '原因',
        'observ.refresh': '刷新',
        'observ.empty': '暂无数据',
      };
      let s = map[key] || key;
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          s = s.replace(`{${k}}`, String(v));
        });
      }
      return s;
    },
  }),
}));

vi.mock('@/components/v15/LanguageSwitcher', () => ({
  default: () => null,
}));

import {
  autoTunePrompt, deactivatePromptVersion,
  fetchPromptABScores, fetchPromptVersions,
} from '@/services/observabilityApi';


const fakeVersions = [
  {
    version_id: 'pv_001',
    condition_type: 'new_entity_type' as const,
    language: 'zh',
    prompt_text_excerpt: '你是一名 SME...',
    system_prompt: '...',
    created_by: 'sme1',
    activated_at: '2026-04-01T10:00:00',
    deactivated_at: null,
    note: '初始版',
  },
  {
    version_id: 'pv_002',
    condition_type: 'new_entity_type' as const,
    language: 'zh',
    prompt_text_excerpt: '改进版...',
    system_prompt: '...',
    created_by: 'sme2',
    activated_at: '2026-04-15T10:00:00',
    deactivated_at: '2026-04-20T10:00:00',
    note: '已停用',
  },
];

const fakeAB = [
  {
    version_id: 'pv_001',
    condition_type: 'new_entity_type' as const,
    activated_at: '2026-04-01T10:00:00',
    deactivated_at: null,
    is_active: true,
    sample_size: 25,
    approved: 20,
    rejected: 5,
    pending: 0,
    approve_rate: 0.8,
  },
];


describe('PromptVersionManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPromptVersions).mockResolvedValue(fakeVersions);
    vi.mocked(fetchPromptABScores).mockResolvedValue(fakeAB);
  });

  it('renders versions list with active highlight', async () => {
    render(<PromptVersionManager />);
    await waitFor(() => {
      expect(screen.getByText('pv_001')).toBeInTheDocument();
    });
    expect(screen.getByText('pv_002')).toBeInTheDocument();
    // active 版本显示 "激活中"
    expect(screen.getByText('激活中')).toBeInTheDocument();
    // 已停用文案在状态列出现至少一次
    expect(screen.getAllByText('已停用').length).toBeGreaterThan(0);
  });

  it('switches to AB tab and renders approve_rate', async () => {
    render(<PromptVersionManager />);
    await waitFor(() => {
      expect(screen.getByText('pv_001')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('AB 比较'));
    await waitFor(() => {
      expect(screen.getByText('80.0%')).toBeInTheDocument();   // approve_rate
    });
    expect(screen.getByText('25')).toBeInTheDocument();        // sample_size
  });

  it('triggers auto-tune and renders banner', async () => {
    vi.mocked(autoTunePrompt).mockResolvedValue({
      condition_type: 'new_entity_type',
      language: 'zh',
      action: 'promote',
      reason: '候选 v2 approve_rate 超过 v1 5pp',
      previous_active_id: 'pv_001',
      new_active_id: 'pv_003',
    });
    render(<PromptVersionManager />);
    await waitFor(() => {
      expect(screen.getByText('pv_001')).toBeInTheDocument();
    });
    // 选择 condition_type 才能 auto-tune
    const conditionSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(conditionSelect, { target: { value: 'new_entity_type' } });

    fireEvent.click(screen.getByText('触发 auto-tune'));
    await waitFor(() => {
      expect(screen.getByText(/动作: promote/)).toBeInTheDocument();
    });
    expect(screen.getByText(/v1 5pp/)).toBeInTheDocument();
  });

  it('deactivates a version when confirmed', async () => {
    // happy-dom 不实现 window.confirm，需手动 stub
    const origConfirm = window.confirm;
    window.confirm = vi.fn(() => true);
    vi.mocked(deactivatePromptVersion).mockResolvedValue({
      version_id: 'pv_001', deactivated: true,
    });
    render(<PromptVersionManager />);
    await waitFor(() => {
      expect(screen.getByText('pv_001')).toBeInTheDocument();
    });
    // 第一个 active 版本旁有"停用"按钮
    fireEvent.click(screen.getAllByText('停用')[0]);
    await waitFor(() => {
      expect(deactivatePromptVersion).toHaveBeenCalledWith('pv_001');
    });
    window.confirm = origConfirm;
  });

  it('shows error when fetch fails', async () => {
    vi.mocked(fetchPromptVersions).mockRejectedValue(new Error('PG down'));
    render(<PromptVersionManager />);
    await waitFor(() => {
      expect(screen.getByText(/PG down/)).toBeInTheDocument();
    });
  });
});
