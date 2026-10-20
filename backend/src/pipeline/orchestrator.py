"""End-to-end pipeline: extract -> transform/validate -> load -> record quality -> finalize.

The CLI, the API (background task) and the scheduler (through the CLI) all use
this module, so the business logic exists once (TRD §2):

* ``start_run``  claims a run (T1) and returns its id, or raises ``RunInProgressError``;
* ``execute_run`` does the work for a claimed run and always ends in one terminal status;
* ``run_pipeline`` does both.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from src.core.config import Settings
from src.db.repositories import fetch_existing_values, upsert_countries, upsert_indicators, upsert_observations
from src.db.session import SessionFactory
from src.pipeline.quality import (
    CheckResult,
    checks_as_dicts,
    determine_status,
    extraction_check,
    page_count_check,
    write_json_report,
)
from src.pipeline.runs import RunNoLongerRunningError, claim_run, finalize_failure, finalize_run
from src.pipeline.transform import TransformResult, transform
from src.pipeline.worldbank import (
    CountryMeta,
    IndicatorMeta,
    PaginationError,
    SeriesResult,
    WorldBankClient,
    WorldBankError,
)

logger = logging.getLogger(__name__)


class SourceClient(Protocol):
    def fetch_countries(self, country_codes: list[str]) -> list[CountryMeta]: ...
    def fetch_indicator(self, indicator_code: str) -> IndicatorMeta: ...
    def fetch_series(self, indicator_code: str, country_codes: list[str], start_year: int, end_year: int) -> SeriesResult: ...


class PipelineFailure(Exception):
    """A structural problem that makes the run's result untrustworthy (run ends ``failed``)."""


@dataclass
class RunOutcome:
    run_id: uuid.UUID
    status: str
    counts: dict[str, int] = field(default_factory=dict)
    error_summary: str | None = None


def build_client(settings: Settings) -> WorldBankClient:
    return WorldBankClient(
        settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        backoff_seconds=settings.retry_backoff_seconds,
        per_page=settings.per_page,
    )


def config_snapshot(settings: Settings) -> dict[str, Any]:
    """Non-secret settings that explain a run (no database URLs)."""
    return {
        "api_base_url": settings.api_base_url,
        "country_codes": settings.country_codes,
        "indicator_codes": settings.indicator_codes,
        "start_year": settings.start_year,
        "end_year": settings.end_year,
        "per_page": settings.per_page,
        "max_retries": settings.max_retries,
        "request_timeout_seconds": settings.request_timeout_seconds,
    }


def start_run(session_factory: SessionFactory, settings: Settings, triggered_by: str) -> uuid.UUID:
    return claim_run(
        session_factory,
        triggered_by=triggered_by,
        stale_minutes=settings.stale_run_minutes,
        countries_requested=len(settings.country_codes),
        indicators_requested=len(settings.indicator_codes),
        config_snapshot=config_snapshot(settings),
    )


def _fetch_metadata(client: SourceClient, settings: Settings) -> tuple[list[CountryMeta], list[IndicatorMeta]]:
    try:
        countries = client.fetch_countries(list(settings.country_codes))
    except WorldBankError as exc:
        raise PipelineFailure(f"Country metadata request failed ({exc.kind}); check COUNTRY_CODES: {exc}") from None
    by_code = {c.country_code: c for c in countries}
    unknown = sorted(set(settings.country_codes) - set(by_code))
    if unknown:
        raise PipelineFailure(f"Configuration error: unknown country codes {', '.join(unknown)}")
    aggregates = sorted(code for code in settings.country_codes if by_code[code].is_aggregate)
    if aggregates:
        raise PipelineFailure(f"Configuration error: aggregate codes are not allowed (D-08): {', '.join(aggregates)}")

    indicators = []
    for code in settings.indicator_codes:
        try:
            indicators.append(client.fetch_indicator(code))
        except WorldBankError as exc:
            raise PipelineFailure(f"Indicator metadata request failed for {code} ({exc.kind}): {exc}") from None
    return [by_code[code] for code in settings.country_codes], indicators


def _summary(counts: dict[str, int], failures: list[str], extra: str | None = None) -> str | None:
    parts = []
    if failures:
        parts.append(f"{len(failures)} of {counts['indicators_requested']} series failed: " + "; ".join(failures))
    if counts.get("records_rejected"):
        parts.append(f"{counts['records_rejected']} rows rejected by validation")
    if extra:
        parts.append(extra)
    return " | ".join(parts) or None


def execute_run(
    run_id: uuid.UUID,
    session_factory: SessionFactory,
    settings: Settings,
    client: SourceClient | None = None,
) -> RunOutcome:
    """Run every stage for a claimed run. Never raises; always returns the terminal outcome."""
    started = time.perf_counter()
    source = client or build_client(settings)
    counts: dict[str, int] = {
        "countries_requested": len(settings.country_codes),
        "indicators_requested": len(settings.indicator_codes),
    }
    checks: list[CheckResult] = []
    failures: list[str] = []

    def fail(summary: str) -> RunOutcome:
        counts["error_count"] = len(failures) + 1
        recorded = finalize_failure(session_factory, run_id, counts=counts, checks=checks, error_summary=summary)
        logger.error(
            "Run failed",
            extra={"event": "run_finished", "stage": "finalize", "run_id": run_id, "status": "failed", "recorded": recorded,
                   "summary": summary, "duration_s": round(time.perf_counter() - started, 3), **counts},
        )
        outcome = RunOutcome(run_id, "failed", {**counts, "records_loaded": 0, "records_inserted": 0, "records_value_changed": 0}, summary)
        _maybe_report(settings, outcome, checks)
        return outcome

    try:
        countries, indicators = _fetch_metadata(source, settings)

        series_ok: list[SeriesResult] = []
        mismatches: list[str] = []
        for code in settings.indicator_codes:
            try:
                series_ok.append(source.fetch_series(code, list(settings.country_codes), settings.start_year, settings.end_year))
            except WorldBankError as exc:
                failures.append(f"{code}: {exc.kind} ({exc})")
                if isinstance(exc, PaginationError):
                    mismatches.append(code)
        logger.info(
            "Extraction finished",
            extra={"event": "stage_finished", "stage": "extract", "run_id": run_id, "series_ok": len(series_ok), "series_failed": len(failures)},
        )
        checks.append(extraction_check(len(settings.indicator_codes), len(failures), failures))
        checks.append(page_count_check(len(settings.indicator_codes), mismatches))
        if not series_ok:
            return fail(_summary(counts, failures) or "All series failed")

        result: TransformResult = transform(
            series_ok,
            country_codes=settings.country_codes,
            indicator_codes=settings.indicator_codes,
            start_year=settings.start_year,
            end_year=settings.end_year,
        )
        checks.extend(result.checks)
        counts.update(
            records_extracted=result.extracted,
            records_rejected=result.rejected,
            records_null_skipped=result.null_skipped,
            records_duplicates_dropped=result.duplicates_dropped,
            records_transformed=result.transformed,
        )
        logger.info(
            "Transformation finished",
            extra={"event": "stage_finished", "stage": "transform", "run_id": run_id, "rejection_reasons": result.rejection_reasons,
                   **{k: v for k, v in counts.items() if k.startswith("records_")}},
        )
        if result.transformed == 0:
            return fail(_summary(counts, failures, "No load-ready rows") or "No load-ready rows")
    except PipelineFailure as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - any unexpected error ends the run as failed
        logger.error("Unexpected error during extract/transform", exc_info=exc, extra={"event": "unexpected_error", "stage": "extract_transform", "run_id": run_id})
        return fail(f"Unexpected error during extract/transform ({type(exc).__name__})")

    status = determine_status(
        load_committed=True,
        series_requested=len(settings.indicator_codes),
        series_failed=len(failures),
        transformed=result.transformed,
        rejected=result.rejected,
        conflicting_duplicates=result.conflicting_duplicates,
    )
    summary = _summary(counts, failures, "conflicting duplicate values were found" if result.conflicting_duplicates else None)
    counts["error_count"] = len(failures)

    try:
        with session_factory() as session, session.begin():  # T2: data, checks and status together
            upsert_countries(
                session,
                [
                    {"country_code": c.country_code, "name": c.name, "region": c.region, "income_level": c.income_level, "is_aggregate": c.is_aggregate}
                    for c in countries
                ],
            )
            upsert_indicators(
                session,
                [
                    {"indicator_code": i.indicator_code, "name": i.name, "description": i.description, "unit": settings.indicator_units[i.indicator_code]}
                    for i in indicators
                ],
            )
            keys = [(r["country_code"], r["indicator_code"], r["year"]) for r in result.rows]
            existing = fetch_existing_values(session, keys)
            inserted = sum(1 for key in keys if key not in existing)
            changed = sum(1 for key, row in zip(keys, result.rows) if key in existing and existing[key] != row["value"])
            loaded = upsert_observations(session, result.rows, run_id=run_id, ingested_at=datetime.now(UTC))
            counts.update(records_loaded=loaded, records_inserted=inserted, records_value_changed=changed)
            finalize_run(session, run_id, status=status, counts=counts, checks=checks, error_summary=summary)
    except RunNoLongerRunningError:
        logger.error("Load rolled back: run was recovered as stale", extra={"event": "load_rolled_back", "stage": "load", "run_id": run_id, "reason": "recovered_as_stale"})
        counts.update(records_loaded=0, records_inserted=0, records_value_changed=0)
        return RunOutcome(run_id, "failed", counts, "Run was recovered as stale before it finished; nothing was loaded")
    except Exception as exc:  # noqa: BLE001 - load rolled back; record the failure separately (T3)
        logger.error("Load rolled back", extra={"event": "load_rolled_back", "stage": "load", "run_id": run_id, "error_type": type(exc).__name__})
        return fail(_summary(counts, failures, f"Load failed and was rolled back ({type(exc).__name__})") or "Load failed")

    outcome = RunOutcome(run_id, status, counts, summary)
    logger.info(
        "Run finished",
        extra={"event": "run_finished", "stage": "finalize", "run_id": run_id, "status": status,
               "duration_s": round(time.perf_counter() - started, 3), **counts},
    )
    _maybe_report(settings, outcome, checks)
    return outcome


def _maybe_report(settings: Settings, outcome: RunOutcome, checks: list[CheckResult]) -> None:
    if settings.write_json_report:
        write_json_report(
            settings.reports_dir,
            str(outcome.run_id),
            {"run_id": str(outcome.run_id), "status": outcome.status, "counts": outcome.counts, "error_summary": outcome.error_summary, "checks": checks_as_dicts(checks)},
        )


def run_pipeline(
    session_factory: SessionFactory,
    settings: Settings,
    triggered_by: str,
    client: SourceClient | None = None,
) -> RunOutcome:
    """Claim and execute a run (raises ``RunInProgressError`` if another run is active)."""
    run_id = start_run(session_factory, settings, triggered_by)
    return execute_run(run_id, session_factory, settings, client)
