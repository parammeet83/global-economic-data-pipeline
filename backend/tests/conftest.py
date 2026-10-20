"""Shared test fixtures."""

from collections.abc import Callable
from typing import Any

import pytest

from src.core.config import Settings, load_settings

# Placeholder URLs for unit tests. Nothing connects to them; unit tests never use backend/.env.
DEV_URL = "postgresql+psycopg://unit_user:unit-secret-pw@db.invalid:5432/gedp_dev"
TEST_URL = "postgresql+psycopg://unit_user:unit-secret-pw@db.invalid:5432/gedp_test"


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Settings]:
    """Build Settings from explicit values only, ignoring backend/.env and the environment.

    Setting variables (e.g. TEST_DATABASE_URL, which CI exports) are removed for the test so
    results never depend on the machine; a test may still set one explicitly afterwards.
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)

    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {"_env_file": None, "database_url": DEV_URL, **overrides}
        return load_settings(**values)

    return factory
