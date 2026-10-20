"""Migration reproducibility, verified without touching any real table (D-37).

The upgrade/downgrade cycle runs in a throwaway schema inside a transaction that
is rolled back; PostgreSQL's transactional DDL removes everything afterwards.
"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from src.db.models import Base
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {"countries", "indicators", "economic_observations", "pipeline_runs", "data_quality_checks"}


def test_migrated_schema_matches_models(db_connection):
    diff = compare_metadata(MigrationContext.configure(db_connection), Base.metadata)

    assert diff == []


def test_upgrade_downgrade_upgrade_in_isolated_schema(db_connection):
    schema = f"migration_check_{uuid.uuid4().hex[:12]}"
    db_connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    config = alembic_config(db_connection)

    command.upgrade(config, "head")
    assert EXPECTED_TABLES <= set(inspect(db_connection).get_table_names(schema=schema))
    indexes = {ix["name"] for ix in inspect(db_connection).get_indexes("pipeline_runs", schema=schema)}
    assert "uq_pipeline_runs_one_running" in indexes

    command.downgrade(config, "base")
    assert set(inspect(db_connection).get_table_names(schema=schema)) == {"alembic_version"}

    command.upgrade(config, "head")
    assert EXPECTED_TABLES <= set(inspect(db_connection).get_table_names(schema=schema))
    # The fixture rolls back the outer transaction, removing the schema entirely.
