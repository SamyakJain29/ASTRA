# ASTRA — Space Operations Intelligence Platform

**Global orbital awareness + public RF observations + spacecraft anomaly detection + operator-validated Adaptive Event Memory**

ASTRA combines global orbital awareness, public RF observation integration, spacecraft anomaly detection, and operator-validated Adaptive Event Memory. It addresses a spacecraft operations problem: rare but legitimate behavior can repeatedly trigger anomaly alarms, leaving operators to reassess patterns they have already validated.

The repository includes a FastAPI backend, an HTML/CSS/JavaScript interface, CelesTrak catalog ingestion with local SGP4 propagation, SatNOGS observation integration, anomaly-detection baselines, and an Event Memory workflow evaluated on historical ESA Mission-1 telemetry. Public orbital data, public RF observations, and historical research telemetry remain separate; no authorized live mission feed is connected.

Adaptive Event Memory lets operators validate an unusual operational pattern and recognize similar future events using telemetry signatures and operational context. The research question is whether this can reduce repeated rare-nominal alarms without materially reducing genuine-anomaly recall. The current evidence is exploratory and specific to a selected Mission-1 subset.

## Problem

Anomaly detectors can repeatedly flag rare but legitimate spacecraft behavior. Repeated alarms create alarm fatigue and consume operator attention that could otherwise go to unfamiliar or genuinely anomalous events.

Operators need context, supporting evidence, and memory of previously validated operational patterns. ASTRA supports that review; it does not diagnose physical root cause.

## Core Idea

```text
Telemetry
  -> anomaly detector
  -> event signature
  -> operational context
  -> similarity search
  -> operator validation
  -> event memory
  -> known operational pattern recognition
```

The first occurrence of an unfamiliar event is still surfaced. An operator reviews the evidence and validates whether it represents a legitimate operation. Only validated operational patterns enter the memory used for operational-pattern recognition; future similar events can then be recognized. Unmatched events remain unusual events requiring review, and the operator stays in control.

## What ASTRA Includes

| Workspace / capability | Current scope |
| --- | --- |
| **GLOBAL** | CelesTrak public active satellite catalog using GP/OMM orbital elements; local SGP4 propagation for current estimated position, altitude, velocity, and orbit paths; ground-contact/pass context, object search, and source freshness/provenance. |
| **RF OBSERVATIONS** | SatNOGS Community Ground Network integration in the object inspector: recent RF observations, raw frames, decoded telemetry only when genuinely available, explicit availability states, caching, and source-failure handling. |
| **FLEET** | Reserved for authorized mission spacecraft; intentionally empty when no authorized feed is connected. |
| **SPACECRAFT** | Workspace for authorized mission telemetry. Currently shows the disconnected state and does not fabricate spacecraft telemetry. |
| **ALERTS** | Unusual-event and known-operational-pattern status in the historical research/demo workflow. |
| **OPERATIONS** | Adaptive Event Memory, event evidence, and operator validation using prepared historical research scenarios. |
| **DATA SOURCES** | Provider health, source attribution, and cache/freshness state. |
| **RESEARCH** | ESA Mission-1 exploratory evaluation on selected telemetry channels. |


## Architecture

```text
CelesTrak                     SatNOGS
    |                             |
    v                             v
GP/OMM Elements                RF Observations / Public Telemetry
    |                             |
    v                             v
Local SGP4 Propagation         Observation Layer
    |
    v
Global Orbital Awareness
ESA Mission-1                  Authorized Mission Feed
    |                             |
    v                             v
Historical Telemetry          Future operational spacecraft
    |                         telemetry integration
    v                         (not connected)
Anomaly Detector
    |
    v
Event Signature + Context
    |
    v
Adaptive Event Memory <--- Operator-validated patterns
    |
    v
Operator Decision
FastAPI + HTTP/WebSocket endpoints
    |
    v
HTML / CSS / JavaScript operator interface
```

These sources are separate and not interchangeable. Orbital elements support propagated orbital awareness, RF observations describe public reception activity and available payloads, and ESA telemetry supports historical research. None establishes access to an authorized operational mission feed.

## Adaptive Event Memory

Event signatures summarize an event window using duration, affected channels, telemetry statistics, and detector-score features. Telecommand/context features include command timing and nearby command counts; command proximity is contextual evidence, not proof of causation.

Similarity matching combines feature-vector cosine similarity, affected-channel overlap, and command-context proximity. A score-discrepancy guard conservatively rejects some matches when an event is substantially more anomalous than its stored operational counterpart. Thresholds and these safeguards require mission-specific validation; they do not guarantee that every anomaly remains visible.

The SQLite-backed memory queries records validated as `VALID_OPERATION`. Confirmed-anomaly records can be recorded separately but are excluded from operational-pattern matching. The current backend uses an in-memory database, so its operator memory is session-local.

Ground-truth category labels are not inference features in the signature or similarity calculation. The historical experiment does use labelled event windows and labels to simulate operator feedback and evaluate outcomes. This is a retrospective simulation, not a prospective operational trial. Adaptive Event Memory applies established similarity methods within an operator-review workflow.

## Research Evaluation

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

**27/36 is a label-conditioned retrospective memory-stage recurrence measurement. It is not an end-to-end detector alarm count.** The 75.0% value measures repeated-review reduction in that separate study.

This is an exploratory Mission-1 evaluation, **not a pristine untouched final benchmark**. Thresholds and memory behavior were developed while inspecting Mission-1. Cross-mission validation remains future work. Reproduction under frozen thresholds and an untouched evaluation protocol is required before generalization claims.

Both studies use CH_41–CH_46, anonymized research telemetry channels, and similarity threshold 0.80. Labels define historical event windows and simulate operator review; they are not similarity features. The existing neighboring-sample fallback for empty windows is retained. Repeated-review reduction counts windows relative to reviewing every cohort window; it is not a measurement of operator time saved.

Reproduce the separate studies with prepared local data:

```bash
uv run python scripts/run_memory_experiment.py
uv run python scripts/run_memory_stage_recurrence_experiment.py
```

See the [end-to-end report](reports/astra_memory_experiment.md) and [recurrence report](reports/astra_memory_stage_recurrence.md). The separate [historical context-ablation report](reports/astra_context_ablation.md) is not either headline study.

## Data Sources

| Source | Data supplied | Boundary |
| --- | --- | --- |
| CelesTrak | Public orbital elements | Not spacecraft telemetry; displayed orbital state is locally propagated. |
| SatNOGS | Public community RF observations, frames, and available decoded telemetry | Not an authorized mission feed; availability varies by satellite and observation. |
| ESA Anomaly Detection Benchmark | Historical research telemetry and event annotations | Not live spacecraft telemetry. |
| Authorized Mission Feed | Future operational telemetry integration | Not connected in the current prototype. |

## Tech Stack

| Layer | Implemented technologies |
| --- | --- |
| Runtime and API | Python 3.11, FastAPI, Uvicorn, WebSocket |
| Telemetry and research | NumPy, Pandas, Polars, PyArrow, DuckDB, scikit-learn, Matplotlib |
| Orbital propagation | SGP4 |
| Event memory | SQLite through Python's standard library |
| Interface | HTML, CSS, JavaScript |
| Configuration and HTTP | Pydantic, PyYAML, HTTPX |
| Development | uv, pytest, Ruff |

## Repository Structure

```text
app/
  backend/               FastAPI endpoints and application state
  frontend/              HTML, CSS, and JavaScript interface
configs/                 Data, baseline, experiment, demo, and orbit settings
data/
  raw/                   Immutable source data (Git-ignored)
  interim/               Intermediate transformations (Git-ignored)
  processed/             Reproducible prepared datasets (Git-ignored)
  external/              External supporting data (Git-ignored)
  cache/                 Public-source caches (Git-ignored)
docs/                    Research and engineering documentation
reports/                 Existing research and engineering reports
scripts/                 Preparation, evaluation, and analysis entry points
src/astra/
  context/               Context package boundary
  data/                  Inspection, preparation, audits, and splits
  domain/                Space-object and telemetry domain definitions
  evaluation/            Research metrics
  explain/               Explanation package boundary
  features/              Event-signature extraction
  memory/                Adaptive Event Memory
  models/                Anomaly-detection baselines
  sources/               CelesTrak, SatNOGS, propagation, and passes
  utils/                 Logging and reproducibility helpers
tests/                   Automated checks
```

Local datasets, caches, checkpoints, and generated experiment artifacts are Git-ignored. Data-directory placeholder files may be tracked. Existing Markdown reports are repository documentation; they are not a bundled dataset.

## Quick Start

Install uv and use the repository's Python 3.11 environment:

```bash
git clone https://github.com/TanayP26/ASTRA.git
cd ASTRA
uv sync --extra dev
uv run uvicorn app.backend.main:app --host 127.0.0.1 --port 8050
```

Open: [http://127.0.0.1:8050](http://127.0.0.1:8050)

Checks:

```bash
uv run pytest
uv run ruff check .
```

Research/demo workflows require separately prepared local data and `artifacts/demo_scenarios.json`; a fresh clone does not include these assets. See [dataset documentation](docs/DATASET.md), [experiment documentation](docs/EXPERIMENTS.md), and the preparation scripts for the existing research workflow.

## Important Data Requirements

- ESA raw and processed research data is not bundled in GitHub because of size, licensing, and data-handling constraints. Obtain it separately under the applicable source terms; a fresh clone does not contain the full ESA dataset.
- Keep raw inputs immutable under `data/raw/`. Reproducible transformations belong under `data/interim/` and `data/processed/`.
- CelesTrak and SatNOGS public-source access depends on network and upstream availability.
- Supported public sources include caching and offline resilience. Cached data may be stale; freshness and failure states must be considered. Without a usable cache or network access, source data may be unavailable.

## Current Prototype Status

ASTRA is a research and engineering prototype suitable for SIH evaluation.

It is **not**:

- flight-certified;
- connected to ISRO mission telemetry;
- production-proven in spacecraft operations; or
- an autonomous spacecraft controller.

## Limitations

- Exploratory evidence covers only Mission-1 channels 41–46; cross-mission generalization remains unvalidated.
- Historical event windows and simulated operator feedback limit claims about end-to-end operational detection.
- No authorized live mission feed is connected; public RF telemetry availability varies.
- Public orbital state is propagated from orbital elements, not direct onboard telemetry.
- Backend Event Memory is session-local; durable feedback governance remains future work.

## Future Work

- Authorized CCSDS/MQTT/Kafka/WebSocket mission telemetry adapters.
- Mission-specific calibration and cross-mission evaluation.
- Reproduction under frozen thresholds and an untouched evaluation protocol.
- Richer operator-feedback governance, including memory revocation and versioning.
- Stronger anomaly detectors evaluated against interpretable baselines.
- Deployment and security hardening.

## SIH 2026

Smart India Hackathon 2026

| Field | Detail |
| --- | --- |
| Theme | Space Technology |
| Team | Hercules |
| Project | ASTRA |

## References

- [ESA Anomaly Detection Benchmark](https://github.com/kplabs-pl/ESA-ADB)
- [ESA Anomaly Dataset — Zenodo record](https://zenodo.org/records/12528696)
- [CelesTrak GP orbital elements](https://celestrak.org/NORAD/elements/gp.php)
- [SatNOGS Community Ground Network](https://network.satnogs.org/)
- [SGP4 Python package](https://pypi.org/project/sgp4/)
