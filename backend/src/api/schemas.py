"""Typed response models (documented in OpenAPI at /docs).

Numeric observation values are JSON numbers; a missing observation is absent
(trend points) or listed as unavailable (comparison), never 0.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

RunStatus = Literal["running", "success", "partial_success", "failed"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    status: RunStatus
    triggered_by: Literal["cli", "api", "scheduler"]
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    records_extracted: int
    records_rejected: int
    records_null_skipped: int
    records_duplicates_dropped: int
    records_transformed: int
    records_loaded: int
    records_inserted: int
    records_value_changed: int
    error_count: int
    error_summary: str | None


class QualityCheck(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_name: str
    status: Literal["passed", "warning", "failed"]
    checked_at: datetime
    records_checked: int
    records_failed: int
    details: dict[str, Any] | None


class RunDetail(RunSummary):
    countries_requested: int
    indicators_requested: int
    config_snapshot: dict[str, Any] | None
    checks: list[QualityCheck]


class Defaults(BaseModel):
    indicator_code: str
    country_codes: list[str]


class DashboardSummary(BaseModel):
    countries: int
    indicators: int
    observations: int
    latest_successful_load_at: datetime | None
    latest_run: RunSummary | None
    defaults: Defaults


class IndicatorOut(BaseModel):
    indicator_code: str
    name: str
    description: str | None
    unit: str
    source_name: str
    frequency: str
    observation_count: int
    first_year: int | None
    last_year: int | None


class CountryOut(BaseModel):
    country_code: str
    name: str
    region: str | None
    income_level: str | None


class ObservationOut(BaseModel):
    country_code: str
    country_name: str
    indicator_code: str
    indicator_name: str
    year: int
    value: float
    unit: str
    ingested_at: datetime


class IndicatorRef(BaseModel):
    indicator_code: str
    name: str
    unit: str


class TrendPoint(BaseModel):
    year: int
    value: float


class TrendSeries(BaseModel):
    country_code: str
    country_name: str
    points: list[TrendPoint] = Field(description="Only years with an observation; missing years are absent, not 0")


class TrendResponse(BaseModel):
    indicator: IndicatorRef
    start_year: int | None
    end_year: int | None
    series: list[TrendSeries]


class ComparisonItem(BaseModel):
    country_code: str
    country_name: str
    value: float


class UnavailableCountry(BaseModel):
    country_code: str
    country_name: str


class ComparisonResponse(BaseModel):
    indicator: IndicatorRef
    year: int
    items: list[ComparisonItem] = Field(description="Sorted by value, descending")
    unavailable: list[UnavailableCountry] = Field(description="Selected countries with no value for this year")


class QualityLatest(BaseModel):
    run: RunSummary | None
    checks: list[QualityCheck]


class RunAccepted(BaseModel):
    run_id: uuid.UUID
    status: Literal["running"]
    status_url: str
