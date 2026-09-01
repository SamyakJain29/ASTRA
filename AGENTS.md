# ASTRA Engineering Instructions

## Project

ASTRA is a research-driven spacecraft health intelligence platform being developed for SIH 2026.

The research goal is to determine whether operational context and operator-validated event memory can reduce false alarms caused by rare nominal spacecraft events without materially reducing genuine-anomaly recall.

ASTRA must be scientifically defensible and reproducible.

## Current Phase

Phase 1: Research Core.

The current goal is NOT to build the web application.

Current priorities:

1. Load ESA spacecraft telemetry data safely.
2. Validate dataset structure.
3. Create reproducible preprocessing.
4. Extract labelled telemetry events.
5. Implement simple anomaly-detection baselines.
6. Evaluate them using meaningful metrics.
7. Keep experiments reproducible.

## Strict Scope Rules

Do NOT:

- build a frontend
- build authentication
- create microservices
- add Docker unless specifically requested
- add Kubernetes
- add blockchain
- add an LLM
- implement collision avoidance
- implement satellite imagery analysis
- introduce unnecessary frameworks
- invent dataset fields
- invent research results
- hard-code fabricated anomaly scores
- claim model accuracy without experiments

If dataset structure is unknown, inspect it or create an adapter/interface. Never fabricate a schema.

## Engineering Principles

Prefer:

- simple implementations
- modular components
- type hints
- clear interfaces
- deterministic experiments
- testable functions
- configuration over hard-coded values
- streaming/lazy data processing when possible
- Parquet for processed telemetry
- memory-efficient processing

Avoid unnecessary abstractions.

## Python

Target Python 3.11.

Use:

- PyTorch
- scikit-learn
- NumPy
- Polars
- Pandas only where useful
- DuckDB
- PyArrow
- Pydantic
- PyYAML
- Matplotlib
- pytest
- Ruff

Do not add dependencies without a concrete reason.

## Data

Raw datasets MUST NOT be modified.

Directory policy:

data/raw        immutable source data
data/interim    intermediate transformations
data/processed  reproducible final datasets

Do not commit large datasets to Git.

All processed datasets must be reproducible from scripts.

## Research Integrity

Never fabricate:

- metrics
- anomaly labels
- dataset descriptions
- citations
- experimental results

Clearly distinguish:

- confirmed facts
- assumptions
- engineering targets
- measured results

## Models

Start with interpretable baselines before deep models.

Initial baselines:

1. statistical/dynamic threshold
2. Isolation Forest

Later:

3. forecasting model
4. ASTRA contextual classifier
5. ASTRA Adaptive Event Memory

Do not implement later models until explicitly requested.

## Testing

Every important data transformation must have unit tests.

Before completing a task:

1. run tests
2. run Ruff
3. describe changed files
4. report unresolved assumptions

## Git

Keep commits small and logically grouped.

Never commit:

- datasets
- model checkpoints
- API keys
- .env files
- generated experiment artifacts

## Coding Style

Names should be descriptive but concise.

Prefer small functions.

Avoid giant scripts.

Avoid unnecessary classes.

Public functions should have short docstrings.

Add comments only when they explain reasoning rather than obvious syntax.

## Decision Rule

If unsure between:

A. adding complexity

and

B. keeping the research pipeline simple

choose B.

If scientific assumptions are uncertain, ask rather than invent.