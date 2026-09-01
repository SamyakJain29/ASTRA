# Architecture

## Purpose

ASTRA uses a research-first, configuration-driven Python architecture. Phase 1 prioritizes inspectable data handling, interpretable baselines, reproducible evaluation, and a clear boundary between measured evidence and future ideas.

This document describes intended component responsibilities. It does not imply that research algorithms or data pipelines have already been implemented.

## Data flow

The intended Phase 1 flow is:

```text
explicit configuration
        |
        v
dataset inspection -> reproducible preparation -> baseline execution -> evaluation
        |                     |                        |                |
        v                     v                        v                v
 observed metadata      derived datasets          predictions      measured metrics
```

Inputs and generated artifacts remain outside version control. Configuration, code, tests, and documentation are versioned so that derived data and results can later be reproduced.

## Package responsibilities

The Python package lives under `src/astra/`.

| Package | Phase 1 responsibility |
| --- | --- |
| `astra.data` | Dataset access, observed-schema validation, and reproducible transformations. Raw data must never be modified. |
| `astra.features` | Deterministic feature construction after input fields and units have been verified. |
| `astra.models` | Interpretable baseline interfaces and, when explicitly requested, statistical/dynamic threshold and Isolation Forest implementations. |
| `astra.evaluation` | Split protocols, metric computation, and evaluation records with clearly documented aggregation rules. |
| `astra.context` | Scaffold for later operational-context interfaces; no context algorithm is implemented now. |
| `astra.memory` | Scaffold for later operator-validated event-memory interfaces; no memory algorithm is implemented now. |
| `astra.explain` | Scaffold for later explanation interfaces; no explanation algorithm is implemented now. |
| `astra.utils` | Small cross-cutting utilities, including reusable logging configuration. |

Dependencies should point from scripts into package modules, and from higher-level research workflows toward small reusable components. Package code must not depend on CLI scripts. Circular dependencies and unnecessary abstraction layers should be avoided.

## Command-line entry points

The `scripts/` directory exposes workflow boundaries without pretending that unfinished functionality exists:

- `inspect_dataset.py` is the entry point for safe structural inspection.
- `prepare_subset.py` is the entry point for reproducible subset preparation.
- `run_baseline.py` is the entry point for baseline execution.
- `evaluate.py` is the entry point for evaluation.

During repository scaffolding, these commands may expose help and explicit TODO behavior. They must not emit fabricated data, anomaly scores, or results.

## Configuration

Configuration is separated by concern:

- `configs/data.yaml` holds data-location and preparation placeholders.
- `configs/baseline.yaml` holds baseline-selection and parameter placeholders.
- `configs/experiment.yaml` holds experiment-control and evaluation placeholders.

Placeholder values are engineering inputs, not claims about an ESA dataset. Dataset-specific field names, units, labels, sampling behavior, and partitions must be added only after inspection.

## Storage boundaries

- `data/raw/` contains immutable source files.
- `data/interim/` contains intermediate transformations.
- `data/processed/` contains reproducible final datasets, preferably in Parquet when appropriate.
- `data/external/` contains separately sourced supporting data whose provenance must be recorded.

Large data, checkpoints, caches, and experiment artifacts are ignored by Git. Raw data is never overwritten by preparation code.

## Reproducibility and observability

Research runs should eventually record configuration, input identity, code revision, environment, random seeds where relevant, and output locations. Logging must make workflow progress and failures inspectable without embedding secrets or duplicating large datasets.

Important transformations require focused unit tests. Repository-level smoke tests verify imports, configuration readability, and the expected directory layout.

## Current boundaries

This scaffold does not include:

- dataset downloads or an asserted ESA schema;
- contextual, memory, or explanation algorithms;
- neural networks;
- a frontend or backend application;
- authentication, microservices, or deployment infrastructure; or
- experimental findings.

