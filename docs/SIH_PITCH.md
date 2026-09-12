# ASTRA — Space Operations Intelligence Platform

Smart India Hackathon 2026 · Space Technology · Team Hercules

## Problem and approach

Rare but legitimate spacecraft behavior can repeatedly trigger unusual-event reviews. Operators need telemetry evidence, operational context, and a record of previously validated patterns.

ASTRA combines global orbital awareness, public RF observation integration, anomaly detection, and operator-validated Adaptive Event Memory. The first unfamiliar event remains visible. After review, an operator can validate a legitimate operational pattern for future similarity matching. This does not diagnose physical root cause.

## Two separate exploratory evaluations

### EXPLORATORY MISSION-1 EVALUATION

On the exploratory ESA Mission-1 subset, the 3σ GlobalStd detector identified 25 of 29 labelled genuine anomaly windows (86.2%). Five of 36 labelled Rare Event windows triggered detector alarms. Adaptive Event Memory reduced those five detector alarms to four while suppressing none of the 25 detected genuine anomalies.

In a separate retrospective, label-conditioned memory-stage recurrence study, 27 of 36 Rare Event windows were subsequently recognized as previously learned operational patterns, reducing repeated operator review by 75.0%.

The end-to-end detector evaluation and the retrospective memory-stage recurrence study are separate evaluations with different denominators.

| Metric | Result |
| --- | --- |
| Genuine anomaly detection before and after memory | 25 / 29 = 86.2% |
| Rare Event detector alarms before Event Memory | 5 |
| Rare Event detector alarms after Event Memory | 4 |
| End-to-end Rare Event detector-alarm reduction | 20.0% |
| Detected genuine anomalies suppressed by Event Memory | 0 / 25 |
| Retrospective memory-stage Rare Event recognition | 27 / 36 = 75.0% |
| Review-required Rare Event windows in recurrence study | 9 / 36 |

The 75.0% figure refers to repeated-review reduction in the retrospective label-conditioned memory-stage study, not end-to-end detector alarm reduction or anomaly recall improvement.

### End-to-end pipeline

```text
Historical telemetry -> 3σ GlobalStd detector -> detector alarms only
  -> event signature + command context -> Event Memory -> operator decision
```

The detector-positive genuine anomaly denominator is 25. The labelled genuine anomaly cohort is 29. Four labelled anomalies were not detected by the baseline; they were not suppressed by memory.

### Memory-stage recurrence

Only labelled Rare Event test windows enter this separate retrospective cohort. Memory starts empty and windows are processed chronologically. Each signature is queried before operator validation. Unmatched windows require review and are then stored as VALID_OPERATION; matched windows count as subsequently recognized. All 36 cohort windows enter this study, irrespective of detector alarms.

### Safeguards and limits

A conservative score-discrepancy guard rejects a memory match when current anomaly evidence is substantially stronger than the stored operational pattern. It is conditional on both current and stored scores; exceeding 3.5 alone does not automatically bypass memory. Thresholds and safeguards are not a guarantee against missed anomalies.

This is an exploratory Mission-1 evaluation, **not a pristine untouched final benchmark**. Thresholds and memory behavior were developed while inspecting Mission-1. Cross-mission validation remains future work. Reproduction under frozen thresholds and an untouched evaluation protocol is required before generalization claims.

Both studies use CH_41–CH_46, anonymized research telemetry channels, and similarity threshold 0.80. Labels define historical event windows and simulate operator review; they are not similarity features. The existing neighboring-sample fallback for empty windows is retained. Repeated-review reduction counts windows relative to reviewing every cohort window; it is not a measurement of operator time saved.

## Evaluator demonstration

Use historical ESA Mission-1 telemetry scenario replay in Operations to demonstrate first review, operator validation, pattern recurrence, and an unfamiliar anomaly. These selected scenarios illustrate the workflow; they are not a live mission feed or the complete experiment. Event Memory in the current backend is session-local.

The Alerts workspace is a historical research alert archive and is not synchronized to Operations. The Research workspace reports both studies with separate denominators. Full local research data is not bundled in Git; deployed availability depends on actual prepared assets.

## Data-source boundaries

- CelesTrak supplies public orbital elements for local SGP4 propagation, not spacecraft telemetry.
- SatNOGS supplies opportunistic public community RF observations and available frames/decoding, not an authorized mission feed.
- ESA Mission-1 supplies historical anonymized research telemetry, not live spacecraft telemetry.
- Authorized mission telemetry is not connected. ASTRA is not connected to ISRO mission telemetry, flight-certified, production-proven, or an autonomous spacecraft controller.

## Reproduction and evidence

```bash
uv run python scripts/run_memory_experiment.py
uv run python scripts/run_memory_stage_recurrence_experiment.py
```

See [end-to-end results](../reports/astra_memory_experiment.md), [recurrence results](../reports/astra_memory_stage_recurrence.md), and [research integrity review](../reports/astra_integrity_audit.md). The historical context-ablation study is a separate exploratory comparison; its numbers are not the headline configuration.

The implementation uses Python 3.11, FastAPI, NumPy, Pandas/PyArrow, scikit-learn, SQLite-backed Event Memory, SGP4, and an HTML/CSS/JavaScript interface.
