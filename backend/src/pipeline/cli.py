"""Command-line entry point (run from backend/):

    python -m src.pipeline.cli run [--triggered-by cli|scheduler]

Exit codes (TRD §13, D-31): 0 success, 1 failed, 2 partial_success,
3 refused because another run is in progress, 4 configuration/startup error
before a run row could be created.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from src.core.config import ConfigurationError, load_settings
from src.core.logging import configure_logging
from src.db.session import SessionFactory, create_db_engine, create_session_factory
from src.pipeline.orchestrator import SourceClient, execute_run, start_run
from src.pipeline.runs import RunInProgressError

logger = logging.getLogger(__name__)

EXIT_CODES = {"success": 0, "failed": 1, "partial_success": 2}
EXIT_IN_PROGRESS = 3
EXIT_STARTUP_ERROR = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.pipeline.cli", description="Global Economic Data Pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="extract, validate and load World Bank data once")
    run.add_argument("--triggered-by", choices=["cli", "scheduler"], default="cli")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: SessionFactory | None = None,
    client: SourceClient | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return EXIT_STARTUP_ERROR
    configure_logging(settings.log_level)

    engine = None
    if session_factory is None:
        engine = create_db_engine(settings.database_url)
        session_factory = create_session_factory(engine)
    try:
        try:
            run_id = start_run(session_factory, settings, args.triggered_by)
        except RunInProgressError as exc:
            print(f"Another pipeline run is already in progress (run_id={exc.running_run_id}). Nothing was started.", file=sys.stderr)
            return EXIT_IN_PROGRESS
        except Exception as exc:  # noqa: BLE001 - e.g. database unreachable; no run row exists
            print(f"Could not start a run: the database is unavailable or not migrated ({type(exc).__name__}). "
                  "Check that PostgreSQL is running and run 'alembic upgrade head'.", file=sys.stderr)
            return EXIT_STARTUP_ERROR

        outcome = execute_run(run_id, session_factory, settings, client)
    finally:
        if engine is not None:
            engine.dispose()

    c = outcome.counts
    print(f"run_id={outcome.run_id} status={outcome.status}")
    print(
        "extracted={0} rejected={1} null_skipped={2} duplicates_dropped={3} transformed={4} "
        "loaded={5} inserted={6} value_changed={7}".format(
            *(c.get(k, 0) for k in (
                "records_extracted", "records_rejected", "records_null_skipped", "records_duplicates_dropped",
                "records_transformed", "records_loaded", "records_inserted", "records_value_changed",
            ))
        )
    )
    if outcome.error_summary:
        print(f"summary: {outcome.error_summary}")
    return EXIT_CODES[outcome.status]


if __name__ == "__main__":
    sys.exit(main())
