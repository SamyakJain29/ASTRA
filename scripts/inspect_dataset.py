"""Inspect and profile a local ESA mission archive without modifying raw data."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from zipfile import BadZipFile

from astra.data.inspection import (
    build_dataset_profile,
    inspect_zip_archive,
    safe_extract_zip,
    write_profile_json,
    write_profile_markdown,
)
from astra.utils.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)

DEFAULT_EXTRACT_DIR = Path("data/interim/esa_adb/mission1")
DEFAULT_PROFILE_PATH = Path("artifacts/data/mission1_profile.json")
DEFAULT_REPORT_PATH = Path("reports/mission1_data_profile.md")


def build_parser() -> argparse.ArgumentParser:
    """Build the dataset-inspection argument parser."""
    parser = argparse.ArgumentParser(
        description="Safely extract and profile an ESA mission ZIP archive."
    )
    parser.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="Path to the immutable raw mission ZIP archive.",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        default=DEFAULT_EXTRACT_DIR,
        help=f"Extraction destination (default: {DEFAULT_EXTRACT_DIR}).",
    )
    parser.add_argument(
        "--profile-json",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help=f"Machine-readable profile path (default: {DEFAULT_PROFILE_PATH}).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Human-readable report path (default: {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Logging verbosity.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Extract and profile a mission archive using the requested output paths."""
    args = build_parser().parse_args(argv)
    configure_logging(level=args.log_level)

    if not args.archive.is_file():
        LOGGER.error("Archive not found; expected a ZIP file at %s", args.archive.resolve())
        return 2

    archive_stat = args.archive.stat()
    try:
        archive_profile = inspect_zip_archive(args.archive)
        LOGGER.info(
            "Inspected %s: %d members, %d compressed bytes, %d uncompressed bytes",
            archive_profile["filename"],
            archive_profile["member_count"],
            archive_profile["size_bytes"],
            archive_profile["uncompressed_size_bytes"],
        )

        extraction = safe_extract_zip(args.archive, args.extract_dir, logger=LOGGER)
        profile = build_dataset_profile(args.archive, args.extract_dir)
        profile["extraction"] = extraction
        write_profile_json(profile, args.profile_json)
        write_profile_markdown(profile, args.report)
    except (BadZipFile, OSError, ValueError) as error:
        LOGGER.error("Dataset inspection failed: %s", error)
        return 1

    final_stat = args.archive.stat()
    if (final_stat.st_size, final_stat.st_mtime_ns) != (
        archive_stat.st_size,
        archive_stat.st_mtime_ns,
    ):
        LOGGER.error("Raw archive changed during inspection; outputs must not be trusted")
        return 1

    LOGGER.info("Wrote machine-readable profile to %s", args.profile_json)
    LOGGER.info("Wrote human-readable report to %s", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
