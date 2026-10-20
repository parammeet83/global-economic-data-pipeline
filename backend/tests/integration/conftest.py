"""Fixtures for tests that use the real PostgreSQL test database (never the development database).

Isolation is non-destructive (D-37): the schema is created once with
``alembic upgrade head`` (additive), and every test runs inside an outer
transaction that is always rolled back. Code under test commits to savepoints
inside that transaction, so nothing a test writes persists and no table is ever
truncated or dropped.
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import BACKEND_DIR, ConfigurationError, load_settings
from src.db.session import SessionFactory, create_db_engine


@pytest.fixture(scope="session")
def test_database_url() -> SecretStr:
    """TEST_DATABASE_URL from backend/.env or the environment; skips the test when it is not configured.

    Settings validation already guarantees the name ends in ``_test`` and differs
    from DATABASE_URL (D-06).
    """
    # In CI the database tests are mandatory: a missing configuration is a failure, not a skip.
    unavailable = pytest.fail if os.environ.get("CI") else pytest.skip
    try:
        settings = load_settings()
    except ConfigurationError:
        unavailable("backend/.env or environment variables are not configured")
    if settings.test_database_url is None:
        unavailable("TEST_DATABASE_URL is not configured")
    return settings.test_database_url


def alembic_config(connection: Connection) -> Config:
    """Alembic config that runs migrations on an existing connection, inside its transaction."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: SecretStr) -> Iterator[Engine]:
    """Engine for the test database with all migrations applied (idempotent, additive)."""
    engine = create_db_engine(test_database_url)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection whose outer transaction is rolled back after the test."""
    connection = migrated_engine.connect()
    outer = connection.begin()
    try:
        yield connection
    finally:
        if outer.is_active:
            outer.rollback()
        connection.close()


@pytest.fixture
def session_factory(db_connection: Connection) -> SessionFactory:
    """Sessions whose commits become savepoints inside the test's rolled-back transaction."""
    return sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: SessionFactory) -> Iterator[Session]:
    with session_factory() as session:
        yield session
