# Decision Log

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Last updated:** 2026-10-19 (Phase 0 review)

Each entry records a decision, its rationale and its impact. Detailed requirements live in the six specifications (v1.1), which cite these entries as `D-xx`. Tags show the review finding resolved: **C** contradiction, **F** integration gap, **M** missing requirement. Nothing here is implemented yet.

## Repository and environment

**D-01 — Root `.venv` only (C1).** Use the existing root `.venv` (Python 3.12.10); drop `backend/.venv`. *Why:* one environment already exists. *Impact:* backend commands run from `backend/` with the root environment active.

**D-02 — Repository already exists (C2).** Commit `cf67e9d` and `origin` predate Phase 0. *Why:* the plan assumed a first commit and remote creation in Phases 0/10. *Impact:* review `git status`/`git diff` before every commit; push only with explicit approval.

**D-03 — Dependency strategy (M4).** `pip` with `backend/requirements.txt` (runtime) and `requirements-dev.txt` (`-r requirements.txt` + test tools); `npm` with a committed lock file. *Why:* simple, standard, reproducible. *Impact:* pin direct versions only after they install on Windows/Python 3.12.10; no CSS framework or extra state libraries (TRD §3).

**D-04 — pydantic-settings configuration (M4).** One validated `Settings` class reads environment variables, then `backend/.env`. *Why:* typed, fail-fast configuration. *Impact:* settings and validation rules in TRD §9; `PIPELINE_SCHEDULE_ENABLED` removed (see D-31).

**D-05 — Native PostgreSQL on Windows.** PostgreSQL 17 (≥ 16) via the official installer in Phase 1; role `gedp_app` owns `gedp_dev` and `gedp_test`. *Why:* not installed yet; native is simplest on Windows Home. *Impact:* no Docker in the MVP; CI uses the same major version.

**D-06 — Dedicated test database (M7).** Tests use only `TEST_DATABASE_URL`, and refuse to run unless the database name ends in `_test` and differs from `DATABASE_URL`. *Why:* tests must never overwrite development data. *Impact:* a guard in the test setup, enforced in Phase 2.

## Source data and extraction

**D-07 — Fixed year window (C4).** Always `START_YEAR..END_YEAR` (default 2005–2024, 20 years) rather than "latest 20 available". *Why:* reruns must request identical data. *Impact:* extending the window is a deliberate config change.

**D-08 — ISO-3 codes, countries only (F6, M5).** Read `countryiso3code` (never the ISO-2 `country.id`); fetch country metadata separately; aggregate or unknown codes fail the run. *Why:* the schema and configuration are ISO-3. *Impact:* rows with missing or invalid ISO-3 codes are rejected; `is_aggregate` is kept for later.

**D-09 — Units from configuration (F5).** `INDICATOR_UNITS` defines display units. *Why:* the source's unit field is usually empty. *Impact:* `indicators.unit` is `NOT NULL` (was nullable).

**D-10 — Request strategy and error classification (F8).** One paginated series per indicator for all countries; every response is classified, and HTTP-200 `[{"message": ...}]` payloads are errors. *Why:* an API failure must never look like an empty dataset. *Impact:* classification table in TRD §5; failed series are discarded whole.

## Transformation, validation and loading

**D-11 — Record count definitions (M2).** Counts E, R, N, D, T, L, I, V with `E = R + N + D + T`; processed = E, upserted = L, changed = I + V. *Why:* v1.0 had no place for null-skipped/duplicate rows and couldn't show idempotency. *Impact:* four new `pipeline_runs` columns; rules in Schema §3.3.

**D-12 — Null is never zero.** Null-valued rows are skipped and counted, and `value` becomes `NOT NULL` (was nullable). *Why:* the database is the final guard for the null policy. *Impact:* the UI shows gaps; explicit missing rows would need a deliberate model change.

**D-13 — De-duplicate before upsert (F7).** Keep the first occurrence of each business key in pandas; identical copies are a `warning`, conflicting copies are `failed`. *Why:* PostgreSQL rejects one key twice in an `ON CONFLICT` statement. *Impact:* `unique_business_key` check; conflicting copies prevent `success`.

**D-14 — Unconditional upsert (C7, M3).** On conflict, always update `value`, `source_updated_at`, `ingested_at`, `last_run_id` (was "only when appropriate"). *Why:* simplest idempotent rule. *Impact:* `last_run_id` means "last confirmed by"; changes are measured by I and V.

**D-15 — Run status rules (M1).** `failed` = nothing trustworthy committed; `partial_success` = committed but a series failed, rows were rejected or conflicting duplicates found; `success` = clean. Null values and identical duplicates don't downgrade. *Why:* v1.0 named the statuses but never defined them. *Impact:* rules in TRD §6; drives CLI exit codes.

**D-16 — Database is the quality report (C3, C8).** `pipeline_runs` + `data_quality_checks` are authoritative; a JSON file is an optional export; Markdown/HTML reports are dropped. *Why:* one source of truth for the API. *Impact:* `reports/` is git-ignored; export failures never change run status.

**D-17 — Quality checks and "latest" semantics.** A fixed catalog of nine checks; `/quality/latest` shows the most recent terminal run, even a failed one. *Why:* never show an older green result over a newer failure. *Impact:* catalog in Schema §3.5.

## Run integrity

**D-18 — Transaction boundaries (F4).** T1 commits the `running` row alone; T2 atomically loads data, writes checks and sets the terminal status (conditional on still `running`); T3 records `failed` if needed. *Why:* a failed load must not erase the audit row, and an abandoned run must never commit data. *Impact:* TRD §6 steps 1–7; `last_run_id` always points to a committed run.

**D-19 — Database overlap guard (F2).** A partial unique index allows only one `running` row. *Why:* it covers the CLI, API and Task Scheduler across processes, which an in-memory lock cannot. *Impact:* the API returns 409 and the CLI exits with code 3; refused attempts are logged, not stored.

**D-20 — Stale-run recovery (F3).** At each claim, `running` rows older than `STALE_RUN_MINUTES` (default 60) become `failed`. *Why:* a crash must not block all future runs. *Impact:* no heartbeat, so the threshold must exceed the longest measured run.

**D-21 — Status, timestamp and count constraints (M10).** CHECKs tie `finished_at` to terminal status, bound counts, restrict status and trigger values, and make the observation key a composite primary key. *Why:* the database is the final integrity guard. *Impact:* full list in Schema §6; `E = R + N + D + T` is tested, not CHECK-enforced.

**D-22 — Trigger types (C5).** `cli`, `api`, `scheduler`; `github_action` is removed. *Why:* CI never runs the pipeline against the live API. *Impact:* Task Scheduler passes `--triggered-by scheduler`.

## Backend API

**D-23 — Manual trigger: 202 + background task (F1).** Claim synchronously, return 202 with `run_id` (409 on overlap, 403 when disabled), then run via FastAPI `BackgroundTasks`. *Why:* a real run ID without blocking the request. *Impact:* the run dies with the API process (recovered as stale); no queue or auth, so local/demo only (TRD §7).

**D-24 — Polling via run detail (C9).** Poll `GET /api/v1/runs/{run_id}` every 3 s, stopping after 10 minutes. *Why:* no extra status endpoint is needed. *Impact:* WebAppFlow §7.

**D-25 — API conventions (M6).** Standard `page`/`page_size` pagination, repeated `country_code` parameters, allow-listed sorting, and one error body shape (422/503). *Why:* v1.0 standardized pagination for runs only. *Impact:* TRD §7.

**D-26 — Overview defaults from backend (M8).** Default indicator and countries are configuration returned by `dashboard/summary`. *Why:* no hard-coded lists in the frontend. *Impact:* two new settings.

**D-27 — Health response.** `/health` returns 200 or 503 and reports database status. *Why:* the UI must distinguish "backend down" from "database down". *Impact:* TRD §7, WebAppFlow §3.

## Frontend

**D-28 — Frontend test timing (C6).** Build check in CI from Phase 7; Vitest + React Testing Library from Phase 8. *Why:* the documents disagreed on when frontend tests start. *Impact:* implementation plan Phases 7–8.

**D-29 — Responsive scope (C10).** P0 = desktop, nothing critical clipped at 320 px; tuned tablet/mobile layouts and a collapsible sidebar are P1. *Why:* the PRD put mobile layouts in P1 but the UI docs required them. *Impact:* accessibility basics stay P0.

**D-30 — Deferred UI features.** Run-list filters, URL-synced filters, CSV export and history charts are P1. *Why:* keep the MVP small. *Impact:* route recovery on refresh stays P0.

## Operations

**D-31 — Windows Task Scheduler runs the CLI (F10).** No in-process scheduler; Task Scheduler runs the CLI with "Do not start a new instance". *Why:* zero scheduling code, and it can't be left running when the API stops. *Impact:* CLI exit codes 0–4 (TRD §13); scheduling verified manually instead of tested; enable/disable in Task Scheduler.

**D-32 — CI after the database foundation (F9).** GitHub Actions with a PostgreSQL service container from the end of Phase 2 (was Phase 10); the World Bank API is always mocked. *Why:* upsert and constraint tests need real PostgreSQL. *Impact:* frontend jobs are added in Phases 7–8.

**D-33 — Deferred technologies.** APScheduler, Docker Compose (moved P1 → P2), Airflow, Prefect, cloud, auth and a `rejected_records` table each need a written requirement first. *Why:* resume-grade MVP focus. *Impact:* PRD §8.

**D-34 — Unused country fields removed.** `capital_city`, `latitude`, `longitude` dropped; `region` and `income_level` kept. *Why:* no approved feature uses them. *Impact:* re-add by migration if a map is approved.

**D-35 — `.gitignore` additions (M9).** `node_modules/`, `reports/`, `coverage/`, `*.tsbuildinfo`. *Why:* frontend and report outputs must never be committed. *Impact:* the existing `.env` rules and the `!.env.example` exception are unchanged.

**D-36 — Redundant index dropped.** `(country_code, year)` is removed because the composite primary key already serves country-first lookups. *Why:* add indexes only for a real query need. *Impact:* `(indicator_code, year)` is kept.

## Amendments during implementation

**D-37 — Non-destructive test isolation (Phase 2).** Database tests never truncate, drop or reset anything. The test database gets its schema once via `alembic upgrade head` (additive); each test runs in an outer transaction that is always rolled back, with application commits becoming savepoints (`join_transaction_mode="create_savepoint"`). Migration upgrade/downgrade is tested in a throwaway schema inside a rolled-back transaction. *Why:* the owner prohibited destructive resets of either database. *Impact:* all database code takes a `sessionmaker`, so tests can bind it to the test connection; integration tests fail (not skip) in CI when the database is missing.

**D-38 — Manual trigger accepts loopback clients only (Phase 6).** Besides `ENABLE_MANUAL_TRIGGER`, `POST /api/v1/pipeline/run` returns 403 `manual_trigger_local_only` unless the client address is loopback (the Vite dev proxy connects from 127.0.0.1). *Why:* defense in depth for a route with no authentication (D-23). *Impact:* exposing the API beyond localhost cannot expose the trigger by accident; public deployment still needs real authentication.

**D-39 — Proxy-aware local-only trigger check (remediation).** The trigger accepts a request only if the `Host` header is a loopback name and the originating client is loopback. `X-Forwarded-For` is used only when the TCP peer is listed in `TRUSTED_PROXY_IPS` (empty by default); the client is then the right-most untrusted entry. Forwarding headers from an unlisted loopback peer fail closed. The Vite dev server binds to 127.0.0.1 and its proxy appends the real client address (`xfwd`) and keeps `Host`. The backend is started with `--host 127.0.0.1`. *Why:* through the Vite proxy every request arrives from 127.0.0.1, so the D-38 peer check alone could be bypassed when Vite was exposed with `--host`. *Impact:* the local Run button through Vite needs `TRUSTED_PROXY_IPS=127.0.0.1,::1` (in `.env.example`); the test-only "testclient" allowance was removed from production code. This is still not authentication.

**D-40 — JSON application logs with redaction (remediation).** Application loggers emit one JSON object per line (`ts`, `level`, `logger`, `message`, plus event fields such as `event`, `run_id`, `stage`, counts and `duration_s`). Credentials in URLs, `password=`-style pairs and secret-named fields are masked; exceptions are logged as type and redacted message without tracebacks. *Why:* TRD §6 step 9 and PRD P0 require structured, machine-readable logs without secrets. *Impact:* uvicorn's own access log keeps its plain format; the CLI's stdout summary is unchanged.
