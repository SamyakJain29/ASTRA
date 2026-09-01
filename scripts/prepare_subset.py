"""Prepare the reproducible ESA Mission-1 research subset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from astra.data import preparation
from astra.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the subset-preparation argument parser."""
    parser = argparse.ArgumentParser(
        description="Prepare the configured ESA Mission-1 subset without modifying raw data."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data.yaml"),
        help="Path to the data configuration file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild and safely replace existing generated subset files.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Logging verbosity.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run Mission-1 subset preparation and report a concise summary."""
    args = build_parser().parse_args(argv)
    configure_logging(level=args.log_level)

    try:
        summary = preparation.prepare_mission1_subset(args.config, force=args.force)
    except preparation.PreparationError as error:
        LOGGER.error("Mission-1 subset preparation failed: %s", error)
        return 1

    LOGGER.info("Mission-1 subset preparation completed successfully")
    print(json.dumps(summary, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
