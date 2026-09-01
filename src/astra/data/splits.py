"""Leakage-resistant temporal splits for the ESA Mission-1 subset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from astra.data.preparation import write_json_deterministic

MISSION1_VALIDATION_BOUNDARY = pd.Timestamp("2006-10-01T00:00:00Z")
MISSION1_TEST_BOUNDARY = pd.Timestamp("2007-01-01T00:00:00Z")


class SplitError(ValueError):
    """Raised when temporal split inputs are invalid."""


@dataclass(frozen=True)
class TemporalSplit:
    """Timestamp boundaries using the official Mission-1 endpoint convention.

    Train and validation include their upper boundary. Validation and test begin
    strictly after the preceding boundary, matching ESA's published preparation
    scripts.
    """

    dataset_start: pd.Timestamp
    validation_boundary: pd.Timestamp
    test_boundary: pd.Timestamp
    dataset_end: pd.Timestamp

    def __post_init__(self) -> None:
        values = tuple(_as_utc(value) for value in (
            self.dataset_start,
            self.validation_boundary,
            self.test_boundary,
            self.dataset_end,
        ))
        if not values[0] <= values[1] < values[2] <= values[3]:
            raise SplitError("Split boundaries must be ordered within the dataset extent.")

    def partition(self, timestamps: pd.Series | pd.DatetimeIndex | np.ndarray) -> np.ndarray:
        """Return the temporal partition for each timestamp without shuffling."""
        values = pd.to_datetime(timestamps, utc=True)
        if len(values) == 0:
            return np.asarray([], dtype="<U10")
        minimum = values.min()
        maximum = values.max()
        if minimum < _as_utc(self.dataset_start) or maximum > _as_utc(self.dataset_end):
            raise SplitError("Timestamps fall outside the declared dataset extent.")
        result = np.full(len(values), "test", dtype="<U10")
        result[values <= _as_utc(self.test_boundary)] = "validation"
        result[values <= _as_utc(self.validation_boundary)] = "train"
        return result

    def as_dict(self) -> dict[str, Any]:
        """Return exact boundaries and inclusion rules for a manifest."""
        return {
            "dataset_start": _iso(self.dataset_start),
            "train": {
                "start": _iso(self.dataset_start),
                "end": _iso(self.validation_boundary),
                "start_inclusive": True,
                "end_inclusive": True,
            },
            "validation": {
                "start_after": _iso(self.validation_boundary),
                "end": _iso(self.test_boundary),
                "start_inclusive": False,
                "end_inclusive": True,
            },
            "test": {
                "start_after": _iso(self.test_boundary),
                "end": _iso(self.dataset_end),
                "start_inclusive": False,
                "end_inclusive": True,
            },
            "dataset_end": _iso(self.dataset_end),
        }


def _as_utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _iso(value: Any) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def mission1_temporal_split(
    dataset_start: Any,
    dataset_end: Any,
    *,
    validation_boundary: Any = MISSION1_VALIDATION_BOUNDARY,
    test_boundary: Any = MISSION1_TEST_BOUNDARY,
) -> TemporalSplit:
    """Build the configured calendar split for Mission-1."""
    return TemporalSplit(
        dataset_start=_as_utc(dataset_start),
        validation_boundary=_as_utc(validation_boundary),
        test_boundary=_as_utc(test_boundary),
        dataset_end=_as_utc(dataset_end),
    )


def event_level_table(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse selected-channel label rows to one record per event ID."""
    required = {
        "event_id",
        "category",
        "class",
        "start_timestamp",
        "end_timestamp",
        "is_selected_channel",
    }
    missing = required.difference(events.columns)
    if missing:
        raise SplitError(f"Event table is missing columns: {sorted(missing)}")
    selected = events.loc[events["is_selected_channel"].astype(bool)].copy()
    if selected.empty:
        return pd.DataFrame(
            columns=["event_id", "category", "class", "start_timestamp", "end_timestamp"]
        )
    selected["start_timestamp"] = pd.to_datetime(selected["start_timestamp"], utc=True)
    selected["end_timestamp"] = pd.to_datetime(selected["end_timestamp"], utc=True)
    taxonomy_counts = selected.groupby("event_id", observed=True)[["category", "class"]].nunique()
    inconsistent = taxonomy_counts[(taxonomy_counts > 1).any(axis=1)]
    if not inconsistent.empty:
        raise SplitError("An event ID maps to more than one Category or Class.")
    return (
        selected.groupby("event_id", observed=True, as_index=False)
        .agg(
            category=("category", "first"),
            **{
                "class": ("class", "first"),
                "start_timestamp": ("start_timestamp", "min"),
                "end_timestamp": ("end_timestamp", "max"),
            },
        )
        .sort_values(["start_timestamp", "event_id"], kind="stable")
        .reset_index(drop=True)
    )


def assign_events_to_splits(events: pd.DataFrame, split: TemporalSplit) -> pd.DataFrame:
    """Assign each event ID by its earliest selected-channel StartTime."""
    event_rows = event_level_table(events)
    event_rows["split"] = split.partition(event_rows["start_timestamp"])
    event_rows["crosses_validation_boundary"] = (
        (event_rows["start_timestamp"] <= split.validation_boundary)
        & (event_rows["end_timestamp"] > split.validation_boundary)
    )
    event_rows["crosses_test_boundary"] = (
        (event_rows["start_timestamp"] <= split.test_boundary)
        & (event_rows["end_timestamp"] > split.test_boundary)
    )
    return event_rows


def _nested_counts(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    if frame.empty:
        return {}
    grouped = frame.groupby(columns, observed=True).size()
    output: dict[str, Any] = {}
    for keys, count in grouped.items():
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        node = output
        for key in key_tuple[:-1]:
            node = node.setdefault(str(key), {})
        node[str(key_tuple[-1])] = int(count)
    return output


def build_split_manifest(
    events: pd.DataFrame,
    split: TemporalSplit,
    *,
    dataset_manifest_sha256: str,
    telemetry_timestamps: pd.Series | pd.DatetimeIndex | np.ndarray | None = None,
) -> dict[str, Any]:
    """Build a deterministic split manifest from the prepared event table."""
    assigned = assign_events_to_splits(events, split)
    telemetry_rows = None
    if telemetry_timestamps is not None:
        parts = split.partition(telemetry_timestamps)
        unique_parts, counts = np.unique(parts, return_counts=True)
        telemetry_rows = {str(k): int(v) for k, v in zip(unique_parts, counts, strict=True)}

    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "protocol": "ESA Mission-1 first-half/second-half calendar split",
        "sample_assignment_rule": (
            "train <= 2006-10-01T00:00:00Z; validation is later and <= "
            "2007-01-01T00:00:00Z; test is later"
        ),
        "event_assignment_rule": "earliest selected-channel StartTime",
        "boundaries": split.as_dict(),
        "telemetry_rows_per_channel": telemetry_rows,
        "event_counts_by_split_and_category": _nested_counts(
            assigned, ["split", "category"]
        ),
        "event_class_distribution": _nested_counts(
            assigned, ["split", "category", "class"]
        ),
        "event_id_count": int(len(assigned)),
        "boundary_crossing_event_ids": {
            "validation": assigned.loc[
                assigned["crosses_validation_boundary"], "event_id"
            ].astype(str).tolist(),
            "test": assigned.loc[assigned["crosses_test_boundary"], "event_id"]
            .astype(str)
            .tolist(),
        },
    }
    return manifest


def write_split_manifest(
    events_path: Path,
    output_path: Path,
    split: TemporalSplit,
    *,
    dataset_manifest_sha256: str,
) -> dict[str, Any]:
    """Read prepared labels and write their deterministic split manifest."""
    events = pq.read_table(events_path).to_pandas()
    manifest = build_split_manifest(
        events,
        split,
        dataset_manifest_sha256=dataset_manifest_sha256,
    )
    write_json_deterministic(manifest, output_path)
    return manifest
