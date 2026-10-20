"""Pipeline run lifecycle in PostgreSQL (D-18, D-19, D-20).

* ``claim_run``: own committed transaction (T1). Recovers stale runs, then inserts
  the ``running`` row; the partial unique index refuses a second running run.
* ``finalize_run``: conditional terminal update used inside the load transaction
  (T2). Matching zero rows means the run was recovered as stale meanwhile, and
  the caller must roll back.
* ``finalize_failure``: separate transaction (T3) for runs that cannot load.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import DataQualityCheck, PipelineRun
from src.db.session import SessionFactory
from src.pipeline.quality import CheckResult

logger = logging.getLogger(__name__)

ONE_RUNNING_INDEX = "uq_pipeline_runs_one_running"
ABANDONED_SUMMARY = "Abandoned: no terminal status within STALE_RUN_MINUTES (recovered as stale)"
MAX_SUMMARY_LENGTH = 500


class RunInProgressError(Exception):
    """Another run holds the single ``running`` slot (D-19)."""

    def __init__(self, running_run_id: uuid.UUID | None) -> None:
        super().__init__("A pipeline run is already in progress")
        self.running_run_id = running_run_id


class RunNoLongerRunningError(Exception):
    """The run was finalized elsewhere (normally by stale recovery) before this update."""


def _duration_expr():
    return func.extract("epoch", func.clock_timestamp() - PipelineRun.started_at)


def recover_stale_runs(session: Session, stale_minutes: int) -> list[uuid.UUID]:
    cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, stale_minutes)
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.status == "running", PipelineRun.started_at < cutoff)
        .values(
            status="failed",
            finished_at=func.clock_timestamp(),
            duration_seconds=_duration_expr(),
            error_summary=ABANDONED_SUMMARY,
            error_count=PipelineRun.error_count + 1,
        )
        .returning(PipelineRun.run_id)
    )
    return list(result.scalars())


def running_run_id(session_factory: SessionFactory) -> uuid.UUID | None:
    with session_factory() as session:
        return session.scalar(select(PipelineRun.run_id).where(PipelineRun.status == "running"))


def claim_run(
    session_factory: SessionFactory,
    *,
    triggered_by: str,
    stale_minutes: int,
    countries_requested: int,
    indicators_requested: int,
    config_snapshot: dict[str, Any],
) -> uuid.UUID:
    """T1: commit a ``running`` row, or raise ``RunInProgressError``."""
    run_id = uuid.uuid4()
    try:
        with session_factory() as session, session.begin():
            for recovered in recover_stale_runs(session, stale_minutes):
                logger.warning("Recovered stale run as failed", extra={"event": "stale_run_recovered", "stage": "claim", "run_id": recovered})
            session.add(
                PipelineRun(
                    run_id=run_id,
                    triggered_by=triggered_by,
                    status="running",
                    countries_requested=countries_requested,
                    indicators_requested=indicators_requested,
                    config_snapshot=config_snapshot,
                )
            )
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == ONE_RUNNING_INDEX:
            raise RunInProgressError(running_run_id(session_factory)) from None
        raise
    logger.info("Run claimed", extra={"event": "run_claimed", "stage": "claim", "run_id": run_id, "triggered_by": triggered_by})
    return run_id


def _insert_checks(session: Session, run_id: uuid.UUID, checks: Sequence[CheckResult]) -> None:
    if checks:
        session.execute(
            insert(DataQualityCheck),
            [
                {
                    "run_id": run_id,
                    "check_name": c.check_name,
                    "status": c.status,
                    "records_checked": c.records_checked,
                    "records_failed": c.records_failed,
                    "details": c.details or None,
                }
                for c in checks
            ],
        )


def finalize_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    status: str,
    counts: Mapping[str, int],
    checks: Sequence[CheckResult],
    error_summary: str | None,
) -> None:
    """Terminal update inside the caller's transaction; raises if the run is no longer running."""
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.run_id == run_id, PipelineRun.status == "running")
        .values(
            status=status,
            finished_at=func.clock_timestamp(),
            duration_seconds=_duration_expr(),
            error_summary=error_summary[:MAX_SUMMARY_LENGTH] if error_summary else None,
            **counts,
        )
    )
    if result.rowcount == 0:
        raise RunNoLongerRunningError(f"run {run_id} is no longer running")
    _insert_checks(session, run_id, checks)


def finalize_failure(
    session_factory: SessionFactory,
    run_id: uuid.UUID,
    *,
    counts: Mapping[str, int],
    checks: Sequence[CheckResult],
    error_summary: str,
) -> bool:
    """T3: record ``failed`` with whatever is known. Returns False if it could not be recorded."""
    safe_counts = {**counts, "records_loaded": 0, "records_inserted": 0, "records_value_changed": 0}
    try:
        with session_factory() as session, session.begin():
            finalize_run(session, run_id, status="failed", counts=safe_counts, checks=checks, error_summary=error_summary)
        return True
    except RunNoLongerRunningError:
        logger.warning("Run was already finalized", extra={"event": "run_already_finalized", "stage": "finalize", "run_id": run_id})
        return False
    except Exception as exc:  # noqa: BLE001 - the run stays 'running' until stale recovery (D-18 step 5)
        logger.error(
            "Could not record run failure", extra={"event": "failure_not_recorded", "stage": "finalize", "run_id": run_id, "error_type": type(exc).__name__}
        )
        return False
