"""Settings validation and secret handling."""

import pytest

from src.core.config import ConfigurationError, describe_database, load_settings
from tests.conftest import DEV_URL, TEST_URL

SECRET = "unit-secret-pw"


def test_defaults_load_with_only_database_url(make_settings):
    settings = make_settings()

    assert settings.country_codes[:2] == ["IND", "USA"]
    assert settings.indicator_units["SP.POP.TOTL"] == "people"
    assert (settings.start_year, settings.end_year) == (2005, 2024)
    assert settings.test_database_url is None


def test_database_url_is_masked_in_repr(make_settings):
    settings = make_settings(test_database_url=TEST_URL)

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert settings.database_url.get_secret_value() == DEV_URL


def test_describe_database_omits_password(make_settings):
    description = describe_database(make_settings().database_url)

    assert description == "gedp_dev on db.invalid:5432 as unit_user"
    assert SECRET not in description


def test_missing_database_url_gives_friendly_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(_env_file=None)

    message = str(excinfo.value)
    assert "DATABASE_URL: is required but was not set" in message
    assert "backend/.env.example" in message


def test_wrong_driver_is_rejected_without_echoing_the_url(make_settings):
    with pytest.raises(ConfigurationError) as excinfo:
        make_settings(database_url=f"postgresql://unit_user:{SECRET}@db.invalid:5432/gedp_dev")

    message = str(excinfo.value)
    assert "postgresql+psycopg://" in message
    assert SECRET not in message


def test_unparseable_url_is_rejected_without_echoing_it(make_settings):
    with pytest.raises(ConfigurationError) as excinfo:
        make_settings(database_url=f"not a url {SECRET}")

    assert "not a valid database URL" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)


def test_test_database_name_must_end_in_test(make_settings):
    with pytest.raises(ConfigurationError, match="must point to a database whose name ends in '_test'"):
        make_settings(test_database_url=DEV_URL)


def test_test_database_must_differ_from_dev_database(make_settings):
    with pytest.raises(ConfigurationError, match="must not point to the same database"):
        make_settings(database_url=TEST_URL, test_database_url=TEST_URL)


def test_empty_test_database_url_means_not_configured(make_settings):
    assert make_settings(test_database_url="").test_database_url is None


def test_comma_separated_codes_from_environment(monkeypatch, make_settings):
    monkeypatch.setenv("COUNTRY_CODES", " ind, usa ,GBR ")
    monkeypatch.setenv("DEFAULT_COUNTRY_CODES", "IND")

    settings = make_settings()

    assert settings.country_codes == ["IND", "USA", "GBR"]
    assert settings.default_country_codes == ["IND"]


def test_environment_variable_overrides_default(monkeypatch, make_settings):
    monkeypatch.setenv("START_YEAR", "2010")

    assert make_settings().start_year == 2010


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"country_codes": "IND,INDIA"}, "ISO-3 codes; invalid: INDIA"),
        ({"country_codes": "IND,IND,USA", "default_country_codes": "IND"}, "duplicate codes: IND"),
        ({"indicator_units": {"NY.GDP.MKTP.CD": "current US$"}}, "INDICATOR_UNITS has no unit for"),
        ({"start_year": 2020, "end_year": 2010}, "START_YEAR must be less than or equal to END_YEAR"),
        ({"default_country_codes": "FRA"}, "DEFAULT_COUNTRY_CODES must be in COUNTRY_CODES"),
        ({"default_indicator_code": "XX.UNKNOWN"}, "DEFAULT_INDICATOR_CODE must be one of"),
        ({"log_level": "loud"}, "LOG_LEVEL: must be one of"),
    ],
)
def test_inconsistent_settings_are_rejected(make_settings, overrides, expected):
    with pytest.raises(ConfigurationError) as excinfo:
        make_settings(**overrides)

    assert expected in str(excinfo.value)
