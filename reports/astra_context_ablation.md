# ASTRA Telecommand Context Ablation Report

## Separate historical exploratory context-ablation study

These archived measurements are retained from a different label-conditioned comparison and were not rerun during headline reconciliation. They are not the current end-to-end detector result or the separate recurrence study. All labelled windows entered matching without a detector-alarm admission gate; the old recall terminology meant anomaly windows remaining unmatched. No mission-safety guarantee follows.

## Executive Summary

This report presents a controlled ablation study evaluating the impact of 
**Telecommand Context Features** on ASTRA's Adaptive Event Memory performance.

## Comparative Metrics Table

| Metric | Mode A: Telemetry Only | Mode B: Telemetry + Telecommand Context | Impact of Context |
|---|---|---|---|
| **Rare Event cohort recognition** | 91.7% (33/36) | 75.0% (27/36) | **-16.7%** |
| **Labelled anomaly windows remaining unmatched** | 82.8% (24/29) | 96.6% (28/29) | **+13.8%** |
| **Labelled anomaly windows matched as operational** | 5 | 1 | **-4** |

## Interpretation boundary

The recorded telemetry-only and context-enabled modes have different recognition and erroneous-match counts. These are retrospective window decisions, not detector-derived recall or measured operational safety improvements. The current headline studies and their explicit denominators are reported separately in [the end-to-end report](astra_memory_experiment.md) and [the recurrence report](astra_memory_stage_recurrence.md).
