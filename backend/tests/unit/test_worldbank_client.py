"""World Bank client: classification, retries and pagination (all HTTP is mocked)."""

from datetime import date

import pytest
import requests
import responses
from responses import matchers

from src.pipeline.worldbank import (
    ApiErrorPayload,
    HttpStatusError,
    MalformedResponseError,
    PaginationError,
    TransportError,
    WorldBankClient,
    parse_page,
)

BASE = "https://api.test.invalid/v2"
SERIES_PATH = "country/IND;USA/indicator/SP.POP.TOTL"
SERIES_URL = f"{BASE}/{SERIES_PATH}"


def obs(iso3: str, year: int, value: float | None) -> dict:
    return {
        "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
        "country": {"id": iso3[:2], "value": iso3},
        "countryiso3code": iso3,
        "date": str(year),
        "value": value,
    }


def page(rows: list, *, page_no: int = 1, pages: int = 1, total: int | None = None, per_page="50") -> list:
    meta = {"page": page_no, "pages": pages, "per_page": per_page, "total": len(rows) if total is None else total, "lastupdated": "2026-10-08"}
    return [meta, rows]


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(sleeps) -> WorldBankClient:
    return WorldBankClient(BASE, timeout_seconds=5, max_retries=3, backoff_seconds=1, per_page=50, sleep=sleeps.append)


def page_param(n: int):
    return matchers.query_param_matcher({"page": str(n)}, strict_match=False)


# -- classification -------------------------------------------------------


def test_parse_page_accepts_string_or_int_metadata():
    meta, rows = parse_page(page([obs("IND", 2020, 1.0)], per_page="50"), "x")
    assert (meta.page, meta.pages, meta.per_page, meta.total) == (1, 1, 50, 1)
    assert meta.last_updated == date(2026, 10, 8)
    assert rows[0]["countryiso3code"] == "IND"


def test_valid_empty_result_is_not_an_error():
    meta, rows = parse_page([{"page": 1, "pages": 0, "per_page": 50, "total": 0}, None], "x")
    assert rows == [] and meta.total == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": "object"},
        [{"page": 1}],
        [{"page": 1, "pages": 1, "per_page": 50, "total": 2}, None],  # data missing but rows reported
        [{"page": "one", "pages": 1, "per_page": 50, "total": 1}, [obs("IND", 2020, 1)]],
        [{"page": 1, "pages": 1, "per_page": 50, "total": 1}, ["not an object"]],
    ],
)
def test_malformed_payloads(payload):
    with pytest.raises(MalformedResponseError):
        parse_page(payload, "x")


@responses.activate
def test_http_200_error_payload_is_an_error_not_empty(client):
    responses.get(SERIES_URL, json=[{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}])

    with pytest.raises(ApiErrorPayload, match="id 120: Invalid value") as excinfo:
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert excinfo.value.endpoint == SERIES_PATH
    assert len(responses.calls) == 1  # not retried


@responses.activate
def test_invalid_json_body(client):
    responses.get(SERIES_URL, body="<html>proxy error</html>", status=200)

    with pytest.raises(MalformedResponseError, match="not valid JSON"):
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)
    assert len(responses.calls) == 1


# -- success and pagination -----------------------------------------------


@responses.activate
def test_single_page_series_keeps_nulls(client):
    rows = [obs("IND", 2021, 1.4e9), obs("USA", 2021, None)]
    responses.get(SERIES_URL, json=page(rows), match=[matchers.query_param_matcher({"format": "json", "date": "2020:2021", "per_page": "50", "page": "1"})])

    result = client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert result.total == 2 and result.pages == 1
    assert [r["value"] for r in result.rows] == [1.4e9, None]  # null stays null
    assert result.last_updated == date(2026, 10, 8)


@responses.activate
def test_multi_page_series_fetches_every_page(client):
    responses.get(SERIES_URL, json=page([obs("IND", 2021, 1), obs("IND", 2020, 2)], page_no=1, pages=2, total=3), match=[page_param(1)])
    responses.get(SERIES_URL, json=page([obs("USA", 2021, 3)], page_no=2, pages=2, total=3), match=[page_param(2)])

    result = client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert len(result.rows) == 3 and result.pages == 2
    assert len(responses.calls) == 2


@responses.activate
def test_valid_empty_series(client):
    responses.get(SERIES_URL, json=[{"page": 1, "pages": 0, "per_page": 50, "total": 0}, None])

    result = client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert result.rows == [] and result.total == 0


@responses.activate
def test_row_count_must_match_total(client):
    responses.get(SERIES_URL, json=page([obs("IND", 2021, 1)], total=2))

    with pytest.raises(PaginationError, match="received 1 rows but metadata reports 2"):
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)


@responses.activate
def test_page_count_change_between_pages(client):
    responses.get(SERIES_URL, json=page([obs("IND", 2021, 1)], page_no=1, pages=2, total=2), match=[page_param(1)])
    responses.get(SERIES_URL, json=page([obs("USA", 2021, 1)], page_no=2, pages=3, total=2), match=[page_param(2)])

    with pytest.raises(PaginationError, match="changed between pages"):
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)


# -- retries --------------------------------------------------------------


@responses.activate
def test_transient_5xx_is_retried_with_exponential_backoff(client, sleeps):
    responses.get(SERIES_URL, status=503)
    responses.get(SERIES_URL, status=502)
    responses.get(SERIES_URL, json=page([obs("IND", 2021, 1)]))

    result = client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert len(result.rows) == 1
    assert len(responses.calls) == 3
    assert sleeps == [1, 2]


@responses.activate
def test_retry_after_header_is_honored(client, sleeps):
    responses.get(SERIES_URL, status=429, headers={"Retry-After": "7"})
    responses.get(SERIES_URL, json=page([obs("IND", 2021, 1)]))

    client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert sleeps == [7]


@responses.activate
def test_retries_are_bounded(client, sleeps):
    responses.get(SERIES_URL, status=500)

    with pytest.raises(HttpStatusError, match="HTTP 500 after 4 attempt") as excinfo:
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert excinfo.value.status_code == 500
    assert len(responses.calls) == 4  # 1 + max_retries
    assert sleeps == [1, 2, 4]


@responses.activate
def test_permanent_4xx_is_not_retried(client, sleeps):
    responses.get(SERIES_URL, status=404)

    with pytest.raises(HttpStatusError, match="HTTP 404"):
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert len(responses.calls) == 1 and sleeps == []


@responses.activate
@pytest.mark.parametrize("exc", [requests.ConnectionError("refused"), requests.Timeout("read timed out")])
def test_transport_errors_are_retried_then_reported(client, sleeps, exc):
    responses.get(SERIES_URL, body=exc)

    with pytest.raises(TransportError, match="after 4 attempt"):
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert len(responses.calls) == 4 and sleeps == [1, 2, 4]


@responses.activate
def test_error_messages_do_not_include_response_bodies(client):
    responses.get(SERIES_URL, status=500, body="internal secret stack trace")

    with pytest.raises(HttpStatusError) as excinfo:
        client.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2020, 2021)

    assert "secret" not in str(excinfo.value)


# -- metadata endpoints ---------------------------------------------------


@responses.activate
def test_fetch_countries_flags_aggregates(client):
    responses.get(
        f"{BASE}/country/IND;WLD",
        json=page(
            [
                {"id": "IND", "name": "India", "region": {"id": "SAS", "value": "South Asia"}, "incomeLevel": {"value": "Lower middle income"}},
                {"id": "WLD", "name": "World", "region": {"id": "NA", "value": "Aggregates"}, "incomeLevel": {"value": "Aggregates"}},
            ]
        ),
    )

    india, world = client.fetch_countries(["IND", "WLD"])

    assert (india.country_code, india.region, india.is_aggregate) == ("IND", "South Asia", False)
    assert (world.country_code, world.is_aggregate) == ("WLD", True)


@responses.activate
def test_fetch_indicator_metadata(client):
    responses.get(
        f"{BASE}/indicator/SP.POP.TOTL",
        json=page([{"id": "SP.POP.TOTL", "name": "Population, total", "unit": "", "sourceNote": "Total population."}]),
    )

    meta = client.fetch_indicator("SP.POP.TOTL")

    assert (meta.name, meta.description) == ("Population, total", "Total population.")


@pytest.mark.live
def test_live_small_request():
    """Optional smoke test against the real API (excluded by default: run with ``pytest -m live``)."""
    live = WorldBankClient("https://api.worldbank.org/v2", per_page=2, max_retries=1)
    result = live.fetch_series("SP.POP.TOTL", ["IND", "USA"], 2022, 2023)
    assert result.total == 4 and result.pages == 2 and len(result.rows) == 4
