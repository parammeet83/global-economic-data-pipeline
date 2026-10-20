"""Application settings loaded from environment variables and ``backend/.env``.

Environment variables take precedence over values in ``backend/.env``. Database
URLs are stored as ``SecretStr`` so they are masked in ``repr()`` and logs, and
validation errors are reported without echoing any submitted value, because a
URL can contain a password.

Run ``python -m src.core.config`` from ``backend/`` to check the configuration.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"

REQUIRED_DRIVER = "postgresql+psycopg"
ISO3_PATTERN = re.compile(r"^[A-Z]{3}$")

# A list of codes written as a comma-separated string in .env, e.g. "IND,USA".
CodeList = Annotated[list[str], NoDecode]


class ConfigurationError(Exception):
    """Raised when settings are missing or invalid. The message never contains secret values."""


def _split_codes(value: Any) -> Any:
    if isinstance(value, str):
        return [part.strip().upper() for part in value.split(",") if part.strip()]
    return value


def _parse_database_url(name: str, secret: SecretStr) -> URL:
    try:
        url = make_url(secret.get_secret_value())
    except ArgumentError:
        raise ValueError(
            f"{name} is not a valid database URL. Expected the form "
            f"{REQUIRED_DRIVER}://USER:PASSWORD@HOST:PORT/DATABASE"
        ) from None
    if url.drivername != REQUIRED_DRIVER:
        raise ValueError(
            f"{name} must start with '{REQUIRED_DRIVER}://' so SQLAlchemy uses the psycopg 3 driver"
        )
    if not url.host or not url.database:
        raise ValueError(f"{name} must include a host and a database name")
    return url


def _check_unique(name: str, codes: list[str]) -> None:
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise ValueError(f"{name} contains duplicate codes: {', '.join(duplicates)}")


class Settings(BaseSettings):
    """Typed application settings. Variable names are case-insensitive (DATABASE_URL = database_url)."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: SecretStr
    test_database_url: SecretStr | None = None

    # World Bank source and scope (D-07, D-08, D-09)
    api_base_url: str = "https://api.worldbank.org/v2"
    country_codes: CodeList = Field(
        default_factory=lambda: ["IND", "USA", "GBR", "DEU", "JPN", "CHN", "BRA", "ZAF", "CAN", "AUS"]
    )
    indicator_codes: CodeList = Field(
        default_factory=lambda: ["NY.GDP.MKTP.CD", "SP.POP.TOTL", "SL.UEM.TOTL.ZS"]
    )
    indicator_units: dict[str, str] = Field(
        default_factory=lambda: {
            "NY.GDP.MKTP.CD": "current US$",
            "SP.POP.TOTL": "people",
            "SL.UEM.TOTL.ZS": "% of total labor force",
        }
    )
    start_year: int = Field(default=2005, ge=1900, le=2200)
    end_year: int = Field(default=2024, ge=1900, le=2200)

    # HTTP client
    per_page: int = Field(default=1000, ge=1, le=20000)
    request_timeout_seconds: float = Field(default=30, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=1, ge=0)

    # Run control (D-20, D-23)
    stale_run_minutes: int = Field(default=60, ge=1)
    enable_manual_trigger: bool = True

    # Dashboard defaults (D-26)
    default_indicator_code: str = "NY.GDP.MKTP.CD"
    default_country_codes: CodeList = Field(default_factory=lambda: ["IND", "USA", "CHN", "DEU", "BRA"])

    # Reports, logging, CORS
    write_json_report: bool = False
    reports_dir: str = "reports"
    log_level: str = "INFO"
    cors_origins: CodeList = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("country_codes", "indicator_codes", "default_country_codes", mode="before")
    @classmethod
    def _parse_code_list(cls, value: Any) -> Any:
        return _split_codes(value)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return level

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr) -> SecretStr:
        _parse_database_url("DATABASE_URL", value)
        return value

    @field_validator("test_database_url")
    @classmethod
    def _check_test_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        url = _parse_database_url("TEST_DATABASE_URL", value)
        if not url.database.endswith("_test"):
            raise ValueError("TEST_DATABASE_URL must point to a database whose name ends in '_test' (D-06)")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        bad_codes = [code for code in self.country_codes if not ISO3_PATTERN.match(code)]
        if bad_codes:
            raise ValueError(f"COUNTRY_CODES must be 3-letter ISO-3 codes; invalid: {', '.join(bad_codes)}")
        if not self.country_codes:
            raise ValueError("COUNTRY_CODES must contain at least one code")
        if not self.indicator_codes:
            raise ValueError("INDICATOR_CODES must contain at least one code")
        _check_unique("COUNTRY_CODES", self.country_codes)
        _check_unique("INDICATOR_CODES", self.indicator_codes)

        missing_units = [code for code in self.indicator_codes if not self.indicator_units.get(code)]
        if missing_units:
            raise ValueError(f"INDICATOR_UNITS has no unit for: {', '.join(missing_units)}")

        if self.start_year > self.end_year:
            raise ValueError("START_YEAR must be less than or equal to END_YEAR")

        if self.default_indicator_code not in self.indicator_codes:
            raise ValueError("DEFAULT_INDICATOR_CODE must be one of INDICATOR_CODES")
        extra_defaults = [c for c in self.default_country_codes if c not in self.country_codes]
        if extra_defaults:
            raise ValueError(f"DEFAULT_COUNTRY_CODES must be in COUNTRY_CODES; not found: {', '.join(extra_defaults)}")

        if self.test_database_url is not None:
            dev = make_url(self.database_url.get_secret_value())
            test = make_url(self.test_database_url.get_secret_value())
            if (dev.host, dev.port, dev.database) == (test.host, test.port, test.database):
                raise ValueError("TEST_DATABASE_URL must not point to the same database as DATABASE_URL (D-06)")
        return self


def _format_errors(error: ValidationError) -> str:
    lines = [
        "Configuration error. Check backend/.env (copy it from backend/.env.example) "
        "or your environment variables:"
    ]
    for item in error.errors(include_input=False, include_url=False):
        field = ".".join(str(part) for part in item["loc"]).upper()
        message = item["msg"].removeprefix("Value error, ")
        if item["type"] == "missing":
            message = "is required but was not set"
        lines.append(f"  - {field}: {message}" if field else f"  - {message}")
    return "\n".join(lines)


def load_settings(**overrides: Any) -> Settings:
    """Build settings, converting validation errors into a secret-free ConfigurationError.

    Keyword overrides are passed to ``Settings`` (tests use ``_env_file=None`` to ignore backend/.env).
    """
    try:
        return Settings(**overrides)
    except ValidationError as error:
        raise ConfigurationError(_format_errors(error)) from None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once."""
    return load_settings()


def describe_database(secret: SecretStr) -> str:
    """Human-readable database location without the password, e.g. 'gedp_dev on localhost:5432 as gedp_app'."""
    url = make_url(secret.get_secret_value())
    return f"{url.database} on {url.host}:{url.port or 5432} as {url.username}"


if __name__ == "__main__":
    import sys

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print("Configuration OK.")
    print(f"  Development database: {describe_database(settings.database_url)}")
    if settings.test_database_url is not None:
        print(f"  Test database:        {describe_database(settings.test_database_url)}")
    else:
        print("  Test database:        not configured (TEST_DATABASE_URL is empty)")
