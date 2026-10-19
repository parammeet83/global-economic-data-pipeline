# Technical Requirements Document (TRD)

**Project:** Global Economic Data Pipeline & Analytics Dashboard  
**Version:** 1.0  
**Last updated:** 2026-10-19

## 1. Purpose

This document defines the technical architecture, technology choices, interfaces, runtime behavior, quality requirements, and implementation constraints for the project. It is the engineering companion to `PRD.md`.

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

Browser clients call FastAPI only. Database credentials and SQL remain on the backend. The pipeline should be importable and callable from a CLI as well as from the API without duplicating business logic.

## 3. Planned technology stack

| Layer | Technology | Responsibility |
|---|---|---|
| Runtime | Python 3.12.x | ETL, API, tests |
| API ingestion | `requests` | HTTP, timeout, retry/backoff and pagination handling |
| Data processing | `pandas`, `numpy` if needed | tabular transforms, type normalization, null handling |
| Validation | `pandera` | schema and data-quality rules |
| Backend API | `FastAPI`, `uvicorn`, Pydantic | REST API and request/response validation |
| Database | PostgreSQL | durable analytical observations and operational history |
| ORM / data access | SQLAlchemy 2.x, psycopg 3 | transactions, queries and upserts |
| Schema migration | Alembic | versioned database schema changes |
| Tests | `pytest`, `httpx` test client; optional `pytest-cov` | automated backend tests and coverage reporting |
| Frontend | Node.js LTS, React, TypeScript, Vite | browser-based analytics application |
| Visualization | Recharts | line/bar charts and simple metrics |
| Frontend tests | Vitest and React Testing Library (after core UI) | component and utility tests |
| CI | GitHub Actions | run backend tests and frontend build checks |
| Scheduling | OS scheduler or APScheduler for first version; Airflow/Prefect later | repeatable scheduled execution |

Dependency versions must be pinned or bounded after compatibility is tested on Python 3.12 and the selected Node.js LTS release. Do not blindly install unverified latest versions or put incompatible libraries into `requirements.txt`.

## 4. Repository layout

```text
global-economic-data-pipeline/
├── docs/
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
│   ├── requirements.txt
│   └── .env.example
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
- Request JSON using `format=json`; set `per_page` to a reasonable configurable value.
- Parse and validate the API's response envelope before accessing page data.
- Treat transport failures, HTTP errors, API-level error payloads, and malformed JSON as distinct errors.
- Use connect/read timeouts and a bounded retry policy with exponential backoff for transient failures (network failures, 429, and retryable 5xx). Respect `Retry-After` if present. Do not endlessly retry permanent 4xx errors.
- Read page count / total count from response metadata and retrieve every page. Include tests for one-page and multi-page responses.
- Use an explicit country list and indicator list from configuration. Keep them out of hard-coded business logic.
- Preserve source indicator codes, country codes, year, and numeric value. Do not silently fill nulls with zero.
- Record retrieval timestamps and run IDs for lineage.

## 6. Pipeline contract

1. Create a `pipeline_runs` row with status `running` and a start timestamp.
2. Extract source records and retain extraction counts / errors.
3. Normalize country and indicator metadata, year, and numeric values.
4. Validate required fields, type and domain constraints, and duplicate keys.
5. Separate accepted rows from rejected rows and record rejection reasons; reject only the invalid records where safe, but fail the run when structural/source errors make the result untrustworthy.
6. Upsert dimensions, then accepted observations, in a transaction or clearly defined transaction boundaries.
7. Persist quality checks and summary counts.
8. Mark status `success`, `partial_success`, or `failed`; store end time and concise error details. A failed run must not be shown as successful merely because some records loaded.
9. Write structured logs with run ID, stage, duration, counts, and error context (never secrets).
10. Generate a JSON quality report and optionally a human-readable Markdown/HTML summary in `reports/`.

## 7. REST API contract (planned)

Prefix: `/api/v1`. Exact response schemas should be implemented as typed Pydantic models and documented through FastAPI OpenAPI.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health; database connectivity status may be reported separately |
| GET | `/api/v1/dashboard/summary` | KPI counts and last-run summary |
| GET | `/api/v1/indicators` | List configured/known indicators and units |
| GET | `/api/v1/countries` | List countries represented in the data |
| GET | `/api/v1/observations` | Filtered, paginated observation rows |
| GET | `/api/v1/analytics/trend` | Annual time series for an indicator and selected countries |
| GET | `/api/v1/analytics/country-comparison` | Compare countries for an indicator/year |
| GET | `/api/v1/runs` | Paginated recent pipeline runs |
| GET | `/api/v1/runs/{run_id}` | One run and its counts/errors |
| GET | `/api/v1/quality/latest` | Most recent data-quality summary/checks |
| POST | `/api/v1/pipeline/run` | Request a manual pipeline run; return a run ID/status or accepted response |

### API rules
- Validate year boundaries, allowed sort fields, page size, indicator codes and country codes.
- Use consistent error bodies; do not expose stack traces or credentials.
- Use pagination on potentially large lists.
- Define numeric values and missing-value behavior clearly in OpenAPI and README.
- Restrict CORS to configured local/deployment origins.
- The trigger route must remain local-only for the MVP. Add authentication, rate limiting, and execution controls before a public deployment.

## 8. Data storage and correctness

See `Backend_DB_Schema.md` for entities, constraints, and indexes. Required integrity invariants:

- Unique observation key: `(country_code, indicator_code, year)`.
- One durable run record for each execution attempt, including failures after run creation.
- All quality checks refer to a known run.
- Foreign keys prevent orphaned observations.
- Upsert uses the unique key and preserves idempotency.
- Writes must be transactional where possible; an exception must roll back the affected write unit.

## 9. Configuration and secrets

Configuration is environment-driven. Expected settings include:

- `DATABASE_URL` (local example only in `.env`; never commit actual credentials)
- `API_BASE_URL`
- `COUNTRY_CODES`
- `INDICATOR_CODES`
- `START_YEAR`, `END_YEAR`
- `REQUEST_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`
- `LOG_LEVEL`, `REPORTS_DIR`
- `CORS_ORIGINS`
- `PIPELINE_SCHEDULE_ENABLED` and timezone/schedule details if scheduling is implemented

Validate configuration at startup and fail with an actionable message when mandatory settings are missing. `.env.example` must contain placeholders only. `.env` is ignored by Git.

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

- Unit tests: API response parsing, pagination, retry classification, transformations, validation, report calculations, upsert key logic.
- Integration tests: PostgreSQL schema, transaction rollback, unique constraint/upsert, repository queries, API routes.
- API contract tests: query validation, pagination, expected response schema, error cases.
- Frontend tests: filter behavior, loading/empty/error states, number formatting, charts with sample data.
- End-to-end smoke check: start services, run pipeline once, verify records and run metadata, load dashboard.
- CI should not rely on live World Bank availability for unit tests. Use mocked responses in CI; keep a separate optional live integration check.

## 13. Scheduling and operations

MVP first: run pipeline manually via CLI and API, and prove safe reruns. Add local recurring scheduling only after these work reliably. The scheduler must prevent overlapping runs, retain failures, use a configured timezone, and be stoppable cleanly. Airflow or Prefect is a later upgrade only if it adds demonstrable value and can be run reliably.

## 14. Deployment approach

Initial target is a local development/demo environment. Later options:

1. Local PostgreSQL + backend + frontend.
2. Docker Compose for repeatable demos.
3. Cloud deployment after configuration, CORS, error handling, and access control are hardened.

Do not describe the project as production-deployed until deployment and operational behavior have actually been tested.
