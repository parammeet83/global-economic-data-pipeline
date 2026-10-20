// Mirrors backend/src/api/schemas.py. Missing observations are absent, never 0.

export type RunStatus = "running" | "success" | "partial_success" | "failed";
export type CheckStatus = "passed" | "warning" | "failed";
export type TriggerType = "cli" | "api" | "scheduler";

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  triggered_by: TriggerType;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  records_extracted: number;
  records_rejected: number;
  records_null_skipped: number;
  records_duplicates_dropped: number;
  records_transformed: number;
  records_loaded: number;
  records_inserted: number;
  records_value_changed: number;
  error_count: number;
  error_summary: string | null;
}

export interface QualityCheck {
  check_name: string;
  status: CheckStatus;
  checked_at: string;
  records_checked: number;
  records_failed: number;
  details: Record<string, unknown> | null;
}

export interface RunDetail extends RunSummary {
  countries_requested: number;
  indicators_requested: number;
  config_snapshot: Record<string, unknown> | null;
  checks: QualityCheck[];
}

export interface DashboardSummary {
  countries: number;
  indicators: number;
  observations: number;
  latest_successful_load_at: string | null;
  latest_run: RunSummary | null;
  defaults: { indicator_code: string; country_codes: string[] };
}

export interface Indicator {
  indicator_code: string;
  name: string;
  description: string | null;
  unit: string;
  source_name: string;
  frequency: string;
  observation_count: number;
  first_year: number | null;
  last_year: number | null;
}

export interface Country {
  country_code: string;
  name: string;
  region: string | null;
  income_level: string | null;
}

export interface Observation {
  country_code: string;
  country_name: string;
  indicator_code: string;
  indicator_name: string;
  year: number;
  value: number;
  unit: string;
  ingested_at: string;
}

export interface IndicatorRef {
  indicator_code: string;
  name: string;
  unit: string;
}

export interface TrendSeries {
  country_code: string;
  country_name: string;
  points: { year: number; value: number }[];
}

export interface TrendResponse {
  indicator: IndicatorRef;
  start_year: number | null;
  end_year: number | null;
  series: TrendSeries[];
}

export interface ComparisonResponse {
  indicator: IndicatorRef;
  year: number;
  items: { country_code: string; country_name: string; value: number }[];
  unavailable: { country_code: string; country_name: string }[];
}

export interface QualityLatest {
  run: RunSummary | null;
  checks: QualityCheck[];
}

export interface RunAccepted {
  run_id: string;
  status: "running";
  status_url: string;
}

export interface Health {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
}
