# Development Log

Per-phase record of what was built and verified. Test counts are copied from actual runs on the development machine (Windows, Python 3.12.10, PostgreSQL 17.11). A phase's commit hash is recorded in the next entry, because a commit cannot contain its own hash.

| Phase | Commit | Summary |
|---|---|---|
| 0 | `5a0a763` | Specifications reconciled; decision log; README skeleton |
| 1 | `477dcfb` | Settings, `/health`, unit + integration tests (26 passed) |
| 2 | `a3892da` | Schema, migrations, repositories, CI (48 passed) |
| 3 | see Phase 4 entry | World Bank client: classification, retries, pagination |

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
