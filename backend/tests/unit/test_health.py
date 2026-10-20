"""GET /health with the database mocked: no running PostgreSQL is needed."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from src.api.health import get_engine
from src.core.config import ConfigurationError
from src.db.session import check_database_connection, create_db_engine
from src.main import create_app


@pytest.fixture
def fake_engine() -> MagicMock:
    return MagicMock(name="engine")


@pytest.fixture
def client(make_settings, fake_engine):
    app = create_app(settings=make_settings())
    app.dependency_overrides[get_engine] = lambda: fake_engine
    with TestClient(app) as test_client:
        yield test_client


def test_health_ok_when_select_1_succeeds(client, fake_engine):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    executed = fake_engine.connect.return_value.__enter__.return_value.execute.call_args.args[0]
    assert str(executed) == "SELECT 1"


def test_health_503_when_database_unreachable(client, fake_engine):
    driver_error = Exception('connection to "secret-host" failed: password authentication failed for user "gedp_app"')
    fake_engine.connect.side_effect = OperationalError("SELECT 1", {}, driver_error)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    for leaked in ("secret-host", "password", "gedp_app", "SELECT", "Traceback"):
        assert leaked not in response.text


def test_health_503_on_unexpected_error(client, fake_engine):
    fake_engine.connect.side_effect = RuntimeError("unexpected")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_openapi_documents_both_health_responses(client):
    responses = client.get("/openapi.json").json()["paths"]["/health"]["get"]["responses"]

    def example(code: str) -> dict:
        return responses[code]["content"]["application/json"]["example"]

    assert example("200") == {"status": "ok", "database": "ok"}
    assert example("503") == {"status": "degraded", "database": "unavailable"}
    for code in ("200", "503"):
        schema = responses[code]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/HealthResponse"}


def test_check_fails_against_a_real_closed_port():
    # Real SQLAlchemy + psycopg path, but nothing listens on port 1, so no database is needed.
    engine = create_db_engine(SecretStr("postgresql+psycopg://nobody:pw@127.0.0.1:1/gedp_test"))
    try:
        assert check_database_connection(engine) is False
    finally:
        engine.dispose()


def test_startup_fails_with_readable_error_when_config_is_invalid(monkeypatch):
    def broken_settings():
        raise ConfigurationError("Configuration error.\n  - DATABASE_URL: is required but was not set")

    monkeypatch.setattr("src.main.get_settings", broken_settings)
    app = create_app()

    with pytest.raises(ConfigurationError, match="DATABASE_URL: is required"):
        with TestClient(app):
            pass
