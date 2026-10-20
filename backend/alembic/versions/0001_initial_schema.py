"""Initial schema: the five tables, constraints and indexes from docs/Backend_DB_Schema.md (v1.1).

Includes the partial unique index uq_pipeline_runs_one_running (D-19) that allows
at most one running pipeline run.

Revision ID: 0001
Revises:
Create Date: 2026-10-20 12:40:01.781870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('countries',
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('region', sa.Text(), nullable=True),
    sa.Column('income_level', sa.Text(), nullable=True),
    sa.Column('is_aggregate', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("country_code ~ '^[A-Z]{3}$'", name=op.f('ck_countries_country_code_iso3')),
    sa.PrimaryKeyConstraint('country_code', name=op.f('pk_countries'))
    )
    op.create_table('indicators',
    sa.Column('indicator_code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('unit', sa.Text(), nullable=False),
    sa.Column('source_name', sa.Text(), server_default=sa.text("'World Bank'"), nullable=False),
    sa.Column('frequency', sa.String(length=16), server_default=sa.text("'annual'"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('indicator_code', name=op.f('pk_indicators'))
    )
    op.create_table('pipeline_runs',
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('triggered_by', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('countries_requested', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('indicators_requested', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_extracted', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_rejected', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_null_skipped', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_duplicates_dropped', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_transformed', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_loaded', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_inserted', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_value_changed', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('error_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('config_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("(status = 'running') = (finished_at IS NULL)", name=op.f('ck_pipeline_runs_finished_iff_terminal')),
    sa.CheckConstraint("status IN ('running', 'success', 'partial_success', 'failed')", name=op.f('ck_pipeline_runs_status_valid')),
    sa.CheckConstraint("triggered_by IN ('cli', 'api', 'scheduler')", name=op.f('ck_pipeline_runs_triggered_by_valid')),
    sa.CheckConstraint('countries_requested >= 0', name=op.f('ck_pipeline_runs_countries_requested_non_negative')),
    sa.CheckConstraint('duration_seconds IS NULL OR duration_seconds >= 0', name=op.f('ck_pipeline_runs_duration_non_negative')),
    sa.CheckConstraint('error_count >= 0', name=op.f('ck_pipeline_runs_error_count_non_negative')),
    sa.CheckConstraint('finished_at IS NOT NULL OR duration_seconds IS NULL', name=op.f('ck_pipeline_runs_duration_only_when_finished')),
    sa.CheckConstraint('finished_at IS NULL OR finished_at >= started_at', name=op.f('ck_pipeline_runs_finished_after_started')),
    sa.CheckConstraint('indicators_requested >= 0', name=op.f('ck_pipeline_runs_indicators_requested_non_negative')),
    sa.CheckConstraint('records_duplicates_dropped >= 0', name=op.f('ck_pipeline_runs_records_duplicates_dropped_non_negative')),
    sa.CheckConstraint('records_extracted >= 0', name=op.f('ck_pipeline_runs_records_extracted_non_negative')),
    sa.CheckConstraint('records_inserted + records_value_changed <= records_loaded', name=op.f('ck_pipeline_runs_changes_within_loaded')),
    sa.CheckConstraint('records_inserted >= 0', name=op.f('ck_pipeline_runs_records_inserted_non_negative')),
    sa.CheckConstraint('records_loaded <= records_transformed', name=op.f('ck_pipeline_runs_loaded_within_transformed')),
    sa.CheckConstraint('records_loaded >= 0', name=op.f('ck_pipeline_runs_records_loaded_non_negative')),
    sa.CheckConstraint('records_null_skipped >= 0', name=op.f('ck_pipeline_runs_records_null_skipped_non_negative')),
    sa.CheckConstraint('records_rejected >= 0', name=op.f('ck_pipeline_runs_records_rejected_non_negative')),
    sa.CheckConstraint('records_transformed >= 0', name=op.f('ck_pipeline_runs_records_transformed_non_negative')),
    sa.CheckConstraint('records_value_changed >= 0', name=op.f('ck_pipeline_runs_records_value_changed_non_negative')),
    sa.PrimaryKeyConstraint('run_id', name=op.f('pk_pipeline_runs'))
    )
    op.create_index('ix_pipeline_runs_started_at', 'pipeline_runs', [sa.literal_column('started_at DESC')], unique=False)
    op.create_index('ix_pipeline_runs_status_started_at', 'pipeline_runs', ['status', sa.literal_column('started_at DESC')], unique=False)
    op.create_index('uq_pipeline_runs_one_running', 'pipeline_runs', ['status'], unique=True, postgresql_where=sa.text("status = 'running'"))
    op.create_table('data_quality_checks',
    sa.Column('quality_check_id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('check_name', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('records_checked', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('records_failed', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint("status IN ('passed', 'warning', 'failed')", name=op.f('ck_data_quality_checks_status_valid')),
    sa.CheckConstraint('records_checked >= 0 AND records_failed >= 0', name=op.f('ck_data_quality_checks_counts_non_negative')),
    sa.CheckConstraint('records_failed <= records_checked', name=op.f('ck_data_quality_checks_failed_within_checked')),
    sa.ForeignKeyConstraint(['run_id'], ['pipeline_runs.run_id'], name=op.f('fk_data_quality_checks_run_id_pipeline_runs')),
    sa.PrimaryKeyConstraint('quality_check_id', name=op.f('pk_data_quality_checks')),
    sa.UniqueConstraint('run_id', 'check_name', name='uq_data_quality_checks_run_id_check_name')
    )
    op.create_index('ix_data_quality_checks_check_name_checked_at', 'data_quality_checks', ['check_name', sa.literal_column('checked_at DESC')], unique=False)
    op.create_table('economic_observations',
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('indicator_code', sa.String(length=32), nullable=False),
    sa.Column('year', sa.SmallInteger(), nullable=False),
    sa.Column('value', sa.Numeric(precision=24, scale=6), nullable=False),
    sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_run_id', sa.UUID(), nullable=True),
    sa.CheckConstraint('year >= 1900 AND year <= 2200', name=op.f('ck_economic_observations_year_range')),
    sa.ForeignKeyConstraint(['country_code'], ['countries.country_code'], name=op.f('fk_economic_observations_country_code_countries')),
    sa.ForeignKeyConstraint(['indicator_code'], ['indicators.indicator_code'], name=op.f('fk_economic_observations_indicator_code_indicators')),
    sa.ForeignKeyConstraint(['last_run_id'], ['pipeline_runs.run_id'], name=op.f('fk_economic_observations_last_run_id_pipeline_runs')),
    sa.PrimaryKeyConstraint('country_code', 'indicator_code', 'year', name=op.f('pk_economic_observations'))
    )
    op.create_index('ix_economic_observations_indicator_code_year', 'economic_observations', ['indicator_code', 'year'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_economic_observations_indicator_code_year', table_name='economic_observations')
    op.drop_table('economic_observations')
    op.drop_index('ix_data_quality_checks_check_name_checked_at', table_name='data_quality_checks')
    op.drop_table('data_quality_checks')
    op.drop_index('uq_pipeline_runs_one_running', table_name='pipeline_runs', postgresql_where=sa.text("status = 'running'"))
    op.drop_index('ix_pipeline_runs_status_started_at', table_name='pipeline_runs')
    op.drop_index('ix_pipeline_runs_started_at', table_name='pipeline_runs')
    op.drop_table('pipeline_runs')
    op.drop_table('indicators')
    op.drop_table('countries')
