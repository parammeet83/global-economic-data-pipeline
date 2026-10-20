# Development Log

Per-phase record of what was built and verified. Test counts are copied from actual runs on the development machine (Windows, Python 3.12.10, PostgreSQL 17.11). A phase's commit hash is recorded in the next entry, because a commit cannot contain its own hash.

| Phase | Commit | Summary |
|---|---|---|
| 0 | `5a0a763` | Specifications reconciled; decision log; README skeleton |
| 1 | `477dcfb` | Settings, `/health`, unit + integration tests (26 passed) |
| 2 | see Phase 3 entry | Schema, migrations, repositories, CI |

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
