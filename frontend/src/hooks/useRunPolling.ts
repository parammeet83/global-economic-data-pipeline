import { useEffect, useState } from "react";
import { ApiError, apiGet } from "../api/client";
import type { RunDetail } from "../api/types";

export const POLL_INTERVAL_MS = 3000;
export const POLL_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Polls GET /api/v1/runs/{runId} (D-24) until the run reaches a terminal status,
 * the 10-minute timeout passes, or polling is disabled.
 */
export function useRunPolling(runId: string | null) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!runId) return;
    setRun(null);
    setTimedOut(false);
    setError(null);
    const started = Date.now();
    let stopped = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const detail = await apiGet<RunDetail>(`/api/v1/runs/${runId}`);
        if (stopped) return;
        setRun(detail);
        setError(null);
        if (detail.status !== "running") return;
      } catch (err) {
        if (stopped) return;
        setError(err instanceof ApiError ? err : null);
      }
      if (Date.now() - started >= POLL_TIMEOUT_MS) {
        setTimedOut(true);
        return;
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    void poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [runId]);

  const finished = !!run && run.status !== "running";
  return { run, finished, timedOut, error };
}
