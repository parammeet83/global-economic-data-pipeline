"""PostgreSQL constraints are the final integrity guard (Schema §6, D-21)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.helpers import add_reference_data, insert_run

pytestmark = pytest.mark.integration


def violates(db_connection, sql: str, params: dict | None = None) -> str:
    """Run ``sql`` in a savepoint and return the violated constraint name."""
    with pytest.raises(IntegrityError) as excinfo:
        with db_connection.begin_nested():
            db_connection.execute(text(sql), params or {})
    return excinfo.value.orig.diag.constraint_name


@pytest.fixture
def reference(db_connection):
    add_reference_data(db_connection)


def test_country_code_must_be_iso3(db_connection):
    name = violates(db_connection, "INSERT INTO countries (country_code, name) VALUES ('in', 'India')")
    assert name == "ck_countries_country_code_iso3"


def test_observation_requires_known_country(db_connection, reference):
    name = violates(
        db_connection,
        "INSERT INTO economic_observations (country_code, indicator_code, year, value, ingested_at) "
        "VALUES ('FRA', 'SP.POP.TOTL', 2020, 1, now())",
    )
    assert name == "fk_economic_observations_country_code_countries"


def test_observation_value_cannot_be_null(db_connection, reference):
    with pytest.raises(IntegrityError, match="not-null"):
        with db_connection.begin_nested():
            db_connection.execute(
                text(
                    "INSERT INTO economic_observations (country_code, indicator_code, year, value, ingested_at) "
                    "VALUES ('IND', 'SP.POP.TOTL', 2020, NULL, now())"
                )
            )


def test_observation_year_range(db_connection, reference):
    name = violates(
        db_connection,
        "INSERT INTO economic_observations (country_code, indicator_code, year, value, ingested_at) "
        "VALUES ('IND', 'SP.POP.TOTL', 1800, 1, now())",
    )
    assert name == "ck_economic_observations_year_range"


def test_observation_primary_key_prevents_duplicates(db_connection, reference):
    insert = (
        "INSERT INTO economic_observations (country_code, indicator_code, year, value, ingested_at) "
        "VALUES ('IND', 'SP.POP.TOTL', 2020, 1, now())"
    )
    db_connection.execute(text(insert))
    assert violates(db_connection, insert) == "pk_economic_observations"


def test_only_one_running_run(db_connection):
    insert_run(db_connection, status="running")

    with pytest.raises(IntegrityError) as excinfo:
        with db_connection.begin_nested():
            insert_run(db_connection, status="running")
    assert excinfo.value.orig.diag.constraint_name == "uq_pipeline_runs_one_running"


def test_terminal_runs_do_not_conflict_with_a_running_run(db_connection):
    insert_run(db_connection, status="running")
    insert_run(db_connection, status="success")
    insert_run(db_connection, status="failed")


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"status": "done"}, "ck_pipeline_runs_status_valid"),
        ({"status": "running", "triggered_by": "github_action"}, "ck_pipeline_runs_triggered_by_valid"),
        ({"status": "success", "records_transformed": 5, "records_loaded": 6}, "ck_pipeline_runs_loaded_within_transformed"),
        (
            {"status": "success", "records_transformed": 5, "records_loaded": 5, "records_inserted": 4, "records_value_changed": 2},
            "ck_pipeline_runs_changes_within_loaded",
        ),
        ({"status": "running", "records_rejected": -1}, "ck_pipeline_runs_records_rejected_non_negative"),
    ],
)
def test_pipeline_run_checks(db_connection, columns, constraint):
    with pytest.raises(IntegrityError) as excinfo:
        with db_connection.begin_nested():
            insert_run(db_connection, **columns)
    assert excinfo.value.orig.diag.constraint_name == constraint


def test_running_row_cannot_have_finished_at(db_connection):
    name = violates(
        db_connection,
        "INSERT INTO pipeline_runs (run_id, triggered_by, status, finished_at) "
        "VALUES (gen_random_uuid(), 'cli', 'running', now())",
    )
    assert name == "ck_pipeline_runs_finished_iff_terminal"


def test_terminal_row_requires_finished_at(db_connection):
    name = violates(
        db_connection,
        "INSERT INTO pipeline_runs (run_id, triggered_by, status) VALUES (gen_random_uuid(), 'cli', 'success')",
    )
    assert name == "ck_pipeline_runs_finished_iff_terminal"


def test_quality_check_rules(db_connection):
    run_id = insert_run(db_connection, status="success")
    insert = (
        "INSERT INTO data_quality_checks (run_id, check_name, status, records_checked, records_failed) "
        "VALUES (:run_id, :name, :status, :checked, :failed)"
    )
    db_connection.execute(text(insert), {"run_id": run_id, "name": "numeric_value", "status": "passed", "checked": 3, "failed": 0})

    assert violates(db_connection, insert, {"run_id": run_id, "name": "numeric_value", "status": "passed", "checked": 1, "failed": 0}) == (
        "uq_data_quality_checks_run_id_check_name"
    )
    assert violates(db_connection, insert, {"run_id": run_id, "name": "x", "status": "ok", "checked": 1, "failed": 0}) == (
        "ck_data_quality_checks_status_valid"
    )
    assert violates(db_connection, insert, {"run_id": run_id, "name": "y", "status": "failed", "checked": 1, "failed": 2}) == (
        "ck_data_quality_checks_failed_within_checked"
    )
