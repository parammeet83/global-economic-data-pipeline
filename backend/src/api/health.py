"""GET /health: service and database status (D-27)."""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from src.db.session import check_database_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


def get_engine(request: Request) -> Engine:
    """The engine created at application startup."""
    return request.app.state.engine


HEALTHY_EXAMPLE = {"status": "ok", "database": "ok"}
UNAVAILABLE_EXAMPLE = {"status": "degraded", "database": "unavailable"}


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Service is up and `SELECT 1` succeeded.",
            "content": {"application/json": {"example": HEALTHY_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse,
            "description": "Service is up but the database cannot be reached.",
            "content": {"application/json": {"example": UNAVAILABLE_EXAMPLE}},
        },
    },
)
def health(response: Response, engine: Engine = Depends(get_engine)) -> HealthResponse:
    if check_database_connection(engine):
        return HealthResponse(**HEALTHY_EXAMPLE)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(**UNAVAILABLE_EXAMPLE)
