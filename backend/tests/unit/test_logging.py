"""JSON log formatting and secret redaction (D-40)."""

import json
import logging
import uuid
from decimal import Decimal

import pytest

from src.core.logging import REDACTED, JsonFormatter, configure_logging, redact

SECRET = "s3cret-Pa55"


def render(msg: str, *args, exc: BaseException | None = None, **extra) -> dict:
    record = logging.LogRecord("src.test", logging.INFO, __file__, 1, msg, args, (type(exc), exc, None) if exc else None)
    for key, value in extra.items():
        setattr(record, key, value)
    line = JsonFormatter().format(record)
    assert "\n" not in line  # one JSON object per line
    return json.loads(line)


def test_record_has_standard_and_extra_fields():
    run_id = uuid.uuid4()
    entry = render("Run finished", event="run_finished", run_id=run_id, records_loaded=600, duration_s=Decimal("1.25"), ok=True)

    assert entry["level"] == "INFO" and entry["logger"] == "src.test" and entry["message"] == "Run finished"
    assert entry["ts"].endswith("+00:00")
    assert entry["event"] == "run_finished" and entry["run_id"] == str(run_id)
    assert (entry["records_loaded"], entry["duration_s"], entry["ok"]) == (600, "1.25", True)


@pytest.mark.parametrize(
    "text",
    [
        f"postgresql+psycopg://gedp_app:{SECRET}@localhost:5432/gedp_dev",
        f"connect failed: password={SECRET} host=localhost",
        f"pwd: {SECRET}",
        f"https://user:{SECRET}@example.invalid/path",
    ],
)
def test_credentials_in_free_text_are_redacted(text):
    entry = render("detail %s", text, note=text)

    assert SECRET not in json.dumps(entry)
    assert REDACTED in entry["message"] and REDACTED in entry["note"]


def test_secret_named_fields_are_replaced_whatever_their_value():
    entry = render("config", database_url="anything", password="x", api_key="y", settings={"TEST_DATABASE_URL": "z", "start_year": 2005})

    assert entry["database_url"] == entry["password"] == entry["api_key"] == REDACTED
    assert entry["settings"] == {"TEST_DATABASE_URL": REDACTED, "start_year": 2005}


def test_urls_without_credentials_are_kept():
    entry = render("fetch", endpoint="https://api.worldbank.org/v2/country/IND;USA/indicator/SP.POP.TOTL")

    assert entry["endpoint"] == "https://api.worldbank.org/v2/country/IND;USA/indicator/SP.POP.TOTL"


def test_exceptions_are_reduced_to_type_and_redacted_message():
    try:
        raise RuntimeError(f"could not connect to postgresql+psycopg://gedp_app:{SECRET}@db/gedp_dev")
    except RuntimeError as exc:
        entry = render("failure", exc=exc)

    assert entry["error_type"] == "RuntimeError"
    assert SECRET not in entry["error"] and "Traceback" not in json.dumps(entry)


def test_configure_logging_installs_one_json_handler():
    # Isolate the root logger: earlier tests may already have started the app, which installs the handler.
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    for handler in saved_handlers:
        root.removeHandler(handler)
    try:
        configure_logging("INFO")
        configure_logging("DEBUG")
        assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.DEBUG
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_redact_is_a_no_op_for_plain_text():
    assert redact("Fetched indicator series") == "Fetched indicator series"
