/**
 * WikiHierarchyTree smoke test（M16 #4）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import WikiHierarchyTree from './WikiHierarchyTree';

vi.mock('@/services/api', () => ({
  fetchWikiPages: vi.fn(),
}));

vi.mock('@/contexts/LocaleContext', () => ({
  useLocale: () => ({
    locale: 'zh', setLocale: vi.fn(),
    t: (key: string) => {
      const map: Record<string, string> = {
        'wiki.layer.index': '索引',
        'wiki.layer.domain_overview': '领域概览',
        'wiki.layer.source_summary': '源文档摘要',
      };
      return map[key] || key;
    },
  }),
}));

import { fetchWikiPages } from '@/services/api';


function makePage(
  id: string, type: string, parent: string,
  title: string, srcCount = 0, crossRef = 0,
): any {
  return {
    page_id: id, title,
    summary: '',
    page_type: type,
    parent_page_id: parent,
    source_doc_count: srcCount,
    cross_ref_count: crossRef,
    compiled_at: '2026-04-30T10:00:00',
    version: 1, status: 'published',
  };
}


describe('WikiHierarchyTree', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows empty state when no pages', async () => {
    vi.mocked(fetchWikiPages).mockResolvedValue([]);
    render(<WikiHierarchyTree projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/暂无 Wiki 页面/)).toBeInTheDocument();
    });
  });

  it('renders 3-tier structure with counts', async () => {
    vi.mocked(fetchWikiPages).mockResolvedValue([
      makePage('idx_1', 'index', '', '总索引'),
      makePage('dom_a', 'domain_overview', 'idx_1', '能源领域', 0, 3),
      makePage('dom_b', 'domain_overview', 'idx_1', '制造领域', 0, 2),
      makePage('src_1', 'source_summary', 'dom_a', '风电运维手册', 5),
      makePage('src_2', 'source_summary', 'dom_a', '光伏巡检', 3),
      makePage('src_3', 'source_summary', 'dom_b', '电机说明书', 4),
    ]);

    render(<WikiHierarchyTree projectId="p1" />);

    await waitFor(() => {
      expect(screen.getByText('总索引')).toBeInTheDocument();
    });
    // 3 计数卡：1 index / 2 domain / 3 source
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    // domain 节点
    expect(screen.getByText('能源领域')).toBeInTheDocument();
    expect(screen.getByText('制造领域')).toBeInTheDocument();
  });

  it('shows error on fetch failure', async () => {
    vi.mocked(fetchWikiPages).mockRejectedValue(new Error('PG down'));
    render(<WikiHierarchyTree projectId="p1" />);
    await waitFor(() => {
      expect(screen.getByText(/PG down/)).toBeInTheDocument();
    });
  });

  it('clicking a node calls onSelectPage', async () => {
    vi.mocked(fetchWikiPages).mockResolvedValue([
      makePage('idx_1', 'index', '', '根'),
    ]);
    const onSelect = vi.fn();
    render(<WikiHierarchyTree projectId="p1" onSelectPage={onSelect} />);
    await waitFor(() => {
      expect(screen.getByText('根')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('根'));
    expect(onSelect).toHaveBeenCalledWith('idx_1');
  });
});
