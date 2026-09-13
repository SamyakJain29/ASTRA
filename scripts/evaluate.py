"""CLI scaffold for evaluating baseline anomaly-detection results."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from astra.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the evaluation argument parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate measured results using a configured research protocol."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiment.yaml"),
        help="Path to the experiment configuration file.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Logging verbosity.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and report the unimplemented evaluation step."""
    args = build_parser().parse_args(argv)
    configure_logging(level=args.log_level)
    LOGGER.error(
        "TODO: evaluation is not implemented; no metrics were calculated "
        "(config=%s).",
        args.config,
    )
    return 1



if __name__ == "__main__":
    raise SystemExit(main())
