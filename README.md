# ASTRA

ASTRA is a research-first spacecraft health intelligence project. The repository is currently in Phase 1: Research Core, with an emphasis on a small, reproducible Python pipeline rather than an application or service.

The research question is:

> Can operational context and operator-validated event memory reduce false spacecraft anomaly alarms caused by rare nominal events without materially reducing genuine anomaly detection?

This is an open research question. The repository does not claim that the hypothesis
has been proven. Phase 1.2 has prepared research data, but no anomaly-detection model
has been trained or evaluated and no experimental result is reported.

## Phase 1 scope

Phase 1 is intended to support:

- safe inspection of an explicitly selected ESA telemetry dataset;
- schema discovery from observed data rather than assumptions;
- reproducible preprocessing and subset preparation;
- interpretable anomaly-detection baselines;
- evaluation of false alarms and genuine anomaly detection; and
- traceable, configuration-driven experiments.

The `context`, `memory`, and `explain` packages are placeholders only. Their algorithms are not part of this repository-scaffolding task.

The repository does not download or bundle ESA data. Local raw and generated data are
Git-ignored. No frontend, backend service, authentication system, microservice,
large-language-model component, or neural network is included.

## Repository layout

```text
configs/                 Reproducible research configuration
data/
  raw/                   Immutable source data (not committed)
  interim/               Intermediate transformations (not committed)
  processed/             Reproducible final datasets (not committed)
  external/              Third-party supporting data (not committed)
docs/                    Research and engineering documentation
scripts/                 Command-line entry points
src/astra/
  data/                  Dataset inspection, trust validation, and preparation
  features/              Feature construction
  models/                Interpretable baselines
  evaluation/            Evaluation protocols and metrics
  context/               Reserved context interfaces
  memory/                Reserved event-memory interfaces
  explain/               Reserved explanation interfaces
  utils/                 Shared utilities, including logging
tests/                   Automated checks
```

## Phase 1.2 prepared dataset

The pinned local archive is `ESA-Mission1.zip`, 3,776,246,054 bytes, with SHA-256
`8c81edb1e81af9084f38a3cc06fa06dbea73b504c99ce1b0fb92bda996b801a7`.
Authoritative source provenance, release, and licensing remain unresolved.

The configuration selects `channel_41` through `channel_46`. Each resolves to literal
metadata `subsystem_5`, `physical_unit_4`, group 8, and `Target=YES`, and each contains
15,381,169 samples. Preparation writes:

- six telemetry Parquet files under `data/processed/mission1/channels/`;
- `data/processed/mission1/events.parquet`, with 3,310 rows for 118 relevant IDs; and
- `data/processed/mission1/telecommands.parquet`, with 1,594,722 execution records.

The eight Parquet files total 708,766,239 bytes. Event categories remain the ESA
literals `Anomaly`, `Rare Event`, and `Communication Gap`. Relevant event IDs retain
their selected- and non-selected-channel label rows for structural context, and
telecommands remain a separate context table. Neither is interpreted causally.

No resampling, interpolation, normalization, or forward filling is performed. These
are prepared research assets, not model inputs with a finalized feature policy and
not evidence of model performance. See [DATASET.md](docs/DATASET.md) for schemas and
quality facts.

See [RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md) for the scientific question and claims boundary, [ARCHITECTURE.md](docs/ARCHITECTURE.md) for component responsibilities, [DATASET.md](docs/DATASET.md) for data policy, and [EXPERIMENTS.md](docs/EXPERIMENTS.md) for experiment-recording expectations.

## Development setup

ASTRA targets Python 3.11.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Activate the virtual environment using the command appropriate for the local shell before installing dependencies.

Run the repository checks with:

```bash
pytest
ruff check .
```

Inspect the supported arguments with:

```bash
python scripts/inspect_dataset.py --help
python scripts/prepare_subset.py --help
python scripts/run_baseline.py --help
python scripts/evaluate.py --help
```

The dataset inspection and Mission-1 subset preparation CLIs are implemented. From
the repository root, rebuild the configured subset with:

```bash
python scripts/prepare_subset.py --config configs/data.yaml
```

Use `--force` to rebuild and replace each generated file atomically, with the manifest
written last. The baseline and evaluation scripts remain explicit TODO entry points;
they do not train or score a model.

## Data handling

Raw input belongs under `data/raw/` and must remain unchanged. Large datasets, Parquet files, checkpoints, caches, and generated experiment artifacts are excluded from Git. Only placeholder files are tracked in the data directories.

The local dataset byte identity and prepared schemas are verified. Authoritative
licensing, source provenance, several field meanings, label semantics, and split rules
remain unresolved and must not be invented. See [DATASET.md](docs/DATASET.md).
