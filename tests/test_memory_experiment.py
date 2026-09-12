"""Sequential detector-to-memory experiment accounting checks."""

from unittest.mock import Mock

import numpy as np
import pytest
from scripts.run_memory_experiment import (
    apply_event_memory,
    detector_alarm_from_scores,
    render_report,
    summarize_experiment,
)

from astra.features.event_signature import EventSignature
from astra.memory.event_memory import AdaptiveEventMemory
from astra.models.baselines import GlobalStdDetector, MultiChannelSpacecraftDetector


def make_signature(score: float = 4.0) -> EventSignature:
    return EventSignature(
        event_id="synthetic-test-event",
        start_timestamp="2007-02-01T00:00:00Z",
        end_timestamp="2007-02-01T00:01:00Z",
        duration_seconds=60.0,
        affected_channels=["channel_41"],
        num_affected_channels=1,
        telemetry_features={"agg_score_max": score},
        context_features={"nearest_tc_diff_sec": 10.0, "tc_count_5m": 1.0},
        feature_vector=[score, 60.0],
        feature_names=["score", "duration"],
    )


@pytest.mark.parametrize("values, expected", [
    ([], False),
    ([0.0, 3.0, -3.0], False),
    ([0.0, 3.01], True),
    ([-3.01], True),
])
def test_alarm_matches_real_detector_predictions(values, expected):
    detector = MultiChannelSpacecraftDetector(["channel_41", "channel_42"], threshold=3.0)
    detector.fit({channel: np.array([-1.0, 1.0]) for channel in detector.channel_names})
    samples = {"channel_41": np.array([0.0]), "channel_42": np.array(values)}
    assert detector_alarm_from_scores(detector.score_channels(samples), detector) is expected
    assert expected == any(np.any(v) for v in detector.predict_channels(samples).values())
    detector.detectors["channel_42"].threshold = 4.0
    assert not detector_alarm_from_scores(detector.score_channels(samples), detector)


@pytest.mark.parametrize("category", ["Anomaly", "Rare Event"])
def test_no_detector_alarm_never_queries_or_teaches_memory(category):
    memory = Mock(spec=AdaptiveEventMemory)
    decision = apply_event_memory(False, None, category, memory)
    assert not decision["alarm_after_memory"]
    assert decision["match_classification"] is None
    memory.query.assert_not_called()
    memory.store_memory.assert_not_called()


def test_chronological_feedback_and_genuine_suppression_are_measured():
    memory = AdaptiveEventMemory(similarity_threshold=0.80)
    sig = make_signature()
    first = apply_event_memory(True, sig, "Rare Event", memory)
    assert first["alarm_after_memory"]
    assert len(memory.list_memories()) == 1
    repeat = apply_event_memory(True, sig, "Rare Event", memory)
    assert not repeat["alarm_after_memory"]
    # A genuine event matching operational memory must count as suppression.
    anomaly = apply_event_memory(True, sig, "Anomaly", memory)
    assert not anomaly["alarm_after_memory"]
    strong_anomaly = apply_event_memory(True, make_signature(10.0), "Anomaly", memory)
    assert strong_anomaly["alarm_after_memory"]
    assert len(memory.list_memories()) == 1


def test_confirmed_anomaly_does_not_teach_operational_memory():
    memory = AdaptiveEventMemory()
    decision = apply_event_memory(True, make_signature(), "Anomaly", memory)
    assert decision["alarm_after_memory"]
    assert memory.list_memories() == []


def test_summary_uses_actual_alarm_counts_and_configured_threshold():
    detector = MultiChannelSpacecraftDetector(["channel_41"], GlobalStdDetector, threshold=3.0)
    memory = AdaptiveEventMemory(similarity_threshold=0.91)
    log = [
        {"category": "Anomaly", "detector_alarm": False, "alarm_after_memory": False},
        {"category": "Anomaly", "detector_alarm": True, "alarm_after_memory": False},
        {"category": "Anomaly", "detector_alarm": True, "alarm_after_memory": True},
        {"category": "Rare Event", "detector_alarm": False, "alarm_after_memory": False},
        {"category": "Rare Event", "detector_alarm": True, "alarm_after_memory": True},
        {"category": "Rare Event", "detector_alarm": True, "alarm_after_memory": False},
    ]
    result = summarize_experiment(log, detector, memory)
    assert result["genuine_anomalies_detected_before_memory"] == 2
    assert result["genuine_anomalies_detected_after_memory"] == 1
    assert result["genuine_anomaly_recall_before_memory"] == pytest.approx(2 / 3)
    assert result["genuine_anomaly_suppression_denominator"] == 2
    assert result["false_genuine_anomaly_suppression_rate"] == 0.5
    assert result["rare_event_alarms_before_memory"] == 2
    assert result["rare_event_alarms_after_memory"] == 1
    assert result["rare_event_alarm_reduction_percentage"] == 50.0
    assert result["similarity_threshold"] == memory.similarity_threshold
    assert result["detector_thresholds"]["channel_41"] == 3.0
    report = render_report(result)
    assert "0.91" in report
    assert "2 / 3 = 66.7%" in report
    assert "1 / 3 = 33.3%" in report
    assert "suppressed 1" in report
    assert "Rare Event alarm reduction was 50.0%" in report


def test_empty_summary_does_not_invent_rates():
    result = summarize_experiment(
        [], MultiChannelSpacecraftDetector(["channel_41"]), AdaptiveEventMemory()
    )
    assert result["rare_event_alarm_reduction_percentage"] is None
    assert result["false_genuine_anomaly_suppression_rate"] is None
    assert result["genuine_anomaly_recall_before_memory"] is None
    assert "N/A" in render_report(result)
