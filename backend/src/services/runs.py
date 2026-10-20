"""Read queries for pipeline run history and quality results."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.db.models import DataQualityCheck, PipelineRun


def list_runs(session: Session, *, page: int, page_size: int) -> tuple[list[PipelineRun], int]:
    total = session.scalar(select(func.count()).select_from(PipelineRun)) or 0
    runs = session.scalars(
        select(PipelineRun)
        .order_by(desc(PipelineRun.started_at), desc(PipelineRun.run_id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(runs), total


def latest_run(session: Session) -> PipelineRun | None:
    return session.scalar(select(PipelineRun).order_by(desc(PipelineRun.started_at), desc(PipelineRun.run_id)).limit(1))


def get_run(session: Session, run_id: uuid.UUID) -> PipelineRun | None:
    return session.get(PipelineRun, run_id)


def run_checks(session: Session, run_id: uuid.UUID) -> list[DataQualityCheck]:
    return list(
        session.scalars(
            select(DataQualityCheck).where(DataQualityCheck.run_id == run_id).order_by(DataQualityCheck.quality_check_id)
        )
    )
