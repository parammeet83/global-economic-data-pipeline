import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { DashboardSummary, Page, QualityLatest, RunSummary, TrendResponse } from "../api/types";
import { KpiCard } from "../components/KpiCard";
import { RunsTable } from "../components/RunsTable";
import { EmptyState, ErrorState, Loading, SkeletonBlock } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { TrendChart } from "../components/TrendChart";
import { useApi } from "../hooks/useApi";
import { STATUS_LABELS, formatCount, formatDate, formatDateTime, formatTime } from "../utils/format";
import { qualityVerdict } from "../utils/quality";

export function OverviewPage() {
  const summary = useApi((s) => apiGet<DashboardSummary>("/api/v1/dashboard/summary", {}, s), "summary");
  const quality = useApi((s) => apiGet<QualityLatest>("/api/v1/quality/latest", {}, s), "quality");
  const runs = useApi((s) => apiGet<Page<RunSummary>>("/api/v1/runs", { page_size: 5 }, s), "runs");

  const data = summary.data;
  const hasData = !!data && data.observations > 0;
  const defaults = data?.defaults;
  const trend = useApi(
    (s) =>
      apiGet<TrendResponse>(
        "/api/v1/analytics/trend",
        { indicator_code: defaults!.indicator_code, country_code: defaults!.country_codes },
        s,
      ),
    hasData && defaults ? `trend:${defaults.indicator_code}:${defaults.country_codes.join(",")}` : null,
  );

  if (summary.loading && !data) {
    return (
      <div className="stack">
        <div className="kpi-grid">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonBlock key={i} height={96} />
          ))}
        </div>
        <Loading label="Loading dashboard…" />
      </div>
    );
  }
  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  if (!data) return null;

  if (!hasData) {
    return (
      <EmptyState title="No observations loaded yet">
        <p>The database is reachable but empty. Load real World Bank data by running the pipeline once:</p>
        <pre>
          cd backend{"\n"}python -m src.pipeline.cli run
        </pre>
        <p>
          Or start a run from <Link to="/runs">Pipeline Runs</Link>.
        </p>
      </EmptyState>
    );
  }

  const latest = data.latest_run;
  const verdict = quality.data ? qualityVerdict(quality.data.run, quality.data.checks) : null;

  return (
    <div className="stack">
      {latest?.status === "failed" && (
        <div className="notice notice-error" role="alert">
          The most recent pipeline run failed. Data from earlier successful runs is still shown.{" "}
          <Link to={`/runs/${latest.run_id}`}>View run details</Link>
        </div>
      )}

      <section className="kpi-grid" aria-label="Key figures">
        <KpiCard label="Countries" value={formatCount(data.countries)} context="with observations" />
        <KpiCard label="Indicators" value={formatCount(data.indicators)} context="with observations" />
        <KpiCard label="Observations" value={formatCount(data.observations)} context="country × indicator × year" />
        <KpiCard
          label="Last successful load"
          value={formatDate(data.latest_successful_load_at)}
          context={[
            data.latest_successful_load_at ? `at ${formatTime(data.latest_successful_load_at)}` : null,
            latest ? `latest run: ${STATUS_LABELS[latest.status].toLowerCase()}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        />
      </section>

      <section className="card">
        <h2>Trend preview</h2>
        {trend.loading && <Loading label="Loading trend…" />}
        {trend.error && <ErrorState error={trend.error} onRetry={trend.reload} />}
        {trend.data && <TrendChart trend={trend.data} height={300} />}
        <p className="muted">
          Default indicator and countries come from the backend configuration. <Link to="/explore">Explore all data</Link>.
        </p>
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Recent pipeline runs</h2>
          {runs.loading && <Loading />}
          {runs.error && <ErrorState error={runs.error} onRetry={runs.reload} />}
          {runs.data && runs.data.items.length === 0 && <EmptyState title="No runs recorded yet" />}
          {runs.data && runs.data.items.length > 0 && <RunsTable runs={runs.data.items} caption="Five most recent pipeline runs" />}
          <p>
            <Link to="/runs">All runs</Link>
          </p>
        </section>

        <section className="card">
          <h2>Latest data quality</h2>
          {quality.loading && <Loading />}
          {quality.error && <ErrorState error={quality.error} onRetry={quality.reload} />}
          {quality.data && verdict && (
            <div className="stack-sm">
              <p className="verdict">
                {verdict.status === "none" ? verdict.label : <StatusBadge status={verdict.status} />}{" "}
                {verdict.status !== "none" && <span>{verdict.label}</span>}
              </p>
              {quality.data.run && (
                <p className="muted">
                  {quality.data.checks.filter((c) => c.status === "passed").length} of {quality.data.checks.length} checks passed · run{" "}
                  <Link to={`/runs/${quality.data.run.run_id}`}>{quality.data.run.run_id.slice(0, 8)}</Link> finished{" "}
                  {formatDateTime(quality.data.run.finished_at)}
                </p>
              )}
              <Link to="/quality">Quality details</Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
