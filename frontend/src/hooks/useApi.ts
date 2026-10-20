import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Runs `fetcher` when `key` changes (or on `reload`) and tracks loading/error/data.
 * Pass `key = null` to skip fetching (e.g. while required filters are incomplete).
 */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, key: string | null): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(key !== null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (key === null) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetcher(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setData(null);
        setError(err instanceof ApiError ? err : new ApiError("http", 0, "unknown_error", "Unexpected error."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // `key` encodes every request input, so `fetcher` is intentionally not a dependency.
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, error, loading, reload };
}
