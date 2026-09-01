"""CLI scaffold for running an interpretable anomaly-detection baseline."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from astra.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the baseline-runner argument parser."""
    parser = argparse.ArgumentParser(
        description="Run a configured baseline after its method has been selected."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/baseline.yaml"),
        help="Path to the baseline configuration file.",
    )
    parser.add_argument(
        "--data-config",
        type=Path,
        default=Path("configs/data.yaml"),
        help="Path to the data configuration file.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Logging verbosity.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and report the unimplemented baseline step."""
    args = build_parser().parse_args(argv)
    configure_logging(level=args.log_level)
    LOGGER.error(
        "TODO: baseline execution is not implemented; no model was trained or scored "
        "(config=%s, data_config=%s).",
        args.config,
        args.data_config,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
