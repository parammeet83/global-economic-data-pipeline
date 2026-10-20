"""Small builders for integration tests. Values are test fixtures, never shown as real data."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from src.db.repositories import upsert_countries, upsert_indicators


def add_reference_data(session: Session | Connection) -> None:
    upsert_countries(
        session,
        [
            {"country_code": "IND", "name": "India", "region": "South Asia", "income_level": "Lower middle income"},
            {"country_code": "USA", "name": "United States", "region": "North America", "income_level": "High income"},
        ],
    )
    upsert_indicators(
        session,
        [
            {"indicator_code": "SP.POP.TOTL", "name": "Population, total", "unit": "people"},
            {"indicator_code": "NY.GDP.MKTP.CD", "name": "GDP (current US$)", "unit": "current US$"},
        ],
    )


def insert_run(
    connection: Connection | Session,
    *,
    status: str = "running",
    age_minutes: float = 0,
    **columns: Any,
) -> uuid.UUID:
    """Insert a pipeline_runs row started ``age_minutes`` ago; terminal rows finish now()."""
    run_id = uuid.uuid4()
    values: dict[str, Any] = {"run_id": run_id, "triggered_by": "cli", "status": status, **columns}
    names = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    finished = "NULL" if status == "running" else "now()"
    connection.execute(
        text(
            f"INSERT INTO pipeline_runs ({names}, started_at, finished_at) "
            f"VALUES ({params}, now() - make_interval(secs => :age), {finished})"
        ),
        {**values, "age": age_minutes * 60},
    )
    return run_id
