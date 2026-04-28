/**
 * 搜索输入框组件
 *
 * 支持防抖输入（默认 300ms）和回车即时搜索，
 * 带搜索图标和清除按钮，可通过 externalValue 受控。
 */

import React, { useState, useEffect, useRef } from 'react';
import { Search, X } from 'lucide-react';

/** 搜索输入框属性 */
interface SearchInputProps {
  value?: string;
  placeholder?: string;
  onSearch: (query: string) => void;
  debounceMs?: number;
  autoFocus?: boolean;
  className?: string;
}

export const SearchInput: React.FC<SearchInputProps> = ({
  value: externalValue,
  placeholder = '搜索...',
  onSearch,
  debounceMs = 300,
  autoFocus = false,
  className = '',
}) => {
  const [value, setValue] = useState(externalValue ?? '');
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (externalValue !== undefined) setValue(externalValue);
  }, [externalValue]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setValue(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onSearch(v), debounceMs);
  };

  const handleClear = () => {
    setValue('');
    onSearch('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (timerRef.current) clearTimeout(timerRef.current);
      onSearch(value);
    }
  };

  return (
    <div className={`relative ${className}`}>
      <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted">
        <Search size={16} />
      </div>
      <input
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="w-full glass-surface rounded-lg pl-10 pr-10 py-2.5 text-sm text-th-text-primary focus:outline-none"
      />
      {value && (
        <button
          onClick={handleClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
          aria-label="清除搜索"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
};

export default SearchInput;
