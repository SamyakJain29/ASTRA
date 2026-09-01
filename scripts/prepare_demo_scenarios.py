"""Prepare real ESA Mission-1 demo scenario data precomputations for FastAPI backend & frontend."""

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
from astra.models.baselines import GlobalStdDetector, MultiChannelSpacecraftDetector

EVENTS_PATH = Path("data/processed/mission1/events.parquet")
CHANNELS_DIR = Path("data/processed/mission1/channels")
TELECOMMANDS_PATH = Path("data/processed/mission1/telecommands.parquet")

CONFIG_PATH = Path("configs/demo.yaml")
ARTIFACT_PATH = Path("artifacts/demo_scenarios.json")


def main():
    print("Loading events & telecommands...")
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
    train_channel_data = {"channel_41": ch41_df.loc[train_mask, "value"].to_numpy()}
    for ch in channels:
        if ch == "channel_41":
            continue
        df_c = pq.read_table(CHANNELS_DIR / f"{ch}.parquet", columns=["timestamp", "value"]).to_pandas()
        df_c["timestamp"] = pd.to_datetime(df_c["timestamp"], utc=True)
        train_channel_data[ch] = df_c.loc[df_c["timestamp"] <= split.validation_boundary, "value"].to_numpy()

    detector = MultiChannelSpacecraftDetector(channel_names=channels, detector_cls=GlobalStdDetector, threshold=3.0)
    detector.fit(train_channel_data)

    events["split"] = split.partition(events["start_timestamp"])
    events = events.sort_values("start_timestamp").reset_index(drop=True)

    test_events = events[events["split"] == "test"].copy().reset_index(drop=True)

    rare_class14 = test_events[(test_events["category"] == "Rare Event") & (test_events["class"] == "class_14")]
    rare_first_row = rare_class14.iloc[0].to_dict()
    rare_repeat_row = rare_class14.iloc[1].to_dict()

    anomaly_class3 = test_events[(test_events["category"] == "Anomaly") & (test_events["class"] == "class_3")]
    anomaly_row = anomaly_class3.iloc[0].to_dict()

    extractor = EventSignatureExtractor(channel_names=channels)

    def extract_scenario_payload(scenario_name: str, event_dict: dict | None, start_iso: str | None, end_iso: str | None):
        if event_dict is not None:
            ev_id = event_dict["event_id"]
            ev_start = pd.Timestamp(event_dict["start_timestamp"])
            ev_end = pd.Timestamp(event_dict["end_timestamp"])
            cat = event_dict["category"]
            cls = event_dict["class"]
        else:
            ev_id = f"normal_{scenario_name}"
            ev_start = pd.Timestamp(start_iso)
            ev_end = pd.Timestamp(end_iso)
            cat = "Nominal"
            cls = "nominal_baseline"

        ev_start_ns = timestamp_ns(ev_start)
        ev_end_ns = timestamp_ns(ev_end)

        pad_ns = 60 * 1_000_000_000

        ch_vals = {}
        ch_time_series = {}

        for ch in channels:
            df_ch = pq.read_table(CHANNELS_DIR / f"{ch}.parquet").to_pandas()
            df_ch["ts_dt"] = pd.to_datetime(df_ch["timestamp"], utc=True)
            df_ch["ts_ns"] = df_ch["ts_dt"].astype("int64")

            ev_mask = (df_ch["ts_ns"] >= ev_start_ns) & (df_ch["ts_ns"] <= ev_end_ns)
            sub_val = df_ch.loc[ev_mask, "value"].to_numpy()
            if len(sub_val) == 0:
                sub_val = df_ch["value"].to_numpy()[:10]
            ch_vals[ch] = sub_val

            w_mask = (df_ch["ts_ns"] >= (ev_start_ns - pad_ns)) & (df_ch["ts_ns"] <= (ev_end_ns + pad_ns))
            df_slice = df_ch.loc[w_mask]

            if len(df_slice) > 80:
                step = len(df_slice) // 80
                df_chart = df_slice.iloc[::step].copy()
            else:
                df_chart = df_slice.copy()

            chart_isos = df_chart["ts_dt"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
            chart_vals = df_chart["value"].tolist()

            ch_time_series[ch] = [
                {"timestamp": str(t), "value": float(v)} for t, v in zip(chart_isos, chart_vals, strict=False)
            ]

        ts_arr_sig = np.array([ev_start_ns, ev_end_ns], dtype="int64")
        scores = detector.score_channels(ch_vals)

        sig = extractor.extract_signature(
            event_id=ev_id,
            channel_values=ch_vals,
            timestamps=ts_arr_sig,
            anomaly_scores=scores,
            telecommands_df=tc_df,
            threshold_score=3.0,
        )

        max_score = float(max(np.max(arr) for arr in scores.values())) if scores else 0.0
        affected = sig.affected_channels

        return {
            "scenario": scenario_name,
            "event_id": ev_id,
            "category": cat,
            "class": cls,
            "start_timestamp": ev_start.isoformat(),
            "end_timestamp": ev_end.isoformat(),
            "anomaly_score": max_score,
            "affected_channels": affected,
            "telemetry_charts": ch_time_series,
            "signature": sig.to_dict(),
            "context": sig.context_features,
        }

    normal_start = pd.Timestamp(split.test_boundary).isoformat()
    normal_end = (pd.Timestamp(split.test_boundary) + pd.Timedelta(minutes=5)).isoformat()

    scenarios = {
        "normal": extract_scenario_payload("normal", None, normal_start, normal_end),
        "rare_first": extract_scenario_payload("rare_first", rare_first_row, None, None),
        "rare_repeat": extract_scenario_payload("rare_repeat", rare_repeat_row, None, None),
        "anomaly": extract_scenario_payload("anomaly", anomaly_row, None, None),
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)
    print(f"Demo scenario data saved to {ARTIFACT_PATH}")

    config_content = f"""# ASTRA Precomputed Real Demo Scenario Configuration
scenarios:
  normal:
    event_id: "normal_window"
    category: "Nominal"
    description: "Steady nominal operational state telemetry window"
  rare_first:
    event_id: "{rare_first_row['event_id']}"
    category: "Rare Event"
    class: "class_14"
    description: "First occurrence of rare operational maneuver (triggers operator review)"
  rare_repeat:
    event_id: "{rare_repeat_row['event_id']}"
    category: "Rare Event"
    class: "class_14"
    description: "Repeated occurrence of validated rare operational maneuver (matches memory)"
  anomaly:
    event_id: "{anomaly_row['event_id']}"
    category: "Anomaly"
    class: "class_3"
    description: "Uncommanded genuine spacecraft component anomaly"

artifact_path: "artifacts/demo_scenarios.json"
"""

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(config_content, encoding="utf-8")
    print(f"Demo configuration written to {CONFIG_PATH}")


if __name__ == "__main__":
    main()
