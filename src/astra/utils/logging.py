"""Reusable logging configuration for scripts and library code."""

import logging
from typing import Final

DEFAULT_LOG_FORMAT: Final = (
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


def configure_logging(
    level: int | str = logging.INFO,
    *,
    force: bool = False,
) -> None:
    """Configure the process-wide root logger with ASTRA's default format."""
    logging.basicConfig(level=level, format=DEFAULT_LOG_FORMAT, force=force)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger without changing global logging configuration."""
    return logging.getLogger(name)

