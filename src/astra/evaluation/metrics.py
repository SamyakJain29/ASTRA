"""Event-wise evaluation for the irregular Mission-1 research subset.

The corrected event-wise formula follows ESA-ADB, while ASTRA's sample-to-interval
conversion remains explicitly local because this project preserves the source
timestamps instead of reproducing ESA's 30-second resampling pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

NANOSECOND = 1


@dataclass(frozen=True, order=True)
class Interval:
    """Closed integer-nanosecond interval."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.end_ns < self.start_ns:
            raise ValueError("An interval cannot end before it starts.")

    @property
    def duration_ns(self) -> int:
        """Continuous duration; a point interval has zero duration."""
        return self.end_ns - self.start_ns


@dataclass(frozen=True)
class CorrectedEventMetrics:
    """Published ESA corrected event-wise components and scores."""

    event_true_positives: int
    event_false_positives: int
    event_false_negatives: int
    false_positive_time_ns: int
    nominal_time_ns: int
    time_true_negative_rate: float
    corrected_event_precision: float
    event_recall: float
    corrected_event_f0_5: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def timestamp_ns(value: Any) -> int:
    """Convert a timestamp to UTC integer nanoseconds without local-time coercion."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.value)


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """Return sorted, overlapping or adjacent closed intervals as a union."""
    ordered = sorted(intervals)
    if not ordered:
        return []
    merged = [ordered[0]]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start_ns <= previous.end_ns + NANOSECOND:
            merged[-1] = Interval(previous.start_ns, max(previous.end_ns, current.end_ns))
        else:
            merged.append(current)
    return merged


def group_prediction_samples(
    timestamps: pd.DatetimeIndex | pd.Series | np.ndarray,
    predictions: np.ndarray,
    *,
    max_gap: pd.Timedelta | timedelta | str | None,
) -> list[Interval]:
    """Convert Boolean samples to ASTRA-local prediction intervals.

    A positive state extends to one nanosecond before the next negative sample,
    matching ESA's half-open state-change convention on a nanosecond timeline.
    A positive state is split and capped when the next observation is farther away
    than ``max_gap``. A terminal positive state ends at its final observed timestamp.
    """
    raw_times = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)).as_unit("ns")
    time_values = np.asarray(raw_times.asi8, dtype=np.int64)
    states = np.asarray(predictions, dtype=bool).reshape(-1)
    if len(time_values) != len(states):
        raise ValueError("Timestamps and predictions must have the same length.")
    if len(time_values) == 0 or not states.any():
        return []
    if np.any(np.diff(time_values) <= 0):
        raise ValueError("Prediction timestamps must be strictly increasing.")
    gap_ns = None if max_gap is None else int(pd.Timedelta(max_gap).value)
    if gap_ns is not None and gap_ns <= 0:
        raise ValueError("max_gap must be positive when provided.")

    positive = np.flatnonzero(states)
    begins = np.ones(len(positive), dtype=bool)
    if len(positive) > 1:
        adjacent = positive[1:] == positive[:-1] + 1
        within_gap = np.ones(len(positive) - 1, dtype=bool)
        if gap_ns is not None:
            within_gap = (time_values[positive[1:]] - time_values[positive[:-1]]) <= gap_ns
        begins[1:] = ~(adjacent & within_gap)
    group_starts = np.flatnonzero(begins)
    group_ends = np.r_[group_starts[1:] - 1, len(positive) - 1]

    intervals: list[Interval] = []
    for start_position, end_position in zip(group_starts, group_ends, strict=True):
        first_index = int(positive[start_position])
        last_index = int(positive[end_position])
        start_ns = int(time_values[first_index])
        if last_index + 1 < len(time_values) and not states[last_index + 1] or last_index + 1 < len(time_values):
            end_ns = int(time_values[last_index + 1]) - NANOSECOND
        else:
            end_ns = int(time_values[last_index])
        if gap_ns is not None:
            end_ns = min(end_ns, int(time_values[last_index]) + gap_ns)
        intervals.append(Interval(start_ns, max(start_ns, end_ns)))
    return intervals


def subtract_intervals(
    intervals: Iterable[Interval], masks: Iterable[Interval]
) -> list[Interval]:
    """Subtract closed mask intervals from closed input intervals."""
    remaining: list[Interval] = []
    mask_union = merge_intervals(masks)
    for interval in merge_intervals(intervals):
        fragments = [interval]
        for mask in mask_union:
            if mask.end_ns < interval.start_ns:
                continue
            if mask.start_ns > interval.end_ns:
                break
            updated: list[Interval] = []
            for fragment in fragments:
                if mask.end_ns < fragment.start_ns or mask.start_ns > fragment.end_ns:
                    updated.append(fragment)
                    continue
                if fragment.start_ns < mask.start_ns:
                    updated.append(Interval(fragment.start_ns, mask.start_ns - NANOSECOND))
                if mask.end_ns < fragment.end_ns:
                    updated.append(Interval(mask.end_ns + NANOSECOND, fragment.end_ns))
            fragments = updated
        remaining.extend(fragments)
    return merge_intervals(remaining)


def clip_intervals(
    intervals: Iterable[Interval], start_ns: int, end_ns: int
) -> list[Interval]:
    """Clip intervals to a closed evaluation range."""
    if end_ns < start_ns:
        raise ValueError("Evaluation end cannot precede evaluation start.")
    return [
        Interval(max(interval.start_ns, start_ns), min(interval.end_ns, end_ns))
        for interval in merge_intervals(intervals)
        if interval.end_ns >= start_ns and interval.start_ns <= end_ns
    ]


def _prepared_event_rows(events: pd.DataFrame) -> pd.DataFrame:
    required = {"event_id", "category", "start_timestamp", "end_timestamp"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Event table is missing columns: {sorted(missing)}")
    selected = events.copy()
    if "is_selected_channel" in selected.columns:
        selected = selected.loc[selected["is_selected_channel"].astype(bool)].copy()
    selected["start_ns"] = selected["start_timestamp"].map(timestamp_ns)
    selected["end_ns"] = selected["end_timestamp"].map(timestamp_ns)
    if (selected["end_ns"] < selected["start_ns"]).any():
        raise ValueError("An event label ends before it starts.")
    return selected


def event_interval_map(
    events: pd.DataFrame,
    *,
    categories: set[str] | None = None,
) -> dict[str, list[Interval]]:
    """Return the union of selected-channel closed intervals for each event ID."""
    selected = _prepared_event_rows(events)
    if categories is not None:
        selected = selected.loc[selected["category"].isin(categories)]
    return {
        str(event_id): merge_intervals(
            Interval(int(row.start_ns), int(row.end_ns))
            for row in group.itertuples(index=False)
        )
        for event_id, group in selected.groupby("event_id", observed=True, sort=True)
    }


def category_intervals(events: pd.DataFrame, categories: set[str]) -> list[Interval]:
    """Return the union of all selected-channel intervals in literal categories."""
    selected = _prepared_event_rows(events)
    selected = selected.loc[selected["category"].isin(categories)]
    return merge_intervals(
        Interval(int(row.start_ns), int(row.end_ns))
        for row in selected.itertuples(index=False)
    )


def _detected_event_ids(
    predictions: list[Interval], event_map: dict[str, list[Interval]]
) -> set[str]:
    if not predictions:
        return set()
    pred_starts = np.fromiter((item.start_ns for item in predictions), dtype=np.int64)
    pred_ends = np.fromiter((item.end_ns for item in predictions), dtype=np.int64)
    detected: set[str] = set()
    for event_id, intervals in event_map.items():
        for interval in intervals:
            candidate = int(np.searchsorted(pred_ends, interval.start_ns, side="left"))
            if candidate < len(predictions) and pred_starts[candidate] <= interval.end_ns:
                detected.add(event_id)
                break
    return detected


def _clip_event_map(
    event_map: dict[str, list[Interval]], start_ns: int, end_ns: int
) -> dict[str, list[Interval]]:
    return {
        event_id: clipped
        for event_id, intervals in event_map.items()
        if (clipped := clip_intervals(intervals, start_ns, end_ns))
    }


def _overlap_flags(predictions: list[Interval], labels: list[Interval]) -> np.ndarray:
    if not predictions or not labels:
        return np.zeros(len(predictions), dtype=bool)
    label_starts = np.fromiter((item.start_ns for item in labels), dtype=np.int64)
    label_ends = np.fromiter((item.end_ns for item in labels), dtype=np.int64)
    flags = np.zeros(len(predictions), dtype=bool)
    for index, prediction in enumerate(predictions):
        candidate = int(np.searchsorted(label_ends, prediction.start_ns, side="left"))
        flags[index] = candidate < len(labels) and label_starts[candidate] <= prediction.end_ns
    return flags


def _duration(intervals: Iterable[Interval]) -> int:
    return sum(interval.duration_ns for interval in merge_intervals(intervals))


def corrected_event_wise_f0_5(
    predictions: Iterable[Interval],
    events: pd.DataFrame,
    *,
    positive_categories: set[str],
    evaluation_start: Any,
    evaluation_end: Any,
    masked_categories: set[str] | None = None,
    beta: float = 0.5,
) -> CorrectedEventMetrics:
    """Calculate ESA's corrected event-wise formula on ASTRA-local intervals."""
    if beta <= 0:
        raise ValueError("beta must be positive.")
    start_ns = timestamp_ns(evaluation_start)
    end_ns = timestamp_ns(evaluation_end)
    raw_predictions = clip_intervals(predictions, start_ns, end_ns)
    masked = category_intervals(events, masked_categories or set())
    evaluated_predictions = subtract_intervals(raw_predictions, masked)

    positive_events = _clip_event_map(
        event_interval_map(events, categories=positive_categories), start_ns, end_ns
    )
    detected = _detected_event_ids(evaluated_predictions, positive_events)
    true_positives = len(detected)
    false_negatives = len(positive_events) - true_positives

    all_labels = category_intervals(
        events, set(_prepared_event_rows(events)["category"].astype(str).unique())
    )
    matched_any = _overlap_flags(evaluated_predictions, all_labels)
    false_positives = int((~matched_any).sum())

    evaluation_domain = [Interval(start_ns, end_ns)]
    nominal_intervals = subtract_intervals(evaluation_domain, all_labels)
    nominal_time = _duration(nominal_intervals)
    false_positive_time = _duration(subtract_intervals(evaluated_predictions, all_labels))
    time_tnr = 1.0 if nominal_time == 0 else max(0.0, 1.0 - false_positive_time / nominal_time)
    event_precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    corrected_precision = event_precision * time_tnr
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    denominator = beta * beta * corrected_precision + recall
    f_beta = (
        (1.0 + beta * beta) * corrected_precision * recall / denominator
        if denominator
        else 0.0
    )
    return CorrectedEventMetrics(
        event_true_positives=true_positives,
        event_false_positives=false_positives,
        event_false_negatives=false_negatives,
        false_positive_time_ns=false_positive_time,
        nominal_time_ns=nominal_time,
        time_true_negative_rate=time_tnr,
        corrected_event_precision=corrected_precision,
        event_recall=recall,
        corrected_event_f0_5=f_beta,
    )


def evaluate_modes(
    predictions: Iterable[Interval],
    events: pd.DataFrame,
    *,
    evaluation_start: Any,
    evaluation_end: Any,
    beta: float = 0.5,
) -> dict[str, Any]:
    """Evaluate ESA unusual-event and ASTRA operational modes explicitly."""
    raw_predictions = merge_intervals(predictions)
    esa = corrected_event_wise_f0_5(
        raw_predictions,
        events,
        positive_categories={"Anomaly", "Rare Event"},
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        masked_categories={"Communication Gap"},
        beta=beta,
    )
    anomaly_score = corrected_event_wise_f0_5(
        raw_predictions,
        events,
        positive_categories={"Anomaly"},
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        masked_categories={"Communication Gap"},
        beta=beta,
    )
    gap_intervals = category_intervals(events, {"Communication Gap"})
    evaluated_predictions = subtract_intervals(
        clip_intervals(
            raw_predictions, timestamp_ns(evaluation_start), timestamp_ns(evaluation_end)
        ),
        gap_intervals,
    )
    range_start_ns = timestamp_ns(evaluation_start)
    range_end_ns = timestamp_ns(evaluation_end)
    rare_map = _clip_event_map(
        event_interval_map(events, categories={"Rare Event"}),
        range_start_ns,
        range_end_ns,
    )
    gap_map = _clip_event_map(
        event_interval_map(events, categories={"Communication Gap"}),
        range_start_ns,
        range_end_ns,
    )
    detected_rare = _detected_event_ids(evaluated_predictions, rare_map)
    clipped_raw_predictions = clip_intervals(
        raw_predictions, timestamp_ns(evaluation_start), timestamp_ns(evaluation_end)
    )
    detected_gaps = _detected_event_ids(clipped_raw_predictions, gap_map)
    anomaly_tp = anomaly_score.event_true_positives
    burden = (
        anomaly_tp + len(detected_rare) + anomaly_score.event_false_positives
    )
    anomaly_precision = anomaly_tp / burden if burden else 0.0

    return {
        "implementation_status": "ASTRA-local interval conversion; ESA corrected formula",
        "esa_unusual_event": esa.as_dict(),
        "astra_operational": {
            "genuine_anomaly_event_true_positives": anomaly_tp,
            "genuine_anomaly_event_false_negatives": anomaly_score.event_false_negatives,
            "genuine_anomaly_recall": anomaly_score.event_recall,
            "genuine_anomaly_precision": anomaly_precision,
            "detected_rare_event_count": len(detected_rare),
            "total_rare_event_count": len(rare_map),
            "rare_event_alarm_rate": len(detected_rare) / len(rare_map) if rare_map else 0.0,
            "false_alarm_intervals_outside_all_labelled_events": (
                anomaly_score.event_false_positives
            ),
            "false_positive_time_ns_outside_all_labelled_events": (
                anomaly_score.false_positive_time_ns
            ),
            "communication_gap_event_predictions": len(detected_gaps),
            "communication_gap_event_count": len(gap_map),
        },
    }
