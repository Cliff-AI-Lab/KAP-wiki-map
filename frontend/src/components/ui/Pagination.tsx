/**
 * 分页组件
 *
 * 自动计算页码显示逻辑：
 * - 总页数 <= 7 时全量展示
 * - 超过 7 页时显示首尾页 + 当前页前后各 1 页 + 省略号
 */

import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/** 分页属性 */
interface PaginationProps {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({ page, pages, onPageChange }) => {
  if (pages <= 1) return null;

  const pageNumbers: (number | '...')[] = [];
  if (pages <= 7) {
    for (let i = 1; i <= pages; i++) pageNumbers.push(i);
  } else {
    pageNumbers.push(1);
    if (page > 3) pageNumbers.push('...');
    for (let i = Math.max(2, page - 1); i <= Math.min(pages - 1, page + 1); i++) {
      pageNumbers.push(i);
    }
    if (page < pages - 2) pageNumbers.push('...');
    pageNumbers.push(pages);
  }

  return (
    <div className="flex items-center justify-center gap-1">
      <button
        className="btn-ghost rounded-lg p-2 disabled:opacity-30"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="上一页"
      >
        <ChevronLeft size={16} />
      </button>

      {pageNumbers.map((n, i) =>
        n === '...' ? (
          <span key={`ellipsis-${i}`} className="px-2 text-muted text-sm">
            ...
          </span>
        ) : (
          <button
            key={n}
            className={`rounded-lg px-3 py-1.5 text-sm transition-all duration-150 ${
              n === page
                ? 'btn-gradient'
                : 'btn-ghost'
            }`}
            onClick={() => onPageChange(n)}
          >
            {n}
          </button>
        ),
      )}

      <button
        className="btn-ghost rounded-lg p-2 disabled:opacity-30"
        disabled={page >= pages}
        onClick={() => onPageChange(page + 1)}
        aria-label="下一页"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  );
};

export default Pagination;
