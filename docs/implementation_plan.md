# Implementation Plan

**Project:** Global Economic Data Pipeline & Analytics Dashboard  
**Version:** 1.0  
**Last updated:** 2026-10-19

## 1. Approach

Build in small, testable vertical slices. The order matters: first make ingestion and storage correct; then expose the data through an API; then build the UI; add scheduling and deployment only after a manual run is reliable. Claude Code should work on one phase at a time and summarize all changed files and tests before moving on.

## 2. Phase-by-phase plan

### Phase 0 — Requirements and repository foundation
**Deliverables**
- Finalize these six documents in `docs/`.
- Root `.gitignore`, README skeleton and repository structure.
- Choose package manager / dependency strategy and define configuration conventions.

**Exit checks**
- Documents agree on name, stack, tables, endpoints and scope.
- No secrets or generated environment files tracked.
- Git initial status reviewed before first commit.

### Phase 1 — Local development environment
**Tasks**
- Verify Python 3.12, Git, Claude Code, Node.js LTS and PostgreSQL installation.
- Create and activate a Python virtual environment in `backend/.venv` (or a root virtual environment if chosen; document one convention and use it consistently).
- Create `backend/requirements.txt`, `backend/.env.example`, and local ignored `.env`.
- Verify PostgreSQL service and create a project database plus a non-superuser application role where practical.
- Scaffold the FastAPI app and a `/health` endpoint.

**Exit checks**
- Dependency installation succeeds on Windows.
- Backend starts locally and `/health` returns a valid response.
- `.env` is ignored by Git and not shown in `git status`.

### Phase 2 — Database schema and migrations
**Tasks**
- Implement SQLAlchemy models for `countries`, `indicators`, `economic_observations`, `pipeline_runs`, and `data_quality_checks`.
- Add constraints, foreign keys and query-driven indexes from `Backend_DB_Schema.md`.
- Initialize Alembic and create/review the first migration.
- Implement session lifecycle and repository helpers.

**Exit checks**
- `alembic upgrade head` creates the schema in a fresh database.
- Integration tests validate foreign keys, unique business key, and transaction behavior.
- Schema can be recreated from migrations without undocumented manual steps.

### Phase 3 — World Bank API client
**Tasks**
- Implement request wrapper with timeouts, retry/backoff, transient/permanent error classification, and JSON checks.
- Implement page metadata parsing and full pagination.
- Fetch country/indicator metadata and configured country/indicator/year combinations.
- Keep configuration injectable for tests.

**Exit checks**
- Mocked unit tests cover success, empty values, bad JSON, HTTP errors, retry behavior and multi-page results.
- Optional live smoke test fetches a small known public request.
- API failure cannot be mistaken for an empty but successful dataset.

### Phase 4 — Transformation and validation
**Tasks**
- Normalize source payloads into a documented record shape.
- Use pandas for column naming, dtype normalization, year parsing, duplicate identification and null accounting.
- Use Pandera to define the core data schema/checks, adapting to the installed version's supported API.
- Split valid rows from rejected rows with sanitized rejection reasons.
- Generate an initial JSON/Markdown quality report.

**Exit checks**
- Deterministic fixture-based tests for each transform and validation rule.
- Null source values are counted, never replaced by zero.
- Invalid numeric values / invalid year / missing identifiers are rejected and reported.

### Phase 5 — Loader and orchestration
**Tasks**
- Implement dimension upserts and observation upsert with `(country_code, indicator_code, year)` conflict key.
- Record run start, counts, quality outcomes, duration and sanitized errors.
- Define transaction boundaries and terminal status behavior.
- Add a CLI command to execute the complete pipeline.

**Exit checks**
- Running the same input twice does not duplicate observations.
- Failed writes roll back as intended and the run record is finalized where possible.
- Every run creates durable status/count metadata and a quality report.
- `success`, `partial_success`, and `failed` definitions are documented and tested.

### Phase 6 — Backend analytics API
**Tasks**
- Implement typed FastAPI routes for summary, countries, indicators, observations, trend, comparison, run history/details and quality summary.
- Add pagination, input validation, consistent errors and CORS configuration.
- Add a manual trigger endpoint that prevents overlapping runs and is only for local/demo use in MVP.
- Add API tests using a test database or isolated fixtures.

**Exit checks**
- OpenAPI docs render locally.
- Test valid and invalid filters, empty DB, unavailable DB, run conflict and normal responses.
- Frontend does not need database credentials.

### Phase 7 — Frontend foundation and overview
**Tasks**
- Scaffold React + TypeScript + Vite.
- Define layout, navigation, theme tokens, typed API client, loading/error primitives.
- Build Overview page with real summary data and latest run status.
- Build initial responsive shell.

**Exit checks**
- Frontend builds cleanly.
- Loading, empty, success and error states are covered.
- Overview figures agree with backend responses.

### Phase 8 — Analytics, runs and quality screens
**Tasks**
- Build Explore Data filters, trend chart and observation table.
- Build Compare Countries bar chart and missing-data display.
- Build Pipeline Runs history/detail with safe manual trigger flow.
- Build Data Quality and About & Sources.
- Add component tests for important states and formatting.

**Exit checks**
- All filters call real backend endpoints; no hard-coded dashboard metrics.
- Chart/table values and units agree.
- Missing values are gaps/unavailable rather than zero.
- Pipeline action shows progress, handles conflicts and refreshes run history.

### Phase 9 — Scheduling and robustness
**Tasks**
- Only after manual execution is stable, add local scheduling with a documented timezone and one-run-at-a-time guard.
- Evaluate APScheduler or Windows Task Scheduler for the local version; do not add Airflow/Prefect without a specific benefit.
- Add tests for run overlap and schedule configuration.

**Exit checks**
- Schedule can be disabled through configuration.
- Application shutdown does not leave an uncontrolled scheduler.
- Scheduled failures are visible in run history and logs.

### Phase 10 — CI, README and GitHub
**Tasks**
- Add GitHub Actions to install backend dependencies, run pytest, install frontend dependencies and run frontend build/tests.
- Finalize README architecture diagram, prerequisites, setup, migration, execution, tests, screenshots, troubleshooting and limitations.
- Add a license only after choosing an appropriate license.
- Review `.gitignore`, `git diff`, status and secret exposure before first push.
- Create the remote repository and push the default branch after explicit review.

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
- Consider Docker Compose, CSV export, Airflow/Prefect or cloud hosting as separate enhancements.

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

- `docs: add product and technical specifications`
- `chore: scaffold backend and frontend`
- `feat(db): add schema and migrations`
- `feat(ingestion): add World Bank API client`
- `feat(pipeline): add validation and idempotent loader`
- `feat(api): expose analytics and pipeline endpoints`
- `feat(ui): add analytics dashboard`
- `test: add pipeline and API coverage`
- `ci: add GitHub Actions checks`
- `docs: finalize setup and portfolio README`

Use commit messages that describe real completed work; do not create these commits before the corresponding functionality exists.

## 5. Definition of done

The project is ready to feature prominently on a resume only when it can be cloned and run, ingests real data, validates it, upserts without duplicates, retains run history, exposes working API endpoints, displays the real values in a UI, passes meaningful tests, runs CI, and documents limitations. A folder of generated files or a dashboard backed by hard-coded numbers does not meet this bar.
