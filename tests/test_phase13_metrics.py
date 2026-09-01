"""Hand-calculated synthetic tests for Phase 1.3 event-wise evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astra.evaluation.metrics import (
    Interval,
    corrected_event_wise_f0_5,
    evaluate_modes,
    group_prediction_samples,
    timestamp_ns,
)

EVALUATION_START = "2000-01-01T00:00:00Z"
EVALUATION_END = "2000-01-01T00:01:40Z"


def _event(
    event_id: str,
    category: str,
    start_seconds: int,
    end_seconds: int,
) -> dict[str, object]:
    origin = pd.Timestamp(EVALUATION_START)
    return {
        "event_id": event_id,
        "category": category,
        "start_timestamp": origin + pd.Timedelta(seconds=start_seconds),
        "end_timestamp": origin + pd.Timedelta(seconds=end_seconds),
        "is_selected_channel": True,
    }


def _events(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _interval(start_seconds: int, end_seconds: int) -> Interval:
    origin_ns = timestamp_ns(EVALUATION_START)
    return Interval(
        origin_ns + start_seconds * 1_000_000_000,
        origin_ns + end_seconds * 1_000_000_000,
    )


def _score(
    predictions: list[Interval],
    events: pd.DataFrame,
    *,
    positive_categories: set[str] | None = None,
    masked_categories: set[str] | None = None,
):
    return corrected_event_wise_f0_5(
        predictions,
        events,
        positive_categories=positive_categories or {"Anomaly"},
        evaluation_start=EVALUATION_START,
        evaluation_end=EVALUATION_END,
        masked_categories=masked_categories,
    )


def test_prediction_grouping_splits_irregular_samples_at_max_gap() -> None:
    timestamps = pd.to_datetime(
        [
            "2000-01-01T00:00:00Z",
            "2000-01-01T00:00:01Z",
            "2000-01-01T00:00:10Z",
            "2000-01-01T00:00:11Z",
        ],
        utc=True,
    )

    intervals = group_prediction_samples(
        timestamps,
        np.array([True, True, True, False]),
        max_gap="2s",
    )

    origin_ns = timestamp_ns(EVALUATION_START)
    assert intervals == [
        Interval(origin_ns, origin_ns + 3_000_000_000),
        Interval(origin_ns + 10_000_000_000, origin_ns + 11_000_000_000 - 1),
    ]


def test_corrected_metric_perfect_detection() -> None:
    events = _events(_event("anomaly-1", "Anomaly", 10, 20))

    result = _score([_interval(10, 20)], events)

    assert result.event_true_positives == 1
    assert result.event_false_positives == 0
    assert result.event_false_negatives == 0
    assert result.false_positive_time_ns == 0
    assert result.corrected_event_precision == pytest.approx(1.0)
    assert result.event_recall == pytest.approx(1.0)
    assert result.corrected_event_f0_5 == pytest.approx(1.0)


def test_corrected_metric_missed_event() -> None:
    events = _events(_event("anomaly-1", "Anomaly", 10, 20))

    result = _score([], events)

    assert result.event_true_positives == 0
    assert result.event_false_positives == 0
    assert result.event_false_negatives == 1
    assert result.corrected_event_precision == 0.0
    assert result.event_recall == 0.0
    assert result.corrected_event_f0_5 == 0.0


def test_corrected_metric_one_false_positive_matches_hand_calculation() -> None:
    events = _events(_event("anomaly-1", "Anomaly", 10, 20))

    result = _score([_interval(10, 20), _interval(30, 40)], events)

    nominal_time_ns = 90_000_000_000 - 2
    false_positive_time_ns = 10_000_000_000
    expected_tnr = 1.0 - false_positive_time_ns / nominal_time_ns
    expected_precision = 0.5 * expected_tnr
    expected_f0_5 = 1.25 * expected_precision / (0.25 * expected_precision + 1.0)
    assert result.event_true_positives == 1
    assert result.event_false_positives == 1
    assert result.event_false_negatives == 0
    assert result.false_positive_time_ns == false_positive_time_ns
    assert result.nominal_time_ns == nominal_time_ns
    assert result.time_true_negative_rate == pytest.approx(expected_tnr)
    assert result.corrected_event_precision == pytest.approx(expected_precision)
    assert result.event_recall == pytest.approx(1.0)
    assert result.corrected_event_f0_5 == pytest.approx(expected_f0_5)


def test_repeated_predictions_inside_one_event_count_as_one_event_detection() -> None:
    events = _events(_event("anomaly-1", "Anomaly", 10, 30))

    result = _score([_interval(11, 12), _interval(20, 21)], events)

    assert result.event_true_positives == 1
    assert result.event_false_positives == 0
    assert result.event_false_negatives == 0
    assert result.corrected_event_f0_5 == pytest.approx(1.0)


def test_closed_event_boundary_counts_as_overlap() -> None:
    events = _events(_event("anomaly-1", "Anomaly", 10, 20))

    result = _score([_interval(20, 20)], events)

    assert result.event_true_positives == 1
    assert result.event_false_negatives == 0


def test_communication_gap_is_masked_and_reported_separately() -> None:
    events = _events(
        _event("anomaly-1", "Anomaly", 10, 20),
        _event("gap-1", "Communication Gap", 30, 40),
    )
    gap_prediction = [_interval(32, 34)]

    corrected = _score(
        gap_prediction,
        events,
        masked_categories={"Communication Gap"},
    )
    modes = evaluate_modes(
        gap_prediction,
        events,
        evaluation_start=EVALUATION_START,
        evaluation_end=EVALUATION_END,
    )

    assert corrected.event_true_positives == 0
    assert corrected.event_false_positives == 0
    assert corrected.event_false_negatives == 1
    assert corrected.false_positive_time_ns == 0
    operational = modes["astra_operational"]
    assert operational["communication_gap_event_predictions"] == 1
    assert operational["communication_gap_event_count"] == 1
    assert operational["false_alarm_intervals_outside_all_labelled_events"] == 0


def test_rare_event_is_positive_only_in_esa_mode() -> None:
    events = _events(
        _event("anomaly-1", "Anomaly", 10, 20),
        _event("rare-1", "Rare Event", 30, 40),
    )
    predictions = [_interval(12, 13), _interval(32, 33)]

    modes = evaluate_modes(
        predictions,
        events,
        evaluation_start=EVALUATION_START,
        evaluation_end=EVALUATION_END,
    )

    esa = modes["esa_unusual_event"]
    assert esa["event_true_positives"] == 2
    assert esa["event_false_negatives"] == 0
    assert esa["event_recall"] == pytest.approx(1.0)

    operational = modes["astra_operational"]
    assert operational["genuine_anomaly_event_true_positives"] == 1
    assert operational["genuine_anomaly_event_false_negatives"] == 0
    assert operational["genuine_anomaly_recall"] == pytest.approx(1.0)
    assert operational["genuine_anomaly_precision"] == pytest.approx(0.5)
    assert operational["detected_rare_event_count"] == 1
    assert operational["total_rare_event_count"] == 1
    assert operational["rare_event_alarm_rate"] == pytest.approx(1.0)
