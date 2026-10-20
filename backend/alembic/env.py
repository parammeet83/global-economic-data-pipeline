"""Alembic environment.

Database selection (never from alembic.ini, so no URL is ever committed):
  alembic upgrade head             -> DATABASE_URL       (development database)
  alembic -x db=test upgrade head  -> TEST_DATABASE_URL  (test database)

Tests can pass an open connection via ``config.attributes["connection"]``; the
migration then runs inside the caller's transaction.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.core.config import load_settings
from src.db.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    target = context.get_x_argument(as_dictionary=True).get("db", "dev")
    settings = load_settings()
    if target == "dev":
        return settings.database_url.get_secret_value()
    if target == "test":
        if settings.test_database_url is None:
            raise SystemExit("TEST_DATABASE_URL is not configured; set it in backend/.env to use -x db=test")
        return settings.test_database_url.get_secret_value()
    raise SystemExit(f"Unknown -x db={target!r}; use 'dev' (default) or 'test'")


def _configure(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    external = config.attributes.get("connection")
    if external is not None:
        _configure(external)
        return
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _configure(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
