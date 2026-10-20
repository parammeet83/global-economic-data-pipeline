"""Shared test fixtures."""

from collections.abc import Callable
from typing import Any

import pytest

from src.core.config import Settings, load_settings

# Placeholder URLs for unit tests. Nothing connects to them; unit tests never use backend/.env.
DEV_URL = "postgresql+psycopg://unit_user:unit-secret-pw@db.invalid:5432/gedp_dev"
TEST_URL = "postgresql+psycopg://unit_user:unit-secret-pw@db.invalid:5432/gedp_test"


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Build Settings from explicit values only, ignoring backend/.env."""

    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {"_env_file": None, "database_url": DEV_URL, **overrides}
        return load_settings(**values)

    return factory
