# ASTRA Adaptive Event Memory Chronological Experiment Report

## EXPLORATORY MISSION-1 EVALUATION

Historical ESA Mission-1 channels 41–46; labelled event windows and simulated operator validation. Only actual GlobalStd detector alarms enter Event Memory.
An event alarms when any selected channel sample exceeds its detector threshold.
The existing empty-window neighboring-sample fallback is retained.

Detector: GlobalStdDetector; thresholds: {'channel_41': 3.0, 'channel_42': 3.0, 'channel_43': 3.0, 'channel_44': 3.0, 'channel_45': 3.0, 'channel_46': 3.0}.
Similarity threshold: 0.80.

| Metric | Measured result |
| --- | --- |
| Labelled test events | 65 |
| Labelled Rare Events | 36 |
| Genuine anomaly detection before memory | 25 / 29 = 86.2% |
| Genuine anomaly detection after memory | 25 / 29 = 86.2% |
| Rare Event alarms before memory | 5 |
| Rare Event alarms after memory | 4 |
| Rare Event alarm reduction | 20.0% |
| Detected genuine anomalies suppressed by memory | 0 / 25 |

The detector detected 25 of 29 labelled genuine anomalies. Event Memory retained 25 of those detections and suppressed 0. Rare Event alarm reduction was 20.0% in this run.

This is NOT a pristine untouched final benchmark. Thresholds and memory behavior were developed while inspecting Mission-1. Reproduction under frozen thresholds and an untouched evaluation protocol is required before generalization claims. Cross-mission validation remains future work.
