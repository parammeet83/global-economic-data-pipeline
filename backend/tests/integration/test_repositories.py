"""Upsert idempotency and transaction behavior (D-13, D-14)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from src.db.models import Country, EconomicObservation
from src.db.repositories import fetch_existing_values, upsert_countries, upsert_observations
from tests.integration.helpers import add_reference_data, insert_run

pytestmark = pytest.mark.integration

ROWS = [
    {"country_code": "IND", "indicator_code": "SP.POP.TOTL", "year": 2020, "value": Decimal("100"), "source_updated_at": None},
    {"country_code": "USA", "indicator_code": "SP.POP.TOTL", "year": 2020, "value": Decimal("200"), "source_updated_at": None},
]


def count_observations(session) -> int:
    return session.scalar(select(func.count()).select_from(EconomicObservation))


@pytest.fixture
def run_ids(db_session):
    add_reference_data(db_session)
    return insert_run(db_session, status="success"), insert_run(db_session, status="success")


def test_upsert_twice_keeps_one_row_per_key(db_session, run_ids):
    first, second = run_ids
    now = datetime.now(UTC)

    upsert_observations(db_session, ROWS, run_id=first, ingested_at=now)
    upsert_observations(db_session, ROWS, run_id=second, ingested_at=now)

    assert count_observations(db_session) == 2
    stored = db_session.scalars(select(EconomicObservation)).all()
    assert {row.last_run_id for row in stored} == {second}


def test_upsert_updates_changed_values(db_session, run_ids):
    first, second = run_ids
    now = datetime.now(UTC)
    upsert_observations(db_session, ROWS, run_id=first, ingested_at=now)

    changed = [{**ROWS[0], "value": Decimal("150.5")}]
    upsert_observations(db_session, changed, run_id=second, ingested_at=now)

    existing = fetch_existing_values(db_session, [("IND", "SP.POP.TOTL", 2020), ("USA", "SP.POP.TOTL", 2020), ("IND", "SP.POP.TOTL", 1999)])
    assert existing == {("IND", "SP.POP.TOTL", 2020): Decimal("150.500000"), ("USA", "SP.POP.TOTL", 2020): Decimal("200.000000")}
    assert count_observations(db_session) == 2


def test_same_key_twice_in_one_statement_is_rejected(db_session, run_ids):
    # Why the pipeline must de-duplicate before loading (D-13).
    with pytest.raises(DBAPIError, match="cannot affect row a second time"):
        with db_session.begin_nested():
            upsert_observations(db_session, [ROWS[0], ROWS[0]], run_id=run_ids[0], ingested_at=datetime.now(UTC))


def test_upsert_countries_updates_metadata(db_session):
    add_reference_data(db_session)
    upsert_countries(db_session, [{"country_code": "IND", "name": "Republic of India", "region": "South Asia", "income_level": None}])

    country = db_session.get(Country, "IND")
    db_session.refresh(country)
    assert country.name == "Republic of India"
    assert db_session.scalar(select(func.count()).select_from(Country)) == 2


def test_rolled_back_write_unit_leaves_nothing(db_session, run_ids):
    with pytest.raises(RuntimeError):
        with db_session.begin_nested():
            upsert_observations(db_session, ROWS, run_id=run_ids[0], ingested_at=datetime.now(UTC))
            raise RuntimeError("simulated failure mid-load")

    assert count_observations(db_session) == 0
