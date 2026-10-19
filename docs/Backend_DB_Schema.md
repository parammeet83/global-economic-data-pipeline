# Backend & Database Schema

**Project:** Global Economic Data Pipeline & Analytics Dashboard  
**Version:** 1.0  
**Last updated:** 2026-10-19

## 1. Design objectives

- Preserve source identifiers and annual observations.
- Avoid duplicate records on reruns.
- Keep country and indicator metadata normalized.
- Audit every execution attempt and its quality outcomes.
- Support dashboard filters, trends, country comparisons, freshness checks, and run history.
- Use PostgreSQL constraints as the final integrity guard, not only Python checks.

## 2. Entity relationship overview

```text
countries (1) --------< economic_observations >-------- (1) indicators
                                |
                                | loaded during / associated with
                                v
                           pipeline_runs
                                |
                                +--------< data_quality_checks
```

`economic_observations` keeps a composite uniqueness constraint on country, indicator, and year. Each observation can optionally record the pipeline run that last inserted or updated it. The run table is the audit log for all execution attempts.

## 3. Tables

### 3.1 `countries`
Stores country/area metadata from the API. The ingestion layer should distinguish actual countries from aggregates if the API returns both; the first configured ingestion should explicitly exclude aggregates unless they are deliberately enabled.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `country_code` | `VARCHAR(3)` | Primary key | World Bank country/area code; uppercase |
| `name` | `TEXT` | Not null | Display name from source |
| `region` | `TEXT` | Nullable | Source region label where available |
| `income_level` | `TEXT` | Nullable | Source income-level label where available |
| `capital_city` | `TEXT` | Nullable | Optional metadata |
| `latitude` | `NUMERIC(9,6)` | Nullable | Source coordinate if useful |
| `longitude` | `NUMERIC(9,6)` | Nullable | Source coordinate if useful |
| `is_aggregate` | `BOOLEAN` | Not null, default false | Indicates aggregate rather than country; set from source metadata/aggregate response |
| `updated_at` | `TIMESTAMPTZ` | Not null | Last local metadata update |

**Indexes:** primary key is sufficient for key lookups. Consider an index on normalized name only if name search is implemented.

### 3.2 `indicators`
Describes each economic indicator. Seed the initial set from configuration and/or metadata returned by the source.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `indicator_code` | `VARCHAR(32)` | Primary key | Example: `NY.GDP.MKTP.CD` |
| `name` | `TEXT` | Not null | Display name |
| `description` | `TEXT` | Nullable | Source description |
| `unit` | `TEXT` | Nullable | Unit such as `Current US$`, `people`, or `%` |
| `source_name` | `TEXT` | Not null, default `World Bank` | Origin of data |
| `frequency` | `VARCHAR(16)` | Not null, default `annual` | Initial implementation assumes annual observations |
| `updated_at` | `TIMESTAMPTZ` | Not null | Last local metadata update |

**Initial indicators:** `NY.GDP.MKTP.CD`, `SP.POP.TOTL`, and `SL.UEM.TOTL.ZS`.

### 3.3 `pipeline_runs`
One record per pipeline execution attempt. Create the row as early as possible so failures remain visible.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `run_id` | `UUID` | Primary key | Stable execution identifier |
| `triggered_by` | `VARCHAR(32)` | Not null | `cli`, `api`, `scheduler`, or `github_action` where applicable |
| `status` | `VARCHAR(24)` | Not null; constrained to `running`, `success`, `partial_success`, `failed` | Current/final outcome |
| `started_at` | `TIMESTAMPTZ` | Not null | Execution start |
| `finished_at` | `TIMESTAMPTZ` | Nullable | Completion timestamp |
| `duration_seconds` | `NUMERIC(12,3)` | Nullable, non-negative | Total runtime |
| `countries_requested` | `INTEGER` | Not null, default 0 | Configured country count |
| `indicators_requested` | `INTEGER` | Not null, default 0 | Configured indicator count |
| `records_extracted` | `INTEGER` | Not null, default 0 | Source rows received |
| `records_transformed` | `INTEGER` | Not null, default 0 | Rows after normalization |
| `records_loaded` | `INTEGER` | Not null, default 0 | Rows inserted or updated |
| `records_rejected` | `INTEGER` | Not null, default 0 | Rows rejected by validation |
| `error_count` | `INTEGER` | Not null, default 0 | Recorded errors |
| `error_summary` | `TEXT` | Nullable | Sanitized short error summary; no secrets or stack dumps |
| `config_snapshot` | `JSONB` | Nullable | Non-secret settings relevant to reproducibility |

**Constraints:** counts and duration must be non-negative; `finished_at >= started_at` when both are present; terminal status must not remain `running` after finalization.

**Indexes:** `(started_at DESC)`, `(status, started_at DESC)`.

### 3.4 `economic_observations`
The primary analytical fact table: one row per country, indicator, and observation year.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `country_code` | `VARCHAR(3)` | FK to `countries.country_code`, not null | Country/area identifier |
| `indicator_code` | `VARCHAR(32)` | FK to `indicators.indicator_code`, not null | Indicator identifier |
| `year` | `SMALLINT` | Not null; reasonable year check | Observation year |
| `value` | `NUMERIC(24,6)` | Nullable | Source numeric value; null observations are normally not loaded into fact rows, but behavior must be explicit |
| `source_updated_at` | `TIMESTAMPTZ` | Nullable | Source's last-updated value when provided |
| `ingested_at` | `TIMESTAMPTZ` | Not null | Time this row was last successfully loaded/updated |
| `last_run_id` | `UUID` | Nullable FK to `pipeline_runs.run_id` | Run that last wrote the record |

**Primary key / unique key:** `(country_code, indicator_code, year)`.  
**Indexes:** `(indicator_code, year)`, `(country_code, year)`, and unique composite key. Do not add indexes without a query/use-case reason.

**Null policy:** World Bank APIs can return null values. The pipeline must count them for quality reporting and normally avoid treating them as real numeric observations. The chosen policy for the first release is to skip null-valued fact rows while retaining missing/null counts in the run-quality report. If the product later needs explicit missing observations, change the model deliberately rather than encoding missing as zero.

**Upsert policy:** on conflict of `(country_code, indicator_code, year)`, update `value`, `source_updated_at`, `ingested_at`, and `last_run_id` only when appropriate. The operation must be idempotent and tested.

### 3.5 `data_quality_checks`
Stores check-level outcomes for a pipeline run.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `quality_check_id` | `BIGINT` | Primary key, generated | Internal ID |
| `run_id` | `UUID` | FK to `pipeline_runs.run_id`, not null | Owning run |
| `check_name` | `VARCHAR(100)` | Not null | Stable machine-readable check name |
| `status` | `VARCHAR(16)` | Not null, e.g. `passed`, `warning`, `failed` | Outcome |
| `checked_at` | `TIMESTAMPTZ` | Not null | Check time |
| `records_checked` | `INTEGER` | Not null, default 0 | Number assessed |
| `records_failed` | `INTEGER` | Not null, default 0 | Number failing |
| `details` | `JSONB` | Nullable | Counts, thresholds, sanitized details |

**Indexes:** `(run_id)`, `(check_name, checked_at DESC)`.

Potential checks include `required_fields_present`, `year_in_range`, `numeric_value`, `unique_business_key`, `unexpected_duplicate_count`, `null_value_rate`, and `api_page_count_consistent`.

## 4. Rejected-row handling

For the first release, do not persist full raw payloads in the main observation table. Record rejected-row counts and sanitized examples/reasons in the quality report. If storing rejected records in PostgreSQL is required later, add a dedicated `rejected_records` table with strict size limits, no secret-bearing payloads, and retention rules. Avoid putting unbounded API payloads into `pipeline_runs.error_summary`.

## 5. Migration strategy

- Use Alembic for version-controlled schema changes.
- Generate an initial migration for all tables, constraints, foreign keys, and indexes.
- Review generated migration code before applying it.
- Apply with a documented command (for example, `alembic upgrade head`).
- Never rely on an undocumented manual pgAdmin change as the only source of schema truth.
- If seed records are added, make the seed operation safe to re-run.

## 6. Suggested SQL constraints

Use PostgreSQL constraints equivalent to these rules (final syntax belongs in the migration):

```sql
CHECK (year >= 1900 AND year <= 2200)
CHECK (records_extracted >= 0)
CHECK (records_transformed >= 0)
CHECK (records_loaded >= 0)
CHECK (records_rejected >= 0)
CHECK (error_count >= 0)
CHECK (status IN ('running', 'success', 'partial_success', 'failed'))
UNIQUE (country_code, indicator_code, year)
```

The year check is a broad defensive bound, not a claim that every indicator exists for those years. More restrictive validation uses the configured request window and source metadata.

## 7. Read patterns supported

- KPI summary: count distinct countries, indicators, observation rows, latest successful load time, latest run status.
- Trend chart: `indicator_code`, selected `country_code` values, and year range; return ordered annual values.
- Country comparison: one indicator and year, multiple country codes.
- Observation table: filter by country, indicator and year range; server-side pagination and stable sort.
- Pipeline history: newest runs ordered by `started_at` descending.
- Latest quality status: quality checks joined to most recent terminal run.

## 8. Database access rules

- Create a SQLAlchemy session per request/task and close it deterministically.
- Use transaction contexts for writes.
- Never construct SQL using user-provided string concatenation.
- Use bound parameters and validated filters.
- Keep database credentials in an environment variable and ignore `.env` in Git.
- Use a dedicated local application database/user for development where practical, rather than hard-coding the PostgreSQL superuser.
