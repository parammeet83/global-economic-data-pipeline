# Backend & Database Schema

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Version:** 1.1
- **Last updated:** 2026-10-19
- **Decisions:** changes from v1.0 are explained in `DECISIONS.md` (referenced as `D-xx`).

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

`economic_observations` uses a composite primary key on country, indicator, and year. Each observation records the pipeline run that last inserted or updated it. The run table is the audit log for all execution attempts.

## 3. Tables

### 3.1 `countries`
Stores country metadata from the API's `country/{codes}` endpoint, keyed by **ISO-3** code (D-08). The first release loads countries only: a configured code that the source reports as an aggregate (region "Aggregates") is a configuration error. `is_aggregate` is kept so aggregates can be enabled deliberately later.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `country_code` | `VARCHAR(3)` | Primary key; `CHECK (country_code ~ '^[A-Z]{3}$')` | World Bank ISO-3 country code; uppercase |
| `name` | `TEXT` | Not null | Display name from source |
| `region` | `TEXT` | Nullable | Source region label where available |
| `income_level` | `TEXT` | Nullable | Source income-level label where available |
| `is_aggregate` | `BOOLEAN` | Not null, default false | Indicates aggregate rather than country; set from source metadata |
| `updated_at` | `TIMESTAMPTZ` | Not null | Last local metadata update |

`capital_city`, `latitude` and `longitude` were removed in v1.1 because no approved feature uses them; re-add them with a migration if a map feature is approved (D-34).

**Indexes:** primary key is sufficient for key lookups. Consider an index on normalized name only if name search is implemented.

### 3.2 `indicators`
Describes each economic indicator. Name and description come from source metadata; the display unit comes from configuration (`INDICATOR_UNITS`) because the source's unit field is usually empty (D-09).

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `indicator_code` | `VARCHAR(32)` | Primary key | Example: `NY.GDP.MKTP.CD` |
| `name` | `TEXT` | Not null | Display name |
| `description` | `TEXT` | Nullable | Source description |
| `unit` | `TEXT` | Not null | Configured display unit, e.g. `current US$`, `people`, `% of total labor force` |
| `source_name` | `TEXT` | Not null, default `World Bank` | Origin of data |
| `frequency` | `VARCHAR(16)` | Not null, default `annual` | Initial implementation assumes annual observations |
| `updated_at` | `TIMESTAMPTZ` | Not null | Last local metadata update |

**Initial indicators:** `NY.GDP.MKTP.CD`, `SP.POP.TOTL`, and `SL.UEM.TOTL.ZS`.

### 3.3 `pipeline_runs`
One record per pipeline execution attempt. The row is inserted with status `running` and **committed in its own transaction** before any data is loaded, so a failed load cannot erase it (D-18).

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `run_id` | `UUID` | Primary key | Stable execution identifier |
| `triggered_by` | `VARCHAR(32)` | Not null; constrained to `cli`, `api`, `scheduler` (D-22) | Entry point |
| `status` | `VARCHAR(24)` | Not null; constrained to `running`, `success`, `partial_success`, `failed` | Current/final outcome (rules: TRD §6) |
| `started_at` | `TIMESTAMPTZ` | Not null | Execution start |
| `finished_at` | `TIMESTAMPTZ` | Null while `running`, not null once terminal | Completion timestamp |
| `duration_seconds` | `NUMERIC(12,3)` | Nullable, non-negative; null while `running` | Total runtime |
| `countries_requested` | `INTEGER` | Not null, default 0 | Configured country count |
| `indicators_requested` | `INTEGER` | Not null, default 0 | Configured indicator count |
| `records_extracted` | `INTEGER` | Not null, default 0 | **E** — rows received from successful series |
| `records_rejected` | `INTEGER` | Not null, default 0 | **R** — rows failing validation |
| `records_null_skipped` | `INTEGER` | Not null, default 0 | **N** — valid rows with a null source value (not loaded) |
| `records_duplicates_dropped` | `INTEGER` | Not null, default 0 | **D** — extra copies of a business key removed before loading |
| `records_transformed` | `INTEGER` | Not null, default 0 | **T** — load-ready rows; `E = R + N + D + T` |
| `records_loaded` | `INTEGER` | Not null, default 0 | **L** — rows written by the committed upsert (inserted + updated); `T` on commit, `0` on rollback |
| `records_inserted` | `INTEGER` | Not null, default 0 | **I** — rows whose key did not exist before |
| `records_value_changed` | `INTEGER` | Not null, default 0 | **V** — existing rows whose value changed |
| `error_count` | `INTEGER` | Not null, default 0 | Recorded errors (e.g. failed series) |
| `error_summary` | `TEXT` | Nullable | Sanitized short error summary; no secrets, SQL, stack dumps or raw payloads |
| `config_snapshot` | `JSONB` | Nullable | Non-secret settings relevant to reproducibility |

**Count rules (D-11):**

- Each extracted row is classified once, in the order R → N → D; the remainder is T.
- R covers: missing or invalid ISO-3 code, unconfigured country or indicator, year not an integer or outside `START_YEAR..END_YEAR`, and a non-null value that is non-numeric, non-finite or outside `NUMERIC(24,6)`.
- Invariants, enforced by tests rather than CHECKs: `E = R + N + D + T`; `L = T` when the load commits and `0` when it rolls back; `I + V <= L`.
- **Processed** = E, **upserted** = L, **changed** = I + V. The other `L − I − V` rows were rewritten with an identical value (only `ingested_at` and `last_run_id` change). A rerun on unchanged source data therefore reports `I = 0` and `V = 0`.
- I and V are computed inside the load transaction by reading existing values for the configured scope before the upsert and comparing at 6-decimal scale. The single-`running`-row guard makes this comparison safe.

**Constraints:** see §6. In summary: status and trigger value lists; `(status = 'running') = (finished_at IS NULL)`; `finished_at >= started_at`; non-negative counts and duration; `records_loaded <= records_transformed`; `records_inserted + records_value_changed <= records_loaded`; and a **partial unique index allowing only one `running` row** (D-19).

**Stale-run recovery:** at the start of every claim, rows still `running` after `STALE_RUN_MINUTES` are set to `failed` with `finished_at`, `duration_seconds` and an "abandoned" `error_summary` (D-20).

**Indexes:** `(started_at DESC)`, `(status, started_at DESC)`, and the partial unique index `uq_pipeline_runs_one_running`.

### 3.4 `economic_observations`
The primary analytical fact table: one row per country, indicator, and observation year.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `country_code` | `VARCHAR(3)` | FK to `countries.country_code`, not null | Country/area identifier |
| `indicator_code` | `VARCHAR(32)` | FK to `indicators.indicator_code`, not null | Indicator identifier |
| `year` | `SMALLINT` | Not null; reasonable year check | Observation year |
| `value` | `NUMERIC(24,6)` | **Not null** | Source numeric value; null source values are never stored as rows (see null policy) |
| `source_updated_at` | `TIMESTAMPTZ` | Nullable | Series-level `lastupdated` from source metadata |
| `ingested_at` | `TIMESTAMPTZ` | Not null | Time this row was last successfully loaded/updated |
| `last_run_id` | `UUID` | Nullable FK to `pipeline_runs.run_id` | Run that last wrote (or re-confirmed) the record; always a `success`/`partial_success` run |

- **Primary key:** composite `(country_code, indicator_code, year)`.
- **Indexes:** the primary key (serves country-first lookups such as trends and comparisons) and `(indicator_code, year)`. The v1.0 `(country_code, year)` index is dropped as redundant with the primary key's leading column (D-36). Do not add indexes without a query/use-case reason.

**Null policy:** World Bank APIs can return null values. The first release skips null-valued fact rows, counts them in `records_null_skipped` and the `null_value_rate` check, and never converts them to zero. `value NOT NULL` makes PostgreSQL enforce the policy (D-12). If the product later needs explicit missing observations, change the model deliberately (e.g. an `is_missing` flag) rather than encoding missing as zero.

**De-duplication:** rows are de-duplicated on the primary key in pandas before the upsert, because PostgreSQL cannot apply `ON CONFLICT DO UPDATE` to the same key twice in one statement (D-13).

**Upsert policy:** `INSERT ... ON CONFLICT (country_code, indicator_code, year) DO UPDATE SET value, source_updated_at, ingested_at, last_run_id`, unconditionally (D-14). Reruns never create duplicates; an unchanged source value stays unchanged, while `ingested_at`/`last_run_id` record the latest confirming run. Before the upsert, within the same transaction, the loader reads existing values for the configured scope to compute `records_inserted` and `records_value_changed` (D-11). The operation must be idempotent and tested.

### 3.5 `data_quality_checks`
Stores check-level outcomes for a pipeline run.

| Column | Type | Rules | Purpose |
|---|---|---|---|
| `quality_check_id` | `BIGINT` | Primary key, generated | Internal ID |
| `run_id` | `UUID` | FK to `pipeline_runs.run_id`, not null | Owning run |
| `check_name` | `VARCHAR(100)` | Not null | Stable machine-readable check name |
| `status` | `VARCHAR(16)` | Not null; constrained to `passed`, `warning`, `failed` | Outcome |
| `checked_at` | `TIMESTAMPTZ` | Not null | Check time |
| `records_checked` | `INTEGER` | Not null, default 0, ≥ 0 | Number assessed |
| `records_failed` | `INTEGER` | Not null, default 0, ≥ 0, ≤ `records_checked` | Number failing |
| `details` | `JSONB` | Nullable | Counts, thresholds, sanitized details |

- **Unique:** `(run_id, check_name)`, one result per check per run.
- **Indexes:** `(check_name, checked_at DESC)`. Lookups by `run_id` use the `(run_id, check_name)` unique constraint's index, so no separate `(run_id)` index is created.

These rows, together with the counts on `pipeline_runs`, are the **authoritative** quality report; the optional JSON file is only an export (D-16). Checks are written in the same transaction that finalizes the run (D-18).

**First-release check catalog (D-17):**

| `check_name` | `records_checked` / `records_failed` | Status rule |
|---|---|---|
| `extraction_requests_succeeded` | series requested / series failed | `passed` if 0 failed; `warning` if some; `failed` if all |
| `api_page_count_consistent` | series / series with a count mismatch | `failed` if any mismatch |
| `required_fields_present` | E / rows missing an identifier or year | `failed` if > 0 |
| `valid_country_code` | E / invalid or unconfigured ISO-3 codes | `failed` if > 0 |
| `valid_indicator_code` | E / unconfigured indicators | `failed` if > 0 |
| `year_in_range` | E / non-integer or out-of-window years | `failed` if > 0 |
| `numeric_value` | non-null values / non-numeric, non-finite or out of range | `failed` if > 0 |
| `null_value_rate` | rows with valid identifiers / null values | `warning` if > 0; never `failed` |
| `unique_business_key` | rows after null skip / duplicates dropped | `passed` if 0; `warning` if identical; `failed` if conflicting (D-13) |

The v1.0 candidate `unexpected_duplicate_count` is folded into `unique_business_key`.

## 4. Rejected-row handling

For the first release, do not persist full raw payloads in the main observation table. Record rejected-row counts and sanitized examples/reasons in the quality check `details` (bounded to a few examples per check). If storing rejected records in PostgreSQL is required later, add a dedicated `rejected_records` table with strict size limits, no secret-bearing payloads, and retention rules. Avoid putting unbounded API payloads into `pipeline_runs.error_summary`.

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
-- countries
CHECK (country_code ~ '^[A-Z]{3}$')

-- economic_observations
PRIMARY KEY (country_code, indicator_code, year)
CHECK (year >= 1900 AND year <= 2200)
-- value NUMERIC(24,6) NOT NULL

-- pipeline_runs
CHECK (status IN ('running', 'success', 'partial_success', 'failed'))
CHECK (triggered_by IN ('cli', 'api', 'scheduler'))
CHECK ((status = 'running') = (finished_at IS NULL))
CHECK (finished_at IS NULL OR finished_at >= started_at)
CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
CHECK (finished_at IS NOT NULL OR duration_seconds IS NULL)
CHECK (records_extracted >= 0)
CHECK (records_rejected >= 0)
CHECK (records_null_skipped >= 0)
CHECK (records_duplicates_dropped >= 0)
CHECK (records_transformed >= 0)
CHECK (records_loaded >= 0)
CHECK (records_inserted >= 0)
CHECK (records_value_changed >= 0)
CHECK (error_count >= 0)
CHECK (countries_requested >= 0 AND indicators_requested >= 0)
CHECK (records_loaded <= records_transformed)
CHECK (records_inserted + records_value_changed <= records_loaded)
CREATE UNIQUE INDEX uq_pipeline_runs_one_running
    ON pipeline_runs (status) WHERE status = 'running';

-- data_quality_checks
CHECK (status IN ('passed', 'warning', 'failed'))
CHECK (records_checked >= 0 AND records_failed >= 0)
CHECK (records_failed <= records_checked)
UNIQUE (run_id, check_name)
```

The year check is a broad defensive bound, not a claim that every indicator exists for those years. More restrictive validation uses the configured request window and source metadata.

The partial unique index means a second `INSERT` of a `running` row fails with a unique violation while another run is active. This is the database-enforced overlap guard for every entry point (CLI, API, Task Scheduler) (D-19). The full count identity `E = R + N + D + T` is **not** a CHECK because a failed run may stop before every count is known; it is enforced by tests (D-21).

## 7. Read patterns supported

- KPI summary: count distinct countries, indicators, observation rows, latest successful load time (latest `finished_at` of a `success`/`partial_success` run), latest run status.
- Trend chart: `indicator_code`, selected `country_code` values, and year range; return ordered annual values. Years without a row are returned as absent (not zero).
- Country comparison: one indicator and year, multiple country codes; countries without a row are listed as unavailable.
- Observation table: filter by country, indicator and year range; server-side pagination and stable sort (primary key as tie-breaker).
- Pipeline history: newest runs ordered by `started_at` descending.
- Latest quality status: quality checks joined to the most recent **terminal** run (`success`, `partial_success` or `failed`), so a failed latest run is shown as failed rather than an older passing run (D-17).
- Run claim / overlap: insert into `pipeline_runs` guarded by the partial unique index; stale recovery update by `status = 'running' AND started_at < now() - STALE_RUN_MINUTES`.

## 8. Database access rules

- Create a SQLAlchemy session per request/task and close it deterministically. Background pipeline runs open their own sessions; they never reuse a request's session.
- Use transaction contexts for writes. Pipeline transaction boundaries: claim (T1) → load + finalize (T2) → failure finalization (T3), as defined in TRD §6 (D-18).
- Tests use only `TEST_DATABASE_URL`, pointing to a dedicated `*_test` database; the test setup refuses to run against the development database (D-06). Tests isolate themselves with a rolled-back outer transaction, never with TRUNCATE or DROP (D-37).
- Never construct SQL using user-provided string concatenation.
- Use bound parameters and validated filters.
- Keep database credentials in an environment variable and ignore `.env` in Git.
- Use a dedicated local application role (`gedp_app`, not a superuser) that owns the `gedp_dev` and `gedp_test` databases, rather than the PostgreSQL superuser (D-05).
