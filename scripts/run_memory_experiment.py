"""Chronological simulation experiment for Adaptive Event Memory on ESA Mission-1 telemetry."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from astra.data.splits import (
    MISSION1_TEST_BOUNDARY,
    MISSION1_VALIDATION_BOUNDARY,
    TemporalSplit,
    event_level_table,
)
from astra.evaluation.metrics import timestamp_ns
from astra.features.event_signature import EventSignature, EventSignatureExtractor
from astra.memory.event_memory import AdaptiveEventMemory
from astra.models.baselines import (
    GlobalStdDetector,
    MultiChannelSpacecraftDetector,
)

EVENTS_PATH = Path("data/processed/mission1/events.parquet")
CHANNELS_DIR = Path("data/processed/mission1/channels")
TELECOMMANDS_PATH = Path("data/processed/mission1/telecommands.parquet")

REPORT_PATH = Path("reports/astra_memory_experiment.md")
ARTIFACT_PATH = Path("artifacts/experiments/astra_memory_experiment.json")


def detector_alarm_from_scores(
    scores: dict[str, np.ndarray], detector: MultiChannelSpacecraftDetector
) -> bool:
    """Alarm if any channel sample exceeds its fitted detector's threshold."""
    return any(
        bool(np.any(values > detector.detectors[channel].threshold))
        for channel, values in scores.items()
    )


def apply_event_memory(
    detector_alarm: bool,
    signature: EventSignature | None,
    category: str,
    memory: AdaptiveEventMemory,
) -> dict[str, Any]:
    """Query only detector alarms; labels simulate review after the memory decision."""
    if not detector_alarm:
        return {
            "detector_alarm": False,
            "alarm_after_memory": False,
            "match_classification": None,
            "best_similarity": None,
            "simulation_status": "NO_DETECTOR_ALARM",
        }
    if signature is None:
        raise ValueError("A detector alarm requires an event signature.")
    match = memory.query(signature)
    suppressed = match.classification == "KNOWN_OPERATIONAL_PATTERN"
    if suppressed:
        status = "SUPPRESSED_AS_KNOWN_PATTERN"
    elif category == "Rare Event":
        memory.store_memory(signature, operator_label="VALID_OPERATION")
        status = "ALARM_TRIGGERED_THEN_LEARNED"
    else:
        status = "CONFIRMED_ANOMALY_ALARMED"
    return {
        "detector_alarm": True,
        "alarm_after_memory": not suppressed,
        "match_classification": match.classification,
        "best_similarity": match.best_similarity,
        "simulation_status": status,
    }


def summarize_experiment(
    log: list[dict[str, Any]],
    detector: MultiChannelSpacecraftDetector,
    memory: AdaptiveEventMemory,
) -> dict[str, Any]:
    """Compute event-level counts and suppression denominators from pipeline decisions."""
    rare = [event for event in log if event["category"] == "Rare Event"]
    anomalies = [event for event in log if event["category"] == "Anomaly"]
    rare_before = sum(event["detector_alarm"] for event in rare)
    rare_after = sum(event["alarm_after_memory"] for event in rare)
    detected_before = sum(event["detector_alarm"] for event in anomalies)
    detected_after = sum(event["alarm_after_memory"] for event in anomalies)
    suppressed = detected_before - detected_after
    return {
        "experiment_name": "EXPLORATORY MISSION-1 EVALUATION",
        "detector": "GlobalStdDetector",
        "detector_thresholds": {
            channel: fitted.threshold for channel, fitted in detector.detectors.items()
        },
        "similarity_threshold": memory.similarity_threshold,
        "test_event_count": len(log),
        "rare_event_count": len(rare),
        "anomaly_event_count": len(anomalies),
        "rare_event_alarms_before_memory": rare_before,
        "rare_event_alarms_after_memory": rare_after,
        "rare_event_alarms_suppressed": rare_before - rare_after,
        "rare_event_alarm_reduction_percentage": (
            (rare_before - rare_after) / rare_before * 100 if rare_before else None
        ),
        "genuine_anomalies_detected_before_memory": detected_before,
        "genuine_anomalies_detected_after_memory": detected_after,
        "genuine_anomaly_recall_before_memory": (
            detected_before / len(anomalies) if anomalies else None
        ),
        "genuine_anomaly_recall_after_memory": (
            detected_after / len(anomalies) if anomalies else None
        ),
        "genuine_anomalies_incorrectly_suppressed": suppressed,
        "genuine_anomaly_suppression_denominator": detected_before,
        "false_genuine_anomaly_suppression_rate": (
            suppressed / detected_before if detected_before else None
        ),
        "simulation_log": log,
    }


def render_report(results: dict[str, Any]) -> str:
    """Render measured results without assumed recall or hardcoded conclusions."""
    def percentage(value: float | None, scale: float = 100.0) -> str:
        return "N/A" if value is None else f"{value * scale:.1f}%"

    before = results["genuine_anomalies_detected_before_memory"]
    after = results["genuine_anomalies_detected_after_memory"]
    total = results["anomaly_event_count"]
    suppressed = results["genuine_anomalies_incorrectly_suppressed"]
    reduction = percentage(results["rare_event_alarm_reduction_percentage"], 1.0)
    lines = [
        "# ASTRA Adaptive Event Memory Chronological Experiment Report",
        "",
        "## EXPLORATORY MISSION-1 EVALUATION",
        "",
        "Historical ESA Mission-1 channels 41–46; labelled event windows and simulated "
        "operator validation. Only actual GlobalStd detector alarms enter Event Memory.",
        "An event alarms when any selected channel sample exceeds its detector threshold.",
        "The existing empty-window neighboring-sample fallback is retained.",
        "",
        f"Detector: {results['detector']}; thresholds: {results['detector_thresholds']}.",
        f"Similarity threshold: {results['similarity_threshold']:.2f}.",
        "",
        "| Metric | Measured result |",
        "| --- | --- |",
        f"| Labelled test events | {results['test_event_count']} |",
        f"| Labelled Rare Events | {results['rare_event_count']} |",
        f"| Genuine anomaly detection before memory | {before} / {total} = "
        f"{percentage(results['genuine_anomaly_recall_before_memory'])} |",
        f"| Genuine anomaly detection after memory | {after} / {total} = "
        f"{percentage(results['genuine_anomaly_recall_after_memory'])} |",
        f"| Rare Event alarms before memory | {results['rare_event_alarms_before_memory']} |",
        f"| Rare Event alarms after memory | {results['rare_event_alarms_after_memory']} |",
        f"| Rare Event alarm reduction | {reduction} |",
        f"| Detected genuine anomalies suppressed by memory | {suppressed} / {before} |",
        "",
        f"The detector detected {before} of {total} labelled genuine anomalies. "
        f"Event Memory retained {after} of those detections and suppressed {suppressed}. "
        f"Rare Event alarm reduction was {reduction} in this run.",
        "",
        "This is NOT a pristine untouched final benchmark. Thresholds and memory behavior "
        "were developed while inspecting Mission-1. Reproduction under frozen thresholds "
        "and an untouched evaluation protocol is required before generalization claims. "
        "Cross-mission validation remains future work.",
        "",
    ]
    return "\n".join(lines)

def run_experiment() -> dict:
    print("Loading events...")
    events_raw = pq.read_table(EVENTS_PATH).to_pandas()
    events = event_level_table(events_raw)
    
    print("Loading telecommands...")
    tc_df = pq.read_table(TELECOMMANDS_PATH).to_pandas()
    tc_df["timestamp_ns"] = pd.to_datetime(tc_df["timestamp"], utc=True).astype("int64")
    
    # Selected channel names
    channels = [f"channel_{i}" for i in range(41, 47)]
    
    print("Loading telemetry channel samples for baseline fitting...")
    # Load channel 41 timestamps to get extent
    ch41_df = pq.read_table(CHANNELS_DIR / "channel_41.parquet").to_pandas()
    ch41_df["timestamp"] = pd.to_datetime(ch41_df["timestamp"], utc=True)
    
    start_ts = ch41_df["timestamp"].min()
    end_ts = ch41_df["timestamp"].max()
    
    split = TemporalSplit(
        dataset_start=start_ts,
        validation_boundary=MISSION1_VALIDATION_BOUNDARY,
        test_boundary=MISSION1_TEST_BOUNDARY,
        dataset_end=end_ts,
    )
    
    # Fit detector on train split telemetry
    train_mask = ch41_df["timestamp"] <= split.validation_boundary
    train_channel_data = {}
    for ch in channels:
        ch_df = pq.read_table(CHANNELS_DIR / f"{ch}.parquet").to_pandas()
        train_channel_data[ch] = ch_df.loc[train_mask, "value"].to_numpy()
        
    detector = MultiChannelSpacecraftDetector(channel_names=channels, detector_cls=GlobalStdDetector, threshold=3.0)
    detector.fit(train_channel_data)
    print("Baseline MultiChannelSpacecraftDetector fitted on training telemetry.")
    
    # Assign events to splits
    events["split"] = split.partition(events["start_timestamp"])
    events = events.sort_values("start_timestamp").reset_index(drop=True)
    
    extractor = EventSignatureExtractor(channel_names=channels)
    memory = AdaptiveEventMemory(similarity_threshold=0.80)
    
    # Filter test split events for chronological simulation
    test_events = events[events["split"] == "test"].copy()
    test_events = test_events[test_events["category"].isin(["Anomaly", "Rare Event"])].reset_index(drop=True)
    
    # Preload channel telemetry dataframes and timestamp arrays once
    print("Preloading channel telemetry data for event window slicing...")
    ch_dfs = {}
    ch_ts_ns = {}
    for ch in channels:
        df_ch = pq.read_table(CHANNELS_DIR / f"{ch}.parquet").to_pandas()
        df_ch["ts_ns"] = pd.to_datetime(df_ch["timestamp"], utc=True).astype("int64")
        ch_dfs[ch] = df_ch["value"].to_numpy()
        ch_ts_ns[ch] = df_ch["ts_ns"].to_numpy()

    simulation_log = []
    
    for row in test_events.to_dict("records"):
        event_id = row["event_id"]
        cat = row["category"]
        ev_start = pd.Timestamp(row["start_timestamp"])
        ev_end = pd.Timestamp(row["end_timestamp"])
        
        ev_start_ns = timestamp_ns(ev_start)
        ev_end_ns = timestamp_ns(ev_end)
        
        # Fast slicing using binary search on preloaded timestamp arrays
        ch_vals = {}
        for ch in channels:
            ts_arr_ch = ch_ts_ns[ch]
            vals_ch = ch_dfs[ch]
            idx_start = np.searchsorted(ts_arr_ch, ev_start_ns, side="left")
            idx_end = np.searchsorted(ts_arr_ch, ev_end_ns, side="right")
            sub_val = vals_ch[idx_start:idx_end]
            if len(sub_val) == 0:
                sub_val = vals_ch[max(0, idx_start-5):min(len(vals_ch), idx_start+5)]
            ch_vals[ch] = sub_val
            
        ts_arr = np.array([ev_start_ns, ev_end_ns], dtype="int64")
        
        # Compute per-channel anomaly scores using fitted detector
        scores = detector.score_channels(ch_vals)
        
        detector_alarm = detector_alarm_from_scores(scores, detector)
        sig = None
        if detector_alarm:
            sig = extractor.extract_signature(
                event_id=event_id,
                channel_values=ch_vals,
                timestamps=ts_arr,
                anomaly_scores=scores,
                telecommands_df=tc_df,
                threshold_score=detector.detectors[channels[0]].threshold,
            )
        decision = apply_event_memory(detector_alarm, sig, cat, memory)
        simulation_log.append({
            "event_id": event_id,
            "category": cat,
            "class": row["class"],
            "channel_max_scores": {
                channel: float(np.max(values)) if len(values) else None
                for channel, values in scores.items()
            },
            **decision,
        })

    experiment_results = summarize_experiment(simulation_log, detector, memory)

    # Save JSON artifact
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(experiment_results, f, indent=2)
    print(f"Artifact written to {ARTIFACT_PATH}")
    
    report_text = render_report(experiment_results)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    
    print(json.dumps({key: value for key, value in experiment_results.items()
                      if key != "simulation_log"}, indent=2))
    return experiment_results

if __name__ == "__main__":
    run_experiment()
