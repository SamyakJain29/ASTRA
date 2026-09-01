"""Trusted, reproducible preparation of the verified ESA Mission-1 subset.

Mission-1 channel and telecommand payloads are pandas protocol-5 pickles. Pickle
is executable data, so this module intentionally exposes no general pickle
loader. The private loader can only receive payload descriptors created after
the configured raw archive and the corresponding extracted member have been
verified against the Phase 1.1 profile and pinned SHA-256 and MD5 digests.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import math
import os
import pickle
import re
import subprocess
import sys
import tempfile
import warnings
import zipfile
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

LOGGER = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^(?P<kind>channel|telecommand)_(?P<number>\d+)$")
_COPY_BUFFER_SIZE = 8 * 1024 * 1024


class PreparationError(RuntimeError):
    """Raised when trusted preparation cannot safely continue."""


@dataclass(frozen=True)
class _VerifiedMissionPickle:
    """A payload admitted through the Mission-1 archive trust boundary."""

    identifier: str
    archive_path: Path
    archive_size_bytes: int
    archive_crc32: str
    member_name: str
    compressed_size_bytes: int
    uncompressed_size_bytes: int
    member_crc32: str


@dataclass(frozen=True)
class _ArchiveVerification:
    """Measured and Phase-1.1-checked raw archive facts."""

    archive_path: Path
    archive_sha256: str
    archive_md5: str
    archive_size_bytes: int
    archive_mtime_ns: int
    member_count: int
    file_count: int
    directory_count: int
    uncompressed_size_bytes: int
    compressed_member_size_bytes: int
    members: Mapping[str, zipfile.ZipInfo]


def _identifier_sort_key(identifier: str) -> tuple[str, int, str]:
    match = _IDENTIFIER_PATTERN.fullmatch(str(identifier))
    if match is None:
        return (str(identifier), sys.maxsize, str(identifier))
    return (match.group("kind"), int(match.group("number")), str(identifier))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    """Return a strict-JSON-compatible representation of common scalar values."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _atomic_replace(temporary_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(temporary_path, output_path)
    except PermissionError as error:
        raise PreparationError(
            f"Could not replace {output_path}; close programs using the file and retry."
        ) from error


def write_json_deterministic(payload: Mapping[str, Any], output_path: Path) -> None:
    """Write strict, sorted, UTF-8 JSON through an atomic sibling replacement."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        _json_value(payload),
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=output_path.parent,
        encoding="utf-8",
        newline="\n",
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    ) as stream:
        stream.write(serialized)
        stream.write("\n")
        temporary_path = Path(stream.name)
    try:
        _atomic_replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_text_atomic(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=output_path.parent,
        encoding="utf-8",
        newline="\n",
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    ) as stream:
        stream.write(text.rstrip())
        stream.write("\n")
        temporary_path = Path(stream.name)
    try:
        _atomic_replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_digests(path: Path) -> tuple[str, str]:
    """Compute SHA-256 and MD5 together so the multi-gigabyte archive is read once."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()  # noqa: S324 - dataset identity, not cryptographic security
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_BUFFER_SIZE):
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest()


def _crc32_file(path: Path) -> int:
    checksum = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_BUFFER_SIZE):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def _resolve_project_path(project_root: Path, configured_path: str | Path) -> Path:
    path = Path(configured_path)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_within(path: Path, parent: Path, description: str) -> Path:
    absolute_path = path.absolute()
    absolute_parent = parent.absolute()
    current = absolute_path
    while _is_relative_to(current, absolute_parent):
        if current.is_symlink():
            raise PreparationError(f"{description} must not traverse a symbolic link: {current}")
        if current == absolute_parent:
            break
        current = current.parent
    resolved_path = path.resolve(strict=True)
    resolved_parent = parent.resolve(strict=True)
    if not _is_relative_to(resolved_path, resolved_parent):
        raise PreparationError(f"{description} escapes verified root {resolved_parent}: {path}")
    return resolved_path


def _require_output_outside_raw(path: Path, raw_root: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_raw = raw_root.resolve(strict=False)
    if _is_relative_to(resolved_path, resolved_raw):
        raise PreparationError(f"Refusing to write inside immutable raw data: {path}")


def _load_yaml_config(config_path: Path) -> tuple[dict[str, Any], Path]:
    config_path = config_path.resolve(strict=True)
    with config_path.open(encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    if not isinstance(loaded, dict):
        raise PreparationError(f"Expected a mapping in {config_path}")
    project_root = config_path.parent.parent
    return loaded, project_root


def _load_phase11_archive_facts(profile_path: Path) -> Mapping[str, Any]:
    try:
        with profile_path.open(encoding="utf-8") as stream:
            profile = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise PreparationError(f"Could not read Phase 1.1 profile {profile_path}: {error}") from error
    archive = profile.get("archive")
    if not isinstance(archive, dict):
        raise PreparationError(f"Phase 1.1 profile has no archive mapping: {profile_path}")
    return archive


def _verify_source_archive(
    archive_path: Path,
    archive_config: Mapping[str, Any],
    phase11_archive: Mapping[str, Any],
) -> _ArchiveVerification:
    if not archive_path.is_file():
        raise PreparationError(f"Mission-1 archive not found at expected path: {archive_path}")
    if archive_path.name != archive_config.get("expected_filename"):
        raise PreparationError(
            f"Archive filename {archive_path.name!r} does not match configured identity."
        )

    stat_before = archive_path.stat()
    expected_size = int(archive_config["expected_size_bytes"])
    if stat_before.st_size != expected_size:
        raise PreparationError(
            f"Archive size mismatch: expected {expected_size}, measured {stat_before.st_size}."
        )
    if phase11_archive.get("filename") != archive_path.name:
        raise PreparationError("Archive filename does not match the Phase 1.1 profile.")
    if int(phase11_archive.get("size_bytes", -1)) != stat_before.st_size:
        raise PreparationError("Archive size does not match the Phase 1.1 profile.")

    LOGGER.info("Computing SHA-256 and MD5 for immutable source archive %s", archive_path)
    measured_sha256, measured_md5 = _archive_digests(archive_path)
    expected_sha256 = str(archive_config["expected_sha256"]).lower()
    if measured_sha256 != expected_sha256:
        raise PreparationError(
            f"Archive SHA-256 mismatch: expected {expected_sha256}, measured {measured_sha256}."
        )
    expected_md5 = str(archive_config["expected_md5"]).lower()
    if measured_md5 != expected_md5:
        raise PreparationError(
            f"Archive MD5 mismatch: expected {expected_md5}, measured {measured_md5}."
        )

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
    files = [info for info in infos if not info.is_dir()]
    directories = [info for info in infos if info.is_dir()]
    uncompressed_size = sum(info.file_size for info in files)
    compressed_size = sum(info.compress_size for info in files)
    expected_member_count = int(phase11_archive.get("member_count", -1))
    expected_uncompressed = int(phase11_archive.get("uncompressed_size_bytes", -1))
    if len(infos) != expected_member_count:
        raise PreparationError(
            "Archive member count does not match the Phase 1.1 profile: "
            f"expected {expected_member_count}, measured {len(infos)}."
        )
    if uncompressed_size != expected_uncompressed:
        raise PreparationError(
            "Archive uncompressed size does not match the Phase 1.1 profile: "
            f"expected {expected_uncompressed}, measured {uncompressed_size}."
        )
    stat_after = archive_path.stat()
    if (
        stat_after.st_size != stat_before.st_size
        or stat_after.st_mtime_ns != stat_before.st_mtime_ns
    ):
        raise PreparationError("Source archive changed while its identity was being verified.")
    members = {PurePosixPath(info.filename).as_posix(): info for info in infos}
    return _ArchiveVerification(
        archive_path=archive_path,
        archive_sha256=measured_sha256,
        archive_md5=measured_md5,
        archive_size_bytes=stat_before.st_size,
        archive_mtime_ns=stat_before.st_mtime_ns,
        member_count=len(infos),
        file_count=len(files),
        directory_count=len(directories),
        uncompressed_size_bytes=uncompressed_size,
        compressed_member_size_bytes=compressed_size,
        members=members,
    )


def _outer_member_name(dataset_directory: str, relative_path: Path) -> str:
    return PurePosixPath(dataset_directory, *relative_path.parts).as_posix()


def _verify_extracted_member(
    path: Path,
    *,
    dataset_root: Path,
    dataset_directory: str,
    archive_verification: _ArchiveVerification,
) -> zipfile.ZipInfo:
    path = _require_within(path, dataset_root, "Extracted Mission-1 member")
    if not path.is_file():
        raise PreparationError(f"Expected extracted Mission-1 file: {path}")
    relative_path = path.relative_to(dataset_root)
    outer_name = _outer_member_name(dataset_directory, relative_path)
    outer_info = archive_verification.members.get(outer_name)
    if outer_info is None or outer_info.is_dir():
        raise PreparationError(f"Extracted file is not present in verified archive: {outer_name}")
    measured_size = path.stat().st_size
    if measured_size != outer_info.file_size:
        raise PreparationError(
            f"Extracted file size mismatch for {outer_name}: "
            f"expected {outer_info.file_size}, measured {measured_size}."
        )
    measured_crc = _crc32_file(path)
    if measured_crc != outer_info.CRC:
        raise PreparationError(
            f"Extracted file CRC mismatch for {outer_name}: "
            f"expected {outer_info.CRC:08x}, measured {measured_crc:08x}."
        )
    return outer_info


def _read_verified_csv(
    path: Path,
    *,
    dataset_root: Path,
    dataset_directory: str,
    archive_verification: _ArchiveVerification,
) -> pd.DataFrame:
    _verify_extracted_member(
        path,
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=archive_verification,
    )
    return pd.read_csv(path, encoding="utf-8-sig")


def _discover_verified_pickles(
    directory: Path,
    *,
    expected_kind: str,
    allowed_identifiers: set[str],
    dataset_root: Path,
    dataset_directory: str,
    archive_verification: _ArchiveVerification,
) -> dict[str, _VerifiedMissionPickle]:
    directory = _require_within(directory, dataset_root, f"{expected_kind} directory")
    discovered: dict[str, _VerifiedMissionPickle] = {}
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix.lower() != ".zip":
            continue
        identifier_from_filename = path.stem
        if identifier_from_filename not in allowed_identifiers:
            continue
        outer_info = _verify_extracted_member(
            path,
            dataset_root=dataset_root,
            dataset_directory=dataset_directory,
            archive_verification=archive_verification,
        )
        try:
            with zipfile.ZipFile(path) as nested_archive:
                members = [info for info in nested_archive.infolist() if not info.is_dir()]
        except zipfile.BadZipFile as error:
            raise PreparationError(f"Invalid nested Mission-1 ZIP: {path}") from error
        if len(members) != 1:
            raise PreparationError(f"Expected exactly one payload in {path}; found {len(members)}.")
        info = members[0]
        member_path = PurePosixPath(info.filename)
        if member_path.is_absolute() or ".." in member_path.parts or len(member_path.parts) != 1:
            raise PreparationError(f"Unsafe or nested payload member in {path}: {info.filename}")
        identifier = member_path.name
        match = _IDENTIFIER_PATTERN.fullmatch(identifier)
        if match is None or match.group("kind") != expected_kind:
            raise PreparationError(f"Unexpected {expected_kind} payload identifier: {identifier}")
        if path.stem != identifier:
            raise PreparationError(
                f"Nested archive {path.name} does not match payload {identifier}."
            )
        if identifier not in allowed_identifiers:
            raise PreparationError(f"Unexpected selected payload identifier: {identifier}")
        if identifier in discovered:
            raise PreparationError(f"Duplicate payload identifier discovered: {identifier}")
        discovered[identifier] = _VerifiedMissionPickle(
            identifier=identifier,
            archive_path=path,
            archive_size_bytes=outer_info.file_size,
            archive_crc32=f"{outer_info.CRC:08x}",
            member_name=info.filename,
            compressed_size_bytes=info.compress_size,
            uncompressed_size_bytes=info.file_size,
            member_crc32=f"{info.CRC:08x}",
        )
    return discovered


def _load_verified_pickle(payload: _VerifiedMissionPickle) -> object:
    """Deserialize only a payload admitted through `_discover_verified_pickles`."""
    if payload.archive_path.stat().st_size != payload.archive_size_bytes:
        raise PreparationError(f"Nested archive size changed before load: {payload.identifier}")
    measured_crc = _crc32_file(payload.archive_path)
    if f"{measured_crc:08x}" != payload.archive_crc32:
        raise PreparationError(f"Nested archive CRC changed before load: {payload.identifier}")
    with zipfile.ZipFile(payload.archive_path) as archive:
        info = archive.getinfo(payload.member_name)
        if (
            info.file_size != payload.uncompressed_size_bytes
            or info.compress_size != payload.compressed_size_bytes
            or f"{info.CRC:08x}" != payload.member_crc32
        ):
            raise PreparationError(f"Nested payload changed before load: {payload.identifier}")
        with archive.open(info, "r") as stream:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                loaded = pickle.load(stream)  # noqa: S301 - pinned archive trust boundary
            if stream.read(1):
                raise PreparationError(f"Trailing bytes after pickle: {payload.identifier}")
    for warning in caught:
        LOGGER.debug("Deserialization warning for %s: %s", payload.identifier, warning.message)
    return loaded


def filter_channel_metadata(
    metadata: pd.DataFrame,
    numeric_ids: Sequence[int],
) -> pd.DataFrame:
    """Select exact `channel_N` metadata rows using configured numeric IDs."""
    if "Channel" not in metadata.columns:
        raise ValueError("Channel metadata must contain a 'Channel' column.")
    expected = {f"channel_{int(number)}" for number in numeric_ids}
    if len(expected) != len(numeric_ids):
        raise ValueError("Configured channel numeric IDs must be unique.")
    selected = metadata.loc[metadata["Channel"].isin(expected)].copy()
    found = set(selected["Channel"].astype(str))
    missing = sorted(expected - found, key=_identifier_sort_key)
    if missing:
        raise ValueError(f"Configured channels are absent from metadata: {missing}")
    if selected["Channel"].duplicated().any():
        raise ValueError("Channel metadata contains duplicate selected identifiers.")
    return selected


def validate_esa_telemetry_frame(
    frame: object,
    expected_identifier: str,
) -> pd.DataFrame:
    """Validate the exact structure observed for trusted Mission-1 telemetry."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{expected_identifier} payload is not a pandas DataFrame.")
    if frame.columns.tolist() != [expected_identifier]:
        raise ValueError(
            f"{expected_identifier} must have one same-named column; got {frame.columns.tolist()}."
        )
    if frame[expected_identifier].dtype != np.dtype("float32"):
        raise ValueError(
            f"{expected_identifier} values must be float32; got {frame[expected_identifier].dtype}."
        )
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{expected_identifier} must use a pandas DatetimeIndex.")
    if frame.index.name != "datetime":
        raise ValueError(f"{expected_identifier} index name must be 'datetime'.")
    if frame.index.dtype != np.dtype("datetime64[ns]") or frame.index.tz is not None:
        raise ValueError(f"{expected_identifier} timestamps must be timezone-naive datetime64[ns].")
    if frame.index.hasnans:
        raise ValueError(f"{expected_identifier} timestamps contain NaT.")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError(f"{expected_identifier} timestamps must be strictly increasing and unique.")
    return frame


def _validate_esa_telecommand_frame(
    frame: object,
    expected_identifier: str,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{expected_identifier} payload is not a pandas DataFrame.")
    if frame.columns.tolist() != [expected_identifier]:
        raise ValueError(f"Unexpected telecommand columns for {expected_identifier}.")
    if frame[expected_identifier].dtype != np.dtype("uint8"):
        raise ValueError(f"{expected_identifier} execution values must be uint8.")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{expected_identifier} must use a pandas DatetimeIndex.")
    if frame.index.name is not None:
        raise ValueError(f"{expected_identifier} timestamp index must be unnamed.")
    if frame.index.dtype != np.dtype("datetime64[ns]") or frame.index.tz is not None:
        raise ValueError(f"{expected_identifier} timestamps must be timezone-naive datetime64[ns].")
    if frame.index.hasnans:
        raise ValueError(f"{expected_identifier} timestamps contain NaT.")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError(f"{expected_identifier} timestamps must be increasing and unique.")
    return frame


def _temporary_sibling(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(name)
    temporary_path.unlink()
    return temporary_path


def write_telemetry_parquet(
    frame: pd.DataFrame,
    *,
    channel_identifier: str,
    output_path: Path,
    row_group_size: int,
    compression: str = "zstd",
    write_statistics: bool = True,
) -> dict[str, Any]:
    """Write one verified channel without changing timestamps or float32 values."""
    validate_esa_telemetry_frame(frame, channel_identifier)
    if row_group_size < 1:
        raise ValueError("row_group_size must be positive.")
    output_path = Path(output_path)
    temporary_path = _temporary_sibling(output_path)
    dictionary_type = pa.dictionary(pa.int8(), pa.string())
    schema = pa.schema(
        [
            pa.field("timestamp", pa.timestamp("ns"), nullable=False),
            pa.field("value", pa.float32(), nullable=True),
            pa.field("channel", dictionary_type, nullable=False),
        ]
    )
    writer: pq.ParquetWriter | None = None
    try:
        writer = pq.ParquetWriter(
            temporary_path,
            schema,
            compression=compression,
            use_dictionary=["channel"],
            write_statistics=write_statistics,
        )
        timestamps = frame.index.asi8
        values = frame[channel_identifier].to_numpy(copy=False)
        dictionary = pa.array([channel_identifier], type=pa.string())
        for start in range(0, len(frame), row_group_size):
            stop = min(start + row_group_size, len(frame))
            indices = pa.array(np.zeros(stop - start, dtype=np.int8))
            channel_array = pa.DictionaryArray.from_arrays(indices, dictionary)
            table = pa.Table.from_arrays(
                [
                    pa.array(timestamps[start:stop], type=pa.timestamp("ns")),
                    pa.array(values[start:stop], type=pa.float32(), from_pandas=True),
                    channel_array,
                ],
                schema=schema,
            )
            writer.write_table(table, row_group_size=stop - start)
        writer.close()
        writer = None
        parquet_file = pq.ParquetFile(temporary_path)
        metadata = parquet_file.metadata
        parquet_file.close()
        if metadata.num_rows != len(frame):
            raise PreparationError(f"Parquet row-count validation failed for {channel_identifier}.")
        _atomic_replace(temporary_path, output_path)
    finally:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
    return {
        "path": output_path.as_posix(),
        "row_count": len(frame),
        "row_group_count": math.ceil(len(frame) / row_group_size) if len(frame) else 0,
        "schema": {
            "timestamp": "timestamp[ns]",
            "value": "float32",
            "channel": "dictionary<int8, string>",
        },
    }


def prepare_event_table(
    labels: pd.DataFrame,
    anomaly_types: pd.DataFrame,
    *,
    selected_channels: Sequence[str],
) -> pd.DataFrame:
    """Normalize selected-channel events while retaining their full channel context."""
    label_columns = {"ID", "Channel", "StartTime", "EndTime"}
    type_columns = {
        "ID",
        "Class",
        "Subclass",
        "Category",
        "Dimensionality",
        "Locality",
        "Length",
    }
    missing_labels = sorted(label_columns - set(labels.columns))
    missing_types = sorted(type_columns - set(anomaly_types.columns))
    if missing_labels or missing_types:
        raise ValueError(
            f"Event tables lack verified columns; labels={missing_labels}, types={missing_types}."
        )
    if anomaly_types["ID"].duplicated().any():
        raise ValueError("Anomaly type IDs must be unique for a many-to-one join.")
    selected_set = set(selected_channels)
    relevant_ids = set(labels.loc[labels["Channel"].isin(selected_set), "ID"])
    relevant = labels.loc[labels["ID"].isin(relevant_ids)].copy()
    merged = relevant.merge(
        anomaly_types[
            [
                "ID",
                "Class",
                "Subclass",
                "Category",
                "Dimensionality",
                "Locality",
                "Length",
            ]
        ],
        on="ID",
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if merged[["Class", "Subclass", "Category"]].isna().all(axis=1).any():
        missing_ids = sorted(set(merged.loc[merged["Category"].isna(), "ID"]))
        raise ValueError(f"Relevant labels lack anomaly-type definitions: {missing_ids}")

    start_timestamps = pd.to_datetime(merged["StartTime"], utc=True, errors="raise")
    end_timestamps = pd.to_datetime(merged["EndTime"], utc=True, errors="raise")
    if (end_timestamps < start_timestamps).any():
        raise ValueError("At least one event ends before it starts.")
    merged["is_selected_channel"] = merged["Channel"].isin(selected_set)
    selected_counts = (
        merged.loc[merged["is_selected_channel"]]
        .groupby("ID", sort=False)["Channel"]
        .nunique()
    )
    all_counts = merged.groupby("ID", sort=False)["Channel"].nunique()
    normalized = pd.DataFrame(
        {
            "event_id": merged["ID"].astype("string"),
            "channel": merged["Channel"].astype("string"),
            "start_timestamp": start_timestamps,
            "end_timestamp": end_timestamps,
            "source_start_time": merged["StartTime"].astype("string"),
            "source_end_time": merged["EndTime"].astype("string"),
            "category": merged["Category"].astype("string"),
            "class": merged["Class"].astype("string"),
            "subclass": merged["Subclass"].astype("string"),
            "dimensionality": merged["Dimensionality"].astype("string"),
            "locality": merged["Locality"].astype("string"),
            "length": merged["Length"].astype("string"),
            "is_selected_channel": merged["is_selected_channel"].astype(bool),
            "selected_channel_count": merged["ID"].map(selected_counts).astype("int32"),
            "all_channel_count": merged["ID"].map(all_counts).astype("int32"),
        }
    )
    normalized["is_multichannel"] = normalized["selected_channel_count"] >= 2
    normalized["duration_ns"] = (
        normalized["end_timestamp"] - normalized["start_timestamp"]
    ).astype("timedelta64[ns]").astype("int64")
    normalized["_event_number"] = (
        normalized["event_id"].str.extract(r"(\d+)$", expand=False).astype("Int64")
    )
    normalized["_channel_number"] = (
        normalized["channel"].str.extract(r"(\d+)$", expand=False).astype("Int64")
    )
    normalized.sort_values(
        ["_event_number", "event_id", "_channel_number", "channel", "start_timestamp"],
        kind="stable",
        inplace=True,
        na_position="last",
    )
    normalized.drop(columns=["_event_number", "_channel_number"], inplace=True)
    normalized.reset_index(drop=True, inplace=True)
    return normalized


def join_telecommand_metadata(
    executions: pd.DataFrame,
    definitions: pd.DataFrame,
) -> pd.DataFrame:
    """Join literal Priority metadata to normalized execution records."""
    required_execution = {"telecommand", "timestamp", "execution_value"}
    required_definition = {"Telecommand", "Priority"}
    if not required_execution.issubset(executions.columns):
        raise ValueError("Execution records lack required normalized columns.")
    if not required_definition.issubset(definitions.columns):
        raise ValueError("Telecommand definitions lack Telecommand or Priority.")
    if definitions["Telecommand"].duplicated().any():
        raise ValueError("Telecommand definitions contain duplicate identifiers.")
    joined = executions.merge(
        definitions[["Telecommand", "Priority"]],
        left_on="telecommand",
        right_on="Telecommand",
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if joined["Priority"].isna().any():
        raise ValueError("Execution records include undefined telecommands.")
    joined.rename(columns={"Priority": "priority"}, inplace=True)
    return joined[["telecommand", "timestamp", "execution_value", "priority"]]


def _write_dataframe_parquet_atomic(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    compression: str,
    row_group_size: int,
    write_statistics: bool,
) -> dict[str, Any]:
    temporary_path = _temporary_sibling(output_path)
    try:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        pq.write_table(
            table,
            temporary_path,
            compression=compression,
            row_group_size=row_group_size,
            write_statistics=write_statistics,
        )
        parquet_file = pq.ParquetFile(temporary_path)
        metadata = parquet_file.metadata
        parquet_file.close()
        if metadata.num_rows != len(frame):
            raise PreparationError(f"Parquet row-count validation failed for {output_path}.")
        _atomic_replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "path": output_path.as_posix(),
        "row_count": len(frame),
        "row_group_count": metadata.num_row_groups,
        "schema": {field.name: str(field.type) for field in table.schema},
    }


def _hash_datetime_index(index: pd.DatetimeIndex) -> str:
    digest = hashlib.sha256()
    values = index.asi8
    for start in range(0, len(values), 1_000_000):
        digest.update(memoryview(values[start : start + 1_000_000]).cast("B"))
    return digest.hexdigest()


def _interval_summary(index: pd.DatetimeIndex) -> dict[str, Any]:
    counts: Counter[int] = Counter()
    previous: int | None = None
    values = index.asi8
    for start in range(0, len(values), 1_000_000):
        chunk = values[start : start + 1_000_000]
        if not len(chunk):
            continue
        if previous is None:
            deltas = np.diff(chunk)
        else:
            deltas = np.diff(np.concatenate((np.array([previous]), chunk)))
        unique, frequencies = np.unique(deltas, return_counts=True)
        counts.update(
            {
                int(delta): int(count)
                for delta, count in zip(unique, frequencies, strict=True)
            }
        )
        previous = int(chunk[-1])
    if not counts:
        return {
            "interval_count": 0,
            "distinct_interval_count": 0,
            "is_uniform": None,
            "minimum_interval_ns": None,
            "maximum_interval_ns": None,
            "mode_interval_ns": None,
            "mode_interval_count": 0,
        }
    mode_ns, mode_count = min(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "interval_count": sum(counts.values()),
        "distinct_interval_count": len(counts),
        "is_uniform": len(counts) == 1,
        "minimum_interval_ns": min(counts),
        "maximum_interval_ns": max(counts),
        "mode_interval_ns": mode_ns,
        "mode_interval_count": mode_count,
        "minimum_interval": pd.Timedelta(min(counts), unit="ns").isoformat(),
        "maximum_interval": pd.Timedelta(max(counts), unit="ns").isoformat(),
        "mode_interval": pd.Timedelta(mode_ns, unit="ns").isoformat(),
    }


def _telemetry_quality(
    frame: pd.DataFrame,
    identifier: str,
    *,
    cached_intervals: dict[str, Mapping[str, Any]],
) -> dict[str, Any]:
    values = frame[identifier].to_numpy(copy=False)
    index_hash = _hash_datetime_index(frame.index)
    interval_summary = cached_intervals.get(index_hash)
    if interval_summary is None:
        interval_summary = _interval_summary(frame.index)
        cached_intervals[index_hash] = interval_summary
    finite = np.isfinite(values)
    finite_values = values[finite]
    quantiles = np.quantile(finite_values, [0.0, 0.25, 0.5, 0.75, 1.0])
    return {
        "channel_identifier": identifier,
        "sample_count": len(frame),
        "timestamp_start": frame.index[0].isoformat() if len(frame) else None,
        "timestamp_end": frame.index[-1].isoformat() if len(frame) else None,
        "timestamp_dtype": str(frame.index.dtype),
        "timestamp_timezone": None,
        "timestamps_strictly_increasing": bool(
            frame.index.is_monotonic_increasing and frame.index.is_unique
        ),
        "duplicate_timestamp_count": int(frame.index.duplicated().sum()),
        "missing_timestamp_count": int(frame.index.isna().sum()),
        "missing_value_count": int(np.isnan(values).sum()),
        "positive_infinity_count": int(np.isposinf(values).sum()),
        "negative_infinity_count": int(np.isneginf(values).sum()),
        "value_dtype": str(values.dtype),
        "value_distribution": {
            "finite_count": int(finite.sum()),
            "minimum": float(quantiles[0]),
            "first_quartile": float(quantiles[1]),
            "median": float(quantiles[2]),
            "third_quartile": float(quantiles[3]),
            "maximum": float(quantiles[4]),
            "mean": float(np.mean(finite_values, dtype=np.float64)),
            "standard_deviation_population": float(
                np.std(finite_values, dtype=np.float64, ddof=0)
            ),
            "distinct_finite_value_count": int(np.unique(finite_values).size),
        },
        "timestamp_index_sha256": index_hash,
        "sampling_intervals": dict(interval_summary),
        "loaded_frame_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
    }


def _peak_working_set_bytes() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = get_current_process()
        result = get_process_memory_info(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.PeakWorkingSetSize) if result else None
    except (AttributeError, OSError):
        return None


def _write_telecommands_parquet(
    payloads: Mapping[str, _VerifiedMissionPickle],
    definitions: pd.DataFrame,
    output_path: Path,
    *,
    compression: str,
    row_group_size: int,
    write_statistics: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    definition_map = definitions.set_index("Telecommand")["Priority"].to_dict()
    schema = pa.schema(
        [
            pa.field("telecommand", pa.dictionary(pa.int16(), pa.string()), nullable=False),
            pa.field("timestamp", pa.timestamp("ns"), nullable=False),
            pa.field("execution_value", pa.uint8(), nullable=False),
            pa.field("priority", pa.int16(), nullable=False),
        ]
    )
    temporary_path = _temporary_sibling(output_path)
    writer: pq.ParquetWriter | None = None
    total_rows = 0
    empty_identifiers: list[str] = []
    per_identifier: list[dict[str, Any]] = []
    priority_counts: Counter[int] = Counter()
    value_counts: Counter[int] = Counter()
    global_start: pd.Timestamp | None = None
    global_end: pd.Timestamp | None = None
    try:
        writer = pq.ParquetWriter(
            temporary_path,
            schema,
            compression=compression,
            use_dictionary=["telecommand"],
            write_statistics=write_statistics,
        )
        for identifier in sorted(payloads, key=_identifier_sort_key):
            if identifier not in definition_map:
                raise PreparationError(f"Missing metadata definition for {identifier}.")
            loaded = _load_verified_pickle(payloads[identifier])
            frame = _validate_esa_telecommand_frame(loaded, identifier)
            priority = int(definition_map[identifier])
            row_count = len(frame)
            if row_count == 0:
                empty_identifiers.append(identifier)
            else:
                first = frame.index[0]
                last = frame.index[-1]
                global_start = first if global_start is None else min(global_start, first)
                global_end = last if global_end is None else max(global_end, last)
            values = frame[identifier].to_numpy(copy=False)
            unique_values, counts = np.unique(values, return_counts=True)
            value_counts.update(
                {
                    int(value): int(count)
                    for value, count in zip(unique_values, counts, strict=True)
                }
            )
            priority_counts[priority] += row_count
            dictionary = pa.array([identifier], type=pa.string())
            for start in range(0, row_count, row_group_size):
                stop = min(start + row_group_size, row_count)
                command = pa.DictionaryArray.from_arrays(
                    pa.array(np.zeros(stop - start, dtype=np.int16)),
                    dictionary,
                )
                table = pa.Table.from_arrays(
                    [
                        command,
                        pa.array(frame.index.asi8[start:stop], type=pa.timestamp("ns")),
                        pa.array(values[start:stop], type=pa.uint8()),
                        pa.array(
                            np.full(stop - start, priority, dtype=np.int16),
                            type=pa.int16(),
                        ),
                    ],
                    schema=schema,
                )
                writer.write_table(table, row_group_size=stop - start)
            per_identifier.append(
                {
                    "telecommand": identifier,
                    "priority": priority,
                    "execution_count": row_count,
                    "timestamp_start": frame.index[0].isoformat() if row_count else None,
                    "timestamp_end": frame.index[-1].isoformat() if row_count else None,
                    "archive_uncompressed_size_bytes": payloads[
                        identifier
                    ].uncompressed_size_bytes,
                }
            )
            total_rows += row_count
            del loaded, frame
        writer.close()
        writer = None
        parquet_file = pq.ParquetFile(temporary_path)
        metadata = parquet_file.metadata
        parquet_file.close()
        if metadata.num_rows != total_rows:
            raise PreparationError("Telecommand Parquet row-count validation failed.")
        _atomic_replace(temporary_path, output_path)
    finally:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
    generated = {
        "path": output_path.as_posix(),
        "row_count": total_rows,
        "row_group_count": metadata.num_row_groups,
        "schema": {field.name: str(field.type) for field in schema},
    }
    quality = {
        "definition_count": len(definitions),
        "execution_count": total_rows,
        "empty_stream_count": len(empty_identifiers),
        "empty_streams": empty_identifiers,
        "timestamp_start": global_start.isoformat() if global_start is not None else None,
        "timestamp_end": global_end.isoformat() if global_end is not None else None,
        "execution_counts_by_priority": {
            str(priority): count for priority, count in sorted(priority_counts.items())
        },
        "execution_value_counts": {
            str(value): count for value, count in sorted(value_counts.items())
        },
        "streams": per_identifier,
        "execution_value_semantics": "unresolved",
        "causal_relationship_to_events": "not inferred",
    }
    return generated, quality


def _event_quality(events: pd.DataFrame) -> dict[str, Any]:
    unique_events = events.drop_duplicates("event_id")
    durations = events["duration_ns"].to_numpy(dtype=np.int64, copy=False)
    category_event_counts = (
        unique_events.groupby("category", dropna=False)["event_id"].nunique().sort_index()
    )
    category_row_counts = events.groupby("category", dropna=False).size().sort_index()
    return {
        "row_count": len(events),
        "event_id_count": int(events["event_id"].nunique()),
        "timestamp_start": (
            events["start_timestamp"].min().isoformat() if len(events) else None
        ),
        "timestamp_end": events["end_timestamp"].max().isoformat() if len(events) else None,
        "selected_channel_reference_count": int(events["is_selected_channel"].sum()),
        "context_channel_reference_count": int((~events["is_selected_channel"]).sum()),
        "multichannel_event_id_count": int(
            events.loc[events["is_multichannel"], "event_id"].nunique()
        ),
        "event_ids_by_literal_category": {
            str(category): int(count) for category, count in category_event_counts.items()
        },
        "rows_by_literal_category": {
            str(category): int(count) for category, count in category_row_counts.items()
        },
        "duration_ns": {
            "minimum": int(durations.min()) if len(durations) else None,
            "median": int(np.median(durations)) if len(durations) else None,
            "maximum": int(durations.max()) if len(durations) else None,
        },
        "zero_duration_row_count": int((durations == 0).sum()),
        "missing_taxonomy_counts": {
            column: int(events[column].isna().sum())
            for column in (
                "category",
                "class",
                "subclass",
                "dimensionality",
                "locality",
                "length",
            )
        },
    }


def _dependency_versions() -> dict[str, str | None]:
    distributions = {
        "astra-research": "astra-research",
        "numpy": "numpy",
        "pandas": "pandas",
        "pyarrow": "pyarrow",
        "pyyaml": "PyYAML",
    }
    versions: dict[str, str | None] = {}
    for key, distribution in distributions.items():
        try:
            versions[key] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[key] = None
    versions["python"] = sys.version.split()[0]
    return versions


def _git_state(project_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        dirty: bool | None = bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        dirty = None
    return {
        "commit": commit,
        "dirty": dirty,
        "note": "Repository has no resolvable commit." if commit is None else None,
    }


def build_subset_manifest(
    *,
    source_archive_sha256: str,
    source_archive_md5: str | None = None,
    selected_channels: Sequence[Mapping[str, Any]],
    generated_files: Sequence[Mapping[str, Any]],
    preparation_config: Mapping[str, Any],
    generation_timestamp: str,
    code_version: str | None = None,
) -> dict[str, Any]:
    """Build a stable manifest independent of discovery order."""
    sorted_channels = sorted(
        (_json_value(dict(item)) for item in selected_channels),
        key=lambda item: _identifier_sort_key(str(item["channel_identifier"])),
    )
    sorted_files = sorted(
        (_json_value(dict(item)) for item in generated_files),
        key=lambda item: str(item["path"]),
    )
    return {
        "manifest_version": 1,
        "source_archive_sha256": source_archive_sha256,
        "source_archive_md5": source_archive_md5,
        "generation_timestamp": generation_timestamp,
        "code_version": code_version,
        "selected_channels": sorted_channels,
        "generated_files": sorted_files,
        "preparation_config": _json_value(dict(preparation_config)),
    }


def _relative_file_record(path: Path, project_root: Path, row_count: int, schema: Any) -> dict:
    return {
        "path": path.relative_to(project_root).as_posix(),
        "row_count": row_count,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "schema": schema,
    }


def _render_quality_report(quality: Mapping[str, Any]) -> str:
    channel_lines: list[str] = []
    for channel in quality["channels"]:
        intervals = channel["sampling_intervals"]
        distribution = channel["value_distribution"]
        channel_lines.extend(
            [
                f"### `{channel['channel_identifier']}`",
                "",
                f"- Samples: {channel['sample_count']:,}",
                f"- Timestamp range: `{channel['timestamp_start']}` to "
                f"`{channel['timestamp_end']}`",
                f"- Timestamps strictly increasing: "
                f"{channel['timestamps_strictly_increasing']}",
                f"- Duplicate timestamps: {channel['duplicate_timestamp_count']:,}",
                f"- Missing timestamps: {channel['missing_timestamp_count']:,}",
                f"- Missing values: {channel['missing_value_count']:,}",
                f"- Non-finite values: "
                f"{channel['positive_infinity_count'] + channel['negative_infinity_count']:,}",
                f"- Value range: {distribution['minimum']!r} to {distribution['maximum']!r}",
                f"- Value quartiles (Q1/median/Q3): {distribution['first_quartile']!r} / "
                f"{distribution['median']!r} / {distribution['third_quartile']!r}",
                f"- Distinct finite values: {distribution['distinct_finite_value_count']:,}",
                f"- Sampling intervals: {intervals['distinct_interval_count']:,} distinct; "
                f"minimum `{intervals.get('minimum_interval')}`, mode "
                f"`{intervals.get('mode_interval')}` ({intervals['mode_interval_count']:,}), "
                f"maximum `{intervals.get('maximum_interval')}`",
                f"- Uniform sampling: {intervals['is_uniform']}",
                "",
            ]
        )
    events = quality["events"]
    telecommands = quality["telecommands"]
    issues = quality["quality_issues"]
    return "\n".join(
        [
            "# Mission-1 Prepared Subset Quality Report",
            "",
            f"Generated: `{quality['generation_timestamp']}`",
            "",
            "This report describes measured properties of the prepared Phase 1.2 "
            "subset. It does not report model results or reinterpret ESA taxonomy.",
            "",
            "## Telemetry",
            "",
            f"Selected channels: {len(quality['channels'])}",
            f"Total samples: {quality['total_telemetry_samples']:,}",
            f"Processed Parquet storage: {quality['processed_storage_size_bytes']:,} bytes "
            f"({quality['processed_storage_size_bytes'] / (1024**2):.2f} MiB)",
            "",
            *channel_lines,
            "## Events",
            "",
            f"- Retained event IDs: {events['event_id_count']:,}",
            f"- Retained label rows: {events['row_count']:,}",
            f"- Selected-channel references: {events['selected_channel_reference_count']:,}",
            f"- Context-channel references: {events['context_channel_reference_count']:,}",
            f"- IDs touching at least two selected channels: "
            f"{events['multichannel_event_id_count']:,}",
            f"- IDs by literal Category: `{json.dumps(events['event_ids_by_literal_category'], sort_keys=True)}`",
            f"- Rows by literal Category: `{json.dumps(events['rows_by_literal_category'], sort_keys=True)}`",
            f"- Label-row duration (minimum/median/maximum): "
            f"{events['duration_ns']['minimum']:,} / {events['duration_ns']['median']:,} / "
            f"{events['duration_ns']['maximum']:,} ns",
            f"- Zero-duration label rows: {events['zero_duration_row_count']:,}",
            f"- Missing taxonomy fields: `{json.dumps(events['missing_taxonomy_counts'], sort_keys=True)}`",
            "",
            "`is_multichannel` means an ID has references to at least two selected "
            "channels. It is structural context, not a causal or scientific inference.",
            "",
            "## Telecommands",
            "",
            f"- Definitions: {telecommands['definition_count']:,}",
            f"- Execution records: {telecommands['execution_count']:,}",
            f"- Empty execution streams: {telecommands['empty_stream_count']:,}",
            f"- Timestamp range: `{telecommands['timestamp_start']}` to "
            f"`{telecommands['timestamp_end']}`",
            f"- Counts by literal Priority: "
            f"`{json.dumps(telecommands['execution_counts_by_priority'], sort_keys=True)}`",
            f"- Execution-value counts: "
            f"`{json.dumps(telecommands['execution_value_counts'], sort_keys=True)}`",
            "",
            "The execution-value meaning and any relationship between telecommands and "
            "events remain unresolved. No causal decision was made.",
            "",
            "## Resource observations",
            "",
            f"- Largest loaded channel frame: {quality['largest_loaded_frame_bytes']:,} bytes",
            f"- Observed process peak working set: "
            f"{quality['peak_working_set_bytes'] if quality['peak_working_set_bytes'] is not None else 'unavailable'}",
            "- Preparation loaded one channel or telecommand stream at a time.",
            "",
            "## Quality issues",
            "",
            *(f"- {issue}" for issue in issues),
            "",
            "## Transformations deliberately not performed",
            "",
            "- No resampling",
            "- No interpolation",
            "- No normalization",
            "- No forward filling",
            "- No model training or anomaly detection",
        ]
    )


def _source_provenance(
    config: Mapping[str, Any],
    verification: _ArchiveVerification,
    phase11_archive: Mapping[str, Any],
    verified_at: str,
) -> dict[str, Any]:
    return {
        "provenance_version": 1,
        "verified_at": verified_at,
        "dataset_identifier": config["dataset"]["identifier"],
        "source_provenance": config["dataset"]["source_provenance"],
        "measured_archive": {
            "filename": verification.archive_path.name,
            "size_bytes": verification.archive_size_bytes,
            "sha256": verification.archive_sha256,
            "md5": verification.archive_md5,
            "mtime_ns": verification.archive_mtime_ns,
            "member_count": verification.member_count,
            "file_count": verification.file_count,
            "directory_count": verification.directory_count,
            "uncompressed_size_bytes": verification.uncompressed_size_bytes,
            "compressed_member_size_bytes": verification.compressed_member_size_bytes,
        },
        "phase_1_1_archive_facts": dict(phase11_archive),
        "verification": {
            "filename_matches": True,
            "size_matches": True,
            "sha256_matches_pinned_value": True,
            "md5_matches_pinned_value": True,
            "member_count_matches_phase_1_1": True,
            "uncompressed_size_matches_phase_1_1": True,
        },
        "license_status": "unresolved; no authoritative local license file discovered",
        "authoritative_source_status": "unresolved; no authoritative local citation discovered",
    }


def _configured_outputs(config: Mapping[str, Any], project_root: Path) -> dict[str, Path]:
    return {
        key: _resolve_project_path(project_root, value)
        for key, value in config["outputs"].items()
    }


def _check_output_policy(
    outputs: Mapping[str, Path],
    *,
    project_root: Path,
    force: bool,
) -> None:
    raw_root = project_root / "data" / "raw"
    for output in outputs.values():
        _require_output_outside_raw(output, raw_root)
    existing_files: list[Path] = []
    for key, output in outputs.items():
        if key in {"processed_root", "channels_directory"}:
            continue
        if output.exists():
            existing_files.append(output)
    channels_directory = outputs["channels_directory"]
    if channels_directory.exists():
        existing_files.extend(channels_directory.glob("*.parquet"))
    if existing_files and not force:
        rendered = ", ".join(str(path) for path in sorted(set(existing_files)))
        raise PreparationError(f"Prepared outputs already exist; use --force to replace: {rendered}")


def prepare_mission1_subset(
    config_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Prepare channels 41-46, related events, and telecommands from Mission-1."""
    config_path = Path(config_path).resolve(strict=True)
    config, project_root = _load_yaml_config(config_path)
    if sys.version_info[:2] != (3, 11):
        raise PreparationError(
            f"Mission-1 preparation requires Python 3.11; running {sys.version.split()[0]}."
        )
    generation_timestamp = _utc_now()
    outputs = _configured_outputs(config, project_root)
    _check_output_policy(outputs, project_root=project_root, force=force)

    archive_config = config["dataset"]["archive"]
    archive_path = _resolve_project_path(project_root, archive_config["path"])
    profile_path = _resolve_project_path(project_root, archive_config["inspection_profile"])
    phase11_archive = _load_phase11_archive_facts(profile_path)
    verification = _verify_source_archive(archive_path, archive_config, phase11_archive)

    provenance = _source_provenance(
        config,
        verification,
        phase11_archive,
        generation_timestamp,
    )
    write_json_deterministic(provenance, outputs["provenance"])
    LOGGER.info("Wrote source provenance before Mission-1 deserialization: %s", outputs["provenance"])

    extracted = config["dataset"]["extracted"]
    extracted_root = _resolve_project_path(project_root, extracted["root"])
    dataset_directory = str(extracted["dataset_directory"])
    dataset_root = _require_within(
        extracted_root / dataset_directory,
        extracted_root,
        "Extracted dataset directory",
    )

    channels_metadata = _read_verified_csv(
        dataset_root / extracted["channels_metadata"],
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )
    labels = _read_verified_csv(
        dataset_root / extracted["labels"],
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )
    anomaly_types = _read_verified_csv(
        dataset_root / extracted["anomaly_types"],
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )
    telecommand_definitions = _read_verified_csv(
        dataset_root / extracted["telecommands_metadata"],
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )

    numeric_ids = [int(number) for number in config["subset"]["channel_numeric_ids"]]
    selected_metadata = filter_channel_metadata(channels_metadata, numeric_ids)
    selected_identifiers = sorted(
        selected_metadata["Channel"].astype(str).tolist(),
        key=_identifier_sort_key,
    )
    channel_payloads = _discover_verified_pickles(
        dataset_root / extracted["channels_directory"],
        expected_kind="channel",
        allowed_identifiers=set(selected_identifiers),
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )
    missing_payloads = sorted(set(selected_identifiers) - set(channel_payloads))
    if missing_payloads:
        raise PreparationError(f"Selected channel payloads were not discovered: {missing_payloads}")

    parquet_config = config["parquet"]
    compression = str(parquet_config["compression"])
    row_group_size = int(parquet_config["row_group_size"])
    write_statistics = bool(parquet_config["write_statistics"])
    outputs["channels_directory"].mkdir(parents=True, exist_ok=True)
    channel_quality: list[dict[str, Any]] = []
    channel_write_records: list[dict[str, Any]] = []
    interval_cache: dict[str, Mapping[str, Any]] = {}
    metadata_by_identifier = selected_metadata.set_index("Channel").to_dict("index")
    for identifier in selected_identifiers:
        LOGGER.info("Preparing %s", identifier)
        loaded = _load_verified_pickle(channel_payloads[identifier])
        frame = validate_esa_telemetry_frame(loaded, identifier)
        quality = _telemetry_quality(
            frame,
            identifier,
            cached_intervals=interval_cache,
        )
        quality["metadata"] = _json_value(metadata_by_identifier[identifier])
        quality["source_archive"] = {
            "path": channel_payloads[identifier].archive_path.relative_to(
                project_root
            ).as_posix(),
            "nested_archive_size_bytes": channel_payloads[identifier].archive_size_bytes,
            "nested_archive_crc32": channel_payloads[identifier].archive_crc32,
            "payload_compressed_size_bytes": channel_payloads[
                identifier
            ].compressed_size_bytes,
            "payload_uncompressed_size_bytes": channel_payloads[
                identifier
            ].uncompressed_size_bytes,
            "payload_crc32": channel_payloads[identifier].member_crc32,
        }
        output_path = outputs["channels_directory"] / f"{identifier}.parquet"
        write_result = write_telemetry_parquet(
            frame,
            channel_identifier=identifier,
            output_path=output_path,
            row_group_size=row_group_size,
            compression=compression,
            write_statistics=write_statistics,
        )
        channel_quality.append(quality)
        channel_write_records.append(write_result)
        del loaded, frame

    events = prepare_event_table(
        labels,
        anomaly_types,
        selected_channels=selected_identifiers,
    )
    event_write_record = _write_dataframe_parquet_atomic(
        events,
        outputs["events"],
        compression=compression,
        row_group_size=row_group_size,
        write_statistics=write_statistics,
    )
    event_quality = _event_quality(events)
    del events

    if telecommand_definitions["Telecommand"].duplicated().any():
        raise PreparationError("Telecommand metadata contains duplicate definitions.")
    telecommand_identifiers = set(telecommand_definitions["Telecommand"].astype(str))
    telecommand_payloads = _discover_verified_pickles(
        dataset_root / extracted["telecommands_directory"],
        expected_kind="telecommand",
        allowed_identifiers=telecommand_identifiers,
        dataset_root=dataset_root,
        dataset_directory=dataset_directory,
        archive_verification=verification,
    )
    missing_telecommands = sorted(
        telecommand_identifiers - set(telecommand_payloads),
        key=_identifier_sort_key,
    )
    if missing_telecommands:
        raise PreparationError(
            f"Telecommand definitions without execution streams: {missing_telecommands}"
        )
    telecommand_write_record, telecommand_quality = _write_telecommands_parquet(
        telecommand_payloads,
        telecommand_definitions,
        outputs["telecommands"],
        compression=compression,
        row_group_size=row_group_size,
        write_statistics=write_statistics,
    )

    raw_stat_after = archive_path.stat()
    if (
        raw_stat_after.st_size != verification.archive_size_bytes
        or raw_stat_after.st_mtime_ns != verification.archive_mtime_ns
    ):
        raise PreparationError("Raw archive changed during preparation.")

    quality_issues: list[str] = []
    if any(channel["missing_value_count"] for channel in channel_quality):
        quality_issues.append("Missing telemetry values are present and were preserved.")
    if any(channel["duplicate_timestamp_count"] for channel in channel_quality):
        quality_issues.append("Duplicate telemetry timestamps are present and were preserved.")
    if any(not channel["sampling_intervals"]["is_uniform"] for channel in channel_quality):
        quality_issues.append(
            "All selected channels have varying observed timestamp intervals; no resampling was applied."
        )
    if any(event_quality["missing_taxonomy_counts"].values()):
        quality_issues.append(
            "Some retained event taxonomy fields are null in the source and remain null."
        )
    if event_quality["zero_duration_row_count"]:
        quality_issues.append(
            f"{event_quality['zero_duration_row_count']} retained label rows have zero duration."
        )
    if telecommand_quality["empty_stream_count"]:
        quality_issues.append(
            f"{telecommand_quality['empty_stream_count']} telecommand streams are empty in the source."
        )
    quality_issues.extend(
        [
            "Authoritative source provenance is unresolved.",
            "Dataset license is unresolved.",
            "Telecommand execution-value semantics are unresolved.",
        ]
    )
    quality = {
        "generation_timestamp": generation_timestamp,
        "channels": channel_quality,
        "total_telemetry_samples": sum(item["sample_count"] for item in channel_quality),
        "events": event_quality,
        "telecommands": telecommand_quality,
        "processed_storage_size_bytes": sum(
            path.stat().st_size
            for path in [
                *(outputs["channels_directory"] / f"{identifier}.parquet"
                  for identifier in selected_identifiers),
                outputs["events"],
                outputs["telecommands"],
            ]
        ),
        "largest_loaded_frame_bytes": max(
            item["loaded_frame_bytes"] for item in channel_quality
        ),
        "peak_working_set_bytes": _peak_working_set_bytes(),
        "quality_issues": quality_issues,
    }
    _write_text_atomic(_render_quality_report(quality), outputs["quality_report"])

    generated_records: list[dict[str, Any]] = []
    for record in channel_write_records:
        path = Path(record["path"])
        file_record = _relative_file_record(
            path,
            project_root,
            record["row_count"],
            record["schema"],
        )
        channel_identifier = path.stem
        channel_summary = next(
            item
            for item in channel_quality
            if item["channel_identifier"] == channel_identifier
        )
        file_record["timestamp_start"] = channel_summary["timestamp_start"]
        file_record["timestamp_end"] = channel_summary["timestamp_end"]
        generated_records.append(file_record)
    for record, timestamp_start, timestamp_end in (
        (
            event_write_record,
            event_quality["timestamp_start"],
            event_quality["timestamp_end"],
        ),
        (
            telecommand_write_record,
            telecommand_quality["timestamp_start"],
            telecommand_quality["timestamp_end"],
        ),
    ):
        path = Path(record["path"])
        file_record = _relative_file_record(
            path,
            project_root,
            record["row_count"],
            record["schema"],
        )
        file_record["timestamp_start"] = timestamp_start
        file_record["timestamp_end"] = timestamp_end
        generated_records.append(file_record)
    quality_report_record = _relative_file_record(
        outputs["quality_report"],
        project_root,
        0,
        {"format": "Markdown"},
    )
    quality_report_record.pop("row_count")
    generated_records.append(quality_report_record)
    provenance_record = _relative_file_record(
        outputs["provenance"],
        project_root,
        0,
        {"format": "JSON"},
    )
    provenance_record.pop("row_count")
    generated_records.append(provenance_record)

    code_path = Path(__file__).resolve()
    code_version = f"sha256:{_sha256_file(code_path)}"
    preparation_config = {
        "channel_numeric_ids": numeric_ids,
        "parquet": parquet_config,
        "preparation": config["preparation"],
        "config_path": config_path.relative_to(project_root).as_posix(),
        "config_sha256": _sha256_file(config_path),
        "module_path": code_path.relative_to(project_root).as_posix(),
        "module_sha256": _sha256_file(code_path),
        "dependency_versions": _dependency_versions(),
        "git": _git_state(project_root),
    }
    manifest = build_subset_manifest(
        source_archive_sha256=verification.archive_sha256,
        source_archive_md5=verification.archive_md5,
        selected_channels=channel_quality,
        generated_files=generated_records,
        preparation_config=preparation_config,
        generation_timestamp=generation_timestamp,
        code_version=code_version,
    )
    manifest["quality_summary"] = quality
    manifest["raw_archive_unchanged"] = True
    write_json_deterministic(manifest, outputs["manifest"])
    LOGGER.info("Wrote manifest last: %s", outputs["manifest"])

    return {
        "archive_sha256": verification.archive_sha256,
        "archive_md5": verification.archive_md5,
        "channel_count": len(selected_identifiers),
        "telemetry_sample_count": quality["total_telemetry_samples"],
        "event_id_count": event_quality["event_id_count"],
        "telecommand_execution_count": telecommand_quality["execution_count"],
        "manifest": outputs["manifest"].relative_to(project_root).as_posix(),
        "quality_report": outputs["quality_report"].relative_to(project_root).as_posix(),
    }
