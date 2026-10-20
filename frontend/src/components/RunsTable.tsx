import { Link } from "react-router-dom";
import type { RunSummary } from "../api/types";
import { TRIGGER_LABELS, elapsedSince, formatCount, formatDateTime, formatDuration, shortId } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

export function RunsTable({ runs, caption }: { runs: RunSummary[]; caption: string }) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">Run</th>
            <th scope="col">Started</th>
            <th scope="col">Duration</th>
            <th scope="col">Trigger</th>
            <th scope="col" className="num">Extracted</th>
            <th scope="col" className="num">Loaded</th>
            <th scope="col" className="num">Rejected</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td><StatusBadge status={run.status} /></td>
              <td>
                <Link to={`/runs/${run.run_id}`} title={run.run_id}>
                  {shortId(run.run_id)}
                </Link>
              </td>
              <td>{formatDateTime(run.started_at)}</td>
              <td>
                {run.status === "running"
                  ? `${formatDuration(elapsedSince(run.started_at))} elapsed`
                  : formatDuration(run.duration_seconds)}
              </td>
              <td>{TRIGGER_LABELS[run.triggered_by] ?? run.triggered_by}</td>
              <td className="num">{formatCount(run.records_extracted)}</td>
              <td className="num">{formatCount(run.records_loaded)}</td>
              <td className="num">{formatCount(run.records_rejected)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
