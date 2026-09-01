# ESA Mission-1 Event Recurrence Analysis

## Executive Summary

This report analyzes event class recurrence across train, validation, and test splits 
for ESA Mission-1 telemetry to evaluate whether operator-validated event memory 
can be tested honestly without synthetic data leakage.

### Key Findings (Rare Events)
- **Total Rare Event Classes**: 9
- **Classes Occurring More Than Once**: 8 (88.9%)
- **Classes First Observed Before Test & Repeated Later**: 6 (e.g. `class_10`, `class_12`, `class_14`, `class_16`, `class_2`, `class_4`)
- **Rare Event Classes First Appearing in Test (Unseen)**: 2 (e.g. `class_8`, `class_15`)

### Key Findings (Genuine Anomalies)
- **Total Anomaly Classes**: 11
- **Classes Occurring More Than Once**: 7
- **Classes First Observed Before Test & Repeated in Test**: 5 (e.g. `class_3`, `class_17`, `class_22`, `class_9`, `class_15`)
- **Anomaly Classes First Appearing in Test**: 2 (e.g. `class_1`, `class_14`)

## Detailed Event Class Breakdown

| Category | Class | Total Event IDs | Train Count | Validation Count | Test Count | Repeats? | First Split | Learned & Repeated in Test? |
|---|---|---|---|---|---|---|---|---|
| Anomaly | class_1 | 1 | 0 | 0 | 1 | No | test | No |
| Anomaly | class_11 | 1 | 1 | 0 | 0 | No | train | No |
| Anomaly | class_14 | 2 | 0 | 0 | 2 | Yes | test | No |
| Anomaly | class_15 | 5 | 4 | 0 | 1 | Yes | train | Yes |
| Anomaly | class_17 | 3 | 1 | 0 | 2 | Yes | train | Yes |
| Anomaly | class_2 | 1 | 1 | 0 | 0 | No | train | No |
| Anomaly | class_20 | 4 | 4 | 0 | 0 | Yes | train | No |
| Anomaly | class_21 | 1 | 1 | 0 | 0 | No | train | No |
| Anomaly | class_22 | 2 | 1 | 0 | 1 | Yes | train | Yes |
| Anomaly | class_3 | 29 | 6 | 2 | 21 | Yes | train | Yes |
| Anomaly | class_9 | 2 | 1 | 0 | 1 | Yes | train | Yes |
| Communication Gap | class_5 | 4 | 4 | 0 | 0 | Yes | train | No |
| Rare Event | class_10 | 3 | 2 | 0 | 1 | Yes | train | Yes |
| Rare Event | class_12 | 3 | 1 | 0 | 2 | Yes | train | Yes |
| Rare Event | class_14 | 28 | 13 | 1 | 14 | Yes | train | Yes |
| Rare Event | class_15 | 1 | 0 | 0 | 1 | No | test | No |
| Rare Event | class_16 | 10 | 5 | 0 | 5 | Yes | train | Yes |
| Rare Event | class_2 | 3 | 1 | 0 | 2 | Yes | train | Yes |
| Rare Event | class_4 | 5 | 2 | 0 | 3 | Yes | train | Yes |
| Rare Event | class_6 | 2 | 2 | 0 | 0 | Yes | train | No |
| Rare Event | class_8 | 8 | 0 | 0 | 8 | Yes | test | No |

## Feasibility of Adaptive Event Memory Evaluation

1. **Honest Chronological Evaluation**: Because multiple `Rare Event` classes appear during training/validation and recur during the test phase (such as `class_14` with 13 train instances and 14 test instances, `class_16` with 5 train and 5 test instances), ASTRA can populate memory chronologically from early occurrences and evaluate alarm suppression on test occurrences.
2. **Unseen Pattern Protection**: Unseen rare events appearing only in test (like `class_8`) ensure that memory does not blindly suppress unknown patterns, providing a realistic test of threshold selectivity.
3. **Genuine Anomaly Protection**: Anomaly classes (like `class_3` and `class_14`) demonstrate how Adaptive Event Memory handles genuine faults when operator feedback correctly marks them as `CONFIRMED_ANOMALY` rather than `VALID_OPERATION`.