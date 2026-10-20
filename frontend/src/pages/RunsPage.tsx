import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, apiGet, apiPost } from "../api/client";
import type { Page, RunAccepted, RunSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Pagination } from "../components/Filters";
import { RunsTable } from "../components/RunsTable";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { useApi } from "../hooks/useApi";
import { useRunPolling } from "../hooks/useRunPolling";
import { formatCount, shortId } from "../utils/format";

const PAGE_SIZE = 20;

type TriggerMessage = { kind: "error" | "info"; text: string; runId?: string } | null;

export function RunsPage() {
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const runs = useApi((s) => apiGet<Page<RunSummary>>("/api/v1/runs", { page, page_size: PAGE_SIZE }, s), `runs:${page}:${refresh}`);

  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [message, setMessage] = useState<TriggerMessage>(null);
  const polling = useRunPolling(activeRunId);

  useEffect(() => {
    if (polling.finished) setRefresh((n) => n + 1); // refresh history once the run ends
  }, [polling.finished]);

  const start = useCallback(async () => {
    setConfirming(false);
    setStarting(true);
    setMessage(null);
    try {
      const accepted = await apiPost<RunAccepted>("/api/v1/pipeline/run");
      setActiveRunId(accepted.run_id);
      setRefresh((n) => n + 1);
    } catch (err) {
      const error = err instanceof ApiError ? err : null;
      if (error?.status === 409) {
        const runId = typeof error.body?.run_id === "string" ? error.body.run_id : undefined;
        setMessage({ kind: "info", text: "A pipeline run is already in progress. Wait for it to finish before starting another.", runId });
      } else if (error?.status === 403) {
        setMessage({ kind: "error", text: error.message });
      } else {
        setMessage({ kind: "error", text: error?.message ?? "The run could not be started." });
      }
    } finally {
      setStarting(false);
    }
  }, []);

  const busy = starting || (!!activeRunId && !polling.finished && !polling.timedOut);
  const active = polling.run;

  return (
    <div className="stack">
      <section className="card stack-sm">
        <div className="toolbar">
          <div>
            <h2>Run the pipeline</h2>
            <p className="muted">Local/demo control: fetches World Bank data and upserts it into PostgreSQL.</p>
          </div>
          <button type="button" className="button" onClick={() => setConfirming(true)} disabled={busy}>
            {starting ? "Starting…" : busy ? "Run in progress…" : "Run pipeline"}
          </button>
        </div>

        {message && (
          <p className={`notice ${message.kind === "error" ? "notice-error" : "notice-info"}`} role="alert">
            {message.text} {message.runId && <Link to={`/runs/${message.runId}`}>View the running run</Link>}
          </p>
        )}

        {activeRunId && (
          <div className="notice notice-info" role="status" aria-live="polite">
            Run <Link to={`/runs/${activeRunId}`}>{shortId(activeRunId)}</Link>:{" "}
            {active ? <StatusBadge status={active.status} /> : "starting…"}
            {active && active.status !== "running" && (
              <span>
                {" "}
                · loaded {formatCount(active.records_loaded)} · inserted {formatCount(active.records_inserted)} · value changed{" "}
                {formatCount(active.records_value_changed)}
              </span>
            )}
            {polling.timedOut && <span> · still running after 10 minutes — check Pipeline Runs later.</span>}
            {polling.error && <span> · status check failed: {polling.error.message}</span>}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Run history</h2>
        {runs.loading && !runs.data && <Loading />}
        {runs.error && <ErrorState error={runs.error} onRetry={runs.reload} />}
        {runs.data && runs.data.total === 0 && (
          <EmptyState title="No pipeline runs yet">Start one above or run <code>python -m src.pipeline.cli run</code>.</EmptyState>
        )}
        {runs.data && runs.data.total > 0 && (
          <>
            <RunsTable runs={runs.data.items} caption="Pipeline run history, newest first" />
            <Pagination page={page} pageSize={PAGE_SIZE} total={runs.data.total} onPage={setPage} />
          </>
        )}
      </section>

      {confirming && (
        <ConfirmDialog title="Run the pipeline now?" confirmLabel="Start run" onConfirm={start} onCancel={() => setConfirming(false)}>
          <p>This will:</p>
          <ul>
            <li>request indicator data from the public World Bank API, and</li>
            <li>write (upsert) observations, run history and quality results to the database.</li>
          </ul>
          <p className="muted">Only one run can execute at a time.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
