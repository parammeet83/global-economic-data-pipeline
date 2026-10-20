// Test fixtures only; never rendered in the running application.
import type { DashboardSummary, QualityCheck, QualityLatest, RunSummary, TrendResponse } from "../api/types";

export function run(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "11111111-2222-3333-4444-555555555555",
    status: "success",
    triggered_by: "cli",
    started_at: "2026-10-20T07:26:37Z",
    finished_at: "2026-10-20T07:26:41Z",
    duration_seconds: 3.8,
    records_extracted: 8,
    records_rejected: 0,
    records_null_skipped: 0,
    records_duplicates_dropped: 0,
    records_transformed: 8,
    records_loaded: 8,
    records_inserted: 8,
    records_value_changed: 0,
    error_count: 0,
    error_summary: null,
    ...overrides,
  };
}

export function check(name: string, status: QualityCheck["status"] = "passed"): QualityCheck {
  return { check_name: name, status, checked_at: "2026-10-20T07:26:41Z", records_checked: 8, records_failed: status === "passed" ? 0 : 1, details: null };
}

export function summary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    countries: 2,
    indicators: 1,
    observations: 3,
    latest_successful_load_at: "2026-10-20T07:26:41Z",
    latest_run: run(),
    defaults: { indicator_code: "SP.POP.TOTL", country_codes: ["AAA", "BBB"] },
    ...overrides,
  };
}

export const trend: TrendResponse = {
  indicator: { indicator_code: "SP.POP.TOTL", name: "Population, total", unit: "people" },
  start_year: null,
  end_year: null,
  series: [
    { country_code: "AAA", country_name: "Country A", points: [{ year: 2019, value: 100 }, { year: 2020, value: 110 }] },
    { country_code: "BBB", country_name: "Country B", points: [{ year: 2019, value: 50 }] },
  ],
};

export const quality: QualityLatest = { run: run(), checks: [check("numeric_value"), check("null_value_rate")] };
