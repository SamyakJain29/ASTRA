# ASTRA Telecommand Context Ablation Report

## Executive Summary

This report presents a controlled ablation study evaluating the impact of 
**Telecommand Context Features** on ASTRA's Adaptive Event Memory performance.

## Comparative Metrics Table

| Metric | Mode A: Telemetry Only | Mode B: Telemetry + Telecommand Context | Impact of Context |
|---|---|---|---|
| **Rare Event Alarm Reduction** | 91.7% (33/36) | 75.0% (27/36) | **-16.7%** |
| **Genuine Anomaly Recall** | 82.8% (24/29) | 96.6% (28/29) | **+13.8%** |
| **Genuine Anomalies Suppressed** | 5 | 1 | **-4** |

## Key Findings

1. **Higher Anomaly Recall Safety**: Adding telecommand context improves Genuine Anomaly Recall from 82.8% to 96.6% (+13.8%), reducing false anomaly suppressions from 5 down to 1.
2. **Context-Aware Discrimination**: Telecommand context provides vital operator state signals that prevent uncommanded anomaly telemetry from falsely matching nominal patterns.
3. **Balanced Operational Performance**: Telecommand context ensures spacecraft safety by prioritizing genuine anomaly preservation over overly aggressive alarm suppression.