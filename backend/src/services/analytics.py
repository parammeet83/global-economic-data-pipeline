"""Read queries for the analytics endpoints (Backend_DB_Schema.md §7).

All filters arrive validated and are applied with bound parameters; sorting
uses an allow-list with the primary key as tie-breaker (D-25). Missing
observations are simply absent from results, never zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

from src.db.models import TERMINAL_STATUSES, Country, EconomicObservation, Indicator, PipelineRun

SORT_COLUMNS = {
    "year": EconomicObservation.year,
    "country_code": EconomicObservation.country_code,
    "indicator_code": EconomicObservation.indicator_code,
    "value": EconomicObservation.value,
}
PRIMARY_KEY_ORDER = (EconomicObservation.country_code, EconomicObservation.indicator_code, EconomicObservation.year)
SUCCESSFUL = ("success", "partial_success")


def dashboard_counts(session: Session) -> dict[str, Any]:
    return {
        "countries": session.scalar(select(func.count(func.distinct(EconomicObservation.country_code)))) or 0,
        "indicators": session.scalar(select(func.count(func.distinct(EconomicObservation.indicator_code)))) or 0,
        "observations": session.scalar(select(func.count()).select_from(EconomicObservation)) or 0,
        "latest_successful_load_at": session.scalar(
            select(func.max(PipelineRun.finished_at)).where(PipelineRun.status.in_(SUCCESSFUL))
        ),
    }


def list_indicators(session: Session) -> list[dict[str, Any]]:
    coverage = (
        select(
            EconomicObservation.indicator_code,
            func.count().label("observation_count"),
            func.min(EconomicObservation.year).label("first_year"),
            func.max(EconomicObservation.year).label("last_year"),
        )
        .group_by(EconomicObservation.indicator_code)
        .subquery()
    )
    rows = session.execute(
        select(Indicator, coverage.c.observation_count, coverage.c.first_year, coverage.c.last_year)
        .outerjoin(coverage, coverage.c.indicator_code == Indicator.indicator_code)
        .order_by(Indicator.indicator_code)
    )
    return [
        {
            "indicator_code": ind.indicator_code,
            "name": ind.name,
            "description": ind.description,
            "unit": ind.unit,
            "source_name": ind.source_name,
            "frequency": ind.frequency,
            "observation_count": count or 0,
            "first_year": first,
            "last_year": last,
        }
        for ind, count, first, last in rows
    ]


def get_indicator(session: Session, indicator_code: str) -> Indicator | None:
    return session.get(Indicator, indicator_code)


def list_countries(session: Session) -> list[dict[str, Any]]:
    """Countries represented in the observation data."""
    represented = select(EconomicObservation.country_code).distinct()
    rows = session.scalars(select(Country).where(Country.country_code.in_(represented)).order_by(Country.name))
    return [
        {"country_code": c.country_code, "name": c.name, "region": c.region, "income_level": c.income_level}
        for c in rows
    ]


def country_names(session: Session, codes: Sequence[str]) -> dict[str, str]:
    rows = session.execute(select(Country.country_code, Country.name).where(Country.country_code.in_(list(codes))))
    return dict(rows.all())


def _observation_filter(
    stmt: Select, indicator_code: str | None, country_codes: Sequence[str], start_year: int | None, end_year: int | None
) -> Select:
    if indicator_code:
        stmt = stmt.where(EconomicObservation.indicator_code == indicator_code)
    if country_codes:
        stmt = stmt.where(EconomicObservation.country_code.in_(list(country_codes)))
    if start_year is not None:
        stmt = stmt.where(EconomicObservation.year >= start_year)
    if end_year is not None:
        stmt = stmt.where(EconomicObservation.year <= end_year)
    return stmt


def list_observations(
    session: Session,
    *,
    indicator_code: str | None,
    country_codes: Sequence[str],
    start_year: int | None,
    end_year: int | None,
    sort_by: str,
    sort_order: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    total = session.scalar(
        _observation_filter(select(func.count()).select_from(EconomicObservation), indicator_code, country_codes, start_year, end_year)
    )
    direction = desc if sort_order == "desc" else asc
    stmt = (
        select(EconomicObservation, Country.name, Indicator.unit, Indicator.name)
        .join(Country, Country.country_code == EconomicObservation.country_code)
        .join(Indicator, Indicator.indicator_code == EconomicObservation.indicator_code)
    )
    stmt = _observation_filter(stmt, indicator_code, country_codes, start_year, end_year)
    stmt = stmt.order_by(direction(SORT_COLUMNS[sort_by]), *PRIMARY_KEY_ORDER).offset((page - 1) * page_size).limit(page_size)
    items = [
        {
            "country_code": obs.country_code,
            "country_name": country_name,
            "indicator_code": obs.indicator_code,
            "indicator_name": indicator_name,
            "year": obs.year,
            "value": float(obs.value),
            "unit": unit,
            "ingested_at": obs.ingested_at,
        }
        for obs, country_name, unit, indicator_name in session.execute(stmt)
    ]
    return items, total or 0


def trend(
    session: Session, *, indicator_code: str, country_codes: Sequence[str], start_year: int | None, end_year: int | None
) -> list[dict[str, Any]]:
    stmt = _observation_filter(
        select(EconomicObservation.country_code, EconomicObservation.year, EconomicObservation.value),
        indicator_code,
        country_codes,
        start_year,
        end_year,
    ).order_by(EconomicObservation.country_code, EconomicObservation.year)
    points: dict[str, list[dict[str, Any]]] = {code: [] for code in country_codes}
    for code, year, value in session.execute(stmt):
        points.setdefault(code, []).append({"year": year, "value": float(value)})
    names = country_names(session, list(points))
    return [
        {"country_code": code, "country_name": names.get(code, code), "points": pts}
        for code, pts in points.items()
    ]


def comparison(
    session: Session, *, indicator_code: str, year: int, country_codes: Sequence[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = session.execute(
        select(EconomicObservation.country_code, EconomicObservation.value).where(
            EconomicObservation.indicator_code == indicator_code,
            EconomicObservation.year == year,
            EconomicObservation.country_code.in_(list(country_codes)),
        )
    ).all()
    names = country_names(session, country_codes)
    values = {code: float(value) for code, value in rows}
    items = sorted(
        ({"country_code": c, "country_name": names.get(c, c), "value": v} for c, v in values.items()),
        key=lambda item: item["value"],
        reverse=True,
    )
    unavailable = [{"country_code": c, "country_name": names.get(c, c)} for c in country_codes if c not in values]
    return items, unavailable


def latest_terminal_run(session: Session) -> PipelineRun | None:
    return session.scalar(
        select(PipelineRun)
        .where(PipelineRun.status.in_(TERMINAL_STATUSES))
        .order_by(desc(PipelineRun.started_at), desc(PipelineRun.run_id))
        .limit(1)
    )
