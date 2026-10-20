"""API contract tests against the test database (D-17, D-23, D-24, D-25, D-26)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.pipeline.orchestrator import run_pipeline
from src.pipeline.worldbank import HttpStatusError
from tests.fakes import TEST_SETTINGS, FakeSource, default_rows, obs
from tests.integration.helpers import insert_run

pytestmark = pytest.mark.integration

# A browser on this machine talking to the API directly (loopback Host header and TCP peer).
LOCAL = {"base_url": "http://127.0.0.1:8000", "client": ("127.0.0.1", 50000)}


@pytest.fixture
def settings(make_settings):
    return make_settings(**TEST_SETTINGS)


@pytest.fixture
def client(settings, session_factory):
    app = create_app(settings, session_factory=session_factory, source_client=FakeSource())
    with TestClient(app, **LOCAL) as test_client:
        yield test_client


@pytest.fixture
def loaded(session_factory, settings):
    """Load fixture data through the real pipeline; IND has no 2020 population value (null)."""
    rows = {code: default_rows(code) for code in ("SP.POP.TOTL", "NY.GDP.MKTP.CD")}
    rows["SP.POP.TOTL"][1] = obs("IND", 2020, None)
    return run_pipeline(session_factory, settings, "cli", FakeSource(rows))


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["message"]
    assert "Traceback" not in response.text and "SELECT" not in response.text
    return body["error"]


# -- summary and reference data --------------------------------------------


def test_summary_on_empty_database(client):
    body = client.get("/api/v1/dashboard/summary").json()

    assert (body["countries"], body["indicators"], body["observations"]) == (0, 0, 0)
    assert body["latest_successful_load_at"] is None and body["latest_run"] is None
    assert body["defaults"] == {"indicator_code": "SP.POP.TOTL", "country_codes": ["IND", "USA"]}


def test_summary_after_a_run(client, loaded):
    body = client.get("/api/v1/dashboard/summary").json()

    assert (body["countries"], body["indicators"], body["observations"]) == (2, 2, 7)
    assert body["latest_successful_load_at"] is not None
    assert body["latest_run"]["run_id"] == str(loaded.run_id)
    assert body["latest_run"]["records_null_skipped"] == 1


def test_indicators_include_configured_units_and_coverage(client, loaded):
    body = {i["indicator_code"]: i for i in client.get("/api/v1/indicators").json()}

    assert body["SP.POP.TOTL"]["unit"] == "people"
    assert body["NY.GDP.MKTP.CD"]["unit"] == "current US$"
    assert (body["SP.POP.TOTL"]["observation_count"], body["SP.POP.TOTL"]["first_year"], body["SP.POP.TOTL"]["last_year"]) == (3, 2019, 2020)


def test_countries_represented_in_data(client, loaded):
    assert [c["country_code"] for c in client.get("/api/v1/countries").json()] == ["IND", "USA"]


# -- observations ----------------------------------------------------------


def test_observations_filter_sort_and_paginate(client, loaded):
    params = {"indicator_code": "ny.gdp.mktp.cd", "country_code": ["usa", "IND"], "sort_by": "value", "sort_order": "desc", "page_size": 3}
    first = client.get("/api/v1/observations", params=params).json()
    second = client.get("/api/v1/observations", params={**params, "page": 2}).json()

    assert (first["total"], first["page"], first["page_size"], len(first["items"]), len(second["items"])) == (4, 1, 3, 3, 1)
    values = [i["value"] for i in first["items"] + second["items"]]
    assert values == sorted(values, reverse=True)
    item = first["items"][0]
    assert set(item) == {"country_code", "country_name", "indicator_code", "indicator_name", "year", "value", "unit", "ingested_at"}
    assert item["unit"] == "current US$" and isinstance(item["value"], float)


def test_observations_year_filter(client, loaded):
    body = client.get("/api/v1/observations", params={"start_year": 2020, "end_year": 2020}).json()

    assert body["total"] == 3 and {i["year"] for i in body["items"]} == {2020}


@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        ({"page_size": 501}, None),
        ({"page": 0}, None),
        ({"start_year": 1800}, None),
        ({"sort_by": "value; DROP TABLE countries"}, None),
        ({"country_code": "IN"}, "ISO-3"),
        ({"start_year": 2021, "end_year": 2020}, "start_year must be less than or equal to end_year"),
        ({"indicator_code": "bad code!"}, "not a valid indicator code"),
    ],
)
def test_observations_reject_invalid_filters(client, params, fragment):
    error = assert_error(client.get("/api/v1/observations", params=params), 422, "validation_error")
    if fragment:
        assert fragment in error["message"]


# -- trend and comparison --------------------------------------------------


def test_trend_omits_missing_years_instead_of_zero(client, loaded):
    body = client.get("/api/v1/analytics/trend", params={"indicator_code": "SP.POP.TOTL", "country_code": ["IND", "USA"]}).json()

    assert body["indicator"] == {"indicator_code": "SP.POP.TOTL", "name": "Population, total", "unit": "people"}
    series = {s["country_code"]: s for s in body["series"]}
    assert [p["year"] for p in series["IND"]["points"]] == [2019]  # 2020 was null at the source: absent, not 0
    assert [p["year"] for p in series["USA"]["points"]] == [2019, 2020]
    assert series["IND"]["country_name"] == "India"


def test_trend_validation(client, loaded):
    assert_error(client.get("/api/v1/analytics/trend", params={"indicator_code": "SP.POP.TOTL"}), 422, "validation_error")
    assert_error(client.get("/api/v1/analytics/trend", params={"indicator_code": "XX.NONE", "country_code": "IND"}), 404, "not_found")
    many = [f"A{chr(65 + i)}{chr(65 + i)}" for i in range(11)]
    assert_error(client.get("/api/v1/analytics/trend", params={"indicator_code": "SP.POP.TOTL", "country_code": many}), 422, "validation_error")


def test_comparison_sorts_values_and_lists_unavailable(client, loaded):
    body = client.get(
        "/api/v1/analytics/country-comparison", params={"indicator_code": "SP.POP.TOTL", "year": 2020, "country_code": ["IND", "USA"]}
    ).json()

    assert [i["country_code"] for i in body["items"]] == ["USA"]
    assert body["unavailable"] == [{"country_code": "IND", "country_name": "India"}]


def test_comparison_requires_two_countries(client, loaded):
    response = client.get("/api/v1/analytics/country-comparison", params={"indicator_code": "SP.POP.TOTL", "year": 2020, "country_code": "IND"})
    assert "at least 2" in assert_error(response, 422, "validation_error")["message"]


# -- runs and quality ------------------------------------------------------


def test_run_list_and_detail(client, loaded):
    page = client.get("/api/v1/runs", params={"page_size": 10}).json()
    assert page["total"] == 1 and page["items"][0]["status"] == "success"

    detail = client.get(f"/api/v1/runs/{loaded.run_id}").json()
    assert detail["records_loaded"] == 7 and len(detail["checks"]) == 9
    assert {c["check_name"]: c["status"] for c in detail["checks"]}["null_value_rate"] == "warning"
    assert "database_url" not in str(detail["config_snapshot"]).lower()


def test_run_detail_errors(client):
    assert_error(client.get(f"/api/v1/runs/{uuid.uuid4()}"), 404, "not_found")
    assert_error(client.get("/api/v1/runs/not-a-uuid"), 422, "validation_error")
    assert_error(client.get("/api/v1/runs", params={"page_size": 101}), 422, "validation_error")


def test_quality_latest_empty(client):
    assert client.get("/api/v1/quality/latest").json() == {"run": None, "checks": []}


def test_quality_latest_shows_a_newer_failed_run_not_an_older_success(client, session_factory, settings, loaded, db_connection):
    error = HttpStatusError("HTTP 500", endpoint="x", status_code=500)
    failed = run_pipeline(session_factory, settings, "cli", FakeSource(series_errors={"SP.POP.TOTL": error, "NY.GDP.MKTP.CD": error}))
    # all test rows share one transaction timestamp, so make the ordering explicit
    db_connection.exec_driver_sql(
        "UPDATE pipeline_runs SET started_at = started_at - interval '1 hour', finished_at = finished_at - interval '1 hour' WHERE run_id = %s",
        (loaded.run_id,),
    )

    body = client.get("/api/v1/quality/latest").json()

    assert body["run"]["run_id"] == str(failed.run_id) and body["run"]["status"] == "failed"
    assert {c["check_name"]: c["status"] for c in body["checks"]}["extraction_requests_succeeded"] == "failed"


# -- manual trigger --------------------------------------------------------


def test_trigger_returns_202_and_run_completes_in_background(client):
    response = client.post("/api/v1/pipeline/run")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running" and response.headers["location"] == body["status_url"]
    # TestClient runs background tasks before returning, so polling now sees the terminal status
    detail = client.get(body["status_url"]).json()
    assert (detail["status"], detail["triggered_by"], detail["records_loaded"]) == ("success", "api", 8)


def test_trigger_conflict_returns_409_with_running_run_id(client, db_connection):
    running = insert_run(db_connection, status="running", age_minutes=1)

    error = assert_error(client.post("/api/v1/pipeline/run"), 409, "run_in_progress")

    assert error["run_id"] == str(running)


def test_trigger_disabled_returns_403(make_settings, session_factory):
    settings = make_settings(**TEST_SETTINGS, enable_manual_trigger=False)
    with TestClient(create_app(settings, session_factory=session_factory, source_client=FakeSource()), **LOCAL) as client:
        assert_error(client.post("/api/v1/pipeline/run"), 403, "manual_trigger_disabled")


def test_trigger_refuses_non_local_clients(settings, session_factory):
    app = create_app(settings, session_factory=session_factory, source_client=FakeSource())
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("203.0.113.7", 50000)) as client:
        assert_error(client.post("/api/v1/pipeline/run"), 403, "manual_trigger_local_only")


# -- local-only guard: direct and proxied requests (D-39) ------------------

VITE_PROXY = ["127.0.0.1", "::1"]


@pytest.fixture
def trigger(make_settings, session_factory):
    """POST /pipeline/run with a given TCP peer, Host header, extra headers and trusted proxies."""

    def post(*, peer="127.0.0.1", host="127.0.0.1:8000", headers=None, trusted=None):
        settings = make_settings(**TEST_SETTINGS, trusted_proxy_ips=",".join(trusted or []))
        app = create_app(settings, session_factory=session_factory, source_client=FakeSource())
        with TestClient(app, base_url=f"http://{host}", client=(peer, 50000)) as client:
            return client.post("/api/v1/pipeline/run", headers=headers or {})

    return post


def test_direct_local_request_is_accepted(trigger):
    assert trigger().status_code == 202


def test_local_browser_through_trusted_vite_proxy_is_accepted(trigger):
    # Vite (xfwd) appends the browser's address; the Host header is the dev server's.
    response = trigger(host="localhost:5173", headers={"X-Forwarded-For": "127.0.0.1"}, trusted=VITE_PROXY)
    assert response.status_code == 202


def test_lan_client_through_trusted_vite_proxy_is_refused(trigger):
    response = trigger(host="localhost:5173", headers={"X-Forwarded-For": "192.168.1.20"}, trusted=VITE_PROXY)
    assert response.json()["error"]["code"] == "manual_trigger_local_only"


def test_forged_loopback_entry_before_the_real_client_is_ignored(trigger):
    # The client sent "X-Forwarded-For: 127.0.0.1"; the proxy appended the real address.
    response = trigger(host="localhost:5173", headers={"X-Forwarded-For": "127.0.0.1, 192.168.1.20"}, trusted=VITE_PROXY)
    assert response.status_code == 403


def test_forwarding_headers_from_an_unconfigured_proxy_fail_closed(trigger):
    response = trigger(host="localhost:5173", headers={"X-Forwarded-For": "127.0.0.1"})
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (403, "manual_trigger_local_only")
    assert "TRUSTED_PROXY_IPS" in error["message"]


@pytest.mark.parametrize("header", [{"Forwarded": "for=127.0.0.1"}, {"X-Real-IP": "127.0.0.1"}])
def test_other_forwarding_headers_are_not_trusted(trigger, header):
    assert trigger(headers=header, trusted=VITE_PROXY).status_code == 403


def test_non_loopback_host_header_is_refused(trigger):
    # A browser on the LAN reaching an exposed dev server sends the server's LAN address as Host.
    assert trigger(host="192.168.1.5:5173").status_code == 403


def test_remote_peer_cannot_claim_loopback_with_a_forged_header(trigger):
    response = trigger(peer="203.0.113.7", headers={"X-Forwarded-For": "127.0.0.1"}, trusted=VITE_PROXY)
    assert response.status_code == 403


def test_disabled_trigger_still_returns_403_before_the_local_check(make_settings, session_factory):
    settings = make_settings(**TEST_SETTINGS, enable_manual_trigger=False)
    app = create_app(settings, session_factory=session_factory, source_client=FakeSource())
    with TestClient(app, base_url="http://192.168.1.5:8000", client=("203.0.113.7", 50000)) as client:
        assert client.post("/api/v1/pipeline/run").json()["error"]["code"] == "manual_trigger_disabled"
