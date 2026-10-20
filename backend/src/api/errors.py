"""Consistent error bodies: ``{"error": {"code": "...", "message": "..."}}`` (TRD §7, D-25).

No handler ever returns stack traces, SQL, driver messages or submitted values.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra


def error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


def error_response(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(code, message, **extra))


def bad_request(message: str) -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", message)


def not_found(message: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message)


HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(part) for part in err["loc"] if part not in ("query", "path", "body")), "message": err["msg"]}
            for err in exc.errors()
        ]
        return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "Invalid request parameters", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(exc.status_code, code, message)

    @app.exception_handler(OperationalError)
    @app.exception_handler(DBAPIError)
    async def _database(_: Request, exc: DBAPIError) -> JSONResponse:
        logger.warning("Database error while handling a request", extra={"event": "api_database_error", "error_type": type(exc).__name__})
        return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "database_unavailable", "The database is unavailable. Try again later.")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error while handling a request", exc_info=exc, extra={"event": "api_unhandled_error"})
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An unexpected error occurred.")
