/**
 * @module useApi
 * @description 通用异步数据请求 Hook。
 * 支持 AbortController 取消 — 组件卸载时自动中止请求，防止内存泄漏。
 * fetcher 可接收 AbortSignal 传给 fetch()。
 */
import { useState, useEffect, useCallback, useRef } from 'react';

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useApi<T>(
  fetcher: (signal?: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trigger, setTrigger] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const refetch = useCallback(() => setTrigger((t) => t + 1), []);

  useEffect(() => {
    // 中止上一次请求
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    fetcher(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // 忽略取消错误
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger, ...deps]);

  return { data, loading, error, refetch };
}

export default useApi;
