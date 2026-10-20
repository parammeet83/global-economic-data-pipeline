# Implementation Plan

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Version:** 1.1
- **Last updated:** 2026-10-19
- **Decisions:** changes from v1.0 are explained in `DECISIONS.md` (referenced as `D-xx`).

## 0. Repository state (2026-10-20)

- Phases 0–11 are implemented and pushed to `origin/main`; per-phase commits and actual test results are in `DEVELOPMENT_LOG.md`.
- The root `.venv` (Python 3.12.10) is the only Python environment; PostgreSQL 17 hosts `gedp_dev` and `gedp_test` (role `gedp_app`).
- Not done by design: the Windows scheduled task is prepared (`scripts/register_task.ps1`) but created by the owner; a code license has not been chosen; P1/P2 enhancements are deferred.

## 1. Approach

Build in small, testable vertical slices. The order matters: first make ingestion and storage correct; then expose the data through an API; then build the UI; add scheduling and deployment only after a manual run is reliable. Claude Code should work on one phase at a time and summarize all changed files and tests before moving on. CI is introduced as soon as the database layer is testable (end of Phase 2) and extended as layers are added, rather than at the end (D-32).

## 2. Phase-by-phase plan

### Phase 0 — Requirements and repository foundation
**Deliverables**
- Reconcile the six documents in `docs/` and record resolutions in `docs/DECISIONS.md`.
- Root `.gitignore` (including `node_modules/`, `reports/`, `coverage/`, `*.tsbuildinfo`), README skeleton labelled "in development".
- Dependency strategy (D-03) and configuration conventions (D-04) defined. No packages installed, no application code.

**Exit checks**
- Documents agree on name, stack, tables, endpoints, scope and the decisions in `DECISIONS.md`.
- No secrets or generated environment files tracked.
- The repository and `origin` remote already exist (D-02): `git status` and `git diff` reviewed by the owner before the Phase 0 commit; no push without explicit approval.

### Phase 1 — Local development environment
**Tasks**
- Verify Python 3.12.10 (root `.venv`, D-01), Git, Claude Code and Node.js LTS.
- Install PostgreSQL natively on Windows (17 preferred, ≥ 16). Create the non-superuser role `gedp_app` and the databases `gedp_dev` and `gedp_test`, both owned by `gedp_app` (D-05).
- Create `backend/requirements.txt` (runtime) and `backend/requirements-dev.txt` (`-r requirements.txt` + test tools). Install into the root `.venv` and pin exact versions only after they install and import on Windows (D-03).
- Create `backend/.env.example` (placeholders only) and a local, git-ignored `backend/.env`.
- Implement the `pydantic-settings` `Settings` class with startup validation (D-04).
- Scaffold the FastAPI app and the `/health` endpoint (D-27).

**Exit checks**
- Dependency installation succeeds on Windows.
- Backend starts locally and `/health` returns a valid response; an invalid setting fails startup with an actionable message.
- `.env` is ignored by Git and not shown in `git status`.

### Phase 2 — Database schema, migrations and CI
**Tasks**
- Implement SQLAlchemy models for `countries`, `indicators`, `economic_observations`, `pipeline_runs`, and `data_quality_checks` per `Backend_DB_Schema.md` v1.1.
- Add constraints, foreign keys and query-driven indexes, including the status/timestamp CHECKs and the partial unique index `uq_pipeline_runs_one_running` (D-19, D-21).
- Initialize Alembic and create/review the first migration.
- Implement session lifecycle and repository helpers.
- Implement the test-database guard (`TEST_DATABASE_URL` must name a `*_test` database different from `DATABASE_URL`) and migration-based test setup (D-06).
- Add `.github/workflows/ci.yml`: Python 3.12, PostgreSQL service container, install `requirements-dev.txt`, `alembic upgrade head`, `pytest` (D-32).

**Exit checks**
- `alembic upgrade head` creates the schema in a fresh database.
- Integration tests validate foreign keys, the primary key, CHECK constraints, the single-`running`-row guard, and transaction rollback.
- Schema can be recreated from migrations without undocumented manual steps.
- CI passes on GitHub with no dependency on the World Bank API (after the owner approves the push).

### Phase 3 — World Bank API client
**Tasks**
- Implement request wrapper with timeouts, retry/backoff, transient/permanent error classification, and JSON checks, following the response classification table in TRD §5, including **World Bank error payloads returned with HTTP 200**.
- Implement page metadata parsing, full pagination, and the rows-received = `total` check.
- Fetch country metadata (ISO-3 `id`, aggregate detection) and indicator metadata; fetch one series per indicator for all configured countries and the configured year window (D-08, D-10).
- Keep configuration and the HTTP session injectable for tests.

**Exit checks**
- Mocked unit tests cover success, valid empty result, null values, bad JSON, HTTP errors, HTTP-200 error payload, retry behavior (including `Retry-After`) and multi-page results.
- Optional live smoke test (marked `live`, excluded by default and from CI) fetches a small known public request.
- API failure cannot be mistaken for an empty but successful dataset.

### Phase 4 — Transformation and validation
**Tasks**
- Normalize source payloads into a documented record shape, reading `countryiso3code` (never `country.id`).
- Use pandas for column naming, dtype normalization, year parsing, null accounting and de-duplication on `(country_code, indicator_code, year)` before loading (D-13).
- Use Pandera to define the core data schema/checks, adapting to the installed version's supported API.
- Split valid rows from rejected rows with sanitized rejection reasons; compute counts E, R, N, D, T and the check results defined in `Backend_DB_Schema.md` §3.3 and §3.5.
- Optional JSON export of the run report (`WRITE_JSON_REPORT`); no Markdown/HTML report (D-16).

**Exit checks**
- Deterministic fixture-based tests for each transform and validation rule.
- Null source values are counted, never replaced by zero.
- Invalid numeric values / invalid year / missing or non-ISO-3 identifiers are rejected and reported.
- Count identity `E = R + N + D + T` holds in tests; identical vs conflicting duplicates are distinguished.

### Phase 5 — Loader and orchestration
**Tasks**
- Implement dimension upserts and the unconditional observation upsert with the `(country_code, indicator_code, year)` conflict key, and compute inserted / value-changed counts (D-11, D-14).
- Implement the run lifecycle (D-18): claim transaction with stale-run recovery (D-20) → in-memory extract/transform/validate → single load + finalize transaction with a conditional status update → separate failure finalization.
- Apply the run status rules (TRD §6) and record counts, quality checks, duration and sanitized errors.
- Add a CLI command to execute the complete pipeline, with `--triggered-by` and the exit codes in TRD §13.

**Exit checks**
- Running the same input twice does not duplicate observations; the second run reports `records_inserted = 0` and `records_value_changed = 0`.
- Failed writes roll back as intended, the run record survives, and it is finalized as `failed` where possible.
- A second concurrent claim is refused; a stale `running` row is recovered as `failed`.
- Every run creates durable status/count metadata and quality-check rows.
- `success`, `partial_success`, and `failed` definitions are documented (TRD §6) and tested.

### Phase 6 — Backend analytics API
**Tasks**
- Implement typed FastAPI routes for summary (including `defaults`), countries, indicators, observations, trend, comparison, run history/details and latest quality.
- Add pagination, input validation, consistent error bodies and CORS configuration (D-25).
- Add the manual trigger endpoint: synchronous claim, **202** with run ID, background execution via FastAPI `BackgroundTasks`, **409** on overlap, **403** when `ENABLE_MANUAL_TRIGGER` is false; local/demo only (D-23).
- Add API tests using the dedicated test database.

**Exit checks**
- OpenAPI docs render locally.
- Test valid and invalid filters, empty DB, unavailable DB, 202/409/403 trigger responses, polling via `GET /api/v1/runs/{run_id}`, and normal responses.
- Frontend does not need database credentials.

### Phase 7 — Frontend foundation and overview
**Tasks**
- Scaffold React + TypeScript + Vite; commit `package-lock.json` (D-03).
- Define layout, navigation, CSS-variable theme tokens, typed API client, loading/error primitives.
- Build Overview page with real summary data, configured defaults and latest run status.
- Build initial shell (desktop first, no clipping at 320 px, D-29).
- Add a frontend job to CI: `npm ci` and `npm run build`.

**Exit checks**
- Frontend builds cleanly locally and in CI.
- Loading, empty, success and error states are covered.
- Overview figures agree with backend responses.

### Phase 8 — Analytics, runs and quality screens
**Tasks**
- Build Explore Data filters, trend chart and observation table.
- Build Compare Countries bar chart and missing-data display.
- Build Pipeline Runs history/detail with safe manual trigger flow (202 → poll every 3 s, 409, 403, 10-minute polling timeout).
- Build Data Quality and About & Sources.
- Add Vitest + React Testing Library tests for important states, formatting and missing-value rendering, and run them in CI (D-28).

**Exit checks**
- All filters call real backend endpoints; no hard-coded dashboard metrics.
- Chart/table values and units agree.
- Missing values are gaps/unavailable rather than zero.
- Pipeline action shows progress, handles conflicts and refreshes run history.

### Phase 9 — Scheduling and robustness
**Tasks**
- Only after manual execution is stable, schedule the CLI with **Windows Task Scheduler** (`--triggered-by scheduler`, "Do not start a new instance", Windows local time zone) and document the setup step by step in the README (D-31).
- Do not add APScheduler, Airflow or Prefect without a specific, written benefit (D-33).
- Overlap behavior is already covered by Phase 5–6 tests; verify one scheduled run manually instead of writing tests for scheduler configuration.

**Exit checks**
- Schedule can be disabled (by disabling the task) without code or configuration changes.
- No in-process scheduler exists, so application shutdown cannot leave one running.
- Scheduled successes and failures are visible in run history and logs, and Task Scheduler's "Last Run Result" matches the CLI exit code.

### Phase 10 — README, CI hardening and GitHub
**Tasks**
- Confirm CI covers backend pytest (with PostgreSQL service), frontend build and frontend tests on push and pull request.
- Finalize README architecture diagram, prerequisites, setup, migration, execution, tests, screenshots, troubleshooting and limitations (including the background-run and stale-recovery limitations).
- Add a license only after choosing an appropriate license.
- Review `.gitignore`, `git diff`, status and secret exposure before every push.
- Push to the existing `origin` remote only after explicit review (D-02).

**Exit checks**
- Fresh-clone setup is documented and tested.
- CI passes on GitHub.
- No `.env`, database dump, virtual environment, cache, log, or local report containing sensitive information is committed.
- README includes genuine screenshots and actual, measured results—not invented metrics.

### Phase 11 — Resume polish and optional extensions
**Tasks**
- Capture screenshots/GIF of the working dashboard.
- Add a small architecture diagram and sample quality report.
- Record real measured run time, rows loaded, test count and coverage only after measuring them.
- Consider CSV export and other P1 items, then Docker Compose, Airflow/Prefect or cloud hosting (P2), as separate enhancements.

**Exit checks**
- A technical interviewer can reproduce one run and explain retry, pagination, validation, idempotency and monitoring decisions.

## 3. Recommended beginner work rhythm

For every phase:
1. Ask Claude Code to inspect the relevant documents and implement only that phase.
2. Review the proposed changes before accepting them.
3. Run the exact test or command shown in the instructions.
4. If it fails, send Claude Code the full error plus the relevant file; do not paste secrets.
5. Review `git diff` before committing.
6. Commit a coherent milestone with a descriptive message.

Do not ask Claude Code to “build the entire app” in one prompt. That commonly creates inconsistent interfaces, dependency drift, missing tests, and code that has not been run end to end.

## 4. Suggested milestone commits

- ~~`docs: add product and technical specifications`~~: already done as `cf67e9d chore: add project documentation and setup`
- `docs: reconcile specifications and add decision log` (Phase 0)
- `chore: scaffold backend environment and health check` (Phase 1)
- `feat(db): add schema and migrations` + `ci: add backend tests with PostgreSQL` (Phase 2)
- `feat(ingestion): add World Bank API client`
- `feat(pipeline): add validation and idempotent loader`
- `feat(api): expose analytics and pipeline endpoints`
- `feat(ui): add analytics dashboard` (with `ci: add frontend build` / tests)
- `docs: document Task Scheduler setup`
- `docs: finalize setup and portfolio README`

Use commit messages that describe real completed work; do not create these commits before the corresponding functionality exists.

## 5. Definition of done

The project is ready to feature prominently on a resume only when it can be cloned and run, ingests real data, validates it, upserts without duplicates, retains run history, exposes working API endpoints, displays the real values in a UI, passes meaningful tests, runs CI, and documents limitations. A folder of generated files or a dashboard backed by hard-coded numbers does not meet this bar.
