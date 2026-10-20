import type { TrendSeries } from "../api/types";

export type TrendRow = { year: number } & Record<string, number | null>;

// Distinct, colour-blind-aware series colours; series are also labelled in the legend and tooltip.
export const SERIES_COLORS = ["#1f5fae", "#d08c00", "#0f8b8d", "#a23b72", "#5b8c2a", "#6c4fb3", "#c44536", "#3d405b", "#8a6f3f", "#2a9d8f"];

/**
 * One row per year across all series. A country without a value for a year gets
 * `null`, which the line chart renders as a gap — never as 0.
 */
export function toTrendRows(series: TrendSeries[]): TrendRow[] {
  const years = new Set<number>();
  for (const s of series) for (const p of s.points) years.add(p.year);
  return [...years]
    .sort((a, b) => a - b)
    .map((year) => {
      const row: TrendRow = { year } as TrendRow;
      for (const s of series) row[s.country_code] = s.points.find((p) => p.year === year)?.value ?? null;
      return row;
    });
}

export function missingYears(series: TrendSeries, rows: TrendRow[]): number[] {
  return rows.filter((row) => row[series.country_code] === null).map((row) => row.year);
}
