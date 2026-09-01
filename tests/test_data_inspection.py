"""Synthetic tests for safe, schema-agnostic dataset inspection."""

from __future__ import annotations

import io
import json
import pickle
import zipfile
from pathlib import Path

import numpy as np
import pytest

from astra.data.inspection import (
    build_dataset_profile,
    inspect_zip_archive,
    profile_csv_table,
    safe_extract_zip,
    write_profile_json,
)


def _write_zip(archive_path: Path, members: dict[str, bytes]) -> Path:
    """Create a small ZIP fixture without touching repository data."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member_name, content in members.items():
            archive.writestr(member_name, content)
    return archive_path


def _raise_if_deserialized() -> None:
    raise AssertionError("dataset pickle was executed")


class _ExplosivePickle:
    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        return _raise_if_deserialized, ()


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member_name, content in members.items():
            archive.writestr(member_name, content)
    return buffer.getvalue()


def test_inspect_zip_archive_records_archive_facts(tmp_path: Path) -> None:
    """Archive inspection should report facts derived from ZIP metadata."""
    members = {
        "mission/metadata/channels.csv": b"channel,unit\nA,temp\n",
        "mission/telemetry/A.csv": b"timestamp,value\n1,2.5\n",
        "README.txt": b"synthetic fixture\n",
    }
    archive_path = _write_zip(tmp_path / "mission.zip", members)

    profile = inspect_zip_archive(archive_path)

    assert profile["filename"] == "mission.zip"
    assert profile["size_bytes"] == archive_path.stat().st_size
    assert profile["member_count"] == len(members)
    assert profile["file_count"] == len(members)
    assert profile["directory_count"] == 0
    assert set(profile["top_level_structure"]) == {"mission", "README.txt"}
    assert profile["file_extensions"] == {".csv": 2, ".txt": 1}
    assert profile["uncompressed_size_bytes"] == sum(map(len, members.values()))
    assert profile["compressed_member_size_bytes"] >= 0


def test_safe_extract_zip_is_repeatable_without_overwriting(tmp_path: Path) -> None:
    """A second extraction should verify and skip identical files."""
    archive_path = _write_zip(
        tmp_path / "mission.zip",
        {
            "mission/metadata.csv": b"name,value\nalpha,1\n",
            "mission/channels/A.csv": b"timestamp,value\n1,2\n",
        },
    )
    destination = tmp_path / "interim" / "mission1"

    first_result = safe_extract_zip(archive_path, destination)
    second_result = safe_extract_zip(archive_path, destination)

    assert set(first_result["extracted_files"]) == {
        "mission/metadata.csv",
        "mission/channels/A.csv",
    }
    assert first_result["skipped_files"] == []
    assert second_result["extracted_files"] == []
    assert set(second_result["skipped_files"]) == {
        "mission/metadata.csv",
        "mission/channels/A.csv",
    }
    assert (destination / "mission" / "metadata.csv").read_bytes() == (
        b"name,value\nalpha,1\n"
    )


def test_safe_extract_zip_refuses_conflicting_existing_file(tmp_path: Path) -> None:
    """Extraction must not silently replace an existing, different file."""
    archive_path = _write_zip(tmp_path / "mission.zip", {"payload.txt": b"original"})
    destination = tmp_path / "interim" / "mission1"
    safe_extract_zip(archive_path, destination)
    (destination / "payload.txt").write_bytes(b"changed!")

    with pytest.raises(FileExistsError):
        safe_extract_zip(archive_path, destination)

    assert (destination / "payload.txt").read_bytes() == b"changed!"


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "../outside.txt",
        "mission/../../outside.txt",
        "/absolute.txt",
        "\\absolute.txt",
        "C:/drive-rooted.txt",
        "C:\\drive-rooted.txt",
        "..\\outside.txt",
    ),
)
def test_safe_extract_zip_rejects_path_traversal(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    """POSIX and Windows traversal or absolute member names must be rejected."""
    archive_path = _write_zip(tmp_path / "unsafe.zip", {unsafe_name: b"unsafe"})
    destination = tmp_path / "interim" / "mission1"

    with pytest.raises(ValueError, match="(?i)(unsafe|path|absolute|traversal|drive)"):
        safe_extract_zip(archive_path, destination)

    assert not (tmp_path / "outside.txt").exists()


def test_safe_extract_zip_refuses_destination_under_raw_data(tmp_path: Path) -> None:
    """Extraction must never target a directory nested under data/raw."""
    archive_path = _write_zip(tmp_path / "mission.zip", {"metadata.csv": b"id\n1\n"})
    raw_destination = tmp_path / "data" / "raw" / "mission1"

    with pytest.raises(ValueError, match="(?i)raw"):
        safe_extract_zip(archive_path, raw_destination)

    assert not raw_destination.exists()


def test_safe_extract_zip_refuses_member_that_resolves_under_raw_data(
    tmp_path: Path,
) -> None:
    """An ancestor destination must not let a member resolve into data/raw."""
    archive_path = _write_zip(
        tmp_path / "mission.zip",
        {
            "safe.txt": b"must not be partially extracted",
            "raw/mission1/payload.bin": b"immutable",
        },
    )
    data_destination = tmp_path / "data"

    with pytest.raises(ValueError, match="(?i)raw"):
        safe_extract_zip(archive_path, data_destination)

    assert not (data_destination / "safe.txt").exists()
    assert not (data_destination / "raw" / "mission1" / "payload.bin").exists()


def test_profile_writer_refuses_raw_data_destination(tmp_path: Path) -> None:
    """Generated reports must not be able to overwrite immutable raw data."""
    raw_output = tmp_path / "data" / "raw" / "profile.json"

    with pytest.raises(ValueError, match="(?i)raw"):
        write_profile_json({"synthetic": True}, raw_output)

    assert not raw_output.exists()


def test_profile_writer_handles_mapped_destination_without_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Windows-style mapped destination remains valid after the safe fallback."""
    output_path = tmp_path / "profile.json"
    output_path.write_text(json.dumps({"old": "x" * 1_000}), encoding="utf-8")
    original_size = output_path.stat().st_size

    def deny_atomic_replace(_source: Path, _destination: Path) -> None:
        raise PermissionError("synthetic mapped file")

    monkeypatch.setattr("astra.data.inspection.os.replace", deny_atomic_replace)

    write_profile_json({"new": True}, output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"new": True}
    assert output_path.stat().st_size == original_size


def test_profile_csv_table_streams_schema_counts_and_bounded_examples(tmp_path: Path) -> None:
    """CSV profiling should count all rows while retaining at most five examples."""
    table_path = tmp_path / "metadata.csv"
    table_path.write_text(
        "record_id,name,value\n"
        "1,alpha,1.5\n"
        "2,,2.5\n"
        "3,gamma,\n"
        "4,delta,4.5\n"
        "5,epsilon,5.5\n"
        "6,zeta,6.5\n",
        encoding="utf-8",
    )

    profile = profile_csv_table(table_path, max_example_rows=99)

    assert profile["filename"] == "metadata.csv"
    assert profile["size_bytes"] == table_path.stat().st_size
    assert profile["row_count"] == 6
    assert profile["column_names"] == ["record_id", "name", "value"]
    assert set(profile["inferred_data_types"]) == {"record_id", "name", "value"}
    assert all(isinstance(value, str) for value in profile["inferred_data_types"].values())
    assert profile["null_counts"] == {"record_id": 0, "name": 1, "value": 1}
    assert len(profile["example_rows"]) == 5
    assert profile["example_rows"][0]["record_id"] == "1"
    assert profile["delimiter"] == ","
    assert profile["encoding"] in {"utf-8", "utf-8-sig"}


def test_build_dataset_profile_and_write_json(tmp_path: Path) -> None:
    """A complete synthetic profile should be emitted as valid JSON."""
    archive_path = _write_zip(
        tmp_path / "mission.zip",
        {"metadata.csv": b"identifier,description\nA,synthetic\n"},
    )
    extracted_root = tmp_path / "interim" / "mission1"
    safe_extract_zip(archive_path, extracted_root)

    profile = build_dataset_profile(archive_path, extracted_root)
    output_path = tmp_path / "artifacts" / "data" / "profile.json"
    write_profile_json(profile, output_path)

    serialized_profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert serialized_profile == profile
    assert profile["archive"]["filename"] == "mission.zip"
    assert profile["extracted"]["file_count"] == 1
    assert profile["metadata_tables"][0]["row_count"] == 1
    assert profile["metadata_tables"][0]["column_names"] == [
        "identifier",
        "description",
    ]
    assert output_path.read_bytes().endswith(b"\n")


def test_pickle_payload_is_profiled_without_deserialization(tmp_path: Path) -> None:
    """Opcode inspection should identify arrays without executing pickle callables."""
    payload = pickle.dumps(
        {
            "values": np.array([1.0, np.nan, 3.0], dtype=np.float32),
            "timestamps": np.array([0, 30, 60], dtype="datetime64[ns]"),
            "must_not_run": _ExplosivePickle(),
        },
        protocol=5,
    )
    nested_zip = _zip_bytes({"channel_alpha": payload})
    archive_path = _write_zip(
        tmp_path / "mission.zip",
        {"mission/channels/channel_alpha.zip": nested_zip},
    )
    extracted_root = tmp_path / "interim" / "mission1"
    safe_extract_zip(archive_path, extracted_root)

    profile = build_dataset_profile(archive_path, extracted_root)
    channel = profile["telemetry"]["data_files"][0]

    assert channel["format"] == "Python pickle protocol 5"
    assert channel["value_representation"]["representations"] == ["NumPy float32"]
    assert channel["timestamp_representation"]["representations"] == [
        "NumPy datetime64[ns]"
    ]
    assert channel["missing_values_observed"] is True
