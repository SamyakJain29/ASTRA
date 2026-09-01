"""Synthetic contract tests for Mission-1 subset preparation."""

from __future__ import annotations

import hashlib
import io
import json
import pickle
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from astra.data.preparation import (
    PreparationError,
    _ArchiveVerification,
    _discover_verified_pickles,
    _load_verified_pickle,
    _verify_source_archive,
    build_subset_manifest,
    filter_channel_metadata,
    join_telecommand_metadata,
    prepare_event_table,
    validate_esa_telemetry_frame,
    write_json_deterministic,
    write_telemetry_parquet,
)


def _nested_zip_bytes(member_name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name, payload)
    return buffer.getvalue()


def _verified_channel_archive(
    tmp_path: Path,
    *,
    payload_member_name: str = "channel_41",
) -> tuple[pd.DataFrame, Path, Path, _ArchiveVerification]:
    """Create matching synthetic raw, profile, and extracted archive evidence."""
    frame = _telemetry_frame()
    payload = pickle.dumps(frame, protocol=5)
    nested_archive_bytes = _nested_zip_bytes(payload_member_name, payload)

    raw_archive = tmp_path / "data" / "raw" / "ESA-Mission1.zip"
    raw_archive.parent.mkdir(parents=True)
    outer_member_name = "ESA-Mission1/channels/channel_41.zip"
    with zipfile.ZipFile(raw_archive, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(outer_member_name, nested_archive_bytes)

    archive_sha256 = hashlib.sha256(raw_archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(raw_archive) as archive:
        members = archive.infolist()
    profile_archive = {
        "filename": raw_archive.name,
        "size_bytes": raw_archive.stat().st_size,
        "member_count": len(members),
        "uncompressed_size_bytes": sum(
            member.file_size for member in members if not member.is_dir()
        ),
    }
    archive_config = {
        "expected_filename": raw_archive.name,
        "expected_size_bytes": raw_archive.stat().st_size,
        "expected_sha256": archive_sha256,
        "expected_md5": hashlib.md5(raw_archive.read_bytes()).hexdigest(),  # noqa: S324
    }
    verification = _verify_source_archive(raw_archive, archive_config, profile_archive)

    dataset_root = tmp_path / "data" / "interim" / "mission1" / "ESA-Mission1"
    nested_archive = dataset_root / "channels" / "channel_41.zip"
    nested_archive.parent.mkdir(parents=True)
    nested_archive.write_bytes(nested_archive_bytes)
    return frame, dataset_root, nested_archive, verification


def _telemetry_frame(channel_identifier: str = "channel_41") -> pd.DataFrame:
    """Return a small frame with the verified ESA telemetry shape."""
    timestamps = pd.DatetimeIndex(
        [
            "2012-01-01T00:00:00.000000001",
            "2012-01-01T00:00:30.000000002",
            "2012-01-01T00:01:00.000000003",
        ],
        name="datetime",
    )
    values = np.array([1.25, np.nan, -3.5], dtype=np.float32)
    return pd.DataFrame({channel_identifier: values}, index=timestamps)


def test_private_trust_boundary_admits_only_verified_channel_payload(
    tmp_path: Path,
) -> None:
    """Raw identity, outer CRC, nested identity, load, and schema checks form one chain."""
    expected_frame, dataset_root, nested_archive, verification = _verified_channel_archive(tmp_path)

    assert verification.archive_path.name == "ESA-Mission1.zip"
    assert (
        verification.archive_sha256
        == hashlib.sha256(verification.archive_path.read_bytes()).hexdigest()
    )
    assert verification.archive_md5 == hashlib.md5(  # noqa: S324
        verification.archive_path.read_bytes()
    ).hexdigest()
    assert verification.archive_size_bytes == verification.archive_path.stat().st_size
    assert verification.member_count == 1
    assert "ESA-Mission1/channels/channel_41.zip" in verification.members

    discovered = _discover_verified_pickles(
        nested_archive.parent,
        expected_kind="channel",
        allowed_identifiers={"channel_41"},
        dataset_root=dataset_root,
        dataset_directory="ESA-Mission1",
        archive_verification=verification,
    )

    assert set(discovered) == {"channel_41"}
    admitted = discovered["channel_41"]
    with zipfile.ZipFile(nested_archive) as archive:
        member = archive.getinfo("channel_41")
    assert admitted.archive_path == nested_archive.resolve()
    assert admitted.member_name == "channel_41"
    assert admitted.compressed_size_bytes == member.compress_size
    assert admitted.uncompressed_size_bytes == member.file_size
    assert admitted.member_crc32 == f"{member.CRC:08x}"

    loaded = _load_verified_pickle(admitted)
    validated = validate_esa_telemetry_frame(loaded, expected_identifier="channel_41")
    pd.testing.assert_frame_equal(validated, expected_frame)


def test_private_trust_boundary_rejects_tampered_extracted_archive(
    tmp_path: Path,
) -> None:
    """A same-size extracted nested ZIP with a changed CRC must not be admitted."""
    _, dataset_root, nested_archive, verification = _verified_channel_archive(tmp_path)
    original_size = nested_archive.stat().st_size
    tampered = bytearray(nested_archive.read_bytes())
    tampered[0] ^= 0xFF
    nested_archive.write_bytes(tampered)
    assert nested_archive.stat().st_size == original_size

    with pytest.raises(PreparationError, match="CRC mismatch"):
        _discover_verified_pickles(
            nested_archive.parent,
            expected_kind="channel",
            allowed_identifiers={"channel_41"},
            dataset_root=dataset_root,
            dataset_directory="ESA-Mission1",
            archive_verification=verification,
        )


def test_private_trust_boundary_rejects_unexpected_nested_member(
    tmp_path: Path,
) -> None:
    """A verified outer member cannot admit a differently named pickle payload."""
    _, dataset_root, nested_archive, verification = _verified_channel_archive(
        tmp_path,
        payload_member_name="channel_99",
    )

    with pytest.raises(PreparationError, match="does not match payload"):
        _discover_verified_pickles(
            nested_archive.parent,
            expected_kind="channel",
            allowed_identifiers={"channel_41"},
            dataset_root=dataset_root,
            dataset_directory="ESA-Mission1",
            archive_verification=verification,
        )


def test_validate_esa_telemetry_frame_accepts_verified_shape() -> None:
    """A trusted ESA-shaped frame should validate without being copied or coerced."""
    frame = _telemetry_frame()

    validated = validate_esa_telemetry_frame(frame, expected_identifier="channel_41")

    assert validated is frame
    assert isinstance(validated.index, pd.DatetimeIndex)
    assert validated.index.name == "datetime"
    assert validated.columns.tolist() == ["channel_41"]
    assert validated["channel_41"].dtype == np.dtype("float32")


@pytest.mark.parametrize(
    ("frame", "expected_error"),
    [
        (pd.Series([1.0], name="channel_41"), TypeError),
        (pd.DataFrame({"channel_41": np.array([1.0], dtype=np.float32)}), ValueError),
        (
            pd.DataFrame(
                {"channel_99": np.array([1.0], dtype=np.float32)},
                index=pd.DatetimeIndex(["2012-01-01"], name="datetime"),
            ),
            ValueError,
        ),
        (
            pd.DataFrame(
                {
                    "channel_41": np.array([1.0], dtype=np.float32),
                    "extra": np.array([2.0], dtype=np.float32),
                },
                index=pd.DatetimeIndex(["2012-01-01"], name="datetime"),
            ),
            ValueError,
        ),
        (
            pd.DataFrame(
                {"channel_41": np.array([1.0], dtype=np.float64)},
                index=pd.DatetimeIndex(["2012-01-01"], name="datetime"),
            ),
            ValueError,
        ),
        (
            pd.DataFrame(
                {"channel_41": np.array([1.0], dtype=np.float32)},
                index=pd.DatetimeIndex(["2012-01-01"], name="wrong-name"),
            ),
            ValueError,
        ),
        (
            pd.DataFrame(
                {"channel_41": np.array([1.0, 2.0], dtype=np.float32)},
                index=pd.DatetimeIndex(
                    ["2012-01-01T00:00:01", "2012-01-01T00:00:00"],
                    name="datetime",
                ),
            ),
            ValueError,
        ),
    ],
    ids=(
        "not-a-dataframe",
        "non-datetime-index",
        "wrong-channel",
        "extra-column",
        "float64",
        "wrong-index-name",
        "non-monotonic-index",
    ),
)
def test_validate_esa_telemetry_frame_rejects_unexpected_structure(
    frame: object,
    expected_error: type[Exception],
) -> None:
    """Unexpected object types and schemas must fail before processing."""
    with pytest.raises(expected_error):
        validate_esa_telemetry_frame(frame, expected_identifier="channel_41")


def test_write_telemetry_parquet_preserves_timestamp_value_and_identity(
    tmp_path: Path,
) -> None:
    """Conversion should preserve nanosecond timestamps, float32 values, and identity."""
    frame = _telemetry_frame()
    output_path = tmp_path / "processed" / "channels" / "channel_41.parquet"

    write_telemetry_parquet(
        frame,
        channel_identifier="channel_41",
        output_path=output_path,
        row_group_size=2,
    )

    converted = pd.read_parquet(output_path)
    assert converted.columns.tolist() == ["timestamp", "value", "channel"]
    assert pd.DatetimeIndex(converted["timestamp"]).equals(frame.index)
    assert converted["value"].dtype == np.dtype("float32")
    np.testing.assert_array_equal(
        converted["value"].to_numpy(),
        frame["channel_41"].to_numpy(),
    )
    assert converted["channel"].tolist() == ["channel_41"] * len(frame)
    assert pq.ParquetFile(output_path).metadata.num_row_groups == 2


def test_filter_channel_metadata_matches_exact_numeric_identifiers() -> None:
    """Numeric selection must not accidentally match prefixes such as 4 or 410."""
    metadata = pd.DataFrame(
        {
            "Channel": ["channel_4", "channel_41", "channel_46", "channel_410"],
            "Subsystem": ["s4", "s41", "s46", "s410"],
            "Physical Unit": ["u4", "u41", "u46", "u410"],
            "Group": ["g4", "g41", "g46", "g410"],
            "Target": ["NO", "YES", "NO", "YES"],
        }
    )

    selected = filter_channel_metadata(metadata, numeric_ids=[41, 46])

    assert selected["Channel"].tolist() == ["channel_41", "channel_46"]
    assert selected["Subsystem"].tolist() == ["s41", "s46"]
    assert selected["Physical Unit"].tolist() == ["u41", "u46"]
    assert selected["Group"].tolist() == ["g41", "g46"]
    assert selected["Target"].tolist() == ["YES", "NO"]


def test_prepare_event_table_preserves_context_categories_and_multichannel_flags() -> None:
    """Relevant events retain all channel rows and ESA's literal taxonomy."""
    labels = pd.DataFrame(
        {
            "ID": ["event_multi", "event_multi", "event_multi", "event_rare", "outside"],
            "Channel": ["channel_41", "channel_42", "channel_9", "channel_46", "channel_8"],
            "StartTime": [
                "2012-01-01T00:00:00Z",
                "2012-01-01T00:00:00Z",
                "2012-01-01T00:00:00Z",
                "2012-02-02T00:00:00Z",
                "2012-03-03T00:00:00Z",
            ],
            "EndTime": [
                "2012-01-01T00:10:00Z",
                "2012-01-01T00:10:00Z",
                "2012-01-01T00:10:00Z",
                "2012-02-02T00:00:30Z",
                "2012-03-03T00:01:00Z",
            ],
        }
    )
    anomaly_types = pd.DataFrame(
        {
            "ID": ["event_multi", "event_rare", "outside"],
            "Class": ["class-a", "class-b", "class-c"],
            "Subclass": ["sub-a", "sub-b", "sub-c"],
            "Category": ["Anomaly", "Rare Event", "Communication Gap"],
            "Dimensionality": ["Multivariate", "Univariate", "Univariate"],
            "Locality": ["Global", "Local", "Local"],
            "Length": ["Subsequence", "Point", "Subsequence"],
        }
    )

    events = prepare_event_table(
        labels,
        anomaly_types,
        selected_channels=["channel_41", "channel_42", "channel_46"],
    )

    assert set(events["event_id"]) == {"event_multi", "event_rare"}
    assert set(events["category"]) == {"Anomaly", "Rare Event"}
    assert "Communication Gap" not in set(events["category"])
    assert {
        "event_id",
        "channel",
        "start_timestamp",
        "end_timestamp",
        "category",
        "class",
        "subclass",
        "dimensionality",
        "locality",
        "length",
        "is_selected_channel",
        "selected_channel_count",
        "all_channel_count",
        "is_multichannel",
    }.issubset(events.columns)

    multi = events.loc[events["event_id"] == "event_multi"]
    assert set(multi["channel"]) == {"channel_41", "channel_42", "channel_9"}
    assert multi.set_index("channel")["is_selected_channel"].to_dict() == {
        "channel_41": True,
        "channel_42": True,
        "channel_9": False,
    }
    assert multi["selected_channel_count"].tolist() == [2, 2, 2]
    assert multi["all_channel_count"].tolist() == [3, 3, 3]
    assert multi["is_multichannel"].tolist() == [True, True, True]

    rare = events.loc[events["event_id"] == "event_rare"].iloc[0]
    assert rare["category"] == "Rare Event"
    assert rare["selected_channel_count"] == 1
    assert rare["all_channel_count"] == 1
    assert not rare["is_multichannel"]


def test_join_telecommand_metadata_preserves_execution_values_and_priority() -> None:
    """Execution rows should receive Priority without changing anonymous values."""
    executions = pd.DataFrame(
        {
            "telecommand": ["telecommand_2", "telecommand_1", "telecommand_2"],
            "timestamp": pd.to_datetime(
                [
                    "2012-01-01T00:00:00",
                    "2012-01-01T00:01:00",
                    "2012-01-01T00:02:00",
                ]
            ),
            "execution_value": np.array([0, 1, 2], dtype=np.uint8),
        }
    )
    definitions = pd.DataFrame(
        {
            "Telecommand": ["telecommand_1", "telecommand_2"],
            "Priority": [3, 1],
        }
    )

    joined = join_telecommand_metadata(executions, definitions)

    assert joined.columns.tolist() == [
        "telecommand",
        "timestamp",
        "execution_value",
        "priority",
    ]
    assert joined["execution_value"].dtype == np.dtype("uint8")
    assert joined["execution_value"].tolist() == [0, 1, 2]
    assert joined["priority"].tolist() == [1, 3, 1]


def test_subset_manifest_and_json_are_deterministic(tmp_path: Path) -> None:
    """Equivalent discovery order should produce byte-identical manifest JSON."""
    selected_channels = [
        {"channel_identifier": "channel_46", "sample_count": 2},
        {"channel_identifier": "channel_41", "sample_count": 3},
    ]
    generated_files = [
        {"path": "channels/channel_46.parquet", "row_count": 2},
        {"path": "channels/channel_41.parquet", "row_count": 3},
    ]
    build_kwargs = {
        "source_archive_sha256": "ab" * 32,
        "preparation_config": {"row_group_size": 2, "numeric_ids": [41, 46]},
        "generation_timestamp": "2026-09-01T00:00:00Z",
        "code_version": "synthetic-test-version",
    }

    first = build_subset_manifest(
        selected_channels=selected_channels,
        generated_files=generated_files,
        **build_kwargs,
    )
    second = build_subset_manifest(
        selected_channels=list(reversed(selected_channels)),
        generated_files=list(reversed(generated_files)),
        **build_kwargs,
    )

    assert first == second
    assert first["source_archive_sha256"] == "ab" * 32
    assert first["generation_timestamp"] == "2026-09-01T00:00:00Z"
    assert first["code_version"] == "synthetic-test-version"
    assert [item["channel_identifier"] for item in first["selected_channels"]] == [
        "channel_41",
        "channel_46",
    ]
    assert [item["path"] for item in first["generated_files"]] == [
        "channels/channel_41.parquet",
        "channels/channel_46.parquet",
    ]

    first_path = tmp_path / "first" / "manifest.json"
    second_path = tmp_path / "second" / "manifest.json"
    write_json_deterministic(first, first_path)
    write_json_deterministic(second, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_path.read_bytes().endswith(b"\n")
    assert json.loads(first_path.read_text(encoding="utf-8")) == first
