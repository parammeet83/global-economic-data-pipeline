"""Normalize and validate extracted observations (pandas + Pandera).

Every extracted row ends up in exactly one bucket, classified in the order
R -> N -> D (Backend_DB_Schema.md §3.3, D-11):

* R  rejected: fails a validation rule (reason recorded);
* N  null-skipped: valid identifiers but a null value (a source gap, never 0);
* D  duplicates dropped: a later copy of an already-seen business key;
* T  transformed: load-ready rows.

so that ``E = R + N + D + T`` always holds.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from src.pipeline.quality import (
    MAX_EXAMPLES,
    CheckResult,
    duplicate_check,
    failed_if_any,
    null_value_check,
)
from src.pipeline.worldbank import SeriesResult

KEY = ["country_code", "indicator_code", "year"]
SCALE = Decimal("0.000001")  # NUMERIC(24,6)
MAX_ABS_VALUE = 1e18  # NUMERIC(24,6) allows 18 integer digits

# Rejection rules in priority order: a row's reason is the first rule it fails.
RULES = ("required_fields_present", "valid_country_code", "valid_indicator_code", "year_in_range", "numeric_value")


@dataclass
class TransformResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    extracted: int = 0
    rejected: int = 0
    null_skipped: int = 0
    duplicates_dropped: int = 0
    conflicting_duplicates: int = 0
    checks: list[CheckResult] = field(default_factory=list)
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def transformed(self) -> int:
        return len(self.rows)


def _series_frame(series_list: Sequence[SeriesResult]) -> pd.DataFrame:
    """One row per extracted observation, with source fields kept as received."""
    records = []
    for series in series_list:
        updated = datetime.combine(series.last_updated, time.min, tzinfo=UTC) if series.last_updated else None
        for row in series.rows:
            indicator = row.get("indicator")
            records.append(
                {
                    "raw_country": row.get("countryiso3code"),  # ISO-3, never the ISO-2 country.id (D-08)
                    "raw_indicator": indicator.get("id") if isinstance(indicator, dict) else None,
                    "raw_year": row.get("date"),
                    "raw_value": row.get("value"),
                    "source_updated_at": updated,
                }
            )
    return pd.DataFrame.from_records(
        records, columns=["raw_country", "raw_indicator", "raw_year", "raw_value", "source_updated_at"]
    )


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["country_code"] = df["raw_country"].astype("string").str.strip().str.upper().replace("", pd.NA)
    df["indicator_code"] = df["raw_indicator"].astype("string").str.strip().replace("", pd.NA)

    year_text = df["raw_year"].astype("string").str.strip()
    df["year_present"] = year_text.notna() & (year_text != "")
    df["year"] = pd.to_numeric(year_text.where(year_text.str.fullmatch(r"\d{4}")), errors="coerce").astype("Int64")

    df["value_present"] = df["raw_value"].notna()
    is_bool = df["raw_value"].map(lambda v: isinstance(v, bool))
    numeric = pd.to_numeric(df["raw_value"].where(~is_bool), errors="coerce").astype("float64")
    df["value_numeric"] = numeric
    df["value_valid"] = np.isfinite(numeric) & (numeric.abs() < MAX_ABS_VALUE)
    return df


def _raw_schema(countries: set[str], indicators: set[str], start_year: int, end_year: int) -> pa.DataFrameSchema:
    """Lazy schema whose named checks are the row-level rejection rules (D-17)."""
    return pa.DataFrameSchema(
        checks=[
            pa.Check(
                lambda d: d["country_code"].notna() & d["indicator_code"].notna() & d["year_present"],
                name="required_fields_present",
            ),
            pa.Check(lambda d: d["country_code"].isna() | d["country_code"].isin(countries), name="valid_country_code"),
            pa.Check(lambda d: d["indicator_code"].isna() | d["indicator_code"].isin(indicators), name="valid_indicator_code"),
            pa.Check(
                lambda d: ~d["year_present"] | d["year"].between(start_year, end_year).fillna(False),
                name="year_in_range",
            ),
            pa.Check(lambda d: ~d["value_present"] | d["value_valid"], name="numeric_value"),
        ],
    )


def _load_ready_schema(countries: set[str], indicators: set[str], start_year: int, end_year: int) -> pa.DataFrameSchema:
    """Strict guard on the final frame; failing it is a pipeline bug, not a data problem."""
    return pa.DataFrameSchema(
        {
            "country_code": pa.Column(str, pa.Check.isin(sorted(countries)), coerce=True),
            "indicator_code": pa.Column(str, pa.Check.isin(sorted(indicators)), coerce=True),
            "year": pa.Column(int, pa.Check.in_range(start_year, end_year), coerce=True),
            "value_numeric": pa.Column(float, nullable=False, coerce=True),
        },
        unique=KEY,
    )


def _rule_failures(df: pd.DataFrame, schema: pa.DataFrameSchema) -> dict[str, set[Any]]:
    """Row indexes failing each named rule, collected lazily by Pandera."""
    failures: dict[str, set[Any]] = {rule: set() for rule in RULES}
    try:
        schema.validate(df, lazy=True)
    except SchemaErrors as errors:
        cases = errors.failure_cases
        for rule in RULES:
            failures[rule] = set(cases.loc[cases["check"] == rule, "index"].dropna().tolist())
    return failures


def _example(row: pd.Series, reason: str) -> dict[str, Any]:
    def short(value: Any) -> str | None:
        return None if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)[:40]

    return {
        "reason": reason,
        "country": short(row["raw_country"]),
        "indicator": short(row["raw_indicator"]),
        "date": short(row["raw_year"]),
        "value": short(row["raw_value"]),
    }


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(SCALE, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:  # pragma: no cover - excluded by the numeric_value rule
        raise ValueError("value cannot be stored as NUMERIC(24,6)") from exc


def transform(
    series_list: Sequence[SeriesResult],
    *,
    country_codes: Sequence[str],
    indicator_codes: Sequence[str],
    start_year: int,
    end_year: int,
) -> TransformResult:
    countries, indicators = set(country_codes), set(indicator_codes)
    df = _normalize(_series_frame(series_list))
    result = TransformResult(extracted=len(df))

    # R: rule violations (each check counts its own failures; a row's reason is its first failed rule).
    failures = _rule_failures(df, _raw_schema(countries, indicators, start_year, end_year))
    reason = pd.Series(pd.NA, index=df.index, dtype="string")
    for rule in reversed(RULES):
        reason[reason.index.isin(failures[rule])] = rule
    rejected_mask = reason.notna()
    result.rejected = int(rejected_mask.sum())
    result.rejection_reasons = dict(Counter(reason.dropna().tolist()))

    checked = {
        "required_fields_present": len(df),
        "valid_country_code": len(df),
        "valid_indicator_code": len(df),
        "year_in_range": len(df),
        "numeric_value": int(df["value_present"].sum()),
    }
    for rule in RULES:
        examples = [_example(df.loc[i], rule) for i in sorted(failures[rule])[:MAX_EXAMPLES]]
        result.checks.append(
            failed_if_any(rule, checked[rule], len(failures[rule]), {"examples": examples} if examples else None)
        )

    # N: valid rows whose source value is null are counted, never loaded and never zero (D-12).
    valid = df[~rejected_mask]
    null_mask = ~valid["value_present"]
    result.null_skipped = int(null_mask.sum())
    result.checks.append(null_value_check(len(valid), result.null_skipped))

    # D: keep the first occurrence of each business key (D-13).
    with_values = valid[~null_mask].copy()
    with_values["value_decimal"] = with_values["raw_value"].map(_to_decimal)
    duplicate_mask = with_values.duplicated(subset=KEY, keep="first")
    result.duplicates_dropped = int(duplicate_mask.sum())
    duplicated_keys = with_values[with_values.duplicated(subset=KEY, keep=False)]
    distinct_values = duplicated_keys.groupby(KEY)["value_decimal"].nunique()
    conflicting = distinct_values[distinct_values > 1]
    result.conflicting_duplicates = len(conflicting)
    examples = [
        {"country": key[0], "indicator": key[1], "year": int(key[2]), "distinct_values": int(n)}
        for key, n in conflicting.head(MAX_EXAMPLES).items()
    ]
    result.checks.append(
        duplicate_check(len(with_values), result.duplicates_dropped, result.conflicting_duplicates, examples)
    )

    # T: load-ready rows, guarded by a strict schema.
    load_ready = with_values[~duplicate_mask]
    _load_ready_schema(countries, indicators, start_year, end_year).validate(load_ready[[*KEY, "value_numeric"]])
    result.rows = [
        {
            "country_code": str(row.country_code),
            "indicator_code": str(row.indicator_code),
            "year": int(row.year),
            "value": row.value_decimal,
            "source_updated_at": row.source_updated_at,
        }
        for row in load_ready.itertuples(index=False)
    ]
    if result.extracted != result.rejected + result.null_skipped + result.duplicates_dropped + result.transformed:
        raise RuntimeError("count identity E = R + N + D + T violated")  # pragma: no cover - invariant guard
    return result
