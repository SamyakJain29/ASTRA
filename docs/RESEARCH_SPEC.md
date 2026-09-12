# Research Specification

## Status

This document retains the original Phase 1 research intent and protocol requirements. Two exploratory Mission-1 studies are now implemented: the detector-gated end-to-end pipeline and a separate label-conditioned memory-stage recurrence study. See [current measured results](../README.md#research-evaluation). Neither establishes universal generalization. The provisional definitions below record the original design scope, not the absence of an implemented prototype.

## Research question

Can operational context and operator-validated event memory reduce false spacecraft anomaly alarms caused by rare nominal events without materially reducing genuine anomaly detection?

## Hypothesis under investigation

The working hypothesis is that adding validated operational context and a controlled memory of operator-validated nominal events to an anomaly-detection workflow can reduce alarms on rare-but-nominal behavior while preserving detection of genuine anomalies.

Current evidence is limited to exploratory Mission-1 windows: 25/29 genuine detections, 5 → 4 Rare Event detector alarms, and 0/25 detected genuine anomalies suppressed. The separate recurrence study recognized 27/36 windows (75.0%). Confirmatory evaluation under an untouched protocol remains required.

## Provisional concepts

These descriptions clarify intent without asserting a dataset schema:

- **False alarm:** an alert that the adopted ground-truth or review protocol identifies as nominal.
- **Genuine anomaly detection:** detection of an event identified as anomalous by the adopted ground-truth or review protocol.
- **Operational context:** validated information about spacecraft operating conditions that is available for the evaluated event. Exact context variables remain undecided until the dataset is inspected.
- **Operator-validated event memory:** a controlled record of past events independently validated by an operator or an equivalent authoritative process. Its representation and update policy are not yet defined.
- **Material reduction:** a predeclared tolerance for degradation in genuine anomaly detection. No tolerance is selected in this scaffold; it must be chosen before confirmatory evaluation.

These definitions must be revised if the selected dataset or annotation process uses different authoritative terminology.

## Evaluation intent

A scientifically useful comparison should eventually include:

1. a reproducible, interpretable baseline without added context or memory;
2. the same evaluation protocol with operational context, once a valid context representation is specified;
3. the same evaluation protocol with operator-validated event memory, once its validation and update policy is specified; and
4. an explicit comparison of false alarms against genuine-anomaly detection performance.

Statistical or dynamic thresholds and Isolation Forest are the planned initial baselines. Contextual classification and adaptive event memory are later research stages and must not be implemented without explicit scope approval.

## Protocol requirements

Before any result can be interpreted, the experiment must document:

- the exact dataset release and provenance;
- the observed schema and the meaning of any labels;
- inclusion and exclusion criteria;
- preprocessing and feature construction;
- a leakage-resistant split strategy appropriate to the observed temporal or grouping structure;
- baseline parameters and random seeds where applicable;
- definitions and aggregation rules for every reported metric;
- the process used to validate nominal and anomalous events; and
- the predeclared meaning of “materially reducing” genuine anomaly detection.

Potential metrics may include event-level false-alarm counts or rates, anomaly recall, precision, and alert burden, but the final set and its denominators must be selected only after the dataset and label semantics are known.

## Validity risks

The research design must address, where applicable:

- uncertain or incomplete labels;
- severe event imbalance;
- temporal dependence and leakage;
- repeated events crossing train and evaluation partitions;
- operator feedback leaking evaluation outcomes into memory;
- sensitivity to threshold selection;
- variation across spacecraft, subsystems, channels, or operating regimes; and
- conclusions that do not generalize beyond the evaluated data.

Whether each risk applies is an empirical question; this list does not assert properties of an ESA dataset.

## Claims boundary

ASTRA may report the measured exploratory results with their cohort definitions and denominators. It must not equate recurrence recognition with detector alarm reduction, measured operator time saved, physical diagnosis, or operational deployment evidence.

