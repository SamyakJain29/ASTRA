"""Retrospective label-conditioned memory-stage recurrence evaluation."""

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

REPORT_PATH = Path("reports/astra_memory_stage_recurrence.md")
ARTIFACT_PATH = Path("artifacts/experiments/astra_memory_stage_recurrence.json")


def evaluate_recurrence(signature: EventSignature, memory: AdaptiveEventMemory) -> dict[str, Any]:
    """Query before simulated validation; only unfamiliar windows teach memory."""
    match = memory.query(signature)
    recognized = match.classification == "KNOWN_OPERATIONAL_PATTERN"
    if not recognized:
        memory.store_memory(signature, operator_label="VALID_OPERATION")
    return {"event_id": signature.event_id, "recognized": recognized,
            "review_required": not recognized, "best_similarity": match.best_similarity}


def summarize_recurrence(log: list[dict[str, Any]], memory: AdaptiveEventMemory) -> dict[str, Any]:
    """Summarize labelled-cohort review decisions, never detector alarm counts."""
    total = len(log)
    recognized = sum(row["recognized"] for row in log)
    rate = recognized / total * 100 if total else None
    return {
        "evaluation_type": "RETROSPECTIVE LABEL-CONDITIONED MEMORY-STAGE EVALUATION",
        "labelled_rare_event_windows": total,
        "review_required_windows": total - recognized,
        "subsequently_recognized_windows": recognized,
        "recognition_rate_pct": rate,
        "repeated_review_reduction_pct": rate,
        "similarity_threshold": memory.similarity_threshold,
        "simulation_log": log,
    }


def render_report(result: dict[str, Any]) -> str:
    """Render a recurrence report with an explicit cohort and denominator."""
    rate = result["repeated_review_reduction_pct"]
    rate_text = f"{rate:.1f}%" if rate is not None else "N/A"
    return "\n".join([
        "# RETROSPECTIVE MEMORY-STAGE RECURRENCE EVALUATION", "",
        "Question: Among labelled Rare Event windows, how effectively can chronological "
        "operator-validated Event Memory recognize recurring operational patterns?", "",
        "This is a retrospective, label-conditioned study of Mission-1 channels 41–46. "
        "Category selects the Rare Event test cohort; category/class/subclass are not similarity "
        "features. Memory starts empty. Each window is queried before simulated VALID_OPERATION "
        "review; only unmatched windows are then stored. No future windows enter memory.", "",
        "GlobalStd scores are signature features here, not a detector-alarm admission gate. "
        "The existing training split, event slicing, and neighboring-sample fallback are retained.", "",
        f"Similarity threshold: {result['similarity_threshold']:.2f}.", "",
        "| Metric | Measured result |", "| --- | --- |",
        f"| Labelled Rare Event windows | {result['labelled_rare_event_windows']} |",
        f"| First/unmatched review-required windows | {result['review_required_windows']} |",
        f"| Subsequently recognized windows | {result['subsequently_recognized_windows']} |",
        f"| Recognition rate | {rate_text} |",
        f"| Memory-stage repeated-review reduction | {rate_text} |", "",
        "These are not detector alarm counts or end-to-end detector performance. "
        "Repeated-review reduction uses all labelled Rare Event windows as its denominator, "
        "relative to reviewing every cohort window. It is not measured operator time saved.", "",
        "This is NOT a pristine untouched final benchmark. Mission-1 informed threshold "
        "development. Cross-mission validation and an untouched evaluation protocol remain "
        "future work; no universal generalization or anomaly-safety claim follows from this study.", "",
    ])


def run_experiment() -> dict:
    """Evaluate chronological recurrence on the labelled Rare Event test cohort only."""
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
    test_events = test_events[test_events["category"] == "Rare Event"].reset_index(drop=True)
    
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
        
        signature = extractor.extract_signature(
            event_id=event_id, channel_values=ch_vals, timestamps=ts_arr,
            anomaly_scores=scores, telecommands_df=tc_df,
            threshold_score=detector.detectors[channels[0]].threshold,
        )
        simulation_log.append(evaluate_recurrence(signature, memory))

    result = summarize_recurrence(simulation_log, memory)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "simulation_log"}, indent=2))
    return result


if __name__ == "__main__":
    run_experiment()
