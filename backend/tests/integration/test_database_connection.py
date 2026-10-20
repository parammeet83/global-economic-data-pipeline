"""Connectivity against the real PostgreSQL test database (read-only: SELECT 1)."""

import pytest
from fastapi.testclient import TestClient

from src.core.config import load_settings
from src.db.session import check_database_connection, create_db_engine
from src.main import create_app

pytestmark = pytest.mark.integration


def test_select_1_on_test_database(test_database_url):
    engine = create_db_engine(test_database_url)
    try:
        assert check_database_connection(engine) is True
    finally:
        engine.dispose()


def test_health_endpoint_against_test_database(test_database_url):
    settings = load_settings(database_url=test_database_url.get_secret_value(), test_database_url="")
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
