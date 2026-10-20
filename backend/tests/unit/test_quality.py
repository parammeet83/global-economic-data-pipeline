"""Run-status rules (TRD §6, D-15), check builders and the optional JSON report."""

import json

import pytest

from src.pipeline.quality import (
    determine_status,
    duplicate_check,
    extraction_check,
    null_value_check,
    page_count_check,
    write_json_report,
)

CLEAN = {"load_committed": True, "series_requested": 3, "series_failed": 0, "transformed": 10, "rejected": 0, "conflicting_duplicates": 0}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, "success"),
        ({"series_failed": 1}, "partial_success"),
        ({"rejected": 2}, "partial_success"),
        ({"conflicting_duplicates": 1}, "partial_success"),
        ({"series_failed": 3}, "failed"),  # every series failed
        ({"transformed": 0}, "failed"),  # nothing load-ready
        ({"load_committed": False}, "failed"),  # rolled back
        ({"load_committed": False, "rejected": 0}, "failed"),
    ],
)
def test_run_status_rules(changes, expected):
    assert determine_status(**{**CLEAN, **changes}) == expected


def test_extraction_check_levels():
    assert extraction_check(3, 0, []).status == "passed"
    partial = extraction_check(3, 1, ["SP.POP.TOTL: transport_error"])
    assert (partial.status, partial.records_failed, partial.details["failures"]) == ("warning", 1, ["SP.POP.TOTL: transport_error"])
    assert extraction_check(3, 3, ["a", "b", "c"]).status == "failed"


def test_page_null_and_duplicate_checks():
    assert page_count_check(3, []).status == "passed"
    assert page_count_check(3, ["NY.GDP.MKTP.CD"]).status == "failed"
    assert null_value_check(0, 0).details == {"null_rate": 0.0}
    assert duplicate_check(5, 0, 0, []).status == "passed"
    assert duplicate_check(5, 1, 0, []).status == "warning"
    assert duplicate_check(5, 1, 1, []).status == "failed"


def test_json_report_is_written(tmp_path):
    path = write_json_report(tmp_path / "reports", "abc", {"status": "success", "counts": {"records_loaded": 2}})

    assert path is not None and path.name == "run_abc.json"
    assert json.loads(path.read_text(encoding="utf-8"))["counts"]["records_loaded"] == 2


def test_json_report_failure_is_not_raised(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")

    assert write_json_report(blocker / "nested", "abc", {}) is None
