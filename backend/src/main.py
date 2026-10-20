"""FastAPI application entry point: ``uvicorn src.main:app --reload`` (run from backend/)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.health import router as health_router
from src.core.config import Settings, get_settings
from src.core.logging import configure_logging
from src.db.session import create_db_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Settings are resolved at startup rather than import time, so importing this
    module never requires a configured environment. Tests pass explicit settings.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()  # raises ConfigurationError with a readable message
        configure_logging(resolved.log_level)
        app.state.settings = resolved
        app.state.engine = create_db_engine(resolved.database_url)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="Global Economic Data Pipeline API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
