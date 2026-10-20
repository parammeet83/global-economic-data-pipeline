"""Fixtures for tests that use the real PostgreSQL test database (never the development database)."""

import pytest
from pydantic import SecretStr

from src.core.config import ConfigurationError, load_settings


@pytest.fixture(scope="session")
def test_database_url() -> SecretStr:
    """TEST_DATABASE_URL from backend/.env or the environment; skips the test when it is not configured.

    Settings validation already guarantees the name ends in ``_test`` and differs
    from DATABASE_URL (D-06).
    """
    try:
        settings = load_settings()
    except ConfigurationError:
        pytest.skip("backend/.env or environment variables are not configured")
    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return settings.test_database_url
