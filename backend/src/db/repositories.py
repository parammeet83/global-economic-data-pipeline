"""Write helpers for dimension and fact tables (PostgreSQL upserts).

Upserts are keyed on the primary key and are idempotent: running the same input
twice leaves one row per key (D-14). Callers own the transaction; nothing here
commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.db.models import Country, EconomicObservation, Indicator

ObservationKey = tuple[str, str, int]


def upsert_countries(session: Session, rows: Sequence[Mapping[str, Any]]) -> int:
    """Insert or update countries; returns the number of rows written."""
    if not rows:
        return 0
    stmt = insert(Country).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=[Country.country_code],
        set_={
            "name": stmt.excluded.name,
            "region": stmt.excluded.region,
            "income_level": stmt.excluded.income_level,
            "is_aggregate": stmt.excluded.is_aggregate,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_indicators(session: Session, rows: Sequence[Mapping[str, Any]]) -> int:
    """Insert or update indicators; returns the number of rows written."""
    if not rows:
        return 0
    stmt = insert(Indicator).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=[Indicator.indicator_code],
        set_={
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "unit": stmt.excluded.unit,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    return len(rows)


def fetch_existing_values(session: Session, keys: Iterable[ObservationKey]) -> dict[ObservationKey, Decimal]:
    """Current stored values for the given business keys (used to compute inserted / value-changed counts)."""
    key_list = list(keys)
    if not key_list:
        return {}
    columns = (
        EconomicObservation.country_code,
        EconomicObservation.indicator_code,
        EconomicObservation.year,
    )
    result = session.execute(
        select(*columns, EconomicObservation.value).where(tuple_(*columns).in_(key_list))
    )
    return {(row.country_code, row.indicator_code, row.year): row.value for row in result}


def upsert_observations(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: uuid.UUID,
    ingested_at: datetime,
    batch_size: int = 1000,
) -> int:
    """Unconditional upsert on (country_code, indicator_code, year) (D-14).

    ``rows`` must already be de-duplicated on the business key (D-13): PostgreSQL
    rejects a statement that touches the same key twice. Returns rows written.
    """
    written = 0
    for start in range(0, len(rows), batch_size):
        batch = [
            {**row, "ingested_at": ingested_at, "last_run_id": run_id}
            for row in rows[start : start + batch_size]
        ]
        stmt = insert(EconomicObservation).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                EconomicObservation.country_code,
                EconomicObservation.indicator_code,
                EconomicObservation.year,
            ],
            set_={
                "value": stmt.excluded.value,
                "source_updated_at": stmt.excluded.source_updated_at,
                "ingested_at": stmt.excluded.ingested_at,
                "last_run_id": stmt.excluded.last_run_id,
            },
        )
        session.execute(stmt)
        written += len(batch)
    return written
