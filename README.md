# Global Economic Data Pipeline & Analytics Dashboard

> **Status: in development.** Phases 0–9 are complete: configuration, `/health`, the PostgreSQL schema with migrations, CI, and the World Bank pipeline (extract, validate, idempotent load, run history, CLI). The analytics API and all six dashboard pages are built. Scheduling setup and final documentation are in progress. Setup and usage sections describe only what currently works.

A data-engineering portfolio project that will collect public economic indicators from the [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/topics/125589-developer-information), validate them, load them idempotently into PostgreSQL, and present them through a FastAPI backend and a React dashboard. The focus is reliability: retries and pagination, explicit validation, duplicate-safe reloads, audited pipeline runs and per-run data-quality results.

## Planned architecture

```text
World Bank API
  -> requests client (timeouts, bounded retry/backoff, pagination, error classification)
  -> pandas normalize -> Pandera validate -> accepted / rejected / null-skipped / de-duplicated rows
  -> SQLAlchemy transactional upsert -> PostgreSQL
  -> FastAPI (/api/v1) -> React + TypeScript dashboard

Entry points: CLI (manual and Windows Task Scheduler) and POST /api/v1/pipeline/run (local demo only)
```

## Planned technology stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Extraction | requests |
| Transformation / validation | pandas, Pandera |
| Database | PostgreSQL, SQLAlchemy 2.x, psycopg 3, Alembic |
| API | FastAPI, Pydantic, pydantic-settings |
| Frontend | React, TypeScript, Vite, Recharts |
| Tests | pytest, httpx2 (FastAPI TestClient), Vitest |
| CI | GitHub Actions (with a PostgreSQL service container) |
| Scheduling | Windows Task Scheduler running the CLI |

## Initial data scope (planned)

| Indicator | Code | Unit |
|---|---|---|
| GDP (current US$) | `NY.GDP.MKTP.CD` | current US$ |
| Population, total | `SP.POP.TOTL` | people |
| Unemployment, total (% of total labor force, modeled ILO estimate) | `SL.UEM.TOTL.ZS` | % of total labor force |

Ten configurable countries (ISO-3 codes), years 2005–2024 by default. Missing source values are reported as missing, never as zero.

## Project status

| Phase | Scope | Status |
|---|---|---|
| 0 | Requirements reconciliation, decision log, repository foundation | Done |
| 1 | Local environment, PostgreSQL, configuration, `/health` | Done |
| 2 | Database schema, migrations, CI | Done |
| 3 | World Bank API client | Done |
| 4 | Transformation and validation | Done |
| 5 | Idempotent loader, run lifecycle, CLI | Done |
| 6 | Analytics and pipeline API | Done |
| 7–8 | React dashboard | Done |
| 9 | Scheduling (Windows Task Scheduler) | Done (task creation left to the owner) |
| 10–11 | README finalization, screenshots, measured results | Not started |

## Repository layout (current)

```text
global-economic-data-pipeline/
├── backend/
│   ├── src/
│   │   ├── api/health.py      # GET /health
│   │   ├── core/config.py     # settings (pydantic-settings) and validation
│   │   ├── db/session.py      # SQLAlchemy engine and SELECT 1 check
│   │   └── main.py            # FastAPI app
│   ├── tests/
│   │   ├── unit/              # no database needed (database is mocked)
│   │   └── integration/       # use the PostgreSQL test database when configured
│   ├── .env.example           # copy to .env (git-ignored) and add your password
│   ├── pytest.ini
│   ├── requirements.txt       # runtime dependencies
│   └── requirements-dev.txt   # runtime + test dependencies
├── docs/                      # specifications and decision log (see docs/INDEX.md)
├── .gitignore
├── CLAUDE.md                  # guidance for Claude Code
└── README.md
```

`frontend/` will be added in Phase 7.

## Documentation

- [docs/INDEX.md](docs/INDEX.md): reading order
- [docs/PRD.md](docs/PRD.md): product requirements
- [docs/TRD.md](docs/TRD.md): technical requirements and API contract
- [docs/Backend_DB_Schema.md](docs/Backend_DB_Schema.md): database design
- [docs/WebAppFlow.md](docs/WebAppFlow.md): user flows
- [docs/UIUX_design_spec.md](docs/UIUX_design_spec.md): UI/UX design
- [docs/implementation_plan.md](docs/implementation_plan.md): phased plan
- [docs/DECISIONS.md](docs/DECISIONS.md): agreed design decisions

## Setup (backend, Windows PowerShell)

Prerequisites: Python 3.12, PostgreSQL 17 running locally with a non-superuser role `gedp_app` that owns the databases `gedp_dev` and `gedp_test`, and Git. (Node.js is needed from Phase 7.)

From the repository root:

```powershell
python -m venv .venv                       # skip if .venv already exists
.\.venv\Scripts\Activate.ps1
cd backend
pip install -r requirements-dev.txt
Copy-Item .env.example .env                # .env is git-ignored
notepad .env                               # replace both CHANGE_ME values with your gedp_app password
python -m src.core.config                  # checks settings; prints databases without the password
alembic upgrade head                       # creates/updates the schema in gedp_dev (additive)
```

Migrations: `alembic upgrade head` targets `DATABASE_URL`; `alembic -x db=test upgrade head` targets `TEST_DATABASE_URL`. `alembic check` reports any difference between the models and the migrations. The database URL is never stored in `alembic.ini`.

If the password contains special characters such as `@ : / ? # %`, URL-encode them in `.env` (for example `@` becomes `%40`).

## Running the API

From `backend/` with the virtual environment active:

```powershell
uvicorn src.main:app --reload
```

- `http://127.0.0.1:8000/health` returns `200 {"status":"ok","database":"ok"}` when `SELECT 1` succeeds, or `503 {"status":"degraded","database":"unavailable"}` when the database cannot be reached.
- `http://127.0.0.1:8000/docs` shows the interactive API documentation (OpenAPI).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service and database status (200 or 503) |
| GET | `/api/v1/dashboard/summary` | KPI counts, latest run, overview defaults |
| GET | `/api/v1/indicators` | Indicators with configured units and coverage |
| GET | `/api/v1/countries` | Countries present in the data |
| GET | `/api/v1/observations` | Filtered, sorted, paginated observations |
| GET | `/api/v1/analytics/trend` | Annual series per country (missing years are absent, never 0) |
| GET | `/api/v1/analytics/country-comparison` | One indicator and year across 2–10 countries, plus unavailable countries |
| GET | `/api/v1/runs`, `/api/v1/runs/{run_id}` | Run history; run detail with counts and quality checks (polling endpoint) |
| GET | `/api/v1/quality/latest` | Checks of the most recent finished run, including a failed one |
| POST | `/api/v1/pipeline/run` | Start a run: 202 + run ID; 409 if one is running; 403 if disabled or not from this machine |

Errors always use `{"error": {"code": "...", "message": "..."}}` and never include stack traces, SQL or credentials.

## Running the dashboard

Requires Node.js 24 LTS. Start the API first (above), then from `frontend/`:

```powershell
npm install        # first time only (uses package-lock.json)
npm run dev        # http://localhost:5173 ; /api and /health are proxied to http://127.0.0.1:8000
npm run build      # type check + production build into frontend/dist
npm test           # Vitest unit tests (API responses mocked)
```

Set `VITE_BACKEND_URL` to proxy to a different API address. The browser only calls the FastAPI backend; it never receives database credentials.

## Running the pipeline

From `backend/` with the virtual environment active (after `alembic upgrade head`):

```powershell
python -m src.pipeline.cli run                          # fetch, validate and load real World Bank data once
python -m src.pipeline.cli run --triggered-by scheduler # same, recorded as a scheduled run
```

The command prints the run ID, status and counts (extracted, rejected, null-skipped, duplicates dropped, load-ready, loaded, inserted, value changed). Exit codes: `0` success, `1` failed, `2` partial success, `3` another run is already in progress, `4` configuration or database startup error. Running it again on unchanged source data loads the same rows with `inserted=0 value_changed=0`, which shows the load is idempotent.

**Scheduled runs:** `scripts/run_pipeline.ps1` runs the same command with `--triggered-by scheduler` and logs to `logs/` (git-ignored). `scripts/register_task.ps1` creates a daily Windows Task Scheduler task; review it before running. See [docs/SCHEDULING.md](docs/SCHEDULING.md).

## Running tests

From `backend/` with the virtual environment active:

```powershell
pytest                       # all tests; integration tests are skipped if TEST_DATABASE_URL is not configured
pytest tests/unit            # unit tests only (no database needed)
pytest -m integration        # PostgreSQL integration tests (gedp_test only; each test is rolled back)
pytest --cov=src             # with a coverage report
```

Unit tests mock the database. Integration tests use only `TEST_DATABASE_URL`, which must name a `*_test` database different from `DATABASE_URL`. Tests that call the real World Bank API (from Phase 3) are marked `live` and excluded by default.

## Known limitations (planned design)

- Local/demo deployment only; the manual run endpoint has no authentication and must not be exposed publicly.
- API-triggered runs execute inside the API process; a server restart abandons the run, which is later marked failed by stale-run recovery.
- Annual data only; source coverage varies by country, indicator and year.

## Data source

Data comes from the World Bank Indicators API. Review the World Bank's terms of use and attribution requirements before any public release.

## License

Not yet chosen.
