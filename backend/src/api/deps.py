"""Request dependencies: settings, one database session per request, validated filters."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from src.api.errors import bad_request
from src.core.config import Settings
from src.db.session import SessionFactory

ISO3 = re.compile(r"^[A-Z]{3}$")
INDICATOR = re.compile(r"^[A-Z0-9][A-Z0-9._]{0,31}$")
MIN_YEAR, MAX_YEAR = 1900, 2200


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> SessionFactory:
    return request.app.state.session_factory


def get_session(factory: Annotated[SessionFactory, Depends(get_session_factory)]) -> Iterator[Session]:
    with factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
YearQuery = Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)]


def normalize_indicator(code: str) -> str:
    value = code.strip().upper()
    if not INDICATOR.match(value):
        raise bad_request("indicator_code is not a valid indicator code")
    return value


def normalize_countries(codes: list[str] | None, *, maximum: int, minimum: int = 0) -> list[str]:
    values: list[str] = []
    for raw in codes or []:
        code = raw.strip().upper()
        if not ISO3.match(code):
            raise bad_request("country_code values must be 3-letter ISO-3 codes")
        if code not in values:
            values.append(code)
    if len(values) < minimum:
        raise bad_request(f"Select at least {minimum} countries")
    if len(values) > maximum:
        raise bad_request(f"Select at most {maximum} countries")
    return values


def check_year_range(start_year: int | None, end_year: int | None) -> None:
    if start_year is not None and end_year is not None and start_year > end_year:
        raise bad_request("start_year must be less than or equal to end_year")
