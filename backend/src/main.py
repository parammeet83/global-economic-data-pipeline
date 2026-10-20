"""FastAPI application entry point: ``uvicorn src.main:app --reload`` (run from backend/)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from src.api.analytics import router as analytics_router
from src.api.errors import install_error_handlers
from src.api.health import router as health_router
from src.api.runs import router as runs_router
from src.core.config import Settings, get_settings
from src.core.logging import configure_logging
from src.db.session import SessionFactory, create_db_engine, create_session_factory
from src.pipeline.orchestrator import SourceClient


class SettingsCORSMiddleware:
    """CORS restricted to ``CORS_ORIGINS``, resolved after startup so importing the app needs no configuration."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._cors: CORSMiddleware | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self._cors is None:
            settings: Settings = scope["app"].state.settings
            self._cors = CORSMiddleware(
                self.app, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
            )
        await self._cors(scope, receive, send)


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: SessionFactory | None = None,
    source_client: SourceClient | None = None,
) -> FastAPI:
    """Build the application.

    Settings are resolved at startup rather than import time, so importing this
    module never requires a configured environment. Tests pass explicit settings,
    a session factory bound to the test database and a fake World Bank client.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()  # raises ConfigurationError with a readable message
        configure_logging(resolved.log_level)
        app.state.settings = resolved
        app.state.engine = create_db_engine(resolved.database_url)
        app.state.session_factory = session_factory or create_session_factory(app.state.engine)
        app.state.source_client = source_client  # None: the real World Bank client is built per run
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="Global Economic Data Pipeline API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(SettingsCORSMiddleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(analytics_router)
    app.include_router(runs_router)
    return app


app = create_app()
