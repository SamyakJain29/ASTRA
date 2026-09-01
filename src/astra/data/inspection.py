"""Memory-conscious inspection helpers for dataset archives and extracted files."""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import pickletools
import re
import shutil
import stat
import tempfile
import zlib
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from itertools import chain
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile, ZipInfo

CSV_LIKE_SUFFIXES = {".csv", ".tsv", ".txt"}
TELEMETRY_SUFFIXES = CSV_LIKE_SUFFIXES | {".npy", ".npz", ".parquet"}
NULL_TEXT_VALUES = {""}
MAX_PROFILE_EXAMPLE_ROWS = 5
TELEMETRY_SCAN_ROW_LIMIT = 10_000
OBSERVATION_LIMIT_PER_COLUMN = 512
MAX_NESTED_ZIP_DEPTH = 6
SPOOLED_ZIP_MEMORY_LIMIT = 8 * 1024 * 1024
_INTEGER_PATTERN = re.compile(r"[+-]?\d+")
_FLOAT_PATTERN = re.compile(
    r"[+-]?(?:(?:\d+\.\d*)|(?:\d*\.\d+)|(?:\d+))(?:[eE][+-]?\d+)?"
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

JsonObject = dict[str, Any]
BinaryOpener = Callable[[], BinaryIO]


def _as_path(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser()


def _validated_member_path(member_name: str) -> PurePosixPath:
    """Return a normalized safe relative ZIP member path."""
    if not member_name or "\x00" in member_name:
        raise ValueError(f"Unsafe empty or NUL-containing ZIP member: {member_name!r}")

    windows_path = PureWindowsPath(member_name)
    if windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"Unsafe absolute or drive-qualified ZIP member: {member_name!r}")
    if member_name.startswith(("/", "\\")):
        raise ValueError(f"Unsafe absolute ZIP member: {member_name!r}")

    normalized_name = member_name.replace("\\", "/")
    raw_parts = normalized_name.split("/")
    if any(part == ".." for part in raw_parts):
        raise ValueError(f"Unsafe path traversal in ZIP member: {member_name!r}")
    if any(":" in part for part in raw_parts if part):
        raise ValueError(f"Unsafe colon in ZIP member path: {member_name!r}")

    member_path = PurePosixPath(normalized_name)
    if member_path.is_absolute() or not member_path.parts:
        raise ValueError(f"Unsafe ZIP member path: {member_name!r}")
    return member_path


def _is_symlink(info: ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_IFMT(unix_mode) == stat.S_IFLNK


def _validate_zip_members(infos: Sequence[ZipInfo]) -> list[tuple[ZipInfo, PurePosixPath]]:
    validated: list[tuple[ZipInfo, PurePosixPath]] = []
    seen_targets: set[str] = set()
    for info in infos:
        member_path = _validated_member_path(info.filename)
        if _is_symlink(info):
            raise ValueError(f"Symbolic-link ZIP members are not accepted: {info.filename!r}")
        target_key = member_path.as_posix().rstrip("/").casefold()
        if target_key in seen_targets:
            raise ValueError(f"Duplicate ZIP member target: {info.filename!r}")
        seen_targets.add(target_key)
        validated.append((info, member_path))
    return validated


def _extension_label(member_path: PurePosixPath | Path) -> str:
    return member_path.suffix.lower() or "[no extension]"


def _archive_summary(
    *,
    filename: str,
    path: str,
    size_bytes: int,
    infos: Sequence[ZipInfo],
) -> JsonObject:
    validated = _validate_zip_members(infos)
    file_infos = [(info, member) for info, member in validated if not info.is_dir()]
    top_level = sorted({member.parts[0] for _, member in validated})
    extensions = Counter(_extension_label(member) for _, member in file_infos)
    top_level_counts = Counter(member.parts[0] for _, member in file_infos)
    return {
        "filename": filename,
        "path": path,
        "size_bytes": size_bytes,
        "member_count": len(infos),
        "file_count": len(file_infos),
        "directory_count": sum(info.is_dir() for info in infos),
        "top_level_structure": top_level,
        "top_level_file_counts": dict(sorted(top_level_counts.items())),
        "file_extensions": dict(sorted(extensions.items())),
        "uncompressed_size_bytes": sum(info.file_size for info, _ in file_infos),
        "compressed_member_size_bytes": sum(info.compress_size for info, _ in file_infos),
    }


def inspect_zip_archive(path: str | os.PathLike[str]) -> JsonObject:
    """Inspect a ZIP central directory without extracting archive contents."""
    archive_path = _as_path(path)
    if not archive_path.exists():
        raise FileNotFoundError(f"ZIP archive does not exist: {archive_path}")
    if not archive_path.is_file():
        raise IsADirectoryError(f"ZIP archive path is not a file: {archive_path}")

    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        return _archive_summary(
            filename=archive_path.name,
            path=str(archive_path),
            size_bytes=archive_path.stat().st_size,
            infos=infos,
        )


def _is_in_data_raw(path: Path) -> bool:
    parts = [part.casefold() for part in path.resolve(strict=False).parts]
    return any(
        left == "data" and right == "raw"
        for left, right in zip(parts, parts[1:], strict=False)
    )


def _crc32_file(path: Path) -> int:
    checksum = 0
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(1024 * 1024):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def _existing_file_matches(path: Path, info: ZipInfo) -> bool:
    return path.stat().st_size == info.file_size and _crc32_file(path) == info.CRC


def safe_extract_zip(
    archive_path: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    logger: logging.Logger | None = None,
) -> JsonObject:
    """Extract a ZIP safely, skipping identical files and rejecting conflicts."""
    source = _as_path(archive_path)
    target_root = _as_path(destination).resolve(strict=False)
    if _is_in_data_raw(target_root):
        raise ValueError(f"Extraction destination must not be inside data/raw: {target_root}")
    if not source.exists():
        raise FileNotFoundError(f"ZIP archive does not exist: {source}")
    if not source.is_file():
        raise IsADirectoryError(f"ZIP archive path is not a file: {source}")

    extracted_files: list[str] = []
    skipped_files: list[str] = []
    directory_names: list[str] = []
    extracted_size = 0
    skipped_size = 0

    with ZipFile(source) as archive:
        validated = _validate_zip_members(archive.infolist())
        resolved_members: list[tuple[ZipInfo, PurePosixPath, Path]] = []
        for info, member_path in validated:
            target = target_root.joinpath(*member_path.parts).resolve(strict=False)
            try:
                target.relative_to(target_root)
            except ValueError as error:
                raise ValueError(
                    f"ZIP member escapes extraction destination: {info.filename!r}"
                ) from error
            if _is_in_data_raw(target):
                raise ValueError(
                    "Extraction would write inside immutable data/raw: "
                    f"{info.filename!r} -> {target}"
                )
            resolved_members.append((info, member_path, target))

        target_root.mkdir(parents=True, exist_ok=True)
        for info, member_path, target in resolved_members:
            relative_name = member_path.as_posix().rstrip("/")

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                directory_names.append(relative_name)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not target.is_file():
                    raise FileExistsError(f"Extraction target is not a file: {target}")
                if _existing_file_matches(target, info):
                    skipped_files.append(relative_name)
                    skipped_size += info.file_size
                    if logger is not None:
                        logger.info("Skipped identical archive member: %s", relative_name)
                    continue
                raise FileExistsError(f"Refusing to overwrite conflicting file: {target}")

            try:
                with archive.open(info) as source_handle, target.open("xb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
            except Exception:
                target.unlink(missing_ok=True)
                raise

            if not _existing_file_matches(target, info):
                target.unlink(missing_ok=True)
                raise BadZipFile(f"Extracted content failed size or CRC verification: {relative_name}")
            extracted_files.append(relative_name)
            extracted_size += info.file_size
            if logger is not None:
                logger.info("Extracted archive member: %s", relative_name)

    return {
        "archive": str(source),
        "destination": str(target_root),
        "extracted_files": extracted_files,
        "skipped_files": skipped_files,
        "directories": directory_names,
        "extracted_size_bytes": extracted_size,
        "skipped_size_bytes": skipped_size,
    }


def _choose_encoding(sample: bytes) -> str:
    try:
        sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def _sniff_delimiter(sample_text: str, suffix: str) -> str:
    fallback = "\t" if suffix.lower() == ".tsv" else ","
    if not sample_text.strip():
        return fallback
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",\t;|")
    except csv.Error:
        return fallback
    return dialect.delimiter


def _has_header(sample_text: str, first_row: Sequence[str]) -> bool:
    header_tokens = {
        "category",
        "channel",
        "class",
        "description",
        "end",
        "endtime",
        "id",
        "identifier",
        "name",
        "priority",
        "start",
        "starttime",
        "subclass",
        "telecommand",
        "time",
        "timestamp",
        "value",
    }
    if any(_tokens(value) & header_tokens for value in first_row):
        return True
    try:
        return csv.Sniffer().has_header(sample_text)
    except csv.Error:
        return False


def _primitive_type(value: str) -> str:
    stripped = value.strip()
    if stripped in NULL_TEXT_VALUES:
        return "null"
    if stripped.casefold() in {"true", "false"}:
        return "boolean"
    if _INTEGER_PATTERN.fullmatch(stripped):
        return "integer"
    if _FLOAT_PATTERN.fullmatch(stripped):
        try:
            parsed = float(stripped)
        except ValueError:
            return "string"
        return "float" if math.isfinite(parsed) else "string"
    return "string"


def _merge_primitive_types(observed: set[str]) -> str:
    non_null = observed - {"null"}
    if not non_null:
        return "null"
    if non_null <= {"integer"}:
        return "integer"
    if non_null <= {"integer", "float"}:
        return "float"
    if non_null <= {"boolean"}:
        return "boolean"
    return "string"


def _row_as_mapping(columns: Sequence[str], row: Sequence[str]) -> dict[str, str | None]:
    return {
        column: row[index] if index < len(row) else None
        for index, column in enumerate(columns)
    }


def _scan_delimited_stream(
    opener: BinaryOpener,
    *,
    filename: str,
    source_path: str,
    size_bytes: int,
    suffix: str,
    max_example_rows: int,
    row_limit: int | None,
) -> JsonObject:
    encoding = "utf-8-sig"
    last_error: UnicodeDecodeError | None = None
    for candidate_encoding in ("utf-8-sig", "cp1252"):
        try:
            with opener() as binary_handle:
                buffered = io.BufferedReader(binary_handle)
                sample = buffered.peek(65_536)[:65_536]
                if candidate_encoding == "utf-8-sig":
                    encoding = _choose_encoding(sample)
                    if encoding != candidate_encoding:
                        continue
                else:
                    encoding = candidate_encoding
                sample_text = sample.decode(encoding)
                delimiter = _sniff_delimiter(sample_text, suffix)
                text_handle = io.TextIOWrapper(
                    buffered,
                    encoding=encoding,
                    errors="strict",
                    newline="",
                )
                reader = csv.reader(text_handle, delimiter=delimiter)
                try:
                    first_row = next(reader)
                except StopIteration:
                    first_row = []
                header_detected = bool(first_row) and _has_header(sample_text, first_row)
                columns = (
                    first_row
                    if header_detected
                    else [f"column_{index}" for index in range(1, len(first_row) + 1)]
                )
                rows: Iterable[list[str]] = (
                    reader if header_detected or not first_row else chain([first_row], reader)
                )

                observed_types = [set() for _ in columns]
                null_counts = [0 for _ in columns]
                observations: list[list[str]] = [[] for _ in columns]
                examples: list[dict[str, str | None]] = []
                row_count = 0
                malformed_rows = 0
                extra_fields = 0
                truncated = False

                for row in rows:
                    if row_limit is not None and row_count >= row_limit:
                        truncated = True
                        break
                    row_count += 1
                    if len(row) != len(columns):
                        malformed_rows += 1
                    if len(row) > len(columns):
                        extra_fields += len(row) - len(columns)
                    for index, _ in enumerate(columns):
                        value = row[index] if index < len(row) else ""
                        value_type = _primitive_type(value)
                        observed_types[index].add(value_type)
                        if value_type == "null":
                            null_counts[index] += 1
                        elif len(observations[index]) < OBSERVATION_LIMIT_PER_COLUMN:
                            observations[index].append(value)
                    if len(examples) < max_example_rows:
                        examples.append(_row_as_mapping(columns, row))

                bytes_consumed = min(buffered.tell(), size_bytes) if size_bytes else 0
                estimated_count = row_count
                if truncated and bytes_consumed > 0:
                    estimated_count = max(
                        row_count,
                        round(row_count * size_bytes / bytes_consumed),
                    )
                duplicate_columns = sorted(
                    column for column, count in Counter(columns).items() if count > 1
                )
                return {
                    "filename": filename,
                    "path": source_path,
                    "size_bytes": size_bytes,
                    "row_count": estimated_count,
                    "row_count_is_estimate": truncated,
                    "rows_scanned": row_count,
                    "column_names": columns,
                    "inferred_data_types": {
                        column: _merge_primitive_types(observed_types[index])
                        for index, column in enumerate(columns)
                    },
                    "null_counts": {
                        column: null_counts[index] for index, column in enumerate(columns)
                    },
                    "null_counts_scope": "observed rows" if truncated else "all rows",
                    "example_rows": examples,
                    "delimiter": "\\t" if delimiter == "\t" else delimiter,
                    "encoding": encoding,
                    "header_detected": header_detected,
                    "malformed_row_count": malformed_rows,
                    "extra_field_count": extra_fields,
                    "duplicate_column_names": duplicate_columns,
                    "_sample_values": {
                        column: observations[index] for index, column in enumerate(columns)
                    },
                }
        except UnicodeDecodeError as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise UnicodeError(f"Unable to decode tabular file: {source_path}")


def profile_csv_table(
    path: str | os.PathLike[str],
    max_example_rows: int = MAX_PROFILE_EXAMPLE_ROWS,
) -> JsonObject:
    """Stream a delimited text table and return a JSON-serializable profile."""
    if max_example_rows < 0:
        raise ValueError("max_example_rows must be non-negative")
    table_path = _as_path(path)
    if not table_path.exists():
        raise FileNotFoundError(f"Table does not exist: {table_path}")
    if not table_path.is_file():
        raise IsADirectoryError(f"Table path is not a file: {table_path}")
    example_limit = min(max_example_rows, MAX_PROFILE_EXAMPLE_ROWS)
    profile = _scan_delimited_stream(
        lambda: table_path.open("rb"),
        filename=table_path.name,
        source_path=str(table_path),
        size_bytes=table_path.stat().st_size,
        suffix=table_path.suffix,
        max_example_rows=example_limit,
        row_limit=None,
    )
    profile.pop("_sample_values", None)
    return profile


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(value.casefold()))


def _classify_source(source_path: str, member_name: str) -> tuple[str, str]:
    all_tokens = _tokens(source_path)
    member_path = PurePosixPath(member_name.replace("\\", "/"))
    name_tokens = _tokens(member_path.stem)
    parent_tokens = _tokens("/".join(member_path.parts[:-1]))

    label_tokens = {"anomalies", "anomaly", "event", "events", "label", "labels"}
    command_tokens = {"command", "commands", "telecommand", "telecommands"}
    telemetry_tokens = {"channel", "channels", "telemetries", "telemetry"}

    if all_tokens & label_tokens:
        return "labels", "observed label, anomaly, or event token in the source path"
    if all_tokens & command_tokens:
        return "telecommands", "observed command or telecommand token in the source path"
    if parent_tokens & telemetry_tokens:
        return "telemetry", "observed telemetry or channel container in the source path"
    if (all_tokens - name_tokens) & telemetry_tokens:
        return "telemetry", "observed telemetry or channel archive in the source path"
    if member_path.suffix.lower() in CSV_LIKE_SUFFIXES:
        return "metadata", "delimited table outside an observed data-specific container"
    if all_tokens & telemetry_tokens and member_path.suffix.lower() in TELEMETRY_SUFFIXES:
        return "telemetry", "observed telemetry or channel token in the source path"
    return "unclassified", "file role is not evident from its path or format"


def _looks_iso_datetime(value: str) -> bool:
    stripped = value.strip()
    if not stripped or not any(marker in stripped for marker in ("-", "T", ":")):
        return False
    normalized = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def _timestamp_candidates(
    columns: Sequence[str],
    inferred_types: dict[str, str],
    observations: dict[str, list[str]],
) -> list[JsonObject]:
    candidates: list[JsonObject] = []
    timestamp_header_tokens = {"date", "datetime", "epoch", "time", "timestamp"}
    for column in columns:
        values = observations.get(column, [])
        header_match = bool(_tokens(column) & timestamp_header_tokens)
        iso_match = bool(values) and all(_looks_iso_datetime(value) for value in values[:50])
        if not header_match and not iso_match:
            continue
        if iso_match:
            representation = "ISO-8601-like string"
        elif inferred_types.get(column) == "integer":
            representation = "integer"
        elif inferred_types.get(column) == "float":
            representation = "floating-point"
        else:
            representation = "string"
        evidence = []
        if header_match:
            evidence.append("column name")
        if iso_match:
            evidence.append("observed ISO-8601-like values")
        candidates.append(
            {
                "column": column,
                "representation": representation,
                "evidence": evidence,
            }
        )
    return candidates


def _parsed_timestamp_values(values: Sequence[str], representation: str) -> tuple[list[float], str]:
    parsed: list[float] = []
    if representation == "ISO-8601-like string":
        for value in values:
            normalized = value.strip()
            normalized = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
            try:
                parsed.append(datetime.fromisoformat(normalized).timestamp())
            except ValueError:
                continue
        return parsed, "seconds"
    if representation in {"integer", "floating-point"}:
        for value in values:
            try:
                parsed.append(float(value))
            except ValueError:
                continue
        return parsed, "raw timestamp units"
    return [], "unresolved"


def _sampling_interval(
    timestamp_candidates: Sequence[JsonObject],
    observations: dict[str, list[str]],
) -> JsonObject:
    if not timestamp_candidates:
        return {
            "assessment": "unresolved",
            "reason": "no timestamp candidate was identified from observed headers or values",
        }
    candidate = timestamp_candidates[0]
    column = str(candidate["column"])
    parsed, unit = _parsed_timestamp_values(
        observations.get(column, []),
        str(candidate["representation"]),
    )
    deltas = [
        right - left
        for left, right in zip(parsed, parsed[1:], strict=False)
        if right > left
    ]
    if len(deltas) < 2:
        return {
            "assessment": "unresolved",
            "column": column,
            "reason": "fewer than two positive timestamp intervals were observed",
        }
    reference = deltas[0]
    uniform = all(math.isclose(delta, reference, rel_tol=1e-9, abs_tol=1e-12) for delta in deltas)
    return {
        "assessment": "uniform" if uniform else "varying",
        "column": column,
        "observed_interval": reference if uniform else None,
        "minimum_observed_interval": min(deltas),
        "maximum_observed_interval": max(deltas),
        "unit": unit,
        "intervals_measured": len(deltas),
    }


def _value_representation(
    columns: Sequence[str],
    inferred_types: dict[str, str],
    timestamp_candidates: Sequence[JsonObject],
) -> JsonObject:
    timestamp_columns = {str(item["column"]) for item in timestamp_candidates}
    header_candidates = [
        column
        for column in columns
        if _tokens(column) & {"measurement", "reading", "value", "values"}
    ]
    candidate_columns = header_candidates or [
        column for column in columns if column not in timestamp_columns
    ]
    return {
        "candidate_columns": [
            {"column": column, "inferred_type": inferred_types.get(column, "unresolved")}
            for column in candidate_columns
        ],
        "selection_basis": (
            "observed value-like column names"
            if header_candidates
            else "non-timestamp columns; semantic role unresolved"
        ),
    }


def _telemetry_profile_from_table(
    table_profile: JsonObject,
    *,
    member_name: str,
    classification_reason: str,
    compressed_size_bytes: int | None,
) -> JsonObject:
    observations = table_profile.pop("_sample_values", {})
    columns = table_profile["column_names"]
    inferred_types = table_profile["inferred_data_types"]
    timestamp_candidates = _timestamp_candidates(columns, inferred_types, observations)
    missing_observed = any(count > 0 for count in table_profile["null_counts"].values())
    return {
        "identifier": PurePosixPath(member_name.replace("\\", "/")).stem,
        "identifier_source": "file name",
        "path": table_profile["path"],
        "format": PurePosixPath(member_name).suffix.lower() or "extensionless delimited text",
        "classification_reason": classification_reason,
        "compressed_size_bytes": compressed_size_bytes,
        "uncompressed_size_bytes": table_profile["size_bytes"],
        "row_count": table_profile["row_count"],
        "row_count_is_estimate": table_profile["row_count_is_estimate"],
        "rows_scanned": table_profile["rows_scanned"],
        "column_names": columns,
        "inferred_data_types": inferred_types,
        "timestamp_representation": {
            "candidates": timestamp_candidates,
            "status": "observed candidates" if timestamp_candidates else "unresolved",
        },
        "value_representation": _value_representation(
            columns,
            inferred_types,
            timestamp_candidates,
        ),
        "sampling_interval": _sampling_interval(timestamp_candidates, observations),
        "missing_values_observed": missing_observed,
        "missing_value_evidence_scope": table_profile["null_counts_scope"],
        "null_counts": table_profile["null_counts"],
    }


def _candidate_fields(columns: Sequence[str], groups: dict[str, set[str]]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for role, role_tokens in groups.items():
        matching_columns = [column for column in columns if _tokens(column) & role_tokens]
        matches[role] = matching_columns
    return matches


def _strip_internal_profile_fields(profile: JsonObject) -> JsonObject:
    return {key: value for key, value in profile.items() if not key.startswith("_")}


def _entry_source_path(container_path: str, member_name: str | None = None) -> str:
    return container_path if member_name is None else f"{container_path}!{member_name}"


def _profile_tabular_entry(
    *,
    opener: BinaryOpener,
    member_name: str,
    source_path: str,
    size_bytes: int,
    compressed_size_bytes: int | None,
    category: str,
    classification_reason: str,
) -> JsonObject:
    row_limit = TELEMETRY_SCAN_ROW_LIMIT if category == "telemetry" else None
    example_limit = (
        0
        if category == "telemetry" or (category == "telecommands" and "!" in source_path)
        else MAX_PROFILE_EXAMPLE_ROWS
    )
    table_profile = _scan_delimited_stream(
        opener,
        filename=PurePosixPath(member_name).name,
        source_path=source_path,
        size_bytes=size_bytes,
        suffix=PurePosixPath(member_name).suffix,
        max_example_rows=example_limit,
        row_limit=row_limit,
    )
    if category == "telemetry":
        return _telemetry_profile_from_table(
            table_profile,
            member_name=member_name,
            classification_reason=classification_reason,
            compressed_size_bytes=compressed_size_bytes,
        )
    table_profile["classification_reason"] = classification_reason
    table_profile["compressed_size_bytes"] = compressed_size_bytes
    return table_profile


def _new_collector() -> JsonObject:
    return {
        "metadata_tables": [],
        "telemetry_channels": [],
        "telecommand_tables": [],
        "label_tables": [],
        "nested_archives": [],
        "unclassified_files": [],
        "unresolved_questions": [],
    }


def _bounded_content_observation(opener: BinaryOpener) -> JsonObject:
    with opener() as binary_handle:
        sample = binary_handle.read(65_536)
    magic = sample[:16]
    if sample.startswith(b"\x93NUMPY"):
        detected = "NumPy NPY"
    elif sample.startswith(b"PAR1"):
        detected = "Apache Parquet"
    elif sample.startswith(b"PK\x03\x04"):
        detected = "ZIP"
    elif sample.startswith(b"\x80"):
        detected = "Python pickle protocol"
    else:
        try:
            decoded = sample.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = ""
        printable = sum(character.isprintable() or character in "\r\n\t" for character in decoded)
        printable_ratio = printable / len(decoded) if decoded else 0.0
        detected = (
            "delimited or line-oriented UTF-8 text"
            if decoded and printable_ratio >= 0.95 and ("\n" in decoded or "\r" in decoded)
            else "unresolved binary"
        )
    return {
        "detected_format": detected,
        "magic_hex": magic.hex(" "),
        "sample_size_bytes": len(sample),
    }


def _pickle_payload_summary(
    payload: bytes | bytearray,
    evidence_tokens: Sequence[str],
) -> JsonObject:
    import numpy as np

    size_bytes = len(payload)
    tokens = [token.casefold() for token in evidence_tokens]
    token_set = set(tokens)
    summary: JsonObject = {
        "size_bytes": size_bytes,
        "dtype_evidence": list(dict.fromkeys(evidence_tokens)),
        "element_count_if_8_bytes": size_bytes // 8 if size_bytes % 8 == 0 else None,
    }
    byte_order = ">" if ">" in token_set else "<" if "<" in token_set else "="
    datetime_tokens = {
        token for token in tokens if token == "m8" or token.startswith("datetime64")
    }
    datetime_units = {
        "y",
        "m",
        "w",
        "d",
        "h",
        "s",
        "ms",
        "us",
        "ns",
        "ps",
        "fs",
        "as",
    }
    datetime_unit = next(
        (token for token in reversed(tokens) if token in datetime_units),
        None,
    )
    if datetime_tokens and size_bytes % 8 == 0:
        values = np.frombuffer(payload, dtype=f"{byte_order}i8")
        missing_marker = np.iinfo(np.int64).min
        missing_count = int(np.count_nonzero(values == missing_marker))
        observed = values[: min(values.size, TELEMETRY_SCAN_ROW_LIMIT)]
        observed = observed[observed != missing_marker]
        deltas = np.diff(observed)
        unique_deltas = np.unique(deltas)
        seconds_per_unit = {
            "w": 604_800.0,
            "d": 86_400.0,
            "h": 3_600.0,
            "s": 1.0,
            "ms": 1e-3,
            "us": 1e-6,
            "ns": 1e-9,
            "ps": 1e-12,
            "fs": 1e-15,
            "as": 1e-18,
        }.get(datetime_unit)

        def display_interval(value: np.int64) -> float | int:
            if seconds_per_unit is not None:
                return round(float(value) * seconds_per_unit, 12)
            return int(value)

        summary.update(
            {
                "interpreted_dtype": (
                    f"NumPy datetime64[{datetime_unit}]"
                    if datetime_unit is not None
                    else "NumPy datetime64 (unit unresolved)"
                ),
                "element_count": int(values.size),
                "missing_value_kind": "NaT",
                "missing_value_count": missing_count,
                "sampling_observation": {
                    "assessment": (
                        "uniform" if unique_deltas.size == 1 and unique_deltas[0] > 0
                        else "varying"
                        if unique_deltas.size
                        else "unresolved"
                    ),
                    "observed_interval": (
                        display_interval(unique_deltas[0])
                        if unique_deltas.size == 1 and unique_deltas[0] > 0
                        else None
                    ),
                    "unit": "seconds" if seconds_per_unit is not None else "raw datetime64 units",
                    "minimum_observed_interval": (
                        display_interval(unique_deltas.min()) if unique_deltas.size else None
                    ),
                    "maximum_observed_interval": (
                        display_interval(unique_deltas.max()) if unique_deltas.size else None
                    ),
                    "intervals_measured": int(deltas.size),
                    "rows_scanned": int(observed.size),
                    "datetime_unit_observed": datetime_unit,
                },
            }
        )
        return summary

    dtype_aliases = {
        "f2": ("float16", 2),
        "float16": ("float16", 2),
        "f4": ("float32", 4),
        "float32": ("float32", 4),
        "f8": ("float64", 8),
        "float64": ("float64", 8),
        "i1": ("int8", 1),
        "int8": ("int8", 1),
        "i2": ("int16", 2),
        "int16": ("int16", 2),
        "i4": ("int32", 4),
        "int32": ("int32", 4),
        "i8": ("int64", 8),
        "int64": ("int64", 8),
        "u1": ("uint8", 1),
        "uint8": ("uint8", 1),
        "u2": ("uint16", 2),
        "uint16": ("uint16", 2),
        "u4": ("uint32", 4),
        "uint32": ("uint32", 4),
        "u8": ("uint64", 8),
        "uint64": ("uint64", 8),
    }
    dtype_evidence = next(
        (dtype_aliases[token] for token in reversed(tokens) if token in dtype_aliases),
        None,
    )
    if dtype_evidence is None:
        return summary
    dtype_name, item_size = dtype_evidence
    if size_bytes % item_size:
        return summary
    numpy_code = {
        "float16": "f2",
        "float32": "f4",
        "float64": "f8",
        "int8": "i1",
        "int16": "i2",
        "int32": "i4",
        "int64": "i8",
        "uint8": "u1",
        "uint16": "u2",
        "uint32": "u4",
        "uint64": "u8",
    }[dtype_name]
    values = np.frombuffer(payload, dtype=f"{byte_order}{numpy_code}")
    summary.update(
        {
            "interpreted_dtype": f"NumPy {dtype_name}",
            "element_count": int(values.size),
        }
    )
    if dtype_name.startswith("float"):
        summary.update(
            {
                "missing_value_kind": "NaN",
                "missing_value_count": int(np.count_nonzero(np.isnan(values))),
            }
        )
    return summary


def _profile_pickle_stream(
    opener: BinaryOpener,
    *,
    member_name: str,
    source_path: str,
    size_bytes: int,
    compressed_size_bytes: int | None,
) -> JsonObject:
    referenced_strings: list[str] = []
    recent_strings: list[str] = []
    payload_summaries: list[JsonObject] = []
    pending_payload: bytes | bytearray | None = None
    pending_tokens: list[str] = []
    protocol = None

    def finish_payload() -> None:
        nonlocal pending_payload, pending_tokens
        if pending_payload is not None:
            payload_summaries.append(
                _pickle_payload_summary(pending_payload, pending_tokens)
            )
        pending_payload = None
        pending_tokens = []

    with opener() as binary_handle:
        for opcode, argument, _ in pickletools.genops(binary_handle):
            if opcode.name == "PROTO":
                protocol = int(argument)
            if opcode.name == "SHORT_BINBYTES" and isinstance(argument, bytes):
                try:
                    decoded_argument = argument.decode("ascii")
                except UnicodeDecodeError:
                    decoded_argument = ""
                if decoded_argument and decoded_argument.isprintable() and len(argument) <= 32:
                    finish_payload()
                    recent_strings.append(decoded_argument)
                    recent_strings = recent_strings[-64:]
                    if (
                        len(referenced_strings) < 256
                        and decoded_argument not in referenced_strings
                    ):
                        referenced_strings.append(decoded_argument)
                    if pending_payload is not None:
                        pending_tokens.append(decoded_argument)
                    continue
            if opcode.name in {"BINBYTES", "BINBYTES8", "BYTEARRAY8", "SHORT_BINBYTES"}:
                finish_payload()
                if isinstance(argument, (bytes, bytearray)):
                    pending_payload = argument
                    pending_tokens = recent_strings[-16:]
                continue
            if isinstance(argument, str) and len(argument) <= 256:
                recent_strings.append(argument)
                recent_strings = recent_strings[-64:]
                if len(referenced_strings) < 256 and argument not in referenced_strings:
                    referenced_strings.append(argument)
                if pending_payload is not None:
                    pending_tokens.append(argument)
    finish_payload()

    timestamp_payloads = [
        item
        for item in payload_summaries
        if str(item.get("interpreted_dtype", "")).startswith("NumPy datetime64")
    ]
    value_payloads = [
        item
        for item in payload_summaries
        if str(item.get("interpreted_dtype", "")).startswith("NumPy ")
        and not str(item.get("interpreted_dtype", "")).startswith("NumPy datetime64")
    ]
    count_candidates = [
        int(item["element_count"])
        for item in timestamp_payloads or value_payloads
        if isinstance(item.get("element_count"), int)
    ]
    row_count = max(count_candidates) if count_candidates else None
    sampling = (
        timestamp_payloads[0].get("sampling_observation", {"assessment": "unresolved"})
        if timestamp_payloads
        else {"assessment": "unresolved"}
    )
    missing_capable_payloads = [
        item
        for item in timestamp_payloads + value_payloads
        if "missing_value_count" in item
    ]
    missing_count = sum(
        int(item.get("missing_value_count", 0))
        for item in missing_capable_payloads
    )
    pandas_references = sorted(
        value for value in referenced_strings if "pandas" in value.casefold()
    )
    numpy_references = sorted(
        value for value in referenced_strings if "numpy" in value.casefold()
    )
    object_type_symbols = []
    if "pandas.core.frame" in referenced_strings and "DataFrame" in referenced_strings:
        object_type_symbols.append("pandas.core.frame.DataFrame")
    missing_assessment_complete = bool(timestamp_payloads and value_payloads) and all(
        "missing_value_count" in item for item in timestamp_payloads + value_payloads
    )
    return {
        "identifier": PurePosixPath(member_name.replace("\\", "/")).stem,
        "identifier_source": "file name",
        "path": source_path,
        "format": f"Python pickle protocol {protocol}",
        "inspection_mode": "pickle opcode and embedded array inspection; payload not executed",
        "compressed_size_bytes": compressed_size_bytes,
        "uncompressed_size_bytes": size_bytes,
        "row_count": row_count,
        "row_count_is_estimate": row_count is not None,
        "row_count_basis": "largest recognized embedded timestamp or numeric array",
        "referenced_pandas_symbols": pandas_references,
        "referenced_numpy_symbols": numpy_references,
        "object_type_symbols_observed": object_type_symbols,
        "pickle_strings_observed": referenced_strings,
        "payload_summaries": payload_summaries,
        "timestamp_representation": {
            "status": "observed" if timestamp_payloads else "unresolved",
            "representations": sorted(
                {str(item["interpreted_dtype"]) for item in timestamp_payloads}
            ),
        },
        "value_representation": {
            "status": "observed" if value_payloads else "unresolved",
            "representations": sorted(
                {str(item["interpreted_dtype"]) for item in value_payloads}
            ),
        },
        "sampling_interval": sampling,
        "missing_values_observed": (
            missing_count > 0 if missing_count or missing_assessment_complete else None
        ),
        "missing_value_count": missing_count,
        "missing_value_evidence_scope": (
            "NaT in all recognized datetime64 arrays and NaN in all recognized floating-point "
            "arrays; undocumented numeric sentinels are not interpreted"
        ),
    }


def _collect_profiled_entry(
    collector: JsonObject,
    *,
    opener: BinaryOpener,
    member_name: str,
    source_path: str,
    size_bytes: int,
    compressed_size_bytes: int | None,
) -> None:
    suffix = PurePosixPath(member_name).suffix.lower()
    category, reason = _classify_source(source_path, member_name)
    content_observation = (
        _bounded_content_observation(opener)
        if not suffix and category in {"telecommands", "telemetry"}
        else None
    )
    is_detected_text = bool(
        content_observation
        and content_observation["detected_format"]
        == "delimited or line-oriented UTF-8 text"
    )
    if suffix in CSV_LIKE_SUFFIXES or is_detected_text:
        table_profile = _profile_tabular_entry(
            opener=opener,
            member_name=member_name,
            source_path=source_path,
            size_bytes=size_bytes,
            compressed_size_bytes=compressed_size_bytes,
            category=category,
            classification_reason=reason,
        )
        if content_observation is not None:
            table_profile["content_observation"] = content_observation
        destination_key = {
            "metadata": "metadata_tables",
            "telemetry": "telemetry_channels",
            "telecommands": "telecommand_tables",
            "labels": "label_tables",
        }.get(category, "metadata_tables")
        collector[destination_key].append(table_profile)
        if category == "unclassified":
            collector["unresolved_questions"].append(
                f"Confirm the semantic role of delimited table {source_path}."
            )
        return

    if (
        content_observation is not None
        and content_observation["detected_format"] == "Python pickle protocol"
    ):
        pickle_profile = _profile_pickle_stream(
            opener,
            member_name=member_name,
            source_path=source_path,
            size_bytes=size_bytes,
            compressed_size_bytes=compressed_size_bytes,
        )
        pickle_profile["classification_reason"] = reason
        if category == "telemetry":
            collector["telemetry_channels"].append(pickle_profile)
        else:
            collector["unclassified_files"].append(pickle_profile)
        return

    if category == "telemetry" and suffix in TELEMETRY_SUFFIXES:
        collector["telemetry_channels"].append(
            {
                "identifier": PurePosixPath(member_name).stem,
                "identifier_source": "file name",
                "path": source_path,
                "format": suffix,
                "classification_reason": reason,
                "compressed_size_bytes": compressed_size_bytes,
                "uncompressed_size_bytes": size_bytes,
                "row_count": None,
                "row_count_is_estimate": None,
                "timestamp_representation": {"status": "unresolved"},
                "value_representation": {"status": "unresolved"},
                "sampling_interval": {"assessment": "unresolved"},
                "missing_values_observed": None,
                "missing_value_evidence_scope": "not inspected for this format",
            }
        )
        collector["unresolved_questions"].append(
            f"Inspect schema and missing-value encoding for non-delimited telemetry file {source_path}."
        )
        return

    collector["unclassified_files"].append(
        {
            "path": source_path,
            "format": suffix or "[no extension]",
            "size_bytes": size_bytes,
            "compressed_size_bytes": compressed_size_bytes,
            "classification_reason": reason,
            "content_observation": content_observation,
        }
    )


def _nested_archive_summary(
    archive: ZipFile,
    *,
    display_path: str,
    archive_size: int,
) -> JsonObject:
    return _archive_summary(
        filename=PurePosixPath(display_path).name,
        path=display_path,
        size_bytes=archive_size,
        infos=archive.infolist(),
    )


def _scan_open_zip(
    archive: ZipFile,
    *,
    display_path: str,
    archive_size: int,
    collector: JsonObject,
    depth: int,
) -> None:
    if depth > MAX_NESTED_ZIP_DEPTH:
        collector["unresolved_questions"].append(
            f"Nested archive depth limit reached at {display_path}."
        )
        return
    validated = _validate_zip_members(archive.infolist())
    collector["nested_archives"].append(
        _nested_archive_summary(archive, display_path=display_path, archive_size=archive_size)
    )
    for info, member_path in validated:
        if info.is_dir():
            continue
        member_name = member_path.as_posix()
        source_path = _entry_source_path(display_path, member_name)
        if member_path.suffix.lower() == ".zip":
            with archive.open(info) as nested_source, tempfile.SpooledTemporaryFile(
                max_size=SPOOLED_ZIP_MEMORY_LIMIT,
                mode="w+b",
            ) as nested_file:
                shutil.copyfileobj(nested_source, nested_file, length=1024 * 1024)
                nested_file.seek(0)
                with ZipFile(nested_file) as nested_archive:
                    _scan_open_zip(
                        nested_archive,
                        display_path=source_path,
                        archive_size=info.file_size,
                        collector=collector,
                        depth=depth + 1,
                    )
            continue
        _collect_profiled_entry(
            collector,
            opener=lambda info=info: archive.open(info),
            member_name=member_name,
            source_path=source_path,
            size_bytes=info.file_size,
            compressed_size_bytes=info.compress_size,
        )


def _scan_nested_zip_file(path: Path, relative_path: str, collector: JsonObject) -> None:
    with ZipFile(path) as archive:
        _scan_open_zip(
            archive,
            display_path=relative_path,
            archive_size=path.stat().st_size,
            collector=collector,
            depth=1,
        )


def _scan_extracted_files(root: Path, collector: JsonObject) -> JsonObject:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    extension_counts = Counter(_extension_label(path) for path in files)
    top_level = sorted({path.relative_to(root).parts[0] for path in files})
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".zip":
            _scan_nested_zip_file(path, relative_path, collector)
            continue
        _collect_profiled_entry(
            collector,
            opener=lambda path=path: path.open("rb"),
            member_name=relative_path,
            source_path=relative_path,
            size_bytes=path.stat().st_size,
            compressed_size_bytes=None,
        )
    return {
        "root": str(root),
        "file_count": len(files),
        "size_bytes": sum(path.stat().st_size for path in files),
        "top_level_structure": top_level,
        "file_extensions": dict(sorted(extension_counts.items())),
        "nested_archives": collector["nested_archives"],
        "unclassified_files": collector["unclassified_files"],
    }


def _archive_role(path: str) -> str:
    tokens = _tokens(path)
    if tokens & {"channel", "channels", "telemetry"}:
        return "telemetry"
    if tokens & {"command", "commands", "telecommand", "telecommands"}:
        return "telecommands"
    return "unclassified"


def _archive_identifier(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).stem


def _archive_format_counts(archives: Sequence[JsonObject]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for archive in archives:
        counts.update(archive.get("file_extensions", {}))
    return dict(sorted(counts.items()))


def _table_field_candidates(table: JsonObject) -> JsonObject:
    columns = table.get("column_names", [])
    observations = table.get("_sample_values", {})
    inferred_types = table.get("inferred_data_types", {})
    return {
        "event_identifiers": _candidate_fields(
            columns, {"fields": {"event", "eventid", "id", "identifier"}}
        )["fields"],
        "start_timestamps": _candidate_fields(
            columns, {"fields": {"begin", "start", "starttime"}}
        )["fields"],
        "end_timestamps": _candidate_fields(
            columns, {"fields": {"end", "endtime", "finish", "stop"}}
        )["fields"],
        "channel_references": _candidate_fields(
            columns, {"fields": {"channel", "channels"}}
        )["fields"],
        "category_or_type_fields": _candidate_fields(
            columns,
            {"fields": {"category", "class", "subclass", "type"}},
        )["fields"],
        "timestamp_candidates": _timestamp_candidates(columns, inferred_types, observations),
    }


def _observed_category_values(tables: Sequence[JsonObject]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for table in tables:
        observations = table.get("_sample_values", {})
        for column in table.get("column_names", []):
            if not (_tokens(column) & {"category", "class", "subclass", "type"}):
                continue
            key = f'{table["path"]}:{column}'
            values[key] = sorted(set(observations.get(column, [])))
    return values


def _public_tables(tables: Sequence[JsonObject]) -> list[JsonObject]:
    return [_strip_internal_profile_fields(table) for table in tables]


def _telemetry_summary(
    archives: Sequence[JsonObject],
    entries: Sequence[JsonObject],
) -> JsonObject:
    sample_counts = [
        int(entry["row_count"])
        for entry in entries
        if isinstance(entry.get("row_count"), int)
    ]
    interval_assessments = Counter(
        str(entry.get("sampling_interval", {}).get("assessment", "unresolved"))
        for entry in entries
    )
    missing_observations = Counter(
        str(entry.get("missing_values_observed")) for entry in entries
    )
    timestamp_representations = sorted(
        {
            str(candidate.get("representation"))
            for entry in entries
            for candidate in entry.get("timestamp_representation", {}).get("candidates", [])
        }
        | {
            str(representation)
            for entry in entries
            for representation in entry.get("timestamp_representation", {}).get(
                "representations", []
            )
        }
    )
    value_representations = sorted(
        {
            str(candidate.get("inferred_type"))
            for entry in entries
            for candidate in entry.get("value_representation", {}).get(
                "candidate_columns", []
            )
        }
        | {
            str(representation)
            for entry in entries
            for representation in entry.get("value_representation", {}).get(
                "representations", []
            )
        }
    )
    measured_intervals = sorted(
        {
            (
                float(entry["sampling_interval"]["observed_interval"]),
                str(entry["sampling_interval"]["unit"]),
            )
            for entry in entries
            if entry.get("sampling_interval", {}).get("assessment") == "uniform"
            and isinstance(
                entry.get("sampling_interval", {}).get("observed_interval"),
                (int, float),
            )
        }
    )
    measured_channel_count = sum(
        entry.get("sampling_interval", {}).get("assessment") == "uniform"
        for entry in entries
    )
    if any(
        entry.get("sampling_interval", {}).get("assessment") == "varying"
        for entry in entries
    ):
        cross_channel_sampling = "varying within at least one inspected channel sample"
    elif len(measured_intervals) > 1:
        cross_channel_sampling = "varying among measured channel intervals"
    elif measured_intervals and len(entries) == measured_channel_count:
        cross_channel_sampling = "uniform among measured channel intervals"
    elif measured_intervals:
        cross_channel_sampling = "partially measured; unresolved for some channels"
    else:
        cross_channel_sampling = "unresolved"
    return {
        "channel_file_count": len(archives),
        "channel_identifiers": sorted(_archive_identifier(item["path"]) for item in archives),
        "archive_formats": {".zip": len(archives)} if archives else {},
        "inner_file_formats": _archive_format_counts(archives),
        "serialization_formats_observed": dict(
            sorted(Counter(str(entry.get("format", "unresolved")) for entry in entries).items())
        ),
        "object_type_symbols_observed": sorted(
            {
                str(symbol)
                for entry in entries
                for symbol in entry.get("object_type_symbols_observed", [])
            }
        ),
        "compressed_size_bytes": sum(int(item.get("size_bytes", 0)) for item in archives),
        "uncompressed_size_bytes": sum(
            int(item.get("uncompressed_size_bytes", 0)) for item in archives
        ),
        "channel_archives": list(archives),
        "data_files": list(entries),
        "sample_counts": [
            {
                "identifier": entry.get("identifier"),
                "row_count": entry.get("row_count"),
                "is_estimate": entry.get("row_count_is_estimate"),
            }
            for entry in entries
        ],
        "sample_count_summary": {
            "files_with_estimates": len(sample_counts),
            "approximate_total": sum(sample_counts) if sample_counts else None,
            "approximate_minimum_per_file": min(sample_counts) if sample_counts else None,
            "approximate_maximum_per_file": max(sample_counts) if sample_counts else None,
            "basis": "recognized embedded array lengths; values are estimates",
        },
        "timestamp_representations_observed": timestamp_representations,
        "value_representations_observed": value_representations,
        "sampling_interval_assessments": dict(sorted(interval_assessments.items())),
        "sampling_rate_comparison": {
            "assessment": cross_channel_sampling,
            "distinct_observed_intervals": [
                {"interval": interval, "unit": unit}
                for interval, unit in measured_intervals
            ],
            "basis": "bounded leading timestamp observations from each recognized channel file",
        },
        "missing_value_observations": dict(sorted(missing_observations.items())),
        "missing_value_evidence_scope": (
            "NaT in recognized datetime arrays and NaN in recognized floating-point arrays; "
            "undocumented numeric sentinels are not interpreted"
        ),
    }


def _telecommand_summary(
    archives: Sequence[JsonObject],
    tables: Sequence[JsonObject],
    unclassified_files: Sequence[JsonObject],
) -> JsonObject:
    definition_tables = [table for table in tables if "!" not in str(table.get("path", ""))]
    execution_tables = [table for table in tables if "!" in str(table.get("path", ""))]
    definition_count = None
    if definition_tables:
        definition_count = sum(int(table.get("row_count", 0)) for table in definition_tables)
    priority_fields = sorted(
        {
            column
            for table in definition_tables
            for column in table.get("column_names", [])
            if _tokens(column) & {"impact", "priority"}
        }
    )
    pickle_execution_files = [
        item for item in unclassified_files if _archive_role(str(item.get("path", ""))) == "telecommands"
    ]
    execution_files = pickle_execution_files + _public_tables(execution_tables)
    execution_count = sum(int(table.get("row_count", 0)) for table in execution_tables)
    execution_count += sum(
        int(item.get("row_count", 0))
        for item in pickle_execution_files
        if isinstance(item.get("row_count"), int)
    )
    execution_count_is_estimate = any(
        bool(table.get("row_count_is_estimate")) for table in execution_tables
    )
    execution_count_is_estimate = execution_count_is_estimate or any(
        bool(item.get("row_count_is_estimate")) for item in pickle_execution_files
    )
    timestamp_observations = [
        {
            "path": table["path"],
            "candidates": _timestamp_candidates(
                table.get("column_names", []),
                table.get("inferred_data_types", {}),
                table.get("_sample_values", {}),
            ),
        }
        for table in execution_tables
    ]
    timestamp_representations = sorted(
        {
            candidate["representation"]
            for observation in timestamp_observations
            for candidate in observation["candidates"]
        }
        | {
            str(representation)
            for item in pickle_execution_files
            for representation in item.get("timestamp_representation", {}).get(
                "representations", []
            )
        }
    )
    value_representations = sorted(
        {
            str(representation)
            for item in pickle_execution_files
            for representation in item.get("value_representation", {}).get(
                "representations", []
            )
        }
    )
    return {
        "definition_count": definition_count,
        "definition_tables": _public_tables(definition_tables),
        "definition_fields_matching_priority_or_impact": priority_fields,
        "execution_archive_count": len(archives),
        "execution_archive_identifiers": sorted(
            _archive_identifier(item["path"]) for item in archives
        ),
        "execution_record_formats": _archive_format_counts(archives),
        "serialization_formats_observed": dict(
            sorted(
                Counter(
                    str(item.get("format", "unresolved"))
                    for item in pickle_execution_files
                ).items()
            )
        ),
        "object_type_symbols_observed": sorted(
            {
                str(symbol)
                for item in pickle_execution_files
                for symbol in item.get("object_type_symbols_observed", [])
            }
        ),
        "execution_archives": list(archives),
        "execution_files": execution_files,
        "approximate_execution_record_count": execution_count or None,
        "execution_record_count_is_estimate": execution_count_is_estimate,
        "value_representations_observed": value_representations,
        "timestamp_representation": {
            "representations_observed": timestamp_representations,
            "files_with_candidates": sum(
                bool(observation["candidates"]) for observation in timestamp_observations
            )
            + sum(
                item.get("timestamp_representation", {}).get("status") == "observed"
                for item in pickle_execution_files
            ),
            "basis": "observed execution-record values; units and operational semantics unresolved",
        },
    }


def _label_summary(tables: Sequence[JsonObject]) -> JsonObject:
    return {
        "tables": _public_tables(tables),
        "field_candidates": {
            str(table["path"]): _table_field_candidates(table) for table in tables
        },
        "observed_category_or_type_values": _observed_category_values(tables),
        "semantic_interpretation": (
            "Literal fields and values are reported; scientific semantics remain unresolved "
            "unless supplied by authoritative documentation."
        ),
    }


def _build_dataset_profile_from_archives(
    archive_path: str | os.PathLike[str],
    extracted_root: str | os.PathLike[str],
) -> JsonObject:
    """Build a recursive, JSON-serializable profile of an extracted dataset."""
    root = _as_path(extracted_root)
    if not root.exists():
        raise FileNotFoundError(f"Extracted dataset root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Extracted dataset root is not a directory: {root}")

    collector = _new_collector()
    extracted = _scan_extracted_files(root, collector)
    nested_archives = collector["nested_archives"]
    telemetry_archives = [
        archive for archive in nested_archives if _archive_role(str(archive["path"])) == "telemetry"
    ]
    telecommand_archives = [
        archive
        for archive in nested_archives
        if _archive_role(str(archive["path"])) == "telecommands"
    ]
    telemetry = _telemetry_summary(
        telemetry_archives,
        collector["telemetry_channels"],
    )
    telecommands = _telecommand_summary(
        telecommand_archives,
        collector["telecommand_tables"],
        collector["unclassified_files"],
    )
    labels = _label_summary(collector["label_tables"])
    unresolved = list(dict.fromkeys(collector["unresolved_questions"]))
    if not collector["telemetry_channels"]:
        unresolved.append(
            "Telemetry member schema, timestamp/value representation, sampling intervals, and "
            "missing-value encoding were not resolved from recognized tabular formats."
        )
    if telecommand_archives:
        unresolved.append(
            "The meaning of observed telecommand execution values and Priority requires "
            "authoritative documentation."
        )
    if collector["telemetry_channels"]:
        unresolved.extend(
            [
                "The mission time standard and timezone semantics of observed datetime64 "
                "indexes require authoritative documentation.",
                "Missing-value sentinels other than NumPy NaN and NaT remain unresolved.",
                "The cause of varying timestamp spacing is unresolved.",
            ]
        )
    metadata_columns = {
        str(column)
        for table in collector["metadata_tables"]
        for column in table.get("column_names", [])
    }
    if "Target" in metadata_columns:
        unresolved.append(
            "The semantic meaning of the channels.csv Target field remains unresolved."
        )
    observed_categories = {
        value
        for values in labels.get("observed_category_or_type_values", {}).values()
        for value in values
    }
    if "Rare Event" in observed_categories:
        unresolved.append(
            "Whether the literal Rare Event category is identical to the project's "
            "rare-nominal concept remains unresolved."
        )
    if collector["label_tables"]:
        unresolved.append(
            "Event interval endpoint semantics and multi-channel row interpretation remain "
            "unresolved."
        )
    unresolved.append(
        "The authoritative dataset release, source, license, and checksum are not established "
        "by structural inspection alone."
    )
    unresolved = list(dict.fromkeys(unresolved))

    return {
        "profile_version": 1,
        "archive": inspect_zip_archive(archive_path),
        "extracted": extracted,
        "metadata_tables": _public_tables(collector["metadata_tables"]),
        "telemetry": telemetry,
        "telecommands": telecommands,
        "labels": labels,
        "unresolved_questions": unresolved,
    }


def _write_text_atomic(path: Path, text: str) -> None:
    resolved_path = path.resolve(strict=False)
    if _is_in_data_raw(resolved_path):
        raise ValueError(f"Refusing to write inside immutable data/raw: {resolved_path}")
    path = resolved_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except PermissionError:
        # Windows can deny replace/truncate while another process has a mapped read section.
        # Preserve the mapped file size and pad with JSON/Markdown-safe whitespace instead.
        try:
            source_size = temporary_path.stat().st_size
            target_size = path.stat().st_size
            if source_size > target_size:
                raise PermissionError(
                    "Destination is locked and the replacement is larger; close readers of "
                    f"{path} and retry"
                )
            with temporary_path.open("rb") as source_handle, path.open("r+b") as target_handle:
                target_handle.seek(0)
                shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
                remaining = target_size - source_size
                padding = b" " * min(1024 * 1024, remaining)
                while remaining:
                    chunk = padding[:remaining]
                    target_handle.write(chunk)
                    remaining -= len(chunk)
        finally:
            temporary_path.unlink(missing_ok=True)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_profile_json_atomic(profile: JsonObject, path: str | os.PathLike[str]) -> None:
    """Write a dataset profile as deterministic, human-inspectable JSON."""
    output_path = _as_path(path)
    serialized = json.dumps(profile, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _write_text_atomic(output_path, serialized)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unresolved"
    return f"{value:,} bytes"


def _legacy_markdown_cell(value: Any) -> str:
    if value is None:
        return "unresolved"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _legacy_render_table_profile(table: JsonObject) -> list[str]:
    lines = [
        f'### `{table["path"]}`',
        "",
        f'- Rows: {table.get("row_count", "unresolved")}'
        + (" (estimated)" if table.get("row_count_is_estimate") else ""),
        f'- Size: {_format_bytes(table.get("size_bytes"))}',
        f'- Columns: {", ".join(f"`{column}`" for column in table.get("column_names", []))}',
        f'- Inferred types: {_markdown_cell(table.get("inferred_data_types", {}))}',
        f'- Null counts: {_markdown_cell(table.get("null_counts", {}))}',
    ]
    examples = table.get("example_rows", [])[:MAX_PROFILE_EXAMPLE_ROWS]
    if examples:
        columns = table.get("column_names", [])
        lines.extend(["", "Example rows (maximum 5):", ""])
        lines.append("| " + " | ".join(_markdown_cell(column) for column in columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in examples:
            lines.append(
                "| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |"
            )
    lines.append("")
    return lines


def _render_archive_profile_markdown(profile: JsonObject) -> str:
    """Render a concise Markdown report without raw telemetry examples."""
    archive = profile["archive"]
    extracted = profile["extracted"]
    telemetry = profile["telemetry"]
    telecommands = profile["telecommands"]
    labels = profile["labels"]
    lines = [
        "# ESA Mission 1 Data Profile",
        "",
        "This report records observed file and table facts. It does not assign scientific "
        "meaning to ambiguous fields.",
        "",
        "## Archive",
        "",
        f'- Filename: `{archive["filename"]}`',
        f'- Archive size: {_format_bytes(archive.get("size_bytes"))}',
        f'- Member count: {archive.get("member_count")}',
        f'- Member extensions: {_markdown_cell(archive.get("file_extensions", {}))}',
        f'- Uncompressed size estimate: {_format_bytes(archive.get("uncompressed_size_bytes"))}',
        f'- Top-level structure: {_markdown_cell(archive.get("top_level_structure", []))}',
        "",
        "## Extracted structure",
        "",
        f'- Root: `{extracted.get("root", extracted.get("destination"))}`',
        f'- Files: {extracted.get("file_count", len(extracted.get("extracted_files", [])))}',
        f'- Extracted size: {_format_bytes(extracted.get("size_bytes", extracted.get("extracted_size_bytes")))}',
        f'- Top-level structure: {_markdown_cell(extracted.get("top_level_structure", []))}',
        "",
        "## Metadata tables",
        "",
    ]
    for table in profile.get("metadata_tables", []):
        lines.extend(_render_table_profile(table))

    lines.extend(
        [
            "## Telemetry/channel storage",
            "",
            f'- Channel archives: {telemetry.get("channel_file_count")}',
            f'- Channel identifiers: {_markdown_cell(telemetry.get("channel_identifiers", []))}',
            f'- Inner member extensions: {_markdown_cell(telemetry.get("inner_file_formats", {}))}',
            f'- Serialization formats observed: {_markdown_cell(telemetry.get("serialization_formats_observed", {}))}',
            f'- Object-type symbols observed without deserialization: {_markdown_cell(telemetry.get("object_type_symbols_observed", []))}',
            f'- Compressed size: {_format_bytes(telemetry.get("compressed_size_bytes"))}',
            f'- Uncompressed size: {_format_bytes(telemetry.get("uncompressed_size_bytes"))}',
            f'- Approximate sample-count summary: {_markdown_cell(telemetry.get("sample_count_summary", {}))}',
            f'- Timestamp representations observed: {_markdown_cell(telemetry.get("timestamp_representations_observed", []))}',
            f'- Value representations observed: {_markdown_cell(telemetry.get("value_representations_observed", []))}',
            f'- Sampling interval assessments: {_markdown_cell(telemetry.get("sampling_interval_assessments", {}))}',
            f'- Cross-channel sampling comparison: {_markdown_cell(telemetry.get("sampling_rate_comparison", {}))}',
            f'- Missing-value observations: {_markdown_cell(telemetry.get("missing_value_observations", {}))}',
            f'- Missing-value evidence scope: {telemetry.get("missing_value_evidence_scope")}',
            "",
            "Raw telemetry example rows are intentionally omitted.",
            "",
            "## Telecommands",
            "",
            f'- Definitions: {telecommands.get("definition_count")}',
            f'- Execution archives: {telecommands.get("execution_archive_count")}',
            f'- Execution member extensions: {_markdown_cell(telecommands.get("execution_record_formats", {}))}',
            f'- Serialization formats observed: {_markdown_cell(telecommands.get("serialization_formats_observed", {}))}',
            f'- Object-type symbols observed without deserialization: {_markdown_cell(telecommands.get("object_type_symbols_observed", []))}',
            f'- Value representations observed: {_markdown_cell(telecommands.get("value_representations_observed", []))}',
            f'- Priority/impact-like fields observed: {_markdown_cell(telecommands.get("definition_fields_matching_priority_or_impact", []))}',
            f'- Approximate execution records: {telecommands.get("approximate_execution_record_count")} (estimated from embedded array lengths)',
            f'- Timestamp representation: {_markdown_cell(telecommands.get("timestamp_representation"))}',
            "",
        ]
    )
    for table in telecommands.get("definition_tables", []):
        lines.extend(_render_table_profile(table))

    lines.extend(["## Event labels", ""])
    for table in labels.get("tables", []):
        lines.extend(_render_table_profile(table))
    lines.extend(
        [
            f'- Candidate fields: {_markdown_cell(labels.get("field_candidates", {}))}',
            f'- Observed category/type values: {_markdown_cell(labels.get("observed_category_or_type_values", {}))}',
            f'- Interpretation boundary: {labels.get("semantic_interpretation")}',
            "",
            "## Unresolved semantic questions",
            "",
        ]
    )
    unresolved = profile.get("unresolved_questions", [])
    lines.extend(f"- {question}" for question in unresolved)
    if not unresolved:
        lines.append("- None recorded by the structural inspector.")
    return "\n".join(lines).rstrip() + "\n"


def _write_profile_markdown_atomic(
    profile: JsonObject, path: str | os.PathLike[str]
) -> None:
    """Write a human-readable dataset profile report."""
    _write_text_atomic(_as_path(path), render_profile_markdown(profile))


def _aggregate_sampling(channels: Sequence[JsonObject]) -> JsonObject:
    if not channels:
        return {"assessment": "unresolved", "reason": "no channel files were identified"}
    intervals: list[tuple[float, str]] = []
    unresolved_count = 0
    for channel in channels:
        sampling = channel.get("sampling_interval", {})
        if sampling.get("assessment") == "varying":
            return {
                "assessment": "varying",
                "basis": f"varying intervals measured within {channel['path']}",
            }
        interval = sampling.get("observed_interval")
        unit = sampling.get("unit")
        if sampling.get("assessment") == "uniform" and isinstance(interval, (int, float)):
            intervals.append((float(interval), str(unit)))
        else:
            unresolved_count += 1
    if unresolved_count:
        return {
            "assessment": "unresolved",
            "measured_channel_count": len(intervals),
            "unresolved_channel_count": unresolved_count,
            "reason": "sampling intervals could not be measured for every identified channel",
        }
    if not intervals:
        return {"assessment": "unresolved", "reason": "no sampling intervals were measured"}
    reference_value, reference_unit = intervals[0]
    same_unit = all(unit == reference_unit for _, unit in intervals)
    same_interval = all(
        math.isclose(value, reference_value, rel_tol=1e-9, abs_tol=1e-12)
        for value, _ in intervals
    )
    if same_unit and same_interval:
        return {
            "assessment": "uniform",
            "observed_interval": reference_value,
            "unit": reference_unit,
            "measured_channel_count": len(intervals),
        }
    return {
        "assessment": "varying",
        "measured_channel_count": len(intervals),
        "observed_intervals": [
            {"interval": value, "unit": unit} for value, unit in sorted(set(intervals))
        ],
    }


def _build_telemetry_section(channels: list[JsonObject]) -> JsonObject:
    formats = Counter(str(channel["format"]) for channel in channels)
    identifiers = sorted({str(channel["identifier"]) for channel in channels})
    missing_observations = [channel.get("missing_values_observed") for channel in channels]
    if any(value is True for value in missing_observations):
        missing_summary: bool | None = True
    elif channels and all(value is False for value in missing_observations):
        missing_summary = False
    else:
        missing_summary = None
    compressed_sizes = [
        int(channel["compressed_size_bytes"])
        for channel in channels
        if isinstance(channel.get("compressed_size_bytes"), int)
    ]
    return {
        "storage_formats": dict(sorted(formats.items())),
        "channel_file_count": len(channels),
        "channel_identifier_count": len(identifiers),
        "channel_identifiers": identifiers,
        "uncompressed_size_bytes": sum(
            int(channel.get("uncompressed_size_bytes", 0)) for channel in channels
        ),
        "compressed_size_bytes": sum(compressed_sizes) if compressed_sizes else None,
        "compressed_size_file_count": len(compressed_sizes),
        "sampling_rate_uniformity": _aggregate_sampling(channels),
        "missing_values_observed": missing_summary,
        "missing_value_note": (
            "False means no empty fields were observed in the scanned rows; it does not prove "
            "that undocumented missing-value sentinels are absent."
        ),
        "channels": channels,
    }


def _execution_like(path: str) -> bool:
    return bool(
        _tokens(path)
        & {"executed", "execution", "executions", "history", "log", "occurrence", "records"}
    )


def _build_telecommand_section(
    tables: list[JsonObject], unresolved_questions: list[str]
) -> JsonObject:
    definitions: list[JsonObject] = []
    executions: list[JsonObject] = []
    schemas: list[JsonObject] = []
    timestamp_observations: list[JsonObject] = []
    priority_or_impact_fields: list[JsonObject] = []
    type_field_candidates: list[JsonObject] = []
    for table in tables:
        observations = table.get("_sample_values", {})
        columns = table["column_names"]
        timestamp_candidates = _timestamp_candidates(
            columns,
            table["inferred_data_types"],
            observations,
        )
        if timestamp_candidates:
            timestamp_observations.append(
                {"path": table["path"], "candidates": timestamp_candidates}
            )
        priority_columns = [
            column
            for column in columns
            if _tokens(column) & {"effect", "impact", "priority", "severity"}
        ]
        priority_or_impact_fields.extend(
            {"path": table["path"], "column": column} for column in priority_columns
        )
        candidate_types = [
            column
            for column in columns
            if _tokens(column) & {"command", "identifier", "name", "telecommand", "type"}
        ]
        if candidate_types:
            type_field_candidates.append(
                {"path": table["path"], "columns": candidate_types, "basis": "column names"}
            )
        schemas.append(
            {
                "path": table["path"],
                "column_names": columns,
                "inferred_data_types": table["inferred_data_types"],
            }
        )
        cleaned = _strip_internal_profile_fields(table)
        if _execution_like(str(table["path"])):
            executions.append(cleaned)
        else:
            definitions.append(cleaned)

    if tables:
        unresolved_questions.append(
            "Confirm which telecommand table rows represent distinct telecommand types; path "
            "and column names alone do not establish that semantic relationship."
        )
    exact_definition_rows = all(not table["row_count_is_estimate"] for table in definitions)
    exact_execution_rows = all(not table["row_count_is_estimate"] for table in executions)
    return {
        "metadata_schema": schemas,
        "definition_tables": definitions,
        "execution_record_tables": executions,
        "definition_table_count": len(definitions),
        "execution_record_file_count": len(executions),
        "definition_row_count": (
            sum(int(table["row_count"]) for table in definitions) if exact_definition_rows else None
        ),
        "execution_record_row_count": (
            sum(int(table["row_count"]) for table in executions) if exact_execution_rows else None
        ),
        "execution_record_formats": sorted(
            {
                PurePosixPath(str(table["path"])).suffix.lower() or "[no extension]"
                for table in executions
            }
        ),
        "number_of_telecommand_types": None,
        "type_field_candidates": type_field_candidates,
        "timestamp_representation": timestamp_observations,
        "priority_or_impact_fields": priority_or_impact_fields,
    }


def _build_label_section(tables: list[JsonObject], unresolved_questions: list[str]) -> JsonObject:
    schemas: list[JsonObject] = []
    field_candidates: list[JsonObject] = []
    representation_observations: list[JsonObject] = []
    cleaned_tables: list[JsonObject] = []
    groups = {
        "event_identifier": {"event", "id", "identifier"},
        "start_timestamp": {"begin", "from", "start"},
        "end_timestamp": {"end", "stop", "to", "until"},
        "channel_reference": {"channel", "channels", "signal", "telemetry"},
        "category_or_type": {"category", "class", "kind", "label", "type"},
        "anomaly_or_rare_nominal": {"anomaly", "nominal", "rare"},
    }
    for table in tables:
        columns = table["column_names"]
        observations = table.get("_sample_values", {})
        candidates = _candidate_fields(columns, groups)
        field_candidates.append(
            {"path": table["path"], "candidates_by_header": candidates}
        )
        representation_columns = sorted(
            set(candidates["category_or_type"] + candidates["anomaly_or_rare_nominal"])
        )
        if representation_columns:
            representation_observations.append(
                {
                    "path": table["path"],
                    "observed_values": {
                        column: observations.get(column, []) for column in representation_columns
                    },
                    "scope": "bounded observed values; semantics unresolved",
                }
            )
        schemas.append(
            {
                "path": table["path"],
                "column_names": columns,
                "inferred_data_types": table["inferred_data_types"],
            }
        )
        cleaned_tables.append(_strip_internal_profile_fields(table))
    if tables:
        unresolved_questions.append(
            "Confirm event-label column semantics, including anomaly versus rare-nominal "
            "encoding, from authoritative dataset documentation."
        )
    exact_rows = all(not table["row_count_is_estimate"] for table in cleaned_tables)
    return {
        "tables": cleaned_tables,
        "table_count": len(cleaned_tables),
        "row_count": (
            sum(int(table["row_count"]) for table in cleaned_tables) if exact_rows else None
        ),
        "schemas": schemas,
        "field_candidates": field_candidates,
        "anomaly_or_rare_nominal_representation": representation_observations,
        "semantic_status": "unresolved" if tables else "not found",
    }


def _deduplicate_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_dataset_profile(
    archive_path: str | os.PathLike[str],
    extracted_root: str | os.PathLike[str],
) -> JsonObject:
    """Build a structural profile from an archive and its extracted dataset tree."""
    return _build_dataset_profile_from_archives(archive_path, extracted_root)


def write_profile_json(profile: JsonObject, path: str | os.PathLike[str]) -> None:
    """Write a dataset profile as deterministic, human-diffable JSON."""
    _write_profile_json_atomic(profile, path)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unresolved"
    size = float(size_bytes)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{int(size)} B" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _render_table_profile(table: JsonObject) -> list[str]:
    lines = [f"### `{table['path']}`", ""]
    lines.extend(
        [
            f"- Rows: {table['row_count']}"
            + (" (estimated)" if table.get("row_count_is_estimate") else ""),
            f"- Size: {_format_size(table.get('size_bytes'))}",
            f"- Columns: {', '.join(f'`{column}`' for column in table['column_names']) or 'none'}",
            "",
            "| Column | Inferred type | Null count |",
            "|---|---:|---:|",
        ]
    )
    for column in table["column_names"]:
        lines.append(
            f"| {_markdown_cell(column)} | "
            f"{_markdown_cell(table['inferred_data_types'].get(column, 'unresolved'))} | "
            f"{_markdown_cell(table['null_counts'].get(column, 'unresolved'))} |"
        )
    examples = table.get("example_rows", [])[:MAX_PROFILE_EXAMPLE_ROWS]
    if examples:
        lines.extend(
            [
                "",
                "Example rows (maximum 5):",
                "",
                "```json",
                json.dumps(examples, indent=2, ensure_ascii=False),
                "```",
            ]
        )
    lines.append("")
    return lines


def render_profile_markdown(profile: JsonObject) -> str:
    """Render a concise report without embedding raw telemetry examples."""
    return _render_archive_profile_markdown(profile)


def write_profile_markdown(profile: JsonObject, path: str | os.PathLike[str]) -> None:
    """Render and write the human-readable dataset profile."""
    _write_profile_markdown_atomic(profile, path)
