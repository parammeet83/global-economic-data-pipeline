# Technical Requirements Document (TRD)

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Version:** 1.1
- **Last updated:** 2026-10-19

## 1. Purpose

This document defines the technical architecture, technology choices, interfaces, runtime behavior, quality requirements, and implementation constraints for the project. It is the engineering companion to `PRD.md`. Decisions referenced as `D-xx` are explained in `DECISIONS.md`.

## 2. Architecture overview

```text
World Bank Indicators API
          |
          v
Python extraction client (requests, timeouts, retries, pagination)
          |
          v
pandas transformation -> Pandera validation -> rejected-row details
          |
          v
SQLAlchemy transaction + PostgreSQL upsert
          |                         |
          v                         v
observations / dimensions     run + quality metadata
          ^                         ^
          |                         |
          +------- FastAPI REST API-+
                       ^
                       |
             React + TypeScript UI
             KPIs / charts / tables / runs
```

Browser clients call FastAPI only. Database credentials and SQL remain on the backend. The pipeline should be importable and callable from a CLI as well as from the API without duplicating business logic. The CLI is also the entry point for scheduled runs (Windows Task Scheduler, D-31); API-triggered runs execute the same function as a FastAPI background task (D-23).

## 3. Planned technology stack

| Layer | Technology | Responsibility |
|---|---|---|
| Runtime | Python 3.12.x | ETL, API, tests |
| API ingestion | `requests` | HTTP, timeout, retry/backoff and pagination handling |
| Data processing | `pandas`, `numpy` if needed | tabular transforms, type normalization, null handling |
| Validation | `pandera` | schema and data-quality rules |
| Backend API | `FastAPI`, `uvicorn`, Pydantic | REST API and request/response validation |
| Configuration | `pydantic-settings` | typed settings from environment / `backend/.env`, validated at startup |
| Database | PostgreSQL (native Windows install; 17 preferred, ≥ 16) | durable analytical observations and operational history |
| ORM / data access | SQLAlchemy 2.x, psycopg 3 | transactions, queries and upserts |
| Schema migration | Alembic | versioned database schema changes |
| Tests | `pytest`, `httpx2` (FastAPI/Starlette test client; replaces the deprecated `httpx` backend), `responses` (HTTP mocking), `pytest-cov` | automated backend tests and coverage reporting |
| Frontend | Node.js LTS, React, TypeScript, Vite, plain CSS with CSS variables | browser-based analytics application |
| Visualization | Recharts | line/bar charts and simple metrics |
| Frontend tests | Vitest and React Testing Library (Phase 8; build check from Phase 7) | component and utility tests |
| CI | GitHub Actions with a PostgreSQL service container | run backend tests and frontend build/test checks |
| Scheduling | Windows Task Scheduler running the CLI (MVP); APScheduler/Airflow/Prefect deferred | repeatable scheduled execution |

Dependency versions must be pinned or bounded after compatibility is tested on Python 3.12 and the selected Node.js LTS release. Do not blindly install unverified latest versions or put incompatible libraries into `requirements.txt`. Runtime dependencies live in `backend/requirements.txt`; test/dev tools in `backend/requirements-dev.txt` (which includes the runtime file). Frontend dependencies are locked by a committed `package-lock.json` (D-03). Not added in the MVP: a CSS framework or component library, React Query, Redux, or a CI linter; data fetching uses `fetch` with small typed hooks. Transitive Python dependencies are not locked yet (a lock tool such as pip-tools is deferred).

## 4. Repository layout

```text
global-economic-data-pipeline/
├── .venv/                       # root virtual environment (git-ignored, D-01)
├── docs/
│   ├── INDEX.md
│   ├── DECISIONS.md
│   ├── implementation_plan.md
│   ├── Backend_DB_Schema.md
│   ├── WebAppFlow.md
│   ├── UIUX_design_spec.md
│   ├── TRD.md
│   └── PRD.md
├── backend/
│   ├── src/
│   │   ├── api/                 # FastAPI routers and schemas
│   │   ├── pipeline/            # extract, transform, validate, load, orchestrate
│   │   ├── db/                  # models, session, repositories
│   │   ├── services/            # analytics and run services
│   │   ├── core/                # config, logging, exceptions
│   │   └── main.py
│   ├── tests/
│   ├── sql/                     # optional reference SQL
│   ├── alembic/                 # migrations
│   ├── alembic.ini
│   ├── requirements.txt         # runtime dependencies
│   ├── requirements-dev.txt     # -r requirements.txt + test tools
│   ├── reports/                 # optional JSON exports (git-ignored)
│   └── .env.example             # placeholders only; real .env is git-ignored
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── .github/workflows/ci.yml
├── .gitignore
├── README.md
└── LICENSE                  # decide before public release
```

This is the intended final structure, not a requirement to create every directory in the first step. Early phases may use fewer files; refactor only when there is a working vertical slice.

## 5. API source and ingestion rules

- Base URL: `https://api.worldbank.org/v2`.
- Request JSON using `format=json`; set `per_page` to a reasonable configurable value (`PER_PAGE`, default 1000).
- Request unit: one paginated series per indicator covering all configured countries, `country/{IND;USA;...}/indicator/{code}?format=json&date={START_YEAR}:{END_YEAR}` (D-10).
- Fetch country metadata from `country/{codes}?format=json` before observations; unknown or aggregate codes are configuration errors that fail the run (D-08).
- Parse and validate the API's response envelope before accessing page data.
- Treat transport failures, HTTP errors, API-level error payloads, and malformed JSON as distinct errors. **The World Bank returns some errors with HTTP 200** as `[{"message":[{"id":"...","key":"...","value":"..."}]}]`; detect this shape explicitly. A valid empty result is `[{..."total":0}, null]` and is the only case that yields zero rows without an error (see the classification table below).
- Use connect/read timeouts and a bounded retry policy with exponential backoff for transient failures (network failures, 429, and retryable 5xx). Respect `Retry-After` if present. Do not endlessly retry permanent 4xx errors, malformed responses, or API error payloads.
- Read page count / total count from response metadata and retrieve every page; verify that rows received equal `total`. Include tests for one-page and multi-page responses. A series that fails after retries is discarded entirely (no half-loaded indicator).
- Use an explicit country list and indicator list from configuration. Keep them out of hard-coded business logic.
- Use **ISO-3** country codes consistently: read `countryiso3code` from observation payloads, never the 2-letter `country.id` (D-08).
- Preserve source indicator codes, country codes, year, and numeric value. Do not silently fill nulls with zero.
- Record retrieval timestamps and run IDs for lineage; `source_updated_at` comes from the series metadata `lastupdated`.

### Response classification

Every response is classified before its data is used (D-10):

| Condition | Class | Retried? |
|---|---|---|
| Connection error or timeout | Transport error | Yes (bounded, exponential backoff) |
| HTTP 429, 500, 502, 503, 504 | Transient HTTP error | Yes; honor `Retry-After` when present, capped |
| Any other non-2xx status | Permanent HTTP error | No |
| HTTP 200, body is not valid JSON | Malformed response | No |
| HTTP 200, JSON list whose first element contains `message` | World Bank API error payload | No |
| HTTP 200, JSON not shaped `[metadata, data]`, or data `null` while `total > 0` | Malformed response | No |
| HTTP 200, `total == 0` and data `null` or `[]` | Valid empty result | n/a |

Observed API behavior (2026-10): a `date` range with no data at all can be ignored, and all years are returned. The client therefore never relies on the API to filter years; the `year_in_range` check rejects out-of-window rows.

A series that fails after retries, or whose received row count differs from `total` or whose `pages` value changes between pages, is discarded entirely and counted in `error_count`.

## 6. Pipeline contract

1. **Claim (own committed transaction):** mark stale `running` rows older than `STALE_RUN_MINUTES` as `failed` (D-20), then insert a `pipeline_runs` row with status `running` and a start timestamp, and commit. A database partial unique index allows only one `running` row; a conflicting claim is refused (API 409 / CLI exit code 3) and is logged, not stored (D-19).
2. Extract source records and retain extraction counts / errors.
3. Normalize country and indicator metadata, year, and numeric values.
4. Validate required fields, type and domain constraints.
5. Separate accepted rows from rejected rows and record rejection reasons; skip and count null-valued rows; de-duplicate on `(country_code, indicator_code, year)` before loading (D-13). Reject only the invalid records where safe, but fail the run when structural/source errors make the result untrustworthy.
6. **Load + finalize (one transaction):** upsert dimensions, compute inserted/value-changed counts, upsert accepted observations, insert quality checks, and set the terminal status with a conditional update (`WHERE status = 'running'`). Any error rolls back the whole unit (D-18).
7. If extraction fails structurally or step 6 rolls back, finalize the run as `failed` in a separate transaction with known counts, checks and a sanitized error summary.
8. Set the terminal status using the run status rules below; counts follow `Backend_DB_Schema.md` §3.3 (`E = R + N + D + T`). A failed run must not be shown as successful merely because some records loaded; a failed run loads nothing.
9. Write structured logs with run ID, stage, duration, counts, and error context (never secrets).
10. The database rows are the authoritative quality report. Optionally (`WRITE_JSON_REPORT=true`) also write `{REPORTS_DIR}/run_{run_id}.json`; a failure to write it never changes run status. No Markdown/HTML report (D-16).

### Run status rules (D-15)

| Status | Condition |
|---|---|
| `failed` | Nothing committed: configuration error after the run row exists (e.g. unknown or aggregate country code), metadata fetch failed, every indicator series failed, no load-ready rows (T = 0), load transaction rolled back, unexpected exception, or run recovered as stale |
| `partial_success` | Load committed with T > 0, but at least one series failed after retries, R > 0, or conflicting duplicates were found |
| `success` | Load committed, every series succeeded, R = 0, no conflicting duplicates |

Null source values and identical duplicates are reported as `warning` checks and do not lower the status, because they describe the source rather than a pipeline defect.

## 7. REST API contract (planned)

Prefix: `/api/v1`. Exact response schemas should be implemented as typed Pydantic models and documented through FastAPI OpenAPI.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health: `200 {"status":"ok","database":"ok"}` or `503 {"status":"degraded","database":"unavailable"}` (D-27) |
| GET | `/api/v1/dashboard/summary` | KPI counts and last-run summary |
| GET | `/api/v1/indicators` | List configured/known indicators and units |
| GET | `/api/v1/countries` | List countries represented in the data |
| GET | `/api/v1/observations` | Filtered, paginated observation rows |
| GET | `/api/v1/analytics/trend` | Annual time series for an indicator and selected countries |
| GET | `/api/v1/analytics/country-comparison` | Compare countries for an indicator/year |
| GET | `/api/v1/runs` | Paginated recent pipeline runs |
| GET | `/api/v1/runs/{run_id}` | One run, its counts, quality checks and errors; also the polling endpoint for run status (D-24) |
| GET | `/api/v1/quality/latest` | Checks of the most recent **terminal** run (including a failed one), or an empty result if none (D-17) |
| POST | `/api/v1/pipeline/run` | Claim and start a manual run: **202** `{run_id, status:"running", status_url}`; **409** if a run is in progress; **403** if `ENABLE_MANUAL_TRIGGER` is false (D-23) |

### Manual trigger execution model
The claim (step 1 of §6) happens synchronously in the request so the response can carry a real run ID. The rest of the pipeline runs as a FastAPI `BackgroundTasks` job after the response is sent, in the server's thread pool, using its own database sessions and the same function the CLI calls. Limitations: the run dies with the API process (including `uvicorn --reload` restarts) and is later recovered as stale; there is no queue, cancellation or progress percentage; a single API process is assumed (the database guard still prevents overlap); no authentication, so local/demo only.

### API rules
- Validate year boundaries, allowed sort fields, page size, indicator codes and country codes.
- Use consistent error bodies, `{"error": {"code": "...", "message": "..."}}`, including for validation errors (422) and an unreachable database (503, code `database_unavailable`); do not expose stack traces, SQL, raw payloads or credentials.
- Paginated lists take `page` (≥ 1) and `page_size` (runs: default 20, max 100; observations: default 50, max 500) and return `{items, page, page_size, total}`. Multiple countries are passed as repeated `country_code` parameters. Sorting uses an allow-list with the primary key as tie-breaker (D-25).
- `dashboard/summary` includes the configured `defaults` (indicator and countries) for the Overview chart (D-26).
- Define numeric values and missing-value behavior clearly in OpenAPI and README.
- Restrict CORS to configured local/deployment origins.
- The trigger route must remain local-only for the MVP. Add authentication, rate limiting, and execution controls before a public deployment.

## 8. Data storage and correctness

See `Backend_DB_Schema.md` for entities, constraints, and indexes. Required integrity invariants:

- Unique observation key: `(country_code, indicator_code, year)` (composite primary key).
- One durable run record for each execution attempt, including failures after run creation; the run row is committed in its own transaction before the data load.
- At most one `running` run at any time, enforced by a partial unique index; stale runs are recovered as `failed`.
- All quality checks refer to a known run.
- Foreign keys prevent orphaned observations.
- Upsert uses the unique key and preserves idempotency.
- Writes must be transactional where possible; an exception must roll back the affected write unit.

## 9. Configuration and secrets

Configuration is environment-driven, loaded by a `pydantic-settings` class from environment variables with `backend/.env` as a fallback (D-04). Expected settings:

| Setting | Planned default / example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://gedp_app:<password>@localhost:5432/gedp_dev` | Real value only in `.env`; never commit credentials |
| `TEST_DATABASE_URL` | `postgresql+psycopg://gedp_app:<password>@localhost:5432/gedp_test` | Tests refuse to run unless the DB name ends in `_test` and differs from `DATABASE_URL` (D-06) |
| `API_BASE_URL` | `https://api.worldbank.org/v2` | |
| `COUNTRY_CODES` | `IND,USA,GBR,DEU,JPN,CHN,BRA,ZAF,CAN,AUS` | ISO-3, comma-separated, no duplicates |
| `INDICATOR_CODES` | `NY.GDP.MKTP.CD,SP.POP.TOTL,SL.UEM.TOTL.ZS` | Comma-separated, no duplicates |
| `INDICATOR_UNITS` | `{"NY.GDP.MKTP.CD":"current US$","SP.POP.TOTL":"people","SL.UEM.TOTL.ZS":"% of total labor force"}` | JSON; every configured indicator must have a unit (D-09) |
| `START_YEAR`, `END_YEAR` | `2005`, `2024` | Fixed window; `START_YEAR <= END_YEAR` (D-07) |
| `PER_PAGE` | `1000` | |
| `REQUEST_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_BACKOFF_SECONDS` | `30`, `3`, `1` | Backoff is exponential from this base |
| `STALE_RUN_MINUTES` | `60` | Must exceed the longest measured run (D-20) |
| `DEFAULT_INDICATOR_CODE`, `DEFAULT_COUNTRY_CODES` | `NY.GDP.MKTP.CD`, `IND,USA,CHN,DEU,BRA` | Must be subsets of configured codes (D-26) |
| `ENABLE_MANUAL_TRIGGER` | `true` locally | Must be `false` in any non-local deployment |
| `WRITE_JSON_REPORT`, `REPORTS_DIR` | `false`, `reports` | Optional JSON export (D-16) |
| `LOG_LEVEL` | `INFO` | |
| `CORS_ORIGINS` | `http://localhost:5173` | Vite dev server origin |

There is no `PIPELINE_SCHEDULE_ENABLED` setting: scheduling lives in Windows Task Scheduler and is enabled/disabled there (D-31).

Validate configuration at startup and fail with an actionable message when mandatory settings are missing or inconsistent: country codes must match `^[A-Z]{3}$`, code lists must not contain duplicates, every configured indicator needs an `INDICATOR_UNITS` entry, `START_YEAR <= END_YEAR`, and default codes must be subsets of the configured codes. List settings are comma-separated strings (parsing needs an explicit validator in pydantic-settings; verify in Phase 1). `backend/.env.example` must contain placeholders only. `.env` is ignored by Git.

## 10. Security and privacy

- The source data is public economic data; the project should not store personal data.
- Never commit database passwords, tokens, or local `.env` values.
- Do not expose SQL or detailed stack traces to the web client.
- Avoid arbitrary SQL fragments derived from query parameters.
- Keep manual pipeline execution disabled or protected in any public deployment.
- Apply dependency updates and test before upgrading major versions.

## 11. Non-functional requirements

- **Reliability:** bounded retries, pagination verification, consistent status outcomes, idempotent writes.
- **Observability:** structured logs, durable run history, elapsed time and row counts, quality reports.
- **Maintainability:** separate extraction, transformation, validation, loading, services and API layers.
- **Testability:** injectable HTTP client/configuration, database tests isolated from production data, deterministic unit tests using fixtures/mocks.
- **Performance:** use bulk operations where practical, database indexes for common filters, and bounded API responses. Set measurable targets only after a baseline run.
- **Usability:** dashboard clearly shows units, selected filters, missing-value gaps, last-updated time, and errors.
- **Portability:** setup should support Windows development with Python 3.12; avoid shell-only assumptions in application code.

## 12. Testing strategy

- Unit tests: API response parsing (including HTTP-200 error payloads and valid empty results), pagination, retry classification, transformations, validation, de-duplication, count arithmetic (`E = R + N + D + T`), status rules, upsert key logic.
- Integration tests: PostgreSQL schema and constraints, transaction rollback, unique constraint/upsert, overlap guard, stale-run recovery, repository queries, API routes.
- API contract tests: query validation, pagination, expected response schema, error cases, 202/409/403 trigger responses.
- Frontend tests: filter behavior, loading/empty/error states, number formatting, charts with sample data, missing values never rendered as zero.
- End-to-end smoke check: start services, run pipeline once, verify records and run metadata, load dashboard.
- Database tests use **only** `TEST_DATABASE_URL` (a dedicated `*_test` database) with migrations applied; a guard refuses to run against the development database (D-06). Each test runs inside a transaction that is rolled back, so tests never truncate or drop data (D-37).
- CI must not rely on live World Bank availability. All automated tests mock the source (via an injected `requests.Session` and `responses`). A separate optional live check is marked `live` and excluded by default.
- CI (GitHub Actions) runs backend tests against a PostgreSQL service container from the end of Phase 2; frontend build from Phase 7; frontend tests from Phase 8 (D-32).

## 13. Scheduling and operations

MVP first: run pipeline manually via CLI and API, and prove safe reruns. Add local recurring scheduling only after these work reliably.

The MVP scheduler is **Windows Task Scheduler** invoking the CLI (D-31): program `<repo>\.venv\Scripts\python.exe`, arguments `-m src.pipeline.cli run --triggered-by scheduler` (module path confirmed in Phase 5), start in `<repo>\backend`. There is no in-process scheduler, so nothing can be left running when the API stops. Overlap prevention is the database guard plus Task Scheduler's "Do not start a new instance" setting; failures are retained in run history; the schedule uses the Windows local time zone while stored timestamps are UTC `TIMESTAMPTZ`; the schedule is stopped by disabling the task. CLI exit codes: 0 success, 1 failed, 2 partial_success, 3 refused (run in progress), 4 configuration/startup error before a run row exists. APScheduler, Airflow and Prefect are later upgrades only if they add demonstrable value and can be run reliably.

## 14. Deployment approach

Initial target is a local development/demo environment. Later options:

1. Local PostgreSQL (native Windows install) + backend + frontend.
2. Docker Compose for repeatable demos (deferred to P2, D-33).
3. Cloud deployment after configuration, CORS, error handling, and access control are hardened.

Do not describe the project as production-deployed until deployment and operational behavior have actually been tested.
