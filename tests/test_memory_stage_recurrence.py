"""Checks for the separate retrospective, label-conditioned recurrence study."""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
from scripts import run_memory_stage_recurrence_experiment as recurrence

from astra.features.event_signature import EventSignatureExtractor
from astra.memory.event_memory import AdaptiveEventMemory


def test_recurrence_queries_before_learning_even_without_detector_alarm():
    signature = EventSignatureExtractor(["channel_41"]).extract_signature(
        event_id="synthetic-rare-window",
        channel_values={"channel_41": np.array([1.0, 1.0])},
        timestamps=np.array([0, 60_000_000_000]),
        anomaly_scores={"channel_41": np.array([0.0, 0.0])},
    )
    memory = AdaptiveEventMemory(similarity_threshold=0.80)
    assert memory.list_memories() == []
    first = recurrence.evaluate_recurrence(signature, memory)
    assert first["review_required"]
    assert not first["recognized"]
    assert len(memory.list_memories()) == 1
    repeat = recurrence.evaluate_recurrence(signature, memory)
    assert repeat["recognized"]
    assert not repeat["review_required"]
    assert len(memory.list_memories()) == 1
    result = recurrence.summarize_recurrence([first, repeat], memory)
    assert result["labelled_rare_event_windows"] == 2
    assert result["review_required_windows"] == 1
    assert result["subsequently_recognized_windows"] == 1
    assert result["repeated_review_reduction_pct"] == 50.0
    assert result["recognition_rate_pct"] == 50.0
    assert result["similarity_threshold"] == memory.similarity_threshold == 0.80
    assert "RETROSPECTIVE LABEL-CONDITIONED" in result["evaluation_type"]
    assert not any("alarm" in key or "anomaly" in key for key in result)
    report = recurrence.render_report(result)
    assert "RETROSPECTIVE MEMORY-STAGE RECURRENCE EVALUATION" in report
    assert "not detector alarm counts" in report
    assert "50.0%" in report


def test_empty_recurrence_summary_does_not_invent_rates():
    result = recurrence.summarize_recurrence([], AdaptiveEventMemory(similarity_threshold=0.80))
    assert result["labelled_rare_event_windows"] == 0
    assert result["repeated_review_reduction_pct"] is None
    assert "N/A" in recurrence.render_report(result)


def test_script_filters_and_orders_cohort_without_detector_gate(monkeypatch, tmp_path):
    channel_data = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2006-01-01", "2006-09-01", "2007-02-01", "2007-03-01", "2007-04-01",
        ], utc=True),
        "value": [-1.0, 1.0, 1.0, 1.0, 1.0],
    })
    events = pd.DataFrame({
        "event_id": ["later", "anomaly-excluded", "train-excluded", "earlier"],
        "category": ["Rare Event", "Anomaly", "Rare Event", "Rare Event"],
        "start_timestamp": pd.to_datetime([
            "2007-03-01", "2007-02-15", "2006-09-01", "2007-02-01",
        ], utc=True),
    })
    events["end_timestamp"] = events["start_timestamp"] + pd.Timedelta(seconds=60)
    commands = pd.DataFrame({"timestamp": pd.to_datetime([], utc=True)})

    def read_table(path):
        if path == recurrence.EVENTS_PATH:
            return pa.Table.from_pandas(events)
        if path == recurrence.TELECOMMANDS_PATH:
            return pa.Table.from_pandas(commands)
        return pa.Table.from_pandas(channel_data)

    monkeypatch.setattr(recurrence.pq, "read_table", read_table)
    monkeypatch.setattr(recurrence, "event_level_table", lambda frame: frame)
    monkeypatch.setattr(recurrence, "ARTIFACT_PATH", tmp_path / "recurrence.json")
    monkeypatch.setattr(recurrence, "REPORT_PATH", tmp_path / "recurrence.md")
    result = recurrence.run_experiment()
    assert [row["event_id"] for row in result["simulation_log"]] == ["earlier", "later"]
    assert result["labelled_rare_event_windows"] == 2
    assert result["review_required_windows"] == 1
    assert result["subsequently_recognized_windows"] == 1
    assert result["similarity_threshold"] == 0.80
    assert json.loads(recurrence.ARTIFACT_PATH.read_text()) == result
    assert "label-conditioned" in recurrence.REPORT_PATH.read_text()
