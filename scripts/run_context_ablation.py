"""Context ablation experiment comparing telemetry-only vs telemetry+telecommand context."""

import json
from pathlib import Path

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
from astra.features.event_signature import EventSignatureExtractor
from astra.memory.event_memory import AdaptiveEventMemory
from astra.models.baselines import GlobalStdDetector, MultiChannelSpacecraftDetector

EVENTS_PATH = Path("data/processed/mission1/events.parquet")
CHANNELS_DIR = Path("data/processed/mission1/channels")
TELECOMMANDS_PATH = Path("data/processed/mission1/telecommands.parquet")
REPORT_PATH = Path("reports/astra_context_ablation.md")
ARTIFACT_PATH = Path("artifacts/experiments/astra_context_ablation.json")


def run_ablation_mode(use_context: bool) -> dict:
    events_raw = pq.read_table(EVENTS_PATH).to_pandas()
    events = event_level_table(events_raw)
    tc_df = pq.read_table(TELECOMMANDS_PATH).to_pandas()
    tc_df["timestamp_ns"] = pd.to_datetime(tc_df["timestamp"], utc=True).astype("int64")

    channels = [f"channel_{i}" for i in range(41, 47)]
    ch41_df = pq.read_table(CHANNELS_DIR / "channel_41.parquet").to_pandas()
    ch41_df["timestamp"] = pd.to_datetime(ch41_df["timestamp"], utc=True)

    split = TemporalSplit(
        dataset_start=ch41_df["timestamp"].min(),
        validation_boundary=MISSION1_VALIDATION_BOUNDARY,
        test_boundary=MISSION1_TEST_BOUNDARY,
        dataset_end=ch41_df["timestamp"].max(),
    )

    train_mask = ch41_df["timestamp"] <= split.validation_boundary
    train_channel_data = {}
    for ch in channels:
        ch_df = pq.read_table(CHANNELS_DIR / f"{ch}.parquet").to_pandas()
        train_channel_data[ch] = ch_df.loc[train_mask, "value"].to_numpy()

    detector = MultiChannelSpacecraftDetector(channel_names=channels, detector_cls=GlobalStdDetector, threshold=3.0)
    detector.fit(train_channel_data)

    events["split"] = split.partition(events["start_timestamp"])
    events = events.sort_values("start_timestamp").reset_index(drop=True)

    extractor = EventSignatureExtractor(channel_names=channels)
    memory = AdaptiveEventMemory(similarity_threshold=0.80)

    test_events = events[events["split"] == "test"].copy()
    test_events = test_events[test_events["category"].isin(["Anomaly", "Rare Event"])].reset_index(drop=True)

    test_anomalies = test_events[test_events["category"] == "Anomaly"]
    test_rare_events = test_events[test_events["category"] == "Rare Event"]

    num_test_anomalies = len(test_anomalies)
    num_test_rare = len(test_rare_events)

    ch_dfs = {}
    ch_ts_ns = {}
    for ch in channels:
        df_ch = pq.read_table(CHANNELS_DIR / f"{ch}.parquet").to_pandas()
        df_ch["ts_ns"] = pd.to_datetime(df_ch["timestamp"], utc=True).astype("int64")
        ch_dfs[ch] = df_ch["value"].to_numpy()
        ch_ts_ns[ch] = df_ch["ts_ns"].to_numpy()

    rare_alarms_after = 0
    rare_alarms_suppressed = 0
    anomaly_recalled_after = 0
    anomaly_incorrectly_suppressed = 0

    tc_input = tc_df if use_context else None

    for row in test_events.to_dict("records"):
        event_id = row["event_id"]
        cat = row["category"]
        ev_start = pd.Timestamp(row["start_timestamp"])
        ev_end = pd.Timestamp(row["end_timestamp"])

        ev_start_ns = timestamp_ns(ev_start)
        ev_end_ns = timestamp_ns(ev_end)

        ch_vals = {}
        for ch in channels:
            ts_arr_ch = ch_ts_ns[ch]
            vals_ch = ch_dfs[ch]
            idx_start = np.searchsorted(ts_arr_ch, ev_start_ns, side="left")
            idx_end = np.searchsorted(ts_arr_ch, ev_end_ns, side="right")
            sub_val = vals_ch[idx_start:idx_end]
            if len(sub_val) == 0:
                sub_val = vals_ch[max(0, idx_start - 5) : min(len(vals_ch), idx_start + 5)]
            ch_vals[ch] = sub_val

        ts_arr = np.array([ev_start_ns, ev_end_ns], dtype="int64")
        scores = detector.score_channels(ch_vals)

        sig = extractor.extract_signature(
            event_id=event_id,
            channel_values=ch_vals,
            timestamps=ts_arr,
            anomaly_scores=scores,
            telecommands_df=tc_input,
            threshold_score=3.0,
        )

        match = memory.query(sig)

        if cat == "Rare Event":
            if match.classification == "KNOWN_OPERATIONAL_PATTERN":
                rare_alarms_suppressed += 1
            else:
                rare_alarms_after += 1
                memory.store_memory(sig, operator_label="VALID_OPERATION")
        else:  # Anomaly
            if match.classification == "KNOWN_OPERATIONAL_PATTERN":
                anomaly_incorrectly_suppressed += 1
            else:
                anomaly_recalled_after += 1

    rare_reduction_pct = (rare_alarms_suppressed / num_test_rare * 100) if num_test_rare else 0.0
    recall_after = (anomaly_recalled_after / num_test_anomalies * 100) if num_test_anomalies else 100.0

    return {
        "use_context": use_context,
        "rare_events_total": num_test_rare,
        "rare_events_suppressed": rare_alarms_suppressed,
        "rare_event_reduction_pct": rare_reduction_pct,
        "anomalies_total": num_test_anomalies,
        "anomalies_recalled": anomaly_recalled_after,
        "anomaly_recall_pct": recall_after,
        "anomalies_suppressed": anomaly_incorrectly_suppressed,
    }


def main():
    print("Running Ablation A: Telemetry Features Only...")
    res_a = run_ablation_mode(use_context=False)

    print("Running Ablation B: Telemetry + Telecommand Context Features...")
    res_b = run_ablation_mode(use_context=True)

    artifact_data = {"mode_a_telemetry_only": res_a, "mode_b_telemetry_plus_context": res_b}

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(artifact_data, f, indent=2)

    diff_reduction = res_b["rare_event_reduction_pct"] - res_a["rare_event_reduction_pct"]
    diff_recall = res_b["anomaly_recall_pct"] - res_a["anomaly_recall_pct"]
    diff_suppressed = res_b["anomalies_suppressed"] - res_a["anomalies_suppressed"]

    md = []
    md.append("# ASTRA Telecommand Context Ablation Report")
    md.append("")
    md.append("## Separate exploratory label-conditioned context-ablation study")
    md.append("All labelled windows enter matching without a detector-alarm admission gate. "
              "These are not either headline study or end-to-end detector safety metrics.")
    md.append("")
    md.append("This report presents a controlled ablation study evaluating the impact of ")
    md.append("**Telecommand Context Features** on ASTRA's Adaptive Event Memory performance.")
    md.append("")
    md.append("## Comparative Metrics Table")
    md.append("")
    md.append("| Metric | Mode A: Telemetry Only | Mode B: Telemetry + Telecommand Context | Impact of Context |")
    md.append("|---|---|---|---|")
    md.append(
        f"| **Rare Event cohort recognition** | {res_a['rare_event_reduction_pct']:.1f}% ({res_a['rare_events_suppressed']}/{res_a['rare_events_total']}) | {res_b['rare_event_reduction_pct']:.1f}% ({res_b['rare_events_suppressed']}/{res_b['rare_events_total']}) | **{diff_reduction:+.1f}%** |"
    )
    md.append(
        f"| **Labelled anomaly windows remaining unmatched** | {res_a['anomaly_recall_pct']:.1f}% ({res_a['anomalies_recalled']}/{res_a['anomalies_total']}) | {res_b['anomaly_recall_pct']:.1f}% ({res_b['anomalies_recalled']}/{res_b['anomalies_total']}) | **{diff_recall:+.1f}%** |"
    )
    md.append(
        f"| **Labelled anomaly windows matched as operational** | {res_a['anomalies_suppressed']} | {res_b['anomalies_suppressed']} | **{diff_suppressed:+d}** |"
    )
    md.append("")
    md.append("## Key Findings")
    md.append("")
    md.append("This retrospective comparison reports window recognition and erroneous matching, "
              "not operational safety guarantees, physical diagnosis, or detector-derived recall. "
              "Do not combine these denominators with the headline detector-gated study.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
