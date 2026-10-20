import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { QualityLatest } from "../api/types";
import { ChecksTable } from "../components/ChecksTable";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { useApi } from "../hooks/useApi";
import { formatCount, formatDateTime } from "../utils/format";
import { qualityVerdict } from "../utils/quality";

export function QualityPage() {
  const quality = useApi((s) => apiGet<QualityLatest>("/api/v1/quality/latest", {}, s), "quality");

  if (quality.loading && !quality.data) return <Loading label="Loading quality results…" />;
  if (quality.error) return <ErrorState error={quality.error} onRetry={quality.reload} />;
  if (!quality.data) return null;
  const { run, checks } = quality.data;
  if (!run) {
    return <EmptyState title="No finished pipeline run yet">Quality results appear after the first run completes.</EmptyState>;
  }
  const verdict = qualityVerdict(run, checks);

  return (
    <div className="stack">
      <section className="card stack-sm">
        <h2>Latest finished run</h2>
        <p className="verdict">
          {verdict.status !== "none" && <StatusBadge status={verdict.status} />} <span>{verdict.label}</span>
        </p>
        <dl className="facts">
          <div>
            <dt>Run</dt>
            <dd>
              <Link to={`/runs/${run.run_id}`}>{run.run_id.slice(0, 8)}</Link>
            </dd>
          </div>
          <div>
            <dt>Run status</dt>
            <dd><StatusBadge status={run.status} /></dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>{formatDateTime(run.finished_at)}</dd>
          </div>
          <div>
            <dt>Extracted</dt>
            <dd>{formatCount(run.records_extracted)}</dd>
          </div>
          <div>
            <dt>Rejected</dt>
            <dd>{formatCount(run.records_rejected)}</dd>
          </div>
          <div>
            <dt>Null-skipped</dt>
            <dd>{formatCount(run.records_null_skipped)}</dd>
          </div>
          <div>
            <dt>Loaded</dt>
            <dd>{formatCount(run.records_loaded)}</dd>
          </div>
        </dl>
        {run.error_summary && <p className="notice notice-warning">{run.error_summary}</p>}
      </section>

      <section className="card">
        <h2>Checks</h2>
        {checks.length === 0 ? <p className="muted">This run recorded no checks.</p> : <ChecksTable checks={checks} />}
      </section>

      <section className="card stack-sm">
        <h2>How to read these results</h2>
        <ul>
          <li>
            <strong>Passed</strong>: the rule held for every row or request checked.
          </li>
          <li>
            <strong>Warning</strong>: describes the source rather than a defect. Null values are <em>missing source observations</em>: they are
            counted, skipped and never stored or shown as zero. Identical duplicate rows are dropped.
          </li>
          <li>
            <strong>Failed</strong>: malformed or invalid rows were rejected with a reason, a request failed after retries, or duplicate rows
            disagreed. Rejected rows are never loaded as trustworthy observations.
          </li>
        </ul>
        <p className="muted">
          The page shows the most recent finished run even when it failed; an older passing run is never shown in its place.
        </p>
      </section>
    </div>
  );
}
