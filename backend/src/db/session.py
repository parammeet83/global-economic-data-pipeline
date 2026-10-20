"""SQLAlchemy engine creation and the database connectivity check."""

import logging

from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

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
        logger.warning("Database connectivity check failed (%s)", type(exc).__name__)
        return False
    return True
