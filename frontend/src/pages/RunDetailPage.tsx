import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client";
import type { RunDetail } from "../api/types";
import { ChecksTable } from "../components/ChecksTable";
import { ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { useApi } from "../hooks/useApi";
import { useRunPolling } from "../hooks/useRunPolling";
import { TRIGGER_LABELS, elapsedSince, formatCount, formatDateTime, formatDuration } from "../utils/format";

const COUNTS: { key: keyof RunDetail; label: string; help: string }[] = [
  { key: "records_extracted", label: "Extracted", help: "Rows received from series that were fetched successfully" },
  { key: "records_rejected", label: "Rejected", help: "Rows that failed validation (see checks)" },
  { key: "records_null_skipped", label: "Null-skipped", help: "Source gaps: valid rows with no value, never stored as 0" },
  { key: "records_duplicates_dropped", label: "Duplicates dropped", help: "Extra copies of a country/indicator/year" },
  { key: "records_transformed", label: "Load-ready", help: "Extracted − rejected − null-skipped − duplicates" },
  { key: "records_loaded", label: "Loaded", help: "Rows written by the committed upsert" },
  { key: "records_inserted", label: "Inserted", help: "Rows that did not exist before this run" },
  { key: "records_value_changed", label: "Value changed", help: "Existing rows whose value changed. 0 inserted and 0 changed on a rerun means the load is idempotent" },
];

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const detail = useApi((s) => apiGet<RunDetail>(`/api/v1/runs/${runId}`, {}, s), `run:${runId}`);
  const polling = useRunPolling(detail.data?.status === "running" ? runId : null);
  const [copied, setCopied] = useState(false);

  if (detail.loading && !detail.data) return <Loading label="Loading run…" />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const run = polling.run ?? detail.data;
  if (!run) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(run.run_id);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="stack">
      <p>
        <Link to="/runs">← All runs</Link>
      </p>
      <section className="card stack-sm">
        <div className="toolbar">
          <h2>
            Run <code>{run.run_id}</code>
          </h2>
          <button type="button" className="button secondary" onClick={copy}>
            {copied ? "Copied" : "Copy run ID"}
          </button>
        </div>
        <dl className="facts">
          <div>
            <dt>Status</dt>
            <dd><StatusBadge status={run.status} /></dd>
          </div>
          <div>
            <dt>Trigger</dt>
            <dd>{TRIGGER_LABELS[run.triggered_by] ?? run.triggered_by}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{formatDateTime(run.started_at)}</dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>{formatDateTime(run.finished_at)}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{run.status === "running" ? `${formatDuration(elapsedSince(run.started_at))} elapsed` : formatDuration(run.duration_seconds)}</dd>
          </div>
          <div>
            <dt>Requested</dt>
            <dd>
              {run.countries_requested} countries × {run.indicators_requested} indicators
            </dd>
          </div>
          <div>
            <dt>Errors</dt>
            <dd>{formatCount(run.error_count)}</dd>
          </div>
        </dl>
        {run.status === "running" && <p className="muted">This page refreshes every 3 seconds until the run finishes.</p>}
        {run.error_summary && (
          <div className={`notice ${run.status === "failed" ? "notice-error" : "notice-warning"}`}>
            <strong>Summary:</strong> {run.error_summary}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Stage counts</h2>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Record counts for this run</caption>
            <tbody>
              {COUNTS.map((c) => (
                <tr key={c.key}>
                  <th scope="row">{c.label}</th>
                  <td className="num">{formatCount(run[c.key] as number)}</td>
                  <td className="muted">{c.help}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Quality checks</h2>
        {run.checks.length === 0 ? <p className="muted">No checks were recorded for this run yet.</p> : <ChecksTable checks={run.checks} />}
      </section>
    </div>
  );
}
