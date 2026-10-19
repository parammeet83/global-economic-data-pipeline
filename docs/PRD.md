# Product Requirements Document (PRD)

**Project:** Global Economic Data Pipeline & Analytics Dashboard  
**Document version:** 1.0  
**Status:** Initial product baseline  
**Last updated:** 2026-10-19

## 1. Product summary

Build a portfolio-ready application that automatically collects public economic indicators from the World Bank API, cleans and validates the records, loads them idempotently into PostgreSQL, and presents trusted data through a web dashboard. The project must demonstrate reliable data engineering practices—not only a notebook or a one-time CSV import.

**Primary data source:** [World Bank Indicators API documentation](https://datahelpdesk.worldbank.org/knowledgebase/topics/125589-developer-information)  
**Example API request:** [India GDP observations](https://api.worldbank.org/v2/country/IND/indicator/NY.GDP.MKTP.CD?format=json&per_page=10)

No external dataset download is required for the core project. The application fetches records from the API. Optional CSV export is a product feature, not the primary ingestion method.

## 2. Problem statement

Analysts often need to bring public economic data into a consistent shape before they can compare countries or years. Manual downloads and notebook-only workflows are difficult to repeat, observe, test, and explain. This project provides a repeatable pipeline plus an interface to inspect trends, freshness, and data-quality outcomes.

## 3. Goals

1. Retrieve economic indicator observations from a public API with timeouts, retry/backoff, and pagination support.
2. Standardize records using pandas and reject or quarantine invalid records through explicit validation rules.
3. Store country, indicator, observation, run, and quality metadata in PostgreSQL.
4. Make reruns safe: reloading the same country-indicator-year must update the existing record rather than create a duplicate.
5. Expose read and pipeline-control endpoints through a FastAPI service.
6. Provide a responsive web dashboard for high-level KPIs, indicator trends, country comparisons, raw observation browsing, run history, and quality results.
7. Add automated tests, structured logs, and a per-run data-quality report.
8. Document setup and operations so a reviewer can clone and run the project locally.

## 4. Non-goals for the first release

- Financial advice, forecasting, causal inference, or investment recommendations.
- Building a proprietary economic dataset or redistributing data without checking source terms.
- Replacing a production orchestration platform such as Airflow or Prefect in the MVP.
- Multi-tenant access control, enterprise SSO, or public internet deployment with an unauthenticated run-trigger endpoint.
- A complex BI tool with arbitrary drag-and-drop reports.
- Guaranteeing that the source has a value for every country, indicator, and year.

## 5. Intended users

### Primary: Student / project owner
Needs to configure, run, test, debug, and explain the pipeline and its design decisions.

### Secondary: Recruiter or technical interviewer
Needs a clear README, reproducible setup, architecture, meaningful tests, visible output, and evidence of correct handling of failures and duplicate loads.

### Tertiary: Analyst / dashboard viewer
Needs to select countries, indicators, and years; interpret units and gaps; and assess whether the displayed data was loaded successfully.

## 6. Scope and data

### Initial indicators

| Display name | World Bank indicator code | Unit / interpretation |
|---|---|---|
| GDP (current US$) | `NY.GDP.MKTP.CD` | Current US dollars; nominal, not inflation-adjusted |
| Population, total | `SP.POP.TOTL` | People |
| Unemployment, total (% of total labor force), modeled ILO estimate | `SL.UEM.TOTL.ZS` | Percent |

The source's available years and coverage vary by indicator and country. Missing values are valid source conditions and must not be silently converted to zero. Store the observation year as an integer and retain the source value as numeric data.

### Initial geographic scope

Start with a configurable set of countries to keep the first run manageable (for example: IND, USA, GBR, DEU, JPN, CHN, BRA, ZAF, CAN, AUS). Design extraction so the country list can be expanded later without changing the schema. Country and indicator selection must be configuration-driven, not scattered through the code.

### Historical window

Default to the latest 20 calendar years available, with configurable `START_YEAR` and `END_YEAR`. Do not assume every requested year exists in the source.

## 7. User stories and acceptance criteria

### Ingestion
- As the project owner, I can run the pipeline from a documented command.
- Given a temporary API error, the client retries a bounded number of times and records the final outcome.
- Given a multi-page API response, the extraction retrieves all pages before marking extraction complete.
- Given the same source data is loaded twice, the database has no duplicate observations for the same country, indicator, and year.

**Acceptance:** unit tests cover pagination, retries, malformed responses, and duplicate-safe loading; a manual integration run completes against the public API.

### Validation and quality
- As a viewer, I can see the last run's counts and quality status.
- Invalid rows are rejected or quarantined with a reason; they are not silently loaded as trustworthy observations.
- Each completed run creates a machine-readable quality report.

**Acceptance:** required-field, type, uniqueness, and domain rules are tested; report includes extracted, transformed, loaded, rejected, and null-value counts where available.

### Analytics dashboard
- As an analyst, I can choose an indicator, country/countries, and year range to view observations or trends.
- As an analyst, I can compare selected countries for a chosen year when values exist.
- As a reviewer, I can inspect recent runs and their status, duration, row counts, and errors.

**Acceptance:** loading, empty, error, and success states are designed; filters are reflected in API requests; charts display correct units and missing data as gaps rather than zero.

### Operations
- As the project owner, I can run tests and see the result before pushing code.
- As a reviewer, I can reproduce setup from the README using Python 3.12, PostgreSQL, and Node.js.

**Acceptance:** test commands and setup instructions are documented; GitHub Actions runs backend tests and frontend build checks on pushes and pull requests.

## 8. Product requirements

### P0 — required for initial portfolio release
- World Bank API extraction with timeout, bounded retry/backoff, response checks, and pagination.
- Configurable country list, indicators, year range, and request settings.
- pandas-based transformations and Pandera data-quality schema/checks.
- PostgreSQL schema managed by migrations (Alembic is the planned tool).
- SQLAlchemy upsert keyed by country code + indicator code + year.
- Run metadata and quality-check metadata persisted to the database.
- FastAPI endpoints for health, dashboard summary, observations, trends, country comparisons, run history/details, latest quality report, and manually triggered run.
- React + TypeScript dashboard with overview, trends/comparison, observations table, pipeline runs, and data quality views.
- pytest tests for core pipeline and API; frontend production build check.
- Structured logs, `.env.example`, `.gitignore`, setup guide, screenshots or GIF in README after UI exists.
- Git repository with GitHub Actions CI.

### P1 — recommended after P0 is stable
- Automatic scheduling via APScheduler or an OS scheduler, with timezone and duplicate-run safeguards.
- CSV export from filtered observations.
- Docker Compose for reproducible local PostgreSQL and application setup.
- Data freshness badges and run-duration / record-count history charts.
- Basic accessibility review and mobile layouts.

### P2 — optional extensions
- Airflow or Prefect orchestration.
- Cloud deployment and managed PostgreSQL.
- Authentication/authorization before any public deployment of pipeline controls.
- Additional indicators, countries, or sources.

## 9. Success metrics

- A fresh clone can be configured and run following the README without undocumented manual edits.
- Pipeline is idempotent: repeated loads do not increase duplicate-key counts.
- Automated tests cover key transformation, validation, API route, and database upsert behavior.
- Each run is traceable by a unique run ID and has a final status (`success`, `partial_success`, or `failed`).
- Dashboard values agree with database queries for the same filters.
- CI passes on the default branch.
- README explains assumptions, architecture, setup, test commands, and known limitations.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| API downtime, rate limiting, or slow responses | Set timeouts; bounded retry/backoff; log failed endpoints; mark a run failed or partial instead of silently succeeding |
| Incomplete source coverage | Preserve null/source gaps; show actual observation coverage; never fill missing values with zero |
| Duplicate rows on rerun | Database composite unique key and transactional upsert |
| Secrets accidentally committed | `.env` ignored; safe `.env.example`; inspect `git status` before the first commit |
| Beginner setup complexity | Build in phases; prove each layer works before adding scheduler/deployment |
| Over-scoping | Keep P0 small; do not add Airflow, cloud hosting, auth, or forecasting before the pipeline and dashboard work end to end |

## 11. Assumptions and open decisions

- Development environment is Windows with Python 3.12.x and VS Code.
- The World Bank API is the initial source; it is public and commonly does not require an API key for these endpoints.
- PostgreSQL is the system of record; browser code never connects directly to the database.
- The first version is local/demo use. Do not expose run-trigger endpoints publicly without adding authentication and operational safeguards.
- The user will review Claude Code changes and run commands deliberately; Claude Code should not make destructive changes or push to GitHub without explicit confirmation.
