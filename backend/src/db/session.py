"""SQLAlchemy engine/session creation and the database connectivity check.

All database work goes through a ``sessionmaker`` so the API, CLI and tests share
one session lifecycle: one session per request or pipeline step, closed
deterministically (Schema §8). Tests bind the factory to a connection whose
outer transaction is rolled back, so nothing they write persists.
"""

import logging

from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]

logger = logging.getLogger(__name__)

# Seconds psycopg waits for a TCP/auth handshake before giving up, so /health
# reports an outage promptly instead of hanging.
CONNECT_TIMEOUT_SECONDS = 5


def create_db_engine(database_url: SecretStr) -> Engine:
    """Create an engine. No connection is opened until the engine is first used."""
    return create_engine(
        database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    """Sessions that keep loaded attributes after commit (results are returned to callers)."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def check_database_connection(engine: Engine) -> bool:
    """Return True if ``SELECT 1`` succeeds, False on any failure.

    Every exception counts as "unavailable" so an outage can never be reported as
    healthy. Only the exception type is logged: driver messages can include the
    host and user name.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any failure means the database is not usable
        logger.warning("Database connectivity check failed", extra={"event": "db_check_failed", "error_type": type(exc).__name__})
        return False
    return True
