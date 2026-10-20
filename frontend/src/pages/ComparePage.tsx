import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiGet } from "../api/client";
import type { ComparisonResponse } from "../api/types";
import { CountryPicker, IndicatorSelect } from "../components/Filters";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { useApi } from "../hooks/useApi";
import { useReferenceData } from "../hooks/useReferenceData";
import { SERIES_COLORS } from "../utils/chart";
import { formatAxis, formatValue } from "../utils/format";

export const MIN_COUNTRIES = 2;
export const MAX_COUNTRIES = 10;

interface CompareFilters {
  indicator: string;
  year: number | null;
  countries: string[];
}

export function ComparePage() {
  const ref = useReferenceData();
  const [filters, setFilters] = useState<CompareFilters | null>(null);

  useEffect(() => {
    if (filters || !ref.indicators?.length || !ref.countries || !ref.defaults) return;
    const indicator = ref.indicators.find((i) => i.indicator_code === ref.defaults!.indicator_code) ?? ref.indicators[0];
    const available = new Set(ref.countries.map((c) => c.country_code));
    setFilters({
      indicator: indicator.indicator_code,
      year: indicator.last_year,
      countries: ref.defaults.country_codes.filter((c) => available.has(c)).slice(0, MAX_COUNTRIES),
    });
  }, [filters, ref.indicators, ref.countries, ref.defaults]);

  const valid =
    !!filters && filters.year !== null && filters.countries.length >= MIN_COUNTRIES && filters.countries.length <= MAX_COUNTRIES;
  const comparison = useApi(
    (s) =>
      apiGet<ComparisonResponse>(
        "/api/v1/analytics/country-comparison",
        { indicator_code: filters!.indicator, year: filters!.year, country_code: filters!.countries },
        s,
      ),
    valid ? JSON.stringify(filters) : null,
  );

  if (ref.error) return <ErrorState error={ref.error} onRetry={ref.reload} />;
  if (ref.indicators && ref.indicators.length === 0) {
    return <EmptyState title="No data loaded yet">Run the pipeline once to load World Bank observations.</EmptyState>;
  }
  if (!filters || !ref.indicators || !ref.countries) return <Loading label="Loading filters…" />;

  const indicator = ref.indicators.find((i) => i.indicator_code === filters.indicator)!;
  const years: number[] = [];
  if (indicator.first_year !== null && indicator.last_year !== null) {
    for (let y = indicator.last_year; y >= indicator.first_year; y--) years.push(y);
  }
  const selectionError =
    filters.countries.length < MIN_COUNTRIES
      ? `Select at least ${MIN_COUNTRIES} countries to compare.`
      : filters.countries.length > MAX_COUNTRIES
        ? `Select at most ${MAX_COUNTRIES} countries so the chart stays readable.`
        : null;

  const data = comparison.data;
  return (
    <div className="stack">
      <section className="card stack-sm">
        <div className="filters">
          <IndicatorSelect
            indicators={ref.indicators}
            value={filters.indicator}
            onChange={(code) => {
              const next = ref.indicators!.find((i) => i.indicator_code === code)!;
              setFilters({ ...filters, indicator: code, year: next.last_year });
            }}
          />
          <label className="field" htmlFor="compare-year">
            Year
            <select id="compare-year" value={filters.year ?? ""} onChange={(e) => setFilters({ ...filters, year: Number(e.target.value) })}>
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="muted">Unit: <strong>{indicator.unit}</strong></p>
        <CountryPicker
          countries={ref.countries}
          selected={filters.countries}
          onChange={(codes) => setFilters({ ...filters, countries: codes })}
          legend={`Countries (${MIN_COUNTRIES}–${MAX_COUNTRIES})`}
        />
        {selectionError && <p className="field-error" role="alert">{selectionError}</p>}
      </section>

      {valid && (
        <section className="card">
          <h2>
            {indicator.name}, {filters.year}
          </h2>
          {comparison.loading && <Loading label="Loading comparison…" />}
          {comparison.error && <ErrorState error={comparison.error} onRetry={comparison.reload} />}
          {data && data.items.length === 0 && (
            <EmptyState title={`No values for ${data.year}`}>Try another year or indicator; the source has no data for this selection.</EmptyState>
          )}
          {data && data.items.length > 0 && (
            <div className="stack-sm">
              <figure className="chart" aria-label={`${data.indicator.name} in ${data.year} by country, sorted from highest to lowest`}>
                <div style={{ width: "100%", height: Math.max(160, data.items.length * 44) }}>
                  <ResponsiveContainer>
                    <BarChart data={data.items} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
                      <CartesianGrid stroke="var(--color-border)" horizontal={false} />
                      <XAxis type="number" tickFormatter={(v: number) => formatAxis(v, data.indicator.unit)} tick={{ fontSize: 12 }} />
                      <YAxis type="category" dataKey="country_name" width={130} tick={{ fontSize: 12 }} />
                      <Tooltip formatter={(value) => [formatValue(typeof value === "number" ? value : null, data.indicator.unit, "full"), data.indicator.name]} />
                      <Bar dataKey="value" isAnimationActive={false}>
                        {data.items.map((item, i) => (
                          <Cell key={item.country_code} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </figure>
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Comparison values (table alternative to the chart)</caption>
                  <thead>
                    <tr>
                      <th scope="col">Rank</th>
                      <th scope="col">Country</th>
                      <th scope="col" className="num">Value ({data.indicator.unit})</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item, i) => (
                      <tr key={item.country_code}>
                        <td>{i + 1}</td>
                        <td>{item.country_name}</td>
                        <td className="num" title={formatValue(item.value, data.indicator.unit, "full")}>{formatValue(item.value, data.indicator.unit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {data && data.unavailable.length > 0 && (
            <p className="notice notice-warning" role="note">
              No {data.year} value at the source for: {data.unavailable.map((c) => c.country_name).join(", ")}. These countries are left out of the
              chart instead of being shown as zero.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
