"""Deterministic stand-in for the World Bank client (test fixture data, not real observations)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from src.pipeline.worldbank import CountryMeta, IndicatorMeta, SeriesResult, WorldBankError

COUNTRY_NAMES = {"IND": "India", "USA": "United States", "WLD": "World"}
INDICATOR_NAMES = {"SP.POP.TOTL": "Population, total", "NY.GDP.MKTP.CD": "GDP (current US$)"}

TEST_SETTINGS = {
    "country_codes": "IND,USA",
    "indicator_codes": "SP.POP.TOTL,NY.GDP.MKTP.CD",
    "indicator_units": {"SP.POP.TOTL": "people", "NY.GDP.MKTP.CD": "current US$"},
    "default_indicator_code": "SP.POP.TOTL",
    "default_country_codes": "IND,USA",
    "start_year": 2019,
    "end_year": 2020,
}


def obs(country: str, year: int | str, value: Any, indicator: str = "SP.POP.TOTL") -> dict[str, Any]:
    return {"indicator": {"id": indicator}, "country": {"id": country[:2]}, "countryiso3code": country, "date": str(year), "value": value}


def default_rows(indicator: str, scale: float = 1.0) -> list[dict[str, Any]]:
    base = 1000.0 if indicator == "SP.POP.TOTL" else 5000.0
    return [
        obs(country, year, base * (i + 1) * (year - 2018) * scale, indicator)
        for i, country in enumerate(("IND", "USA"))
        for year in (2019, 2020)
    ]


class FakeSource:
    """Configurable fake: per-indicator rows, failures, or a hook raising on metadata."""

    def __init__(
        self,
        rows: dict[str, list[dict[str, Any]]] | None = None,
        *,
        series_errors: dict[str, WorldBankError] | None = None,
        country_error: WorldBankError | None = None,
        aggregates: set[str] | None = None,
        on_series: Callable[[str], None] | None = None,
    ) -> None:
        self.rows = rows if rows is not None else {code: default_rows(code) for code in INDICATOR_NAMES}
        self.series_errors = series_errors or {}
        self.country_error = country_error
        self.aggregates = aggregates or set()
        self.on_series = on_series
        self.series_calls: list[str] = []

    def fetch_countries(self, country_codes: list[str]) -> list[CountryMeta]:
        if self.country_error:
            raise self.country_error
        return [
            CountryMeta(code, COUNTRY_NAMES.get(code, code), "Aggregates" if code in self.aggregates else "Test region", "Test income", code in self.aggregates)
            for code in country_codes
            if code in COUNTRY_NAMES
        ]

    def fetch_indicator(self, indicator_code: str) -> IndicatorMeta:
        return IndicatorMeta(indicator_code, INDICATOR_NAMES.get(indicator_code, indicator_code), "Test description")

    def fetch_series(self, indicator_code: str, country_codes: list[str], start_year: int, end_year: int) -> SeriesResult:
        self.series_calls.append(indicator_code)
        if self.on_series:
            self.on_series(indicator_code)
        if indicator_code in self.series_errors:
            raise self.series_errors[indicator_code]
        rows = self.rows.get(indicator_code, [])
        return SeriesResult(indicator_code, rows, len(rows), 1, date(2026, 10, 8))
