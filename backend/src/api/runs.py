"""Run history, run detail (also the polling endpoint), latest quality and the manual trigger."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status

from src.api.deps import SessionDep, SettingsDep
from src.api.errors import ApiError, not_found
from src.api.local_only import local_request_error
from src.api.schemas import Page, QualityCheck, QualityLatest, RunAccepted, RunDetail, RunSummary
from src.pipeline.orchestrator import execute_run, start_run
from src.pipeline.runs import RunInProgressError
from src.services import runs as run_service
from src.services.analytics import latest_terminal_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


def _detail(session, run) -> RunDetail:
    return RunDetail(
        **RunSummary.model_validate(run).model_dump(),
        countries_requested=run.countries_requested,
        indicators_requested=run.indicators_requested,
        config_snapshot=run.config_snapshot,
        checks=[QualityCheck.model_validate(c) for c in run_service.run_checks(session, run.run_id)],
    )


@router.get("/runs", response_model=Page[RunSummary])
def list_runs(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    items, total = run_service.list_runs(session, page=page, page_size=page_size)
    return {"items": [RunSummary.model_validate(r) for r in items], "page": page, "page_size": page_size, "total": total}


@router.get("/runs/{run_id}", response_model=RunDetail)
def run_detail(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    run = run_service.get_run(session, run_id)
    if run is None:
        raise not_found("Run not found")
    return _detail(session, run)


@router.get("/quality/latest", response_model=QualityLatest)
def quality_latest(session: SessionDep) -> QualityLatest:
    run = latest_terminal_run(session)
    if run is None:
        return QualityLatest(run=None, checks=[])
    checks = [QualityCheck.model_validate(c) for c in run_service.run_checks(session, run.run_id)]
    return QualityLatest(run=RunSummary.model_validate(run), checks=checks)


@router.post(
    "/pipeline/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunAccepted,
    responses={
        403: {"description": "Manual runs are disabled or the request is not from this machine"},
        409: {"description": "A run is already in progress"},
    },
)
def trigger_run(request: Request, response: Response, background: BackgroundTasks, settings: SettingsDep) -> RunAccepted:
    """Local/demo only (D-23, D-39): claim a run synchronously, then execute it in the background.

    The local-only check is a guard for a demo machine, not authentication.
    """
    if not settings.enable_manual_trigger:
        raise ApiError(status.HTTP_403_FORBIDDEN, "manual_trigger_disabled", "Manual pipeline runs are disabled in this environment.")
    refusal = local_request_error(request.client.host if request.client else None, request.headers, settings.trusted_proxy_ips)
    if refusal:
        logger.warning("Manual run refused: request is not local", extra={"event": "trigger_refused"})
        raise ApiError(status.HTTP_403_FORBIDDEN, "manual_trigger_local_only", refusal)

    session_factory = request.app.state.session_factory
    try:
        run_id = start_run(session_factory, settings, "api")
    except RunInProgressError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "run_in_progress",
            "A pipeline run is already in progress.",
            run_id=str(exc.running_run_id) if exc.running_run_id else None,
        ) from None

    background.add_task(execute_run, run_id, session_factory, settings, request.app.state.source_client)
    status_url = f"/api/v1/runs/{run_id}"
    response.headers["Location"] = status_url
    logger.info("Manual run accepted", extra={"event": "trigger_accepted", "run_id": run_id})
    return RunAccepted(run_id=run_id, status="running", status_url=status_url)
