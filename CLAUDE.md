# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The MVP is **implemented** (implementation-plan phases 0–11; see `docs/DEVELOPMENT_LOG.md` for per-phase commits and test results):
- `backend/` — FastAPI app, World Bank pipeline (`src/pipeline/`), SQLAlchemy models + Alembic migrations, pytest suite (unit + integration on `gedp_test`).
- `frontend/` — React + TypeScript + Vite dashboard with Vitest tests.
- `scripts/` — Windows Task Scheduler wrapper and registration script (the task itself is created by the owner).
- `docs/` — six specifications, `DECISIONS.md`, `SCHEDULING.md`, `DEVELOPMENT_LOG.md`, screenshots and a sample quality report.
- `.venv/` — the single root Python 3.12.10 virtual environment (git-ignored).

Further work should still go phase by phase with tests; deferred P1/P2 items are listed in the README.

## The docs are the contract

Read the relevant document(s) in `docs/` before implementing anything. Recommended order: `PRD.md` → `TRD.md` → `Backend_DB_Schema.md` → `WebAppFlow.md` → `UIUX_design_spec.md` → `implementation_plan.md` (summarized in `docs/INDEX.md`). `docs/DECISIONS.md` is the decision log (`D-xx`: decision, rationale, impact); the detailed rules — run-status rules and response classification (TRD §5–6), record counts and quality checks (Schema §3.3, §3.5) — live in the specs. Keep the log and the specs in sync.

Work **one phase at a time** per `implementation_plan.md` (Phases 0–11). Build thin vertical slices: ingestion+storage correct first, then API, then UI, then scheduling/deployment. Do not "build the entire app" in one pass. Summarize changed files and tests at the end of each phase. Do not create the milestone commits listed in the plan before the corresponding functionality actually exists and runs.

## Non-negotiable invariants

These are easy to violate and central to the project's purpose:

- **Idempotent loads.** Observations are upserted on the composite key `(country_code, indicator_code, year)`. Reloading the same data must update, never duplicate.
- **Null is never zero.** The World Bank API returns missing values. Count them in quality reports; skip null-valued fact rows (current policy) — never coerce a missing value to `0`.
- **Every run is recorded.** Create the `pipeline_runs` row (status `running`) *before* work starts so failures stay visible. Finalize to exactly one terminal status: `success`, `partial_success`, or `failed`. A failed run must never be reported as successful just because some rows loaded.
- **API failure ≠ empty success.** Distinguish transport errors, HTTP errors, API-level error payloads, and malformed JSON. An error must not be mistaken for a valid empty dataset.
- **Browser never touches the DB.** The React app calls FastAPI only. Database credentials and SQL stay on the backend.
- **The manual trigger endpoint (`POST /api/v1/pipeline/run`) is local/demo only** in the MVP — no public exposure without auth, rate limiting, and overlap guards. It must prevent concurrent/overlapping runs.
- **Config-driven, not hard-coded.** Country list, indicator codes, and year range come from environment/config — never scattered through business logic.
- **Pipeline logic is shared.** The pipeline must be callable from both a CLI and the API without duplicating business logic.

## Architecture

```
World Bank API → requests client (timeout, bounded retry/backoff, pagination)
  → pandas normalize → Pandera validate → split accepted / rejected rows
  → SQLAlchemy transactional upsert → PostgreSQL
  → FastAPI (/api/v1) → React + TypeScript dashboard
```

Backend layering (`backend/src/`): `api/` (routers + Pydantic schemas), `pipeline/` (extract/transform/validate/load/orchestrate), `db/` (models, session, repositories), `services/` (analytics + run services), `core/` (config, logging, exceptions), `main.py`.

**Data model** (`docs/Backend_DB_Schema.md`): `countries` and `indicators` (dimensions) → `economic_observations` (fact, unique key `(country_code, indicator_code, year)`) → `pipeline_runs` (audit log, one row per attempt) → `data_quality_checks` (per-run check outcomes). Use PostgreSQL constraints (CHECKs, FKs, unique key) as the final integrity guard, not just Python checks.

**Stack:** Python 3.12 · FastAPI/uvicorn/Pydantic · SQLAlchemy 2.x + psycopg 3 · Alembic · pandas · Pandera · pytest/httpx2 (TestClient) · React + TypeScript + Vite + Recharts · Vitest. Pin or bound dependency versions only after verifying compatibility — do not add unverified latest versions.

## Environment & tooling

- Development is on **Windows**; avoid shell-only assumptions in application code. The shell here is PowerShell (Bash tool also available).
- The virtual environment lives at the **repo root** `.venv/` (Python 3.12.10); this is the only convention (DECISIONS D-01).
  - Activate (PowerShell): `.\.venv\Scripts\Activate.ps1`
- PostgreSQL is the system of record; prefer a dedicated local app database/user over the superuser.

## Commands

Backend (from `backend/`):
- Install: `pip install -r requirements-dev.txt` (runtime deps are in `requirements.txt`; dev file includes it)
- Run API: `uvicorn src.main:app --reload`  (health at `/health`)
- Migrate: `alembic upgrade head`
- New migration: `alembic revision --autogenerate -m "message"` · check models vs migrations: `alembic check` · test DB: `alembic -x db=test upgrade head`
- Run pipeline: `python -m src.pipeline.cli run [--triggered-by scheduler]` (exit codes 0–4, TRD §13)
- Tests: `pytest`  · single test: `pytest tests/path_test.py::test_name`  · coverage: `pytest --cov`. Integration tests use only `TEST_DATABASE_URL` and roll back every test; never truncate, drop or reset either database (D-37).

Frontend (from `frontend/`):
- Install: `npm ci` (uses `package-lock.json`)
- Dev: `npm run dev`  · build: `npm run build`  · test: `npm run test` (Vitest)

CI (`.github/workflows/ci.yml`): backend pytest + frontend build/test. **CI must not depend on live World Bank availability** — unit tests use mocked responses; keep any live smoke test separate and optional.

## Safety

Per the docs' operating assumptions: do not make destructive changes, and do not commit or push to GitHub without explicit confirmation. Keep secrets out of commits — `.env` is git-ignored; `.env.example` holds placeholders only. Never put stack traces, SQL, or raw API payloads into error responses or `pipeline_runs.error_summary`.
