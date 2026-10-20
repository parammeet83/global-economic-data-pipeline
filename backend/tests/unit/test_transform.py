"""Transformation and validation with deterministic fixtures (D-11, D-12, D-13, D-17)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.pipeline.transform import transform
from src.pipeline.worldbank import SeriesResult

COUNTRIES = ["IND", "USA"]
INDICATORS = ["SP.POP.TOTL", "NY.GDP.MKTP.CD"]


def obs(country, year, value, indicator="SP.POP.TOTL") -> dict:
    return {"indicator": {"id": indicator}, "country": {"id": "XX"}, "countryiso3code": country, "date": year, "value": value}


def run(rows, indicator="SP.POP.TOTL", **kwargs):
    series = SeriesResult(indicator_code=indicator, rows=rows, total=len(rows), pages=1, last_updated=date(2026, 10, 8))
    params = {"country_codes": COUNTRIES, "indicator_codes": INDICATORS, "start_year": 2005, "end_year": 2024, **kwargs}
    return transform([series], **params)


def checks(result) -> dict:
    return {c.check_name: c for c in result.checks}


def test_clean_rows_are_normalized_and_load_ready():
    result = run([obs("IND", "2020", 1380004385), obs(" usa ", "2021", 331893745.5)])

    assert result.extracted == 2 and result.transformed == 2
    assert result.rows[0] == {
        "country_code": "IND",
        "indicator_code": "SP.POP.TOTL",
        "year": 2020,
        "value": Decimal("1380004385.000000"),
        "source_updated_at": datetime(2026, 10, 8, tzinfo=UTC),
    }
    assert result.rows[1]["country_code"] == "USA"  # trimmed and upper-cased
    assert {c.status for c in result.checks} == {"passed"}
    assert len(result.checks) == 7


def test_null_values_are_counted_never_zero():
    result = run([obs("IND", "2020", None), obs("USA", "2020", 0), obs("USA", "2021", 5)])

    assert result.null_skipped == 1
    assert result.transformed == 2
    assert [r["value"] for r in result.rows] == [Decimal("0.000000"), Decimal("5.000000")]  # a real 0 stays 0
    assert not any(r["country_code"] == "IND" for r in result.rows)  # the null was not loaded as 0
    null_check = checks(result)["null_value_rate"]
    assert (null_check.status, null_check.records_failed, null_check.details["null_rate"]) == ("warning", 1, 0.3333)


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (obs(None, "2020", 1), "required_fields_present"),
        (obs("", "2020", 1), "required_fields_present"),
        (obs("IND", None, 1), "required_fields_present"),
        ({"countryiso3code": "IND", "date": "2020", "value": 1}, "required_fields_present"),  # no indicator
        (obs("IN", "2020", 1), "valid_country_code"),  # ISO-2 is not accepted (D-08)
        (obs("FRA", "2020", 1), "valid_country_code"),  # not configured
        (obs("WLD", "2020", 1), "valid_country_code"),  # aggregate, not configured
        (obs("IND", "2020", 1, indicator="XX.UNKNOWN"), "valid_indicator_code"),
        (obs("IND", "1999", 1), "year_in_range"),
        (obs("IND", "2020Q1", 1), "year_in_range"),
        (obs("IND", "2020", "abc"), "numeric_value"),
        (obs("IND", "2020", float("inf")), "numeric_value"),
        (obs("IND", "2020", 1e19), "numeric_value"),
        (obs("IND", "2020", True), "numeric_value"),
    ],
)
def test_invalid_rows_are_rejected_with_a_reason(row, reason):
    result = run([row, obs("USA", "2020", 7)])

    assert result.rejected == 1
    assert result.rejection_reasons == {reason: 1}
    assert result.transformed == 1
    check = checks(result)[reason]
    assert check.status == "failed" and check.records_failed == 1
    assert check.details["examples"][0]["reason"] == reason


def test_row_failing_several_rules_is_rejected_once_under_its_first_rule():
    result = run([obs("FRA", "1990", "abc")])

    assert result.rejected == 1
    assert result.rejection_reasons == {"valid_country_code": 1}
    # each check still reports its own failures
    assert checks(result)["year_in_range"].records_failed == 1
    assert checks(result)["numeric_value"].records_failed == 1


def test_identical_duplicates_are_dropped_with_a_warning():
    result = run([obs("IND", "2020", 10), obs("IND", "2020", 10.0), obs("USA", "2020", 3)])

    assert (result.duplicates_dropped, result.conflicting_duplicates, result.transformed) == (1, 0, 2)
    check = checks(result)["unique_business_key"]
    assert (check.status, check.records_failed) == ("warning", 1)


def test_conflicting_duplicates_keep_first_and_fail_the_check():
    result = run([obs("IND", "2020", 10), obs("IND", "2020", 11)])

    assert (result.duplicates_dropped, result.conflicting_duplicates) == (1, 1)
    assert result.rows[0]["value"] == Decimal("10.000000")  # first occurrence kept
    check = checks(result)["unique_business_key"]
    assert check.status == "failed"
    assert check.details["examples"] == [{"country": "IND", "indicator": "SP.POP.TOTL", "year": 2020, "distinct_values": 2}]


def test_count_identity_holds_for_a_mixed_batch():
    rows = [
        obs("IND", "2020", 1),  # T
        obs("IND", "2020", 1),  # D
        obs("USA", "2020", None),  # N
        obs("FRA", "2020", 1),  # R
        obs("USA", "2050", 1),  # R (outside window, e.g. when the API ignores the date filter)
        obs("USA", "2021", 2),  # T
    ]
    result = run(rows)

    assert (result.extracted, result.rejected, result.null_skipped, result.duplicates_dropped, result.transformed) == (6, 2, 1, 1, 2)
    assert result.extracted == result.rejected + result.null_skipped + result.duplicates_dropped + result.transformed


def test_multiple_series_and_empty_input():
    gdp = SeriesResult("NY.GDP.MKTP.CD", [obs("IND", "2020", 2.6e12, indicator="NY.GDP.MKTP.CD")], 1, 1, None)
    pop = SeriesResult("SP.POP.TOTL", [obs("IND", "2020", 1.38e9)], 1, 1, None)

    result = transform([gdp, pop], country_codes=COUNTRIES, indicator_codes=INDICATORS, start_year=2005, end_year=2024)
    assert result.transformed == 2
    assert {r["indicator_code"] for r in result.rows} == set(INDICATORS)
    assert result.rows[0]["source_updated_at"] is None

    empty = transform([], country_codes=COUNTRIES, indicator_codes=INDICATORS, start_year=2005, end_year=2024)
    assert (empty.extracted, empty.transformed) == (0, 0)


def test_decimal_values_keep_six_places():
    result = run([obs("IND", "2020", 7.123456789)])

    assert result.rows[0]["value"] == Decimal("7.123457")
