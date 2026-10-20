"""SQLAlchemy models for the five tables in docs/Backend_DB_Schema.md.

PostgreSQL constraints are the final integrity guard (Schema §6); the Alembic
migration in ``alembic/versions`` must stay in sync with these definitions
(``alembic check`` verifies this).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep migrations reviewable and reproducible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

RUN_STATUSES = ("running", "success", "partial_success", "failed")
TERMINAL_STATUSES = ("success", "partial_success", "failed")
TRIGGER_TYPES = ("cli", "api", "scheduler")
CHECK_STATUSES = ("passed", "warning", "failed")

RUN_COUNT_COLUMNS = (
    "countries_requested",
    "indicators_requested",
    "records_extracted",
    "records_rejected",
    "records_null_skipped",
    "records_duplicates_dropped",
    "records_transformed",
    "records_loaded",
    "records_inserted",
    "records_value_changed",
    "error_count",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Country(Base):
    __tablename__ = "countries"
    __table_args__ = (CheckConstraint("country_code ~ '^[A-Z]{3}$'", name="country_code_iso3"),)

    country_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    income_level: Mapped[str | None] = mapped_column(Text)
    is_aggregate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Indicator(Base):
    __tablename__ = "indicators"

    indicator_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'World Bank'"))
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'annual'"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(_in_list("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint(_in_list("triggered_by", TRIGGER_TYPES), name="triggered_by_valid"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finished_iff_terminal"),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="finished_after_started"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="duration_non_negative"),
        CheckConstraint("finished_at IS NOT NULL OR duration_seconds IS NULL", name="duration_only_when_finished"),
        *(CheckConstraint(f"{col} >= 0", name=f"{col}_non_negative") for col in RUN_COUNT_COLUMNS),
        CheckConstraint("records_loaded <= records_transformed", name="loaded_within_transformed"),
        CheckConstraint(
            "records_inserted + records_value_changed <= records_loaded", name="changes_within_loaded"
        ),
        Index("ix_pipeline_runs_started_at", text("started_at DESC")),
        Index("ix_pipeline_runs_status_started_at", "status", text("started_at DESC")),
        # D-19: at most one running run in the whole database.
        Index(
            "uq_pipeline_runs_one_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    countries_requested: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    indicators_requested: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_extracted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_null_skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_duplicates_dropped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_transformed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_loaded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_value_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_summary: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class EconomicObservation(Base):
    __tablename__ = "economic_observations"
    __table_args__ = (
        CheckConstraint("year >= 1900 AND year <= 2200", name="year_range"),
        Index("ix_economic_observations_indicator_code_year", "indicator_code", "year"),
    )

    country_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("countries.country_code"), primary_key=True
    )
    indicator_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("indicators.indicator_code"), primary_key=True
    )
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.run_id")
    )


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"
    __table_args__ = (
        CheckConstraint(_in_list("status", CHECK_STATUSES), name="status_valid"),
        CheckConstraint("records_checked >= 0 AND records_failed >= 0", name="counts_non_negative"),
        CheckConstraint("records_failed <= records_checked", name="failed_within_checked"),
        UniqueConstraint("run_id", "check_name", name="uq_data_quality_checks_run_id_check_name"),
        Index("ix_data_quality_checks_check_name_checked_at", "check_name", text("checked_at DESC")),
    )

    quality_check_id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.run_id"), nullable=False
    )
    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    records_checked: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
