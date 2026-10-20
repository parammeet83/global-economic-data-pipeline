"""CLI exit codes (TRD §13, D-31)."""

import pytest

from src.core.config import ConfigurationError
from src.pipeline import cli
from src.pipeline.worldbank import HttpStatusError
from tests.fakes import TEST_SETTINGS, FakeSource, default_rows, obs
from tests.integration.helpers import insert_run

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def test_settings(monkeypatch, make_settings):
    settings = make_settings(**TEST_SETTINGS)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    return settings


def test_success_exits_0_and_prints_counts(session_factory, capsys):
    code = cli.main(["run"], session_factory=session_factory, client=FakeSource())

    out = capsys.readouterr().out
    assert code == 0
    assert "status=success" in out and "loaded=8 inserted=8 value_changed=0" in out


def test_partial_success_exits_2(session_factory):
    rows = {code: default_rows(code) for code in ("SP.POP.TOTL", "NY.GDP.MKTP.CD")}
    rows["SP.POP.TOTL"].append(obs("FRA", 2019, 1))

    assert cli.main(["run", "--triggered-by", "scheduler"], session_factory=session_factory, client=FakeSource(rows)) == 2


def test_failed_run_exits_1(session_factory):
    error = HttpStatusError("HTTP 500", endpoint="x", status_code=500)
    source = FakeSource(series_errors={"SP.POP.TOTL": error, "NY.GDP.MKTP.CD": error})

    assert cli.main(["run"], session_factory=session_factory, client=source) == 1


def test_run_in_progress_exits_3(session_factory, db_connection, capsys):
    insert_run(db_connection, status="running", age_minutes=1)

    code = cli.main(["run"], session_factory=session_factory, client=FakeSource())

    assert code == 3
    assert "already in progress" in capsys.readouterr().err


def test_configuration_error_exits_4(monkeypatch, capsys):
    def broken():
        raise ConfigurationError("Configuration error.\n  - DATABASE_URL: is required but was not set")

    monkeypatch.setattr(cli, "load_settings", broken)

    assert cli.main(["run"]) == 4
    assert "DATABASE_URL: is required" in capsys.readouterr().err


def test_unreachable_database_exits_4(monkeypatch, make_settings, capsys):
    unreachable = make_settings(**TEST_SETTINGS, database_url="postgresql+psycopg://nobody:pw@127.0.0.1:1/gedp_dev")
    monkeypatch.setattr(cli, "load_settings", lambda: unreachable)

    assert cli.main(["run"], client=FakeSource()) == 4
    err = capsys.readouterr().err
    assert "database is unavailable" in err and "pw" not in err
