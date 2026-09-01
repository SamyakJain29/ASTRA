"""Event-recurrence and telecommand-proximity audits for prepared data."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from astra.data.splits import TemporalSplit, assign_events_to_splits, event_level_table

EVENT_CATEGORIES_FOR_COMMAND_AUDIT = ("Anomaly", "Rare Event")
DEFAULT_COMMAND_WINDOWS: dict[str, pd.Timedelta] = {
    "5 minutes": pd.Timedelta(minutes=5),
    "30 minutes": pd.Timedelta(minutes=30),
    "2 hours": pd.Timedelta(hours=2),
    "24 hours": pd.Timedelta(hours=24),
}


class AuditError(ValueError):
    """Raised when an audit input cannot be interpreted without assumptions."""


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise AuditError("Audit timestamps must not be missing.")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _utc_series(values: pd.Series, name: str) -> pd.Series:
    try:
        converted = pd.to_datetime(values, utc=True, errors="raise")
    except (TypeError, ValueError) as error:
        raise AuditError(f"Could not interpret {name} as timestamps: {error}") from error
    if converted.isna().any():
        raise AuditError(f"{name} contains missing timestamps.")
    return converted


def _iso(value: Any) -> str:
    return _utc_timestamp(value).isoformat().replace("+00:00", "Z")


def _nanoseconds(values: pd.Series) -> np.ndarray:
    """Return epoch nanoseconds independently of the source datetime unit."""
    return values.dt.as_unit("ns").astype("int64").to_numpy()


def _write_text_atomic(text: str, output_path: Path) -> None:
    output_path = Path(output_path)
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
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _split_counts(events: pd.DataFrame) -> dict[str, int]:
    counts = events["split"].value_counts()
    return {
        "train": int(counts.get("train", 0)),
        "validation": int(counts.get("validation", 0)),
        "test": int(counts.get("test", 0)),
    }


def aggregate_selected_event_ids(events: pd.DataFrame) -> pd.DataFrame:
    """Return one chronological row per event ID using selected-channel labels.

    The earliest selected-channel start and latest selected-channel end define the
    event-level interval. Taxonomy values must be consistent across every selected
    row for an ID; inconsistent source values are rejected instead of reconciled.
    """
    aggregated = event_level_table(events)
    if aggregated.empty:
        return aggregated
    aggregated["start_timestamp"] = _utc_series(
        aggregated["start_timestamp"], "event start_timestamp"
    )
    aggregated["end_timestamp"] = _utc_series(
        aggregated["end_timestamp"], "event end_timestamp"
    )
    if aggregated[["category", "class"]].isna().any().any():
        raise AuditError("Selected event rows contain missing Category or Class values.")
    return aggregated.sort_values(
        ["start_timestamp", "event_id"], kind="stable"
    ).reset_index(drop=True)


def build_event_recurrence_audit(
    events: pd.DataFrame,
    split: TemporalSplit,
) -> dict[str, Any]:
    """Summarize literal Category/Class recurrence without changing taxonomy."""
    assigned = assign_events_to_splits(events, split)
    if not assigned.empty:
        assigned["start_timestamp"] = _utc_series(
            assigned["start_timestamp"], "event start_timestamp"
        )
        assigned = assigned.sort_values(
            ["start_timestamp", "event_id"], kind="stable"
        ).reset_index(drop=True)
    if assigned[["category", "class"]].isna().any().any():
        raise AuditError("Selected event rows contain missing Category or Class values.")

    recurrence: list[dict[str, Any]] = []
    for (category, event_class), group in assigned.groupby(
        ["category", "class"], observed=True, sort=True
    ):
        chronological = group.sort_values(
            ["start_timestamp", "event_id"], kind="stable"
        )
        first = chronological.iloc[0]
        recurrence.append(
            {
                "category": str(category),
                "class": str(event_class),
                "event_id_count": int(len(chronological)),
                "first_occurrence": {
                    "event_id": str(first["event_id"]),
                    "start_timestamp": _iso(first["start_timestamp"]),
                    "split": str(first["split"]),
                },
                "later_occurrence_count": int(len(chronological) - 1),
                "split_distribution": _split_counts(chronological),
            }
        )

    category_counts = {
        str(category): int(count)
        for category, count in assigned.groupby("category", observed=True).size().items()
    }
    rare = assigned.loc[assigned["category"] == "Rare Event"]
    rare_groups = {
        str(event_class): group.sort_values(
            ["start_timestamp", "event_id"], kind="stable"
        )
        for event_class, group in rare.groupby("class", observed=True, sort=True)
    }
    recurrent_rare_classes = [
        event_class for event_class, group in rare_groups.items() if len(group) > 1
    ]
    train_seen_repeated_after_train = [
        event_class
        for event_class, group in rare_groups.items()
        if str(group.iloc[0]["split"]) == "train"
        and group["split"].isin(["validation", "test"]).any()
    ]
    training_side_classes = set(
        rare.loc[rare["split"].isin(["train", "validation"]), "class"].astype(str)
    )
    test_classes = set(rare.loc[rare["split"] == "test", "class"].astype(str))
    unseen_test_classes = sorted(test_classes - training_side_classes)

    return {
        "audit_version": 1,
        "event_scope": "one event ID aggregated from selected-channel label rows",
        "event_assignment_rule": "earliest selected-channel StartTime",
        "event_id_count": int(len(assigned)),
        "event_ids_by_category": category_counts,
        "category_class_recurrence": recurrence,
        "rare_event_summary": {
            "class_count": int(len(rare_groups)),
            "classes_occurring_more_than_once_count": int(len(recurrent_rare_classes)),
            "classes_occurring_more_than_once": sorted(recurrent_rare_classes),
            "classes_first_seen_in_train_and_repeated_after_train_count": int(
                len(train_seen_repeated_after_train)
            ),
            "classes_first_seen_in_train_and_repeated_after_train": sorted(
                train_seen_repeated_after_train
            ),
            "previously_unseen_classes_appearing_in_test_count": int(
                len(unseen_test_classes)
            ),
            "previously_unseen_classes_appearing_in_test": unseen_test_classes,
            "unseen_definition": (
                "a test Rare Event class absent from both train and validation"
            ),
        },
    }


def render_event_recurrence_report(audit: Mapping[str, Any]) -> str:
    """Render recurrence audit data as a compact Markdown report."""
    rare = audit["rare_event_summary"]
    category_counts = audit["event_ids_by_category"]
    lines = [
        "# Mission-1 Event-Class Recurrence",
        "",
        "This audit counts one event ID after aggregating its selected-channel label rows. ",
        "It preserves the literal ESA `Category` and `Class` values and does not implement ",
        "or simulate event memory.",
        "",
        "## Scope and rules",
        "",
        f"- Event IDs audited: {audit['event_id_count']:,}",
        "- Event timestamp: earliest selected-channel `StartTime` for the ID.",
        "- Split assignment: event timestamp, using the configured temporal boundaries.",
        "- Later occurrences: other event IDs with the same literal Category/Class after ",
        "  the first chronological occurrence.",
        "- Event IDs by literal Category: "
        + ", ".join(
            f"`{category}` = {count:,}"
            for category, count in sorted(category_counts.items())
        ),
        "",
        "## Category/Class recurrence",
        "",
        "| Category | Class | Event IDs | First event ID | First start | First split | "
        "Later occurrences | Train | Validation | Test |",
        "| --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in audit["category_class_recurrence"]:
        first = row["first_occurrence"]
        splits = row["split_distribution"]
        lines.append(
            f"| `{row['category']}` | `{row['class']}` | {row['event_id_count']:,} | "
            f"`{first['event_id']}` | `{first['start_timestamp']}` | {first['split']} | "
            f"{row['later_occurrence_count']:,} | {splits['train']:,} | "
            f"{splits['validation']:,} | {splits['test']:,} |"
        )
    lines.extend(
        [
            "",
            "## Rare Event recurrence",
            "",
            f"- Classes represented: {rare['class_count']:,}",
            "- Classes occurring more than once: "
            f"{rare['classes_occurring_more_than_once_count']:,} "
            f"(`{', '.join(rare['classes_occurring_more_than_once']) or 'none'}`)",
            "- Classes first seen in train and repeated after train: "
            f"{rare['classes_first_seen_in_train_and_repeated_after_train_count']:,} "
            "(`"
            + ", ".join(rare["classes_first_seen_in_train_and_repeated_after_train"])
            + "`)",
            "- Previously unseen Rare Event classes appearing in test: "
            f"{rare['previously_unseen_classes_appearing_in_test_count']:,} "
            f"(`{', '.join(rare['previously_unseen_classes_appearing_in_test']) or 'none'}`)",
            "",
            "Here, 'repeated after train' requires at least one validation or test event ID. "
            "'Previously unseen in test' means absent from both train and validation. These ",
            "counts describe recurrence only; they are not an Event Memory result.",
        ]
    )
    return "\n".join(lines)


def write_event_recurrence_report(
    events_path: Path,
    output_path: Path,
    split: TemporalSplit,
) -> dict[str, Any]:
    """Build and write a recurrence report from prepared event Parquet."""
    events = pq.read_table(events_path).to_pandas()
    audit = build_event_recurrence_audit(events, split)
    _write_text_atomic(render_event_recurrence_report(audit), output_path)
    return audit


def _normalized_windows(
    windows: Mapping[str, Any] | None,
) -> dict[str, pd.Timedelta]:
    source = DEFAULT_COMMAND_WINDOWS if windows is None else windows
    normalized: dict[str, pd.Timedelta] = {}
    for label, value in source.items():
        duration = pd.Timedelta(value)
        if duration <= pd.Timedelta(0):
            raise AuditError(f"Command window {label!r} must be positive.")
        normalized[str(label)] = duration
    if not normalized:
        raise AuditError("At least one command window is required.")
    return normalized


def _priority_key(value: Any) -> str:
    if pd.isna(value):
        return "<missing>"
    if isinstance(value, np.generic):
        value = value.item()
    return str(value)


def _delta_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum_seconds": None,
            "median_seconds": None,
            "mean_seconds": None,
            "maximum_seconds": None,
        }
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(len(array)),
        "minimum_seconds": float(array.min()),
        "median_seconds": float(np.median(array)),
        "mean_seconds": float(array.mean()),
        "maximum_seconds": float(array.max()),
    }


def build_telecommand_proximity_audit(
    events: pd.DataFrame,
    telecommands: pd.DataFrame,
    *,
    windows: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure preceding-command proximity for Anomaly and Rare Event IDs.

    Both endpoints of a preceding window are included. Counts by literal Priority
    are non-exclusive because one event can have commands from several priorities.
    The output is an association audit and makes no causal or semantic inference.
    """
    required_commands = {"telecommand", "timestamp", "priority"}
    missing_commands = required_commands.difference(telecommands.columns)
    if missing_commands:
        raise AuditError(f"Telecommand table is missing columns: {sorted(missing_commands)}")

    event_rows = aggregate_selected_event_ids(events)
    event_rows = event_rows.loc[
        event_rows["category"].isin(EVENT_CATEGORIES_FOR_COMMAND_AUDIT)
    ].copy()
    event_rows = event_rows.sort_values(
        ["start_timestamp", "event_id"], kind="stable"
    ).reset_index(drop=True)
    command_rows = telecommands.loc[:, ["telecommand", "timestamp", "priority"]].copy()
    command_rows["timestamp"] = _utc_series(command_rows["timestamp"], "telecommand timestamp")
    command_rows["priority_key"] = command_rows["priority"].map(_priority_key)
    command_rows["telecommand"] = command_rows["telecommand"].astype(str)
    command_rows = command_rows.sort_values(
        ["timestamp", "telecommand", "priority_key"], kind="stable"
    ).reset_index(drop=True)

    normalized_windows = _normalized_windows(windows)
    command_times = _nanoseconds(command_rows["timestamp"])
    event_times = _nanoseconds(event_rows["start_timestamp"])
    priorities = sorted(command_rows["priority_key"].unique().tolist())
    priority_times = {
        priority: command_rows.loc[
            command_rows["priority_key"] == priority, "timestamp"
        ]
        .dt.as_unit("ns")
        .astype("int64")
        .to_numpy()
        for priority in priorities
    }

    upper_indices = np.searchsorted(command_times, event_times, side="right")
    nearest_deltas: list[float | None] = []
    for event_time, upper in zip(event_times, upper_indices, strict=True):
        if upper == 0:
            nearest_deltas.append(None)
        else:
            nearest_deltas.append(float((event_time - command_times[upper - 1]) / 1e9))

    window_hits: dict[str, np.ndarray] = {}
    priority_window_hits: dict[str, dict[str, np.ndarray]] = {
        priority: {} for priority in priorities
    }
    for label, duration in normalized_windows.items():
        duration_ns = int(duration.value)
        lower = np.searchsorted(command_times, event_times - duration_ns, side="left")
        window_hits[label] = upper_indices > lower
        for priority, timestamps in priority_times.items():
            priority_upper = np.searchsorted(timestamps, event_times, side="right")
            priority_lower = np.searchsorted(
                timestamps, event_times - duration_ns, side="left"
            )
            priority_window_hits[priority][label] = priority_upper > priority_lower

    categories: dict[str, Any] = {}
    event_details: list[dict[str, Any]] = []
    for row_index, row in event_rows.iterrows():
        detail = {
            "event_id": str(row["event_id"]),
            "category": str(row["category"]),
            "start_timestamp": _iso(row["start_timestamp"]),
            "nearest_preceding_delta_seconds": nearest_deltas[row_index],
            "window_hits": {
                label: bool(hits[row_index]) for label, hits in window_hits.items()
            },
            "priorities_with_command_by_window": {
                label: [
                    priority
                    for priority in priorities
                    if priority_window_hits[priority][label][row_index]
                ]
                for label in normalized_windows
            },
        }
        event_details.append(detail)

    for category in EVENT_CATEGORIES_FOR_COMMAND_AUDIT:
        category_mask = event_rows["category"].to_numpy() == category
        category_total = int(category_mask.sum())
        category_deltas = [
            delta
            for delta, selected in zip(nearest_deltas, category_mask, strict=True)
            if selected and delta is not None
        ]
        window_summaries: dict[str, Any] = {}
        for label, duration in normalized_windows.items():
            hit_count = int((window_hits[label] & category_mask).sum())
            window_summaries[label] = {
                "duration_seconds": float(duration.total_seconds()),
                "event_ids_with_command_count": hit_count,
                "event_id_rate": hit_count / category_total if category_total else 0.0,
                "event_ids_with_command_by_priority": {
                    priority: int(
                        (priority_window_hits[priority][label] & category_mask).sum()
                    )
                    for priority in priorities
                },
            }
        categories[category] = {
            "event_id_count": category_total,
            "event_ids_with_any_preceding_command_count": int(len(category_deltas)),
            "nearest_preceding_delta_summary": _delta_summary(category_deltas),
            "windows": window_summaries,
        }

    return {
        "audit_version": 1,
        "event_scope": "one event ID aggregated from selected-channel label rows",
        "event_start_rule": "earliest selected-channel StartTime",
        "timezone_rule": (
            "timezone-naive timestamps localized to UTC; timezone-aware timestamps converted to UTC"
        ),
        "window_rule": (
            "telecommand timestamp is within the inclusive interval "
            "[event start - window, event start]"
        ),
        "priority_breakdown_rule": (
            "non-exclusive event-ID counts by literal Priority; an event can appear in multiple priorities"
        ),
        "interpretation": "temporal association only; no causality or command meaning inferred",
        "telecommand_execution_count": int(len(command_rows)),
        "telecommand_type_count": int(command_rows["telecommand"].nunique()),
        "literal_priorities": priorities,
        "categories": categories,
        "event_details": event_details,
    }


def _format_seconds(value: float | int | None) -> str:
    if value is None:
        return "not available"
    return f"{float(value):,.6f}"


def render_telecommand_proximity_report(audit: Mapping[str, Any]) -> str:
    """Render telecommand-proximity audit data as Markdown."""
    lines = [
        "# Mission-1 Telecommand Proximity Audit",
        "",
        "This report measures temporal proximity only. It does not establish causality, ",
        "infer telecommand meaning, or treat literal `Priority` as operational severity ",
        "or urgency.",
        "",
        "## Scope and rules",
        "",
        f"- Telecommand executions: {audit['telecommand_execution_count']:,}",
        f"- Telecommand types represented: {audit['telecommand_type_count']:,}",
        "- Event start: earliest selected-channel `StartTime` for each event ID.",
        "- Preceding windows include both endpoints: `[event start - window, event start]`.",
        "- Naive timestamps are localized to UTC; aware timestamps are converted to UTC.",
        "- Literal-Priority counts are non-exclusive: an event ID can be counted under ",
        "  several priorities in the same window.",
        "",
        "## Events with a preceding telecommand",
        "",
        "| Category | Event IDs | Window | Event IDs with command | Rate |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for category in EVENT_CATEGORIES_FOR_COMMAND_AUDIT:
        summary = audit["categories"][category]
        for label, window in summary["windows"].items():
            lines.append(
                f"| `{category}` | {summary['event_id_count']:,} | {label} | "
                f"{window['event_ids_with_command_count']:,} | "
                f"{window['event_id_rate']:.2%} |"
            )
    lines.extend(
        [
            "",
            "## Non-exclusive breakdown by literal Priority",
            "",
            "| Category | Window | Literal Priority | Event IDs with command |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for category in EVENT_CATEGORIES_FOR_COMMAND_AUDIT:
        summary = audit["categories"][category]
        for label, window in summary["windows"].items():
            for priority, count in window["event_ids_with_command_by_priority"].items():
                lines.append(f"| `{category}` | {label} | `{priority}` | {count:,} |")

    lines.extend(
        [
            "",
            "## Nearest preceding execution",
            "",
            "Nearest means the latest telecommand execution at or before event start. "
            "Differences are measured in seconds.",
            "",
            "| Category | Event IDs with preceding command | Minimum | Median | Mean | Maximum |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for category in EVENT_CATEGORIES_FOR_COMMAND_AUDIT:
        delta = audit["categories"][category]["nearest_preceding_delta_summary"]
        lines.append(
            f"| `{category}` | {delta['count']:,} | "
            f"{_format_seconds(delta['minimum_seconds'])} | "
            f"{_format_seconds(delta['median_seconds'])} | "
            f"{_format_seconds(delta['mean_seconds'])} | "
            f"{_format_seconds(delta['maximum_seconds'])} |"
        )

    lines.extend(
        [
            "",
            "## Event-level nearest differences",
            "",
            "| Category | Event ID | Event start (UTC) | Nearest preceding difference (seconds) |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for event in audit["event_details"]:
        lines.append(
            f"| `{event['category']}` | `{event['event_id']}` | "
            f"`{event['start_timestamp']}` | "
            f"{_format_seconds(event['nearest_preceding_delta_seconds'])} |"
        )
    lines.extend(
        [
            "",
            "These measurements are descriptive associations. They must not be interpreted "
            "as evidence that a telecommand caused, prevented, or explains an event.",
        ]
    )
    return "\n".join(lines)


def write_telecommand_proximity_report(
    events_path: Path,
    telecommands_path: Path,
    output_path: Path,
    *,
    windows: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and write a command-proximity report from prepared Parquet files."""
    events = pq.read_table(events_path).to_pandas()
    telecommands = pq.read_table(
        telecommands_path,
        columns=["telecommand", "timestamp", "priority"],
    ).to_pandas()
    audit = build_telecommand_proximity_audit(events, telecommands, windows=windows)
    _write_text_atomic(render_telecommand_proximity_report(audit), output_path)
    return audit
