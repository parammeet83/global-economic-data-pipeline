"""Pipeline logs are machine-readable JSON with run context and no connection secrets (D-40)."""

import json
import logging

import pytest

from src.core.logging import JsonFormatter
from src.pipeline.orchestrator import run_pipeline
from tests.fakes import TEST_SETTINGS, FakeSource

pytestmark = pytest.mark.integration


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


def test_run_emits_json_events_with_run_context(session_factory, make_settings, test_database_url):
    collector = Collector()
    logger = logging.getLogger("src")
    previous = logger.level
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    try:
        outcome = run_pipeline(session_factory, make_settings(**TEST_SETTINGS), "cli", FakeSource())
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous)

    entries = [json.loads(line) for line in collector.lines]
    events = [(e.get("event"), e.get("stage")) for e in entries]
    assert ("run_claimed", "claim") in events
    assert ("stage_finished", "extract") in events and ("stage_finished", "transform") in events
    finished = next(e for e in entries if e.get("event") == "run_finished")
    assert finished["run_id"] == str(outcome.run_id) and finished["status"] == "success"
    assert (finished["records_loaded"], finished["records_inserted"]) == (8, 8)
    assert isinstance(finished["duration_s"], float)
    raw = "\n".join(collector.lines)
    assert test_database_url.get_secret_value() not in raw and "postgresql" not in raw
