"""Minimal logging setup. Structured per-run pipeline logs are added with the pipeline (Phase 5)."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
