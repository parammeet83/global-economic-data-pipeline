"""API error handling and CORS without a database."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.db.session import create_db_engine, create_session_factory
from src.main import create_app
from src.services import analytics


@pytest.fixture
def unreachable_factory():
    engine = create_db_engine(SecretStr("postgresql+psycopg://nobody:pw-secret@127.0.0.1:1/gedp_test"))
    yield create_session_factory(engine)
    engine.dispose()


def test_database_outage_returns_503_without_details(make_settings, unreachable_factory):
    with TestClient(create_app(make_settings(), session_factory=unreachable_factory)) as client:
        response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 503
    assert response.json() == {"error": {"code": "database_unavailable", "message": "The database is unavailable. Try again later."}}
    for leaked in ("pw-secret", "127.0.0.1", "nobody", "psycopg", "Traceback"):
        assert leaked not in response.text


def test_unexpected_error_returns_500_without_details(make_settings, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("internal secret detail")

    monkeypatch.setattr(analytics, "list_countries", boom)
    app = create_app(make_settings(), session_factory=lambda: _NullSession())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/countries")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text and "Traceback" not in response.text


def test_unknown_route_uses_the_error_shape(make_settings):
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cors_allows_only_configured_origins(make_settings):
    with TestClient(create_app(make_settings(cors_origins="http://localhost:5173"))) as client:
        allowed = client.options(
            "/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
        )
        denied = client.options(
            "/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
        )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_openapi_lists_every_endpoint(make_settings):
    with TestClient(create_app(make_settings())) as client:
        paths = set(client.get("/openapi.json").json()["paths"])

    assert paths == {
        "/health",
        "/api/v1/dashboard/summary",
        "/api/v1/indicators",
        "/api/v1/countries",
        "/api/v1/observations",
        "/api/v1/analytics/trend",
        "/api/v1/analytics/country-comparison",
        "/api/v1/runs",
        "/api/v1/runs/{run_id}",
        "/api/v1/quality/latest",
        "/api/v1/pipeline/run",
    }


class _NullSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
