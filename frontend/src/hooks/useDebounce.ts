/**
 * @module useDebounce
 * @description 值防抖 Hook。
 * 当输入值在指定延迟时间内不再变化时，才更新返回值。
 * 常用于搜索输入框，避免每次按键都触发请求。
 */
import { useState, useEffect } from 'react';

/**
 * 防抖 Hook：延迟 delayMs 毫秒后才更新返回值。
 * @param value - 需要防抖的原始值
 * @param delayMs - 防抖延迟（毫秒），默认 300ms
 */
export function useDebounce<T>(value: T, delayMs: number = 300): T {
  const [debounced, setDebounced] = useState(value); // 防抖后的值

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

export default useDebounce;
