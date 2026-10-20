"""Quality-check results, run-status rules and the optional JSON report.

Check names and status rules: Backend_DB_Schema.md §3.5 (D-17).
Run status rules: TRD §6 (D-15).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PASSED, WARNING, FAILED = "passed", "warning", "failed"
MAX_EXAMPLES = 5


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    status: str
    records_checked: int
    records_failed: int
    details: dict[str, Any] = field(default_factory=dict)


def failed_if_any(check_name: str, checked: int, failed: int, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(check_name, FAILED if failed else PASSED, checked, failed, details or {})


def extraction_check(series_requested: int, series_failed: int, failures: list[str]) -> CheckResult:
    if series_failed == 0:
        status = PASSED
    elif series_failed < series_requested:
        status = WARNING
    else:
        status = FAILED
    return CheckResult(
        "extraction_requests_succeeded",
        status,
        series_requested,
        series_failed,
        {"failures": failures[:MAX_EXAMPLES]} if failures else {},
    )


def page_count_check(series_checked: int, mismatches: list[str]) -> CheckResult:
    return failed_if_any(
        "api_page_count_consistent",
        series_checked,
        len(mismatches),
        {"series": mismatches[:MAX_EXAMPLES]} if mismatches else None,
    )


def null_value_check(rows_checked: int, null_values: int) -> CheckResult:
    """Null source values are gaps, reported as a warning and never as a failure (D-12)."""
    details = {"null_rate": round(null_values / rows_checked, 4) if rows_checked else 0.0}
    return CheckResult("null_value_rate", WARNING if null_values else PASSED, rows_checked, null_values, details)


def duplicate_check(rows_checked: int, dropped: int, conflicting_keys: int, examples: list[dict[str, Any]]) -> CheckResult:
    if dropped == 0:
        status = PASSED
    elif conflicting_keys:
        status = FAILED
    else:
        status = WARNING
    details: dict[str, Any] = {"conflicting_keys": conflicting_keys}
    if examples:
        details["examples"] = examples[:MAX_EXAMPLES]
    return CheckResult("unique_business_key", status, rows_checked, dropped, details)


def determine_status(
    *,
    load_committed: bool,
    series_requested: int,
    series_failed: int,
    transformed: int,
    rejected: int,
    conflicting_duplicates: int,
) -> str:
    """Terminal run status (TRD §6, D-15). Null values and identical duplicates never downgrade."""
    if not load_committed or transformed == 0 or (series_requested and series_failed >= series_requested):
        return "failed"
    if series_failed or rejected or conflicting_duplicates:
        return "partial_success"
    return "success"


def write_json_report(reports_dir: str | Path, run_id: str, report: dict[str, Any]) -> Path | None:
    """Optional export (D-16). A failure is logged and never affects the run status."""
    try:
        directory = Path(reports_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"run_{run_id}.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return path
    except OSError as exc:
        logger.warning("Could not write JSON report (%s)", type(exc).__name__)
        return None


def checks_as_dicts(checks: list[CheckResult]) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]
