# Global Economic Data Pipeline & Analytics Dashboard

> **Status: in development.** Phase 0 (requirements and repository foundation) is under review. **No application code exists yet.** Everything below describes the *planned* system; setup, usage and results sections will be filled in only as each phase is built and verified.

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
| Tests | pytest, httpx, Vitest |
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
| 0 | Requirements reconciliation, decision log, repository foundation | In review |
| 1 | Local environment, PostgreSQL, configuration, `/health` | Not started |
| 2 | Database schema, migrations, CI | Not started |
| 3 | World Bank API client | Not started |
| 4 | Transformation and validation | Not started |
| 5 | Idempotent loader, run lifecycle, CLI | Not started |
| 6 | Analytics and pipeline API | Not started |
| 7–8 | React dashboard | Not started |
| 9 | Scheduling (Windows Task Scheduler) | Not started |
| 10–11 | README finalization, screenshots, measured results | Not started |

## Repository layout (current)

```text
global-economic-data-pipeline/
├── docs/          # specifications and decision log (see docs/INDEX.md)
├── .gitignore
├── CLAUDE.md      # guidance for Claude Code
└── README.md
```

`backend/` and `frontend/` will be added in Phases 1 and 7.

## Documentation

- [docs/INDEX.md](docs/INDEX.md): reading order
- [docs/PRD.md](docs/PRD.md): product requirements
- [docs/TRD.md](docs/TRD.md): technical requirements and API contract
- [docs/Backend_DB_Schema.md](docs/Backend_DB_Schema.md): database design
- [docs/WebAppFlow.md](docs/WebAppFlow.md): user flows
- [docs/UIUX_design_spec.md](docs/UIUX_design_spec.md): UI/UX design
- [docs/implementation_plan.md](docs/implementation_plan.md): phased plan
- [docs/DECISIONS.md](docs/DECISIONS.md): agreed design decisions

## Setup

_To be written in Phase 1._ Planned prerequisites: Windows, Python 3.12, PostgreSQL (native install), Node.js LTS, Git.

## Running the pipeline

_To be written in Phase 5._

## Running tests

_To be written in Phase 2._ Automated tests will mock the World Bank API and use a dedicated test database.

## Known limitations (planned design)

- Local/demo deployment only; the manual run endpoint has no authentication and must not be exposed publicly.
- API-triggered runs execute inside the API process; a server restart abandons the run, which is later marked failed by stale-run recovery.
- Annual data only; source coverage varies by country, indicator and year.

## Data source

Data comes from the World Bank Indicators API. Review the World Bank's terms of use and attribution requirements before any public release.

## License

Not yet chosen.
