"""World Bank Indicators API client (TRD §5, D-08, D-10).

Every response is classified before its data is used, so an API failure can
never be mistaken for a valid empty dataset:

* transport errors and HTTP 429/5xx are retried with bounded exponential backoff
  (honoring ``Retry-After``);
* other HTTP errors, malformed bodies and World Bank error payloads (which arrive
  with HTTP 200) fail immediately;
* only ``total == 0`` with no data is a valid empty result.

Error messages name the endpoint and the failure class only; response bodies are
never copied into errors or logs.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 60.0


class WorldBankError(Exception):
    """Base class. ``endpoint`` is the request path (no host, no query string)."""

    kind = "error"

    def __init__(self, message: str, *, endpoint: str) -> None:
        super().__init__(f"{message} ({endpoint})")
        self.endpoint = endpoint


class TransportError(WorldBankError):
    kind = "transport_error"


class HttpStatusError(WorldBankError):
    kind = "http_error"

    def __init__(self, message: str, *, endpoint: str, status_code: int) -> None:
        super().__init__(message, endpoint=endpoint)
        self.status_code = status_code


class ApiErrorPayload(WorldBankError):
    """The API returned ``[{"message": [...]}]``, usually with HTTP 200."""

    kind = "api_error_payload"


class MalformedResponseError(WorldBankError):
    kind = "malformed_response"


class PaginationError(WorldBankError):
    kind = "pagination_inconsistent"


@dataclass(frozen=True)
class PageMeta:
    page: int
    pages: int
    per_page: int
    total: int
    last_updated: date | None


@dataclass(frozen=True)
class CountryMeta:
    country_code: str
    name: str
    region: str | None
    income_level: str | None
    is_aggregate: bool


@dataclass(frozen=True)
class IndicatorMeta:
    indicator_code: str
    name: str
    description: str | None


@dataclass
class SeriesResult:
    """All rows of one indicator series, exactly as returned (values may be ``None``)."""

    indicator_code: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    pages: int = 0
    last_updated: date | None = None


def _to_int(meta: dict[str, Any], key: str, endpoint: str) -> int:
    try:
        return int(meta[key])
    except (KeyError, TypeError, ValueError):
        raise MalformedResponseError(f"metadata field '{key}' missing or not an integer", endpoint=endpoint) from None


def _to_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_page(payload: Any, endpoint: str) -> tuple[PageMeta, list[dict[str, Any]]]:
    """Classify one decoded JSON page (TRD §5 classification table)."""
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:
        messages = payload[0].get("message") or []
        ids = ", ".join(str(m.get("id", "?")) for m in messages if isinstance(m, dict)) or "unknown"
        keys = "; ".join(str(m.get("key", ""))[:80] for m in messages if isinstance(m, dict))
        raise ApiErrorPayload(f"World Bank API error payload (id {ids}: {keys})", endpoint=endpoint)
    if not (isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict)):
        raise MalformedResponseError("response is not shaped [metadata, data]", endpoint=endpoint)

    raw_meta, data = payload
    meta = PageMeta(
        page=_to_int(raw_meta, "page", endpoint),
        pages=_to_int(raw_meta, "pages", endpoint),
        per_page=_to_int(raw_meta, "per_page", endpoint),
        total=_to_int(raw_meta, "total", endpoint),
        last_updated=_to_date(raw_meta.get("lastupdated")),
    )
    if data is None or data == []:
        if meta.total == 0:
            return meta, []  # the only valid empty result
        raise MalformedResponseError("data is empty but metadata reports rows", endpoint=endpoint)
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise MalformedResponseError("data is not a list of objects", endpoint=endpoint)
    return meta, data


class WorldBankClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        max_retries: int = 3,
        backoff_seconds: float = 1,
        per_page: int = 1000,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.per_page = per_page
        self.session = session or requests.Session()
        self._sleep = sleep

    # -- HTTP --------------------------------------------------------------

    def _retry_delay(self, attempt: int, response: requests.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.strip().isdigit():
                return min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
        return min(self.backoff_seconds * (2 ** (attempt - 1)), MAX_RETRY_AFTER_SECONDS)

    def get_json(self, path: str, params: dict[str, Any]) -> Any:
        """GET ``path`` with bounded retries for transient failures; returns decoded JSON."""
        url = f"{self.base_url}/{path}"
        query = {"format": "json", **params}
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            response: requests.Response | None = None
            try:
                response = self.session.get(url, params=query, timeout=self.timeout_seconds)
            except (requests.ConnectionError, requests.Timeout) as exc:
                error: WorldBankError = TransportError(
                    f"{type(exc).__name__} after {attempt} attempt(s)", endpoint=path
                )
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError:
                        raise MalformedResponseError("response body is not valid JSON", endpoint=path) from None
                error = HttpStatusError(
                    f"HTTP {response.status_code} after {attempt} attempt(s)",
                    endpoint=path,
                    status_code=response.status_code,
                )
                if response.status_code not in RETRYABLE_STATUS:
                    raise error
            if attempt == attempts:
                raise error
            delay = self._retry_delay(attempt, response)
            logger.warning(
                "World Bank request failed; retrying",
                extra={"event": "source_retry", "endpoint": path, "error_kind": error.kind, "attempt": attempt, "max_retries": self.max_retries, "delay_s": round(delay, 2)},
            )
            self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def fetch_all_pages(self, path: str, params: dict[str, Any]) -> tuple[PageMeta, list[dict[str, Any]]]:
        """Fetch every page and verify page count and row total stay consistent."""
        first, rows = parse_page(self.get_json(path, {**params, "page": 1}), path)
        rows = list(rows)
        for page_number in range(2, first.pages + 1):
            meta, page_rows = parse_page(self.get_json(path, {**params, "page": page_number}), path)
            if meta.pages != first.pages or meta.total != first.total:
                raise PaginationError("page count or total changed between pages", endpoint=path)
            rows.extend(page_rows)
        if len(rows) != first.total:
            raise PaginationError(f"received {len(rows)} rows but metadata reports {first.total}", endpoint=path)
        return first, rows

    # -- Endpoints -----------------------------------------------------------

    def fetch_countries(self, country_codes: Sequence[str]) -> list[CountryMeta]:
        path = f"country/{';'.join(country_codes)}"
        _, rows = self.fetch_all_pages(path, {"per_page": max(50, len(country_codes))})
        countries = []
        for row in rows:
            region = (row.get("region") or {}).get("value") or None
            income = (row.get("incomeLevel") or {}).get("value") or None
            countries.append(
                CountryMeta(
                    country_code=str(row.get("id", "")).upper(),
                    name=str(row.get("name") or row.get("id") or ""),
                    region=region,
                    income_level=income,
                    is_aggregate=region == "Aggregates",
                )
            )
        return countries

    def fetch_indicator(self, indicator_code: str) -> IndicatorMeta:
        path = f"indicator/{indicator_code}"
        _, rows = self.fetch_all_pages(path, {"per_page": 50})
        match = next((row for row in rows if row.get("id") == indicator_code), None)
        if match is None:
            raise MalformedResponseError("indicator metadata missing from response", endpoint=path)
        return IndicatorMeta(
            indicator_code=indicator_code,
            name=str(match.get("name") or indicator_code),
            description=match.get("sourceNote") or None,
        )

    def fetch_series(
        self, indicator_code: str, country_codes: Sequence[str], start_year: int, end_year: int
    ) -> SeriesResult:
        """One paginated series for all countries (D-10). Rows are returned unmodified."""
        path = f"country/{';'.join(country_codes)}/indicator/{indicator_code}"
        meta, rows = self.fetch_all_pages(path, {"date": f"{start_year}:{end_year}", "per_page": self.per_page})
        logger.info(
            "Fetched indicator series",
            extra={"event": "series_fetched", "indicator_code": indicator_code, "rows": len(rows), "pages": max(meta.pages, 1)},
        )
        return SeriesResult(
            indicator_code=indicator_code,
            rows=rows,
            total=meta.total,
            pages=meta.pages,
            last_updated=meta.last_updated,
        )
