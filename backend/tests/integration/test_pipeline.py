"""End-to-end pipeline against the test database with a fake source (D-11, D-15, D-18, D-19, D-20)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from src.db.models import Country, DataQualityCheck, EconomicObservation, PipelineRun
from src.pipeline import orchestrator
from src.pipeline.orchestrator import execute_run, run_pipeline, start_run
from src.pipeline.runs import ABANDONED_SUMMARY, RunInProgressError
from src.pipeline.worldbank import ApiErrorPayload, HttpStatusError, PaginationError
from tests.fakes import TEST_SETTINGS, FakeSource, default_rows, obs
from tests.integration.helpers import insert_run

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(make_settings):
    return make_settings(**TEST_SETTINGS)


def get_run(session_factory, run_id) -> PipelineRun:
    with session_factory() as session:
        return session.get(PipelineRun, run_id)


def count(session_factory, model) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def check_statuses(session_factory, run_id) -> dict[str, str]:
    with session_factory() as session:
        rows = session.execute(select(DataQualityCheck.check_name, DataQualityCheck.status).where(DataQualityCheck.run_id == run_id))
        return dict(rows.all())


def test_successful_run_records_everything(session_factory, settings):
    outcome = run_pipeline(session_factory, settings, "cli", FakeSource())

    assert outcome.status == "success"
    run = get_run(session_factory, outcome.run_id)
    assert (run.status, run.triggered_by, run.error_summary) == ("success", "cli", None)
    assert run.finished_at is not None and run.duration_seconds >= 0
    assert (run.records_extracted, run.records_transformed, run.records_loaded, run.records_inserted, run.records_value_changed) == (8, 8, 8, 8, 0)
    assert (run.countries_requested, run.indicators_requested) == (2, 2)
    assert "database_url" not in str(run.config_snapshot)
    assert count(session_factory, EconomicObservation) == 8
    statuses = check_statuses(session_factory, outcome.run_id)
    assert len(statuses) == 9 and set(statuses.values()) == {"passed"}
    with session_factory() as session:
        assert {o.last_run_id for o in session.scalars(select(EconomicObservation))} == {outcome.run_id}
        assert session.get(Country, "IND").name == "India"


def test_rerun_with_unchanged_data_is_idempotent(session_factory, settings):
    first = run_pipeline(session_factory, settings, "cli", FakeSource())
    second = run_pipeline(session_factory, settings, "scheduler", FakeSource())

    assert second.status == "success"
    c = second.counts
    assert (c["records_loaded"], c["records_inserted"], c["records_value_changed"]) == (8, 0, 0)
    assert count(session_factory, EconomicObservation) == 8  # no duplicates
    assert first.run_id != second.run_id


def test_rerun_with_changed_values_counts_value_changes(session_factory, settings):
    run_pipeline(session_factory, settings, "cli", FakeSource())
    changed = {code: default_rows(code) for code in ("SP.POP.TOTL", "NY.GDP.MKTP.CD")}
    changed["SP.POP.TOTL"][0] = obs("IND", 2019, 999999.5)

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource(changed))

    assert (outcome.counts["records_inserted"], outcome.counts["records_value_changed"]) == (0, 1)
    with session_factory() as session:
        stored = session.get(EconomicObservation, ("IND", "SP.POP.TOTL", 2019))
        assert stored.value == Decimal("999999.500000")


def test_null_values_are_skipped_not_stored_as_zero(session_factory, settings):
    rows = {code: default_rows(code) for code in ("SP.POP.TOTL", "NY.GDP.MKTP.CD")}
    rows["SP.POP.TOTL"][0] = obs("IND", 2019, None)

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource(rows))

    assert outcome.status == "success"  # nulls are source gaps, not defects
    assert (outcome.counts["records_null_skipped"], outcome.counts["records_loaded"]) == (1, 7)
    with session_factory() as session:
        assert session.get(EconomicObservation, ("IND", "SP.POP.TOTL", 2019)) is None
    assert check_statuses(session_factory, outcome.run_id)["null_value_rate"] == "warning"


def test_one_failed_series_gives_partial_success(session_factory, settings):
    source = FakeSource(series_errors={"NY.GDP.MKTP.CD": HttpStatusError("HTTP 503 after 4 attempt(s)", endpoint="x", status_code=503)})

    outcome = run_pipeline(session_factory, settings, "cli", source)

    run = get_run(session_factory, outcome.run_id)
    assert run.status == "partial_success"
    assert (run.records_loaded, run.error_count) == (4, 1)
    assert "1 of 2 series failed: NY.GDP.MKTP.CD: http_error" in run.error_summary
    assert check_statuses(session_factory, outcome.run_id)["extraction_requests_succeeded"] == "warning"


def test_rejected_rows_give_partial_success(session_factory, settings):
    rows = {code: default_rows(code) for code in ("SP.POP.TOTL", "NY.GDP.MKTP.CD")}
    rows["SP.POP.TOTL"].append(obs("FRA", 2019, 1))

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource(rows))

    assert outcome.status == "partial_success"
    assert (outcome.counts["records_rejected"], outcome.counts["records_loaded"]) == (1, 8)
    assert check_statuses(session_factory, outcome.run_id)["valid_country_code"] == "failed"


def test_pagination_error_is_a_failed_series_and_failed_check(session_factory, settings):
    source = FakeSource(series_errors={"SP.POP.TOTL": PaginationError("received 1 rows but metadata reports 2", endpoint="x")})

    outcome = run_pipeline(session_factory, settings, "cli", source)

    assert outcome.status == "partial_success"
    assert check_statuses(session_factory, outcome.run_id)["api_page_count_consistent"] == "failed"


def test_all_series_failing_is_a_failed_run_with_nothing_loaded(session_factory, settings):
    error = HttpStatusError("HTTP 500 after 4 attempt(s)", endpoint="x", status_code=500)
    source = FakeSource(series_errors={"SP.POP.TOTL": error, "NY.GDP.MKTP.CD": error})

    outcome = run_pipeline(session_factory, settings, "cli", source)

    run = get_run(session_factory, outcome.run_id)
    assert (run.status, run.records_loaded) == ("failed", 0)
    assert count(session_factory, EconomicObservation) == 0
    assert check_statuses(session_factory, outcome.run_id)["extraction_requests_succeeded"] == "failed"


def test_country_metadata_error_payload_fails_the_run(session_factory, settings):
    source = FakeSource(country_error=ApiErrorPayload("World Bank API error payload (id 120: Invalid value)", endpoint="country/IND;USA"))

    outcome = run_pipeline(session_factory, settings, "cli", source)

    run = get_run(session_factory, outcome.run_id)
    assert run.status == "failed"
    assert "Country metadata request failed (api_error_payload)" in run.error_summary
    assert source.series_calls == []  # no observations requested after a structural failure


def test_aggregate_country_code_is_a_configuration_error(session_factory, make_settings):
    settings = make_settings(**{**TEST_SETTINGS, "country_codes": "IND,WLD", "default_country_codes": "IND"})

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource(aggregates={"WLD"}))

    assert outcome.status == "failed"
    assert "aggregate codes are not allowed" in get_run(session_factory, outcome.run_id).error_summary


def test_load_failure_rolls_back_everything_but_keeps_the_run_record(session_factory, settings, monkeypatch):
    def broken_upsert(*args, **kwargs):
        raise RuntimeError("simulated database failure mid-load")

    monkeypatch.setattr(orchestrator, "upsert_observations", broken_upsert)

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource())

    run = get_run(session_factory, outcome.run_id)
    assert run.status == "failed"
    assert "Load failed and was rolled back (RuntimeError)" in run.error_summary
    assert "simulated" not in run.error_summary  # only the error type, never raw messages
    assert (run.records_extracted, run.records_transformed, run.records_loaded) == (8, 8, 0)
    assert count(session_factory, EconomicObservation) == 0
    assert count(session_factory, Country) == 0  # dimension upserts were in the same rolled-back transaction
    assert len(check_statuses(session_factory, outcome.run_id)) == 9  # checks recorded by the failure transaction


def test_second_claim_is_refused_while_a_run_is_in_progress(session_factory, settings):
    first = start_run(session_factory, settings, "cli")

    with pytest.raises(RunInProgressError) as excinfo:
        start_run(session_factory, settings, "api")

    assert excinfo.value.running_run_id == first
    assert count(session_factory, PipelineRun) == 1  # the refused attempt is not stored


def test_stale_running_run_is_recovered_on_next_claim(session_factory, settings, db_connection):
    stale = insert_run(db_connection, status="running", age_minutes=settings.stale_run_minutes + 5)

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource())

    recovered = get_run(session_factory, stale)
    assert (recovered.status, recovered.error_summary) == ("failed", ABANDONED_SUMMARY)
    assert recovered.finished_at is not None and recovered.duration_seconds > 0
    assert outcome.status == "success"


def test_recent_running_run_is_not_treated_as_stale(session_factory, settings, db_connection):
    insert_run(db_connection, status="running", age_minutes=1)

    with pytest.raises(RunInProgressError):
        start_run(session_factory, settings, "cli")


def test_run_recovered_as_stale_cannot_commit_data_later(session_factory, settings, db_connection):
    run_id = start_run(session_factory, settings, "api")

    def recover_during_extraction(_code: str) -> None:
        with session_factory() as session, session.begin():
            run = session.get(PipelineRun, run_id)
            run.status, run.finished_at, run.error_summary = "failed", func.clock_timestamp(), ABANDONED_SUMMARY

    outcome = execute_run(run_id, session_factory, settings, FakeSource(on_series=recover_during_extraction))

    assert outcome.status == "failed"
    assert count(session_factory, EconomicObservation) == 0
    assert get_run(session_factory, run_id).error_summary == ABANDONED_SUMMARY


def test_json_report_written_when_enabled(session_factory, make_settings, tmp_path):
    settings = make_settings(**TEST_SETTINGS, write_json_report=True, reports_dir=str(tmp_path))

    outcome = run_pipeline(session_factory, settings, "cli", FakeSource())

    assert (tmp_path / f"run_{outcome.run_id}.json").exists()
