# Development Log

Per-phase record of what was built and verified. Test counts are copied from actual runs on the development machine (Windows, Python 3.12.10, PostgreSQL 17.11). A phase's commit hash is recorded in the next entry, because a commit cannot contain its own hash.

| Phase | Commit | Summary |
|---|---|---|
| 0 | `5a0a763` | Specifications reconciled; decision log; README skeleton |
| 1 | `477dcfb` | Settings, `/health`, unit + integration tests (26 passed) |
| 2 | `a3892da` | Schema, migrations, repositories, CI (48 passed) |
| 3 | `a40d4af` | World Bank client: classification, retries, pagination (71 passed) |
| 4 | `34b281c` | pandas/Pandera transform, counts, quality checks, status rules (105 passed) |
| 5 | `1b4d868` | Loader, run lifecycle, orchestrator, CLI (127 passed) |
| 6 | `9543340` | FastAPI analytics, runs, quality and trigger endpoints (157 passed) |
| 7 | `237abe4` | React/TypeScript/Vite shell, API client, Overview page, frontend CI (Vitest 5 passed) |
| 8 | `35705dd` | Explore, Compare, Runs (trigger + polling), Run detail, Quality, About (Vitest 26 passed) |
| 9 | `cd8c4f0` | Windows Task Scheduler wrapper, registration script, guide |
| 10 | `de53453` | Fix: unit-test settings isolated from environment variables (found by fresh-clone check) |
| 10–11 | see final report | README, screenshots, sample report, fresh-clone verification, docs sync |

## Phase 2 — Database schema, migrations and CI

**Built**
- SQLAlchemy models for the five tables with all Schema §6 constraints, deterministic constraint names and the partial unique index `uq_pipeline_runs_one_running` (`backend/src/db/models.py`).
- Alembic configured to read the URL from settings (`-x db=test` for the test database); reviewed initial migration `0001`.
- Upsert helpers for countries, indicators and observations, plus `fetch_existing_values` (`backend/src/db/repositories.py`).
- Non-destructive test isolation (D-37) and GitHub Actions CI with a PostgreSQL 17 service container.

**Verified**
- `alembic upgrade head` on the empty `gedp_dev`: revision `0001 (head)`; `alembic check`: no drift.
- `pytest` (from `backend/`): **48 passed**, 94% coverage, no warnings. Integration tests cover migration upgrade/downgrade/upgrade in a throwaway schema, model/migration parity, every constraint family, the one-running-run guard, upsert idempotency and rollback.
- After the run, `gedp_test` tables held 0 rows and no temporary schemas remained.

**CI on GitHub:** the repository is private, so the Actions result could not be read without credentials; check the repository's Actions tab. The same steps (migrate, `alembic check`, `pytest`) pass locally.

## Phase 3 — World Bank API client

**Built** (`backend/src/pipeline/worldbank.py`)
- Response classification per TRD §5: transport errors, retryable HTTP (429/5xx, `Retry-After` honored, capped), permanent HTTP, malformed JSON/shape, World Bank error payloads returned with HTTP 200, and the single valid-empty case.
- Bounded exponential backoff (1 + `MAX_RETRIES` attempts), full pagination with page-count and row-total checks, country metadata with aggregate detection, indicator metadata, and one series per indicator for all countries.
- Error messages carry the endpoint and failure class only, never response bodies.

**Live API observations** (2026-10-20): error payloads arrive with HTTP 200; `per_page` is sometimes a string; aggregates have region "Aggregates"; a `date` range with no data can be ignored by the API (handled by `year_in_range`).

**Verified**
- `pytest tests/unit/test_worldbank_client.py`: **23 passed** (all HTTP mocked).
- Optional live smoke test (`pytest -m live`): **1 passed** against the real API (2 pages, 4 rows).

## Phase 4 — Transformation and validation

**Built**
- `backend/src/pipeline/transform.py`: pandas normalization (ISO-3 from `countryiso3code`, trimmed/upper-cased codes, strict 4-digit years, numeric values), a lazy Pandera schema whose named checks are the rejection rules, null skipping, first-occurrence de-duplication with identical/conflicting detection, Decimal values at 6 decimal places, and a strict Pandera schema on the load-ready frame. Enforces `E = R + N + D + T`.
- `backend/src/pipeline/quality.py`: the nine check builders (D-17), the run-status rules (D-15) and the optional JSON report export (D-16).
- Library versions: pandas 3.0.6, NumPy 2.5.4, Pandera 0.34.1 (imported as `pandera.pandas`).

**Verified**
- `pytest tests/unit/test_transform.py tests/unit/test_quality.py`: **34 passed**, no warnings.
- Live extract + transform (no database writes) on the configured scope, 10 countries × 3 indicators × 2005–2024: E=600, R=0, N=0, D=0, T=600, all checks passed (2026-10-20).

## Phase 5 — Loader, orchestration and CLI

**Built**
- `backend/src/pipeline/runs.py`: claim transaction with stale-run recovery (T1), conditional terminal update, separate failure finalization (T3); refused overlapping claims raise `RunInProgressError` (D-18, D-19, D-20).
- `backend/src/pipeline/orchestrator.py`: `start_run` / `execute_run` / `run_pipeline`, shared by the CLI and (Phase 6) the API. Load, quality checks and terminal status commit in one transaction (T2); inserted and value-changed counts come from existing values read inside that transaction.
- `backend/src/pipeline/cli.py`: `python -m src.pipeline.cli run [--triggered-by cli|scheduler]` with exit codes 0–4.
- Database timestamps: `started_at` uses `now()`, `finished_at` uses `clock_timestamp()` so durations are wall-clock accurate across transactions.

**Verified**
- `pytest` (from `backend/`): **127 passed**, 96% coverage. New integration tests cover success, idempotent rerun, value changes, nulls, partial success (failed series, rejected rows, pagination error), failed runs (all series, metadata error payload, aggregate code), load rollback with a durable run record, refused overlapping claim, stale recovery, a stale-recovered run unable to commit, the JSON export and CLI exit codes 0–4.
- Real data, `gedp_dev`, 2026-10-20: run 1 `success` loaded=600 inserted=600 value_changed=0 (pipeline 3.77 s); run 2 `success` loaded=600 inserted=0 value_changed=0 (1.78 s). Database: 600 observations, 600 distinct keys, 10 countries, 3 indicators, 18 passed checks, no zero-filled values.

## Phase 6 — Backend analytics API

**Built**
- Endpoints from TRD §7: dashboard summary (with configured defaults), indicators (units, coverage), countries, observations (filters, allow-listed sort with primary-key tie-break, pagination), trend, country comparison (sorted, with unavailable countries), run list/detail (polling), latest quality (most recent terminal run), and `POST /api/v1/pipeline/run` (202 + run ID, background execution through the shared orchestrator, 409, 403).
- One error shape for 404/405/409/403/422/503/500 with no stack traces, SQL or driver messages; CORS limited to `CORS_ORIGINS`; loopback-only trigger (D-38).

**Verified**
- `pytest`: **157 passed**, 97% coverage, no warnings (30 new API tests: contract, validation, empty database, unavailable database, unexpected error, CORS, 202/409/403 including a non-local client).
- Live server against `gedp_dev` (2026-10-20): all endpoints returned real data (600 observations, 10 countries, 3 indicators); a manual run via POST returned 202, a second POST returned 409 while it ran, and polling reached `success` with loaded=600 inserted=0 value_changed=0.

## Phase 7 — Frontend foundation and Overview

**Built** (`frontend/`)
- React 19 + TypeScript 7 + Vite 8 + Recharts 3 + React Router 7 (versions locked in `package-lock.json`, Node.js 24). Vite proxies `/api` and `/health` to FastAPI, so the browser uses relative URLs only.
- Typed API client that separates "backend unreachable" from HTTP errors; `useApi` hook with abort handling; design tokens as CSS variables; layout with sidebar, active route and live health indicator; loading/skeleton, error-with-retry and empty states; status badges with text; unit-aware number formatting that renders missing values as "—".
- Overview page: KPIs, failed-run warning, trend preview from the backend's configured defaults (gaps for missing years), recent runs and latest quality verdict (never "passed" for a failed run or failed check).
- CI: a frontend job runs `npm ci`, `npm run build` and `npm test`.

**Verified**
- `npm run build`: type check and production build succeed (one Vite advisory about a 639 kB bundle, addressed in Phase 8).
- `npm test`: **5 passed** (loading, data, empty database, backend unreachable, database outage, failed latest run).
- Real end-to-end: API on `gedp_dev` + Vite dev server, captured with headless Edge — the Overview showed 10 countries, 3 indicators, 600 observations, the GDP trend for the five default countries, three real runs and "All checks passed".

## Phase 8 — Analytics, runs and quality screens

**Built**
- Explore Data (validated filters, Apply, filter chips, trend chart, sortable server-paginated table as the chart's table alternative), Compare Countries (2–10 countries, year from coverage, sorted bar chart + table, unavailable countries listed instead of zero), Pipeline Runs (history, confirmation dialog, POST trigger, 3 s polling with 10-minute timeout, 409/403 messages), Run detail (full count breakdown, summary, checks, copy run ID, live refresh while running), Data Quality (verdict, checks, explanation of warnings vs failures) and About & Sources (World Bank source, indicators with units and coverage, limitations).
- Route-level code splitting removed the Phase 7 bundle-size advisory.
- Narrow widths (D-29): at a true 320 px viewport, filters and controls fit; only data tables scroll horizontally. Long indicator names in `<select>` no longer widen the page.

**Verified**
- `npm run build`: succeeds with no warnings.
- `npm test`: **26 passed** in 7 files (formatting and missing values, chart gaps as null, filter validation and request parameters, comparison unavailable list, trigger confirm → 202 → polling → success, cancel, 409, 403, quality never green for a failed run, Overview states).
- Real end-to-end: every page captured with headless Edge against the API and `gedp_dev`, at 1440 px and at a true 320 px viewport.

## Phase 9 — Scheduling

**Built**
- `scripts/run_pipeline.ps1`: runs `python -m src.pipeline.cli run --triggered-by scheduler` from `backend/` with the root `.venv`, logs to `logs/` (git-ignored) and exits with the CLI exit code.
- `scripts/register_task.ps1`: creates a daily task (logged-on user, no stored password, "do not start a new instance", 1-hour limit). **Not run**: creating a Windows scheduled task is left to the owner.
- `docs/SCHEDULING.md`: setup (script or Task Scheduler UI), verification, disable/remove commands, exit-code table, troubleshooting.

**Incident during verification (resolved)**
- The first wrapper version piped the CLI's stderr through Windows PowerShell 5.1 with `$ErrorActionPreference = "Stop"`. The first log line on stderr became a terminating error, aborting the script and killing the run it had just claimed (`6036dd1f`), which was left `running`.
- Fix: `cmd.exe` now performs the redirection and the exit code comes straight from Python.
- The orphaned row was cleared by the application's own stale-run recovery (D-20), not by editing the database. The fixed wrapper was run with `STALE_RUN_MINUTES=1` for that invocation only. Before the threshold passed, two attempts were correctly refused with exit code 3. After it, the claim logged `recovered_stale=true`, the abandoned run became `failed` with the standard "Abandoned" summary (kept in history), and scheduled run `4f258275` succeeded.

**Verified**
- Scheduled-style run via the wrapper: exit code 0, `triggered_by=scheduler`, loaded=600, inserted=0, value_changed=0, log written to `logs/`.
- Overlap refusal (exit 3) and stale recovery were observed for real on `gedp_dev`.
- Not verified: an actual Task Scheduler trigger, because the task has not been created.

## Phases 10–11 — CI, README, GitHub and portfolio polish

**Fresh-clone verification** (clone of `origin/main` at `cd8c4f0` into a temporary folder, without its own `.env`, `.venv` or `node_modules`; tested with the root `.venv`, database URLs passed through the environment):
- `alembic -x db=test check`: no drift.
- `pytest`: **1 failed, 156 passed** — `test_defaults_load_with_only_database_url` failed because `TEST_DATABASE_URL` was set as an environment variable, exactly as CI sets it. The unit-test settings fixture ignored `backend/.env` but not the environment, so **the backend CI job was most likely failing since Phase 2** (the private repository's Actions results could not be read here).
- Fix `de53453`: the fixture clears every setting variable per test. Afterwards: 157 passed locally; unit suite passes with CI-style variables set.
- Frontend from the clone: `npm ci` (146 packages), `npm run build` clean, `npm test` **26 passed**. The lock file contains the Linux x64 native packages (Rolldown, LightningCSS, TypeScript 7) that CI needs.

**Portfolio material**
- README rewritten from verified facts: architecture (Mermaid), setup from a fresh clone, usage, API table, tests and measured results, configuration, troubleshooting, security notes, limitations, deferred items.
- Real screenshots of six pages (`docs/screenshots/`), captured with headless Edge against the API and `gedp_dev`.
- `docs/samples/quality-report-sample.json`: the optional JSON export from real run `fff6aa0b` (success, loaded 600, inserted 0, value changed 0).

**Open items for the owner**
- Confirm the GitHub Actions run for the latest commit is green (not readable from this environment).
- Create the scheduled task with `scripts/register_task.ps1` if wanted.
- Choose a code license before publishing.
