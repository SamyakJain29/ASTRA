"""Interpretable Event Feature Signature extraction for ASTRA operational windows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class EventSignature:
    """Interpretable feature signature representing an unusual telemetry event or window."""

    event_id: str
    start_timestamp: str
    end_timestamp: str
    duration_seconds: float
    affected_channels: list[str]
    num_affected_channels: int
    telemetry_features: dict[str, float]
    context_features: dict[str, float]
    feature_vector: list[float]
    feature_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventSignature:
        return cls(
            event_id=data["event_id"],
            start_timestamp=data["start_timestamp"],
            end_timestamp=data["end_timestamp"],
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            affected_channels=list(data.get("affected_channels", [])),
            num_affected_channels=int(data.get("num_affected_channels", len(data.get("affected_channels", [])))),
            telemetry_features=dict(data.get("telemetry_features", {})),
            context_features=dict(data.get("context_features", {})),
            feature_vector=list(data.get("feature_vector", [])),
            feature_names=list(data.get("feature_names", [])),
        )


class EventSignatureExtractor:
    """Extracts telemetry statistics and operational telecommand context features."""

    def __init__(self, channel_names: list[str] | None = None) -> None:
        self.channel_names = channel_names or [f"channel_{i}" for i in range(41, 47)]

    def extract_signature(
        self,
        event_id: str,
        channel_values: dict[str, np.ndarray],
        timestamps: np.ndarray,
        anomaly_scores: dict[str, np.ndarray] | None = None,
        telecommands_df: pd.DataFrame | None = None,
        threshold_score: float = 3.0,
    ) -> EventSignature:
        """Extract a structured EventSignature for a telemetry window."""
        t_start = pd.Timestamp(timestamps[0]) if len(timestamps) > 0 else pd.Timestamp("2000-01-01T00:00:00Z")
        t_end = pd.Timestamp(timestamps[-1]) if len(timestamps) > 0 else t_start
        if t_start.tzinfo is None:
            t_start = t_start.tz_localize("UTC")
        if t_end.tzinfo is None:
            t_end = t_end.tz_localize("UTC")

        duration_sec = max(0.0, float((t_end - t_start).total_seconds()))
        start_ns = int(t_start.value)

        # Identify affected channels
        affected = []
        tel_feats: dict[str, float] = {}

        for ch in self.channel_names:
            vals = channel_values.get(ch, np.array([]))
            scores = anomaly_scores.get(ch, np.array([])) if anomaly_scores else np.array([])
            
            if len(vals) > 0 and np.any(np.isfinite(vals)):
                fin_vals = vals[np.isfinite(vals)]
                c_mean = float(np.mean(fin_vals))
                c_std = float(np.std(fin_vals))
                c_min = float(np.min(fin_vals))
                c_max = float(np.max(fin_vals))
                c_mag = float(c_max - c_min)
                c_diff = float(fin_vals[-1] - fin_vals[0])
            else:
                c_mean, c_std, c_min, c_max, c_mag, c_diff = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

            if len(scores) > 0 and np.any(np.isfinite(scores)):
                s_max = float(np.max(scores))
                s_mean = float(np.mean(scores))
                s_var = float(np.var(scores))
            else:
                s_max, s_mean, s_var = 0.0, 0.0, 0.0

            if s_max > threshold_score or c_mag > 0.05:
                affected.append(ch)

            tel_feats[f"{ch}_mean"] = c_mean
            tel_feats[f"{ch}_std"] = c_std
            tel_feats[f"{ch}_min"] = c_min
            tel_feats[f"{ch}_max"] = c_max
            tel_feats[f"{ch}_mag"] = c_mag
            tel_feats[f"{ch}_diff"] = c_diff
            tel_feats[f"{ch}_score_max"] = s_max
            tel_feats[f"{ch}_score_mean"] = s_mean
            tel_feats[f"{ch}_score_var"] = s_var

        # Aggregate telemetry features across channels
        all_score_maxs = [tel_feats[f"{ch}_score_max"] for ch in self.channel_names]
        tel_feats["agg_score_max"] = float(max(all_score_maxs)) if all_score_maxs else 0.0
        tel_feats["duration_seconds"] = duration_sec

        # Telecommand context features
        ctx_feats: dict[str, float] = {
            "tc_count_5m": 0.0,
            "tc_count_30m": 0.0,
            "tc_count_2h": 0.0,
            "tc_count_24h": 0.0,
            "nearest_tc_diff_sec": 86400.0,  # Default to 24h if none
            "tc_p0_count": 0.0,
            "tc_p1_count": 0.0,
            "tc_p2_count": 0.0,
            "tc_p3_count": 0.0,
        }

        if telecommands_df is not None and not telecommands_df.empty:
            if "timestamp_ns" not in telecommands_df.columns:
                tc_df = telecommands_df.copy()
                tc_df["timestamp_ns"] = pd.to_datetime(tc_df["timestamp"], utc=True).astype("int64")
            else:
                tc_df = telecommands_df

            tc_ts = tc_df["timestamp_ns"].to_numpy()
            tc_p = tc_df["priority"].to_numpy() if "priority" in tc_df.columns else np.zeros(len(tc_ts))

            right_idx = int(np.searchsorted(tc_ts, start_ns, side="right"))
            if right_idx > 0:
                nearest_idx = right_idx - 1
                ctx_feats["nearest_tc_diff_sec"] = float(max(0.0, (start_ns - tc_ts[nearest_idx]) / 1e9))

                W_5M = 300 * 10**9
                W_30M = 1800 * 10**9
                W_2H = 7200 * 10**9
                W_24H = 86400 * 10**9

                idx_5m = int(np.searchsorted(tc_ts, start_ns - W_5M, side="left"))
                idx_30m = int(np.searchsorted(tc_ts, start_ns - W_30M, side="left"))
                idx_2h = int(np.searchsorted(tc_ts, start_ns - W_2H, side="left"))
                idx_24h = int(np.searchsorted(tc_ts, start_ns - W_24H, side="left"))

                ctx_feats["tc_count_5m"] = float(max(0, right_idx - idx_5m))
                ctx_feats["tc_count_30m"] = float(max(0, right_idx - idx_30m))
                ctx_feats["tc_count_2h"] = float(max(0, right_idx - idx_2h))
                ctx_feats["tc_count_24h"] = float(max(0, right_idx - idx_24h))

                p_slice = tc_p[idx_24h:right_idx]
                ctx_feats["tc_p0_count"] = float((p_slice == 0).sum())
                ctx_feats["tc_p1_count"] = float((p_slice == 1).sum())
                ctx_feats["tc_p2_count"] = float((p_slice == 2).sum())
                ctx_feats["tc_p3_count"] = float((p_slice == 3).sum())

        # Construct vector with normalized scales for distance math
        combined_scaled = {}
        for k, v in tel_feats.items():
            if "score" in k:
                combined_scaled[k] = float(v)
            elif "mean" in k or "min" in k or "max" in k or "diff" in k or "mag" in k:
                combined_scaled[k] = float(v)  # Telemetry values
            else:
                combined_scaled[k] = float(v)

        for k, v in ctx_feats.items():
            if "sec" in k:
                combined_scaled[k] = float(np.log1p(max(0.0, v)) / 10.0)  # Log-scale sec
            else:
                combined_scaled[k] = float(v / 10.0)

        vector_names = sorted(combined_scaled.keys())
        vector_vals = [combined_scaled[k] for k in vector_names]

        return EventSignature(
            event_id=event_id,
            start_timestamp=t_start.isoformat(),
            end_timestamp=t_end.isoformat(),
            duration_seconds=duration_sec,
            affected_channels=affected,
            num_affected_channels=len(affected),
            telemetry_features=tel_feats,
            context_features=ctx_feats,
            feature_vector=vector_vals,
            feature_names=vector_names,
        )
