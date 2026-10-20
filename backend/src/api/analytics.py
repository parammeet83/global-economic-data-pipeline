"""Dashboard summary, reference lists, observations, trend and comparison endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from src.api.deps import (
    MAX_YEAR,
    MIN_YEAR,
    SessionDep,
    SettingsDep,
    YearQuery,
    check_year_range,
    normalize_countries,
    normalize_indicator,
)
from src.api.errors import not_found
from src.api.schemas import (
    ComparisonResponse,
    CountryOut,
    DashboardSummary,
    Defaults,
    IndicatorOut,
    IndicatorRef,
    ObservationOut,
    Page,
    RunSummary,
    TrendResponse,
)
from src.services import analytics
from src.services.runs import latest_run

router = APIRouter(prefix="/api/v1", tags=["analytics"])

CountryQuery = Annotated[
    list[str] | None, Query(description="ISO-3 code; repeat the parameter for several countries")
]


def _indicator_ref(session, code: str) -> IndicatorRef:
    indicator = analytics.get_indicator(session, normalize_indicator(code))
    if indicator is None:
        raise not_found(f"Indicator {code.strip().upper()} has no data in the database")
    return IndicatorRef(indicator_code=indicator.indicator_code, name=indicator.name, unit=indicator.unit)


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(session: SessionDep, settings: SettingsDep) -> DashboardSummary:
    run = latest_run(session)
    return DashboardSummary(
        **analytics.dashboard_counts(session),
        latest_run=RunSummary.model_validate(run) if run else None,
        defaults=Defaults(indicator_code=settings.default_indicator_code, country_codes=settings.default_country_codes),
    )


@router.get("/indicators", response_model=list[IndicatorOut])
def indicators(session: SessionDep) -> list[dict]:
    return analytics.list_indicators(session)


@router.get("/countries", response_model=list[CountryOut])
def countries(session: SessionDep) -> list[dict]:
    return analytics.list_countries(session)


@router.get("/observations", response_model=Page[ObservationOut])
def observations(
    session: SessionDep,
    indicator_code: str | None = None,
    country_code: CountryQuery = None,
    start_year: YearQuery = None,
    end_year: YearQuery = None,
    sort_by: Literal["year", "country_code", "indicator_code", "value"] = "year",
    sort_order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    check_year_range(start_year, end_year)
    items, total = analytics.list_observations(
        session,
        indicator_code=normalize_indicator(indicator_code) if indicator_code else None,
        country_codes=normalize_countries(country_code, maximum=50),
        start_year=start_year,
        end_year=end_year,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/analytics/trend", response_model=TrendResponse)
def trend(
    session: SessionDep,
    indicator_code: str,
    country_code: CountryQuery = None,
    start_year: YearQuery = None,
    end_year: YearQuery = None,
) -> TrendResponse:
    check_year_range(start_year, end_year)
    indicator = _indicator_ref(session, indicator_code)
    codes = normalize_countries(country_code, minimum=1, maximum=10)
    series = analytics.trend(
        session, indicator_code=indicator.indicator_code, country_codes=codes, start_year=start_year, end_year=end_year
    )
    return TrendResponse(indicator=indicator, start_year=start_year, end_year=end_year, series=series)


@router.get("/analytics/country-comparison", response_model=ComparisonResponse)
def country_comparison(
    session: SessionDep,
    indicator_code: str,
    year: Annotated[int, Query(ge=MIN_YEAR, le=MAX_YEAR)],
    country_code: CountryQuery = None,
) -> ComparisonResponse:
    indicator = _indicator_ref(session, indicator_code)
    codes = normalize_countries(country_code, minimum=2, maximum=10)
    items, unavailable = analytics.comparison(session, indicator_code=indicator.indicator_code, year=year, country_codes=codes)
    return ComparisonResponse(indicator=indicator, year=year, items=items, unavailable=unavailable)
