import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import type { Observation, Page, TrendResponse } from "../api/types";
import { CountryPicker, IndicatorSelect, Pagination, YearInput } from "../components/Filters";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { TrendChart } from "../components/TrendChart";
import { useApi } from "../hooks/useApi";
import { useReferenceData } from "../hooks/useReferenceData";
import { MISSING, formatDateTime, formatValue } from "../utils/format";

export interface ExploreFilters {
  indicator: string;
  countries: string[];
  startYear: string;
  endYear: string;
}

export const MAX_CHART_COUNTRIES = 10;
const PAGE_SIZE = 25;

/** Returns an error message for invalid filters, or null. Invalid filters are never sent. */
export function validateFilters(f: ExploreFilters): string | null {
  if (!f.indicator) return "Choose an indicator.";
  if (f.countries.length === 0) return "Select at least one country.";
  if (f.countries.length > MAX_CHART_COUNTRIES) return `Select at most ${MAX_CHART_COUNTRIES} countries.`;
  const start = f.startYear === "" ? null : Number(f.startYear);
  const end = f.endYear === "" ? null : Number(f.endYear);
  for (const year of [start, end]) {
    if (year !== null && (!Number.isInteger(year) || year < 1900 || year > 2200)) return "Years must be whole numbers between 1900 and 2200.";
  }
  if (start !== null && end !== null && start > end) return "Start year must be less than or equal to end year.";
  return null;
}

type SortKey = "year" | "country_code" | "value";

export function ExplorePage() {
  const ref = useReferenceData();
  const [draft, setDraft] = useState<ExploreFilters | null>(null);
  const [applied, setApplied] = useState<ExploreFilters | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ by: SortKey; order: "asc" | "desc" }>({ by: "year", order: "desc" });

  // Initialise filters once from the backend's configured defaults and the indicator's coverage.
  useEffect(() => {
    if (draft || !ref.indicators || !ref.countries || !ref.defaults || ref.indicators.length === 0) return;
    const indicator = ref.indicators.find((i) => i.indicator_code === ref.defaults!.indicator_code) ?? ref.indicators[0];
    const available = new Set(ref.countries.map((c) => c.country_code));
    const initial: ExploreFilters = {
      indicator: indicator.indicator_code,
      countries: ref.defaults.country_codes.filter((c) => available.has(c)).slice(0, MAX_CHART_COUNTRIES),
      startYear: indicator.first_year?.toString() ?? "",
      endYear: indicator.last_year?.toString() ?? "",
    };
    setDraft(initial);
    setApplied(validateFilters(initial) ? null : initial);
  }, [draft, ref.indicators, ref.countries, ref.defaults]);

  const params = applied && {
    indicator_code: applied.indicator,
    country_code: applied.countries,
    start_year: applied.startYear,
    end_year: applied.endYear,
  };
  const appliedKey = applied ? JSON.stringify(applied) : null;
  const trend = useApi((s) => apiGet<TrendResponse>("/api/v1/analytics/trend", params!, s), appliedKey);
  const table = useApi(
    (s) =>
      apiGet<Page<Observation>>(
        "/api/v1/observations",
        { ...params!, page, page_size: PAGE_SIZE, sort_by: sort.by, sort_order: sort.order },
        s,
      ),
    appliedKey && `${appliedKey}:${page}:${sort.by}:${sort.order}`,
  );

  if (ref.error) return <ErrorState error={ref.error} onRetry={ref.reload} />;
  if (ref.loading && !draft) return <Loading label="Loading filters…" />;
  if (ref.indicators && ref.indicators.length === 0) {
    return <EmptyState title="No data loaded yet">Run the pipeline once to load World Bank observations.</EmptyState>;
  }
  if (!draft || !ref.indicators || !ref.countries) return <Loading />;

  const indicator = ref.indicators.find((i) => i.indicator_code === draft.indicator);
  const appliedIndicator = ref.indicators.find((i) => i.indicator_code === applied?.indicator);
  const names = new Map(ref.countries.map((c) => [c.country_code, c.name]));

  const apply = () => {
    const error = validateFilters(draft);
    setFormError(error);
    if (error) return;
    setApplied({ ...draft });
    setPage(1);
  };

  const changeSort = (by: SortKey) => {
    setSort((s) => ({ by, order: s.by === by && s.order === "desc" ? "asc" : "desc" }));
    setPage(1);
  };
  const sortLabel = (by: SortKey) => (sort.by === by ? (sort.order === "desc" ? " ↓" : " ↑") : "");
  const ariaSort = (by: SortKey) => (sort.by === by ? (sort.order === "desc" ? "descending" : "ascending") : "none");

  return (
    <div className="stack">
      <section className="card">
        <form
          className="stack-sm"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
          noValidate
        >
          <div className="filters">
            <IndicatorSelect indicators={ref.indicators} value={draft.indicator} onChange={(code) => setDraft({ ...draft, indicator: code })} />
            <YearInput id="start-year" label="Start year" value={draft.startYear} onChange={(v) => setDraft({ ...draft, startYear: v })} />
            <YearInput id="end-year" label="End year" value={draft.endYear} onChange={(v) => setDraft({ ...draft, endYear: v })} />
            <button type="submit" className="button">Apply filters</button>
          </div>
          {indicator && (
            <p className="muted">
              Unit: <strong>{indicator.unit}</strong> · data available {indicator.first_year ?? MISSING}–{indicator.last_year ?? MISSING}
            </p>
          )}
          <CountryPicker countries={ref.countries} selected={draft.countries} onChange={(codes) => setDraft({ ...draft, countries: codes })} legend={`Countries (1–${MAX_CHART_COUNTRIES})`} />
          {formError && (
            <p className="field-error" role="alert">
              {formError}
            </p>
          )}
        </form>
      </section>

      {applied && appliedIndicator && (
        <div className="chips" aria-label="Active filters">
          <span className="chip">{appliedIndicator.name}</span>
          <span className="chip">
            {applied.startYear || "earliest"}–{applied.endYear || "latest"}
          </span>
          {applied.countries.map((c) => (
            <span key={c} className="chip">{names.get(c) ?? c}</span>
          ))}
        </div>
      )}

      <section className="card">
        <h2>Trend</h2>
        {trend.loading && <Loading label="Loading trend…" />}
        {trend.error && <ErrorState error={trend.error} onRetry={trend.reload} />}
        {trend.data && trend.data.series.every((s) => s.points.length === 0) && (
          <EmptyState title="No observations match these filters">Try a wider year range or other countries.</EmptyState>
        )}
        {trend.data && trend.data.series.some((s) => s.points.length > 0) && <TrendChart trend={trend.data} />}
      </section>

      <section className="card">
        <div className="toolbar">
          <h2>Observations</h2>
          {table.data && <span className="muted">{table.data.total.toLocaleString("en-US")} matching rows</span>}
        </div>
        {table.loading && <Loading label="Loading observations…" />}
        {table.error && <ErrorState error={table.error} onRetry={table.reload} />}
        {table.data && table.data.total === 0 && <EmptyState title="No observations match these filters" />}
        {table.data && table.data.total > 0 && (
          <>
            <div className="table-wrap">
              <table>
                <caption className="sr-only">Observations for the selected filters (table alternative to the chart)</caption>
                <thead>
                  <tr>
                    <th scope="col" aria-sort={ariaSort("year")}>
                      <button type="button" className="link-button" onClick={() => changeSort("year")}>Year{sortLabel("year")}</button>
                    </th>
                    <th scope="col" aria-sort={ariaSort("country_code")}>
                      <button type="button" className="link-button" onClick={() => changeSort("country_code")}>Country{sortLabel("country_code")}</button>
                    </th>
                    <th scope="col">Indicator</th>
                    <th scope="col" className="num" aria-sort={ariaSort("value")}>
                      <button type="button" className="link-button" onClick={() => changeSort("value")}>Value{sortLabel("value")}</button>
                    </th>
                    <th scope="col">Loaded</th>
                  </tr>
                </thead>
                <tbody>
                  {table.data.items.map((o) => (
                    <tr key={`${o.country_code}-${o.indicator_code}-${o.year}`}>
                      <td>{o.year}</td>
                      <td>{o.country_name}</td>
                      <td>{o.indicator_name}</td>
                      <td className="num" title={formatValue(o.value, o.unit, "full")}>{formatValue(o.value, o.unit)}</td>
                      <td>{formatDateTime(o.ingested_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={table.data.total} onPage={setPage} />
            <p className="muted">Years without a source value are not listed; they are never shown as 0.</p>
          </>
        )}
      </section>
    </div>
  );
}
