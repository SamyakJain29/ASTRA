"""Synthetic tests for Phase 1.3 temporal splits and statistical baselines."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astra.data.splits import (
    MISSION1_TEST_BOUNDARY,
    MISSION1_VALIDATION_BOUNDARY,
    mission1_temporal_split,
)
from astra.models.baselines import GlobalStdDetector, MedianMadDetector, NoAlarmDetector


def test_temporal_split_preserves_irregular_input_order() -> None:
    """Partitioning is timestamp-based and never shuffles irregular observations."""
    split = mission1_temporal_split(
        "2000-01-01T00:00:00Z",
        "2000-01-04T00:00:00Z",
        validation_boundary="2000-01-02T00:00:00Z",
        test_boundary="2000-01-03T00:00:00Z",
    )
    timestamps = pd.to_datetime(
        [
            "2000-01-03T18:07:11Z",
            "2000-01-01T00:00:03Z",
            "2000-01-02T12:41:00Z",
            "2000-01-01T19:13:29Z",
        ],
        utc=True,
    )

    assert split.partition(timestamps).tolist() == [
        "test",
        "train",
        "validation",
        "train",
    ]


def test_official_mission1_boundaries_use_published_inclusivity() -> None:
    """Each boundary belongs to the earlier partition; the next nanosecond does not."""
    split = mission1_temporal_split(
        "2000-01-01T00:00:00Z",
        "2013-12-31T23:59:59Z",
    )
    timestamps = pd.DatetimeIndex(
        [
            MISSION1_VALIDATION_BOUNDARY - pd.Timedelta(1, unit="ns"),
            MISSION1_VALIDATION_BOUNDARY,
            MISSION1_VALIDATION_BOUNDARY + pd.Timedelta(1, unit="ns"),
            MISSION1_TEST_BOUNDARY,
            MISSION1_TEST_BOUNDARY + pd.Timedelta(1, unit="ns"),
        ]
    )

    assert split.partition(timestamps).tolist() == [
        "train",
        "train",
        "validation",
        "validation",
        "test",
    ]


def test_global_std_fits_only_training_partition() -> None:
    """Future validation and test outliers cannot influence fitted statistics."""
    split = mission1_temporal_split(
        "2000-01-01T00:00:00Z",
        "2000-01-04T00:00:00Z",
        validation_boundary="2000-01-02T00:00:00Z",
        test_boundary="2000-01-03T00:00:00Z",
    )
    timestamps = pd.DatetimeIndex(
        [
            pd.Timestamp("2000-01-01T00:00:01Z"),
            pd.Timestamp("2000-01-01T16:31:09Z"),
            pd.Timestamp("2000-01-02T00:00:00Z") + pd.Timedelta(1, unit="ns"),
            pd.Timestamp("2000-01-03T00:00:00Z") + pd.Timedelta(1, unit="ns"),
        ]
    )
    values = np.array([0.0, 2.0, 1_000.0, 10_000.0])
    partitions = split.partition(timestamps)

    detector = GlobalStdDetector(threshold=3.0).fit(values[partitions == "train"])

    assert detector.training_count_ == 2
    assert detector.center_ == pytest.approx(1.0)
    assert detector.scale_ == pytest.approx(1.0)
    assert detector.predict(values[partitions == "test"]).tolist() == [True]


def test_median_mad_uses_training_median_and_scaled_mad() -> None:
    """MAD fitting ignores non-finite values and applies its configured scale."""
    detector = MedianMadDetector(threshold=2.0).fit(
        np.array([-2.0, -1.0, 0.0, 1.0, 2.0, np.nan])
    )

    assert detector.training_count_ == 5
    assert detector.center_ == pytest.approx(0.0)
    assert detector.raw_mad_ == pytest.approx(1.0)
    assert detector.scale_ == pytest.approx(1.4826)
    assert detector.predict(np.array([2.0, 3.0, np.nan])).tolist() == [False, True, False]


def test_median_mad_zero_dispersion_flags_only_deviations() -> None:
    detector = MedianMadDetector().fit(np.array([4.0, 4.0, 4.0]))

    assert detector.scale_ == 0.0
    assert detector.predict(np.array([4.0, 4.1, np.nan])).tolist() == [False, True, False]


def test_no_alarm_detector_always_returns_boolean_zeros() -> None:
    values = np.array([1.0, np.nan, -8.0])

    predictions = NoAlarmDetector().fit(values).predict(values)

    assert predictions.dtype == np.bool_
    assert predictions.tolist() == [False, False, False]
