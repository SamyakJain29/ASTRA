# 🤝 Contributing to ASTRA

## Spacecraft Telemetry Health Intelligence Platform

> **Build carefully. Measure honestly. Document everything.**

Thank you for your interest in contributing to **ASTRA**.

ASTRA is a research-driven spacecraft telemetry health intelligence platform being developed for **SIH 2026**. The project explores whether operational context and operator-validated event memory can reduce unnecessary anomaly alarms without materially reducing genuine anomaly detection.

Because ASTRA combines **research, data engineering, anomaly detection, adaptive memory, orbital intelligence, and an interactive Mission Control demonstrator**, contributions need to preserve both:

* **Engineering quality**
* **Research integrity**

A feature that works technically but makes an unsupported scientific claim, introduces temporal leakage, silently changes dataset semantics, or makes experiments irreproducible is **not considered a successful contribution**.

---

# 📋 Table of Contents

* [Before You Contribute](#-before-you-contribute)
* [Project Philosophy](#-project-philosophy)
* [Repository Structure](#-repository-structure)
* [Development Setup](#-development-setup)
* [Development Workflow](#-development-workflow)
* [Branching](#-branching)
* [Commit Guidelines](#-commit-guidelines)
* [Testing](#-testing)
* [Code Quality](#-code-quality)
* [Research Contributions](#-research-contributions)
* [Data Contributions](#-data-contributions)
* [Machine Learning Contributions](#-machine-learning-contributions)
* [Memory System Contributions](#-memory-system-contributions)
* [API Contributions](#-api-contributions)
* [Mission Control Contributions](#-mission-control-contributions)
* [External Data Sources](#-external-data-sources)
* [Documentation](#-documentation)
* [Pull Requests](#-pull-requests)
* [Pull Request Checklist](#-pull-request-checklist)
* [What Not to Commit](#-what-not-to-commit)
* [Research Integrity Rules](#-research-integrity-rules)
* [Security](#-security)
* [Roadmap Contributions](#-roadmap-contributions)
* [Questions and Discussions](#-questions-and-discussions)

---

# 🚀 Before You Contribute

Before making a change, please understand the project's central research question:

> **Can operational context and operator-validated event memory reduce false spacecraft anomaly alarms caused by rare nominal events without materially reducing genuine anomaly detection?**

ASTRA is not simply an anomaly detector.

The system combines:

```text
Telemetry
    +
Operational Context
    +
Anomaly Detection
    +
Event Signatures
    +
Operator Validation
    +
Adaptive Memory
    +
Anomaly Protection
    +
Temporal Evaluation
```

The project therefore has several interacting layers.

A change in one layer may affect assumptions in another.

Before implementing a major feature, check the relevant documentation in:

```text
docs/
```

Especially:

```text
ARCHITECTURE.md
DATASET.md
RESEARCH_SPEC.md
EXPERIMENTS.md
PRODUCTION_QUALITY_GATE.md
SIH_PITCH.md
```

---

# 🧠 Project Philosophy

ASTRA follows a research-first philosophy.

### 01 — Evidence over assumptions

Do not turn an assumption into a documented fact.

### 02 — Reproducibility over convenience

A result that cannot be reproduced should not be presented as a reliable research result.

### 03 — Context over blind suppression

An event being unusual does not automatically make it unsafe.

### 04 — Memory is evidence, not authority

A previously validated event should provide contextual information, not unconditional permission to suppress future events.

### 05 — Operators remain in the loop

ASTRA is designed to assist human interpretation rather than silently replace it.

### 06 — Demonstrations are not experiments

A successful scenario demonstration does not constitute scientific validation.

---

# 🏗️ Repository Structure

The major project areas are:

```text
ASTRA/
│
├── app/
│   ├── backend/
│   │   └── main.py
│   │
│   └── frontend/
│
├── configs/
│   ├── data.yaml
│   ├── baseline.yaml
│   ├── experiment.yaml
│   └── demo.yaml
│
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
│
├── docs/
│
├── reports/
│
├── scripts/
│
├── src/
│   └── astra/
│       ├── data/
│       ├── features/
│       ├── models/
│       ├── memory/
│       ├── evaluation/
│       ├── sources/
│       └── utils/
│
└── tests/
```

The repository separates:

* Application code
* Research code
* Data processing
* Configuration
* Experiments
* Documentation
* Tests

Please preserve these boundaries where possible.

---

# 💻 Development Setup

## Requirements

ASTRA currently expects:

| Requirement           | Version                              |
| --------------------- | ------------------------------------ |
| Python                | **3.11**                             |
| Git                   | Current stable version               |
| ESA Mission-1 archive | Required for dataset preparation     |
| Network access        | Required for live external providers |

---

## Clone the Repository

```bash
git clone https://github.com/TanayP26/ASTRA.git
cd ASTRA
```

---

## Create a Virtual Environment

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

---

## Install Development Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

---

# 🧪 Verify Your Environment

Before modifying anything, run:

```bash
pytest
```

Then:

```bash
ruff check .
```

If either command fails **before your changes**, record that in your contribution rather than silently assuming that the failure was caused by your work.

---

# 🔄 Development Workflow

The recommended contribution workflow is:

```text
                    ┌───────────────┐
                    │   Understand  │
                    │   the change  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Read Relevant │
                    │ Documentation │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Create Branch │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Implement     │
                    │ Small Change  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Add / Update  │
                    │ Tests         │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Run pytest    │
                    │ Run ruff      │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Update Docs   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Open Pull     │
                    │ Request       │
                    └───────────────┘
```

Keep contributions focused whenever possible.

---

# 🌿 Branching

Create a dedicated branch for your work.

Example:

```bash
git checkout -b feature/your-feature-name
```

Other useful naming patterns:

```text
feature/...
fix/...
research/...
docs/...
test/...
refactor/...
security/...
```

Examples:

```text
feature/memory-audit-log
fix/websocket-reconnect
research/baseline-evaluation
docs/dataset-provenance
test/event-signature
security/api-rate-limit
```

Avoid doing unrelated changes in the same branch.

---

# 📝 Commit Guidelines

Keep commits focused and understandable.

Good:

```text
Add event signature similarity test
```

```text
Document temporal evaluation boundary
```

```text
Fix cached orbit source status
```

```text
Add validation for feedback payload
```

Avoid vague commits such as:

```text
update
```

```text
changes
```

```text
fix stuff
```

```text
final
```

A useful commit should communicate **what changed**.

---

# 🧪 Testing

Tests are an important part of ASTRA because changes can affect both software behavior and research validity.

Run:

```bash
pytest
```

before submitting a pull request.

---

## What Should Be Tested?

Depending on the change, tests may be appropriate for:

### Data

* Archive inspection
* Dataset preparation
* Schema handling
* Row counts
* Temporal ordering
* Integrity checks

### Features

* Event signatures
* Telemetry statistics
* Telecommand context
* Normalization
* Missing data behavior

### Models

* Detector behavior
* Threshold behavior
* Edge cases
* Anomaly-score calculations

### Memory

* Similarity matching
* Threshold enforcement
* Memory insertion
* Memory retrieval
* Protection guard behavior

### API

* Request validation
* Response structure
* Error handling
* Scenario transitions
* Feedback handling

### Sources

* Provider parsing
* Cache behavior
* Source-status reporting
* Failure handling

### Mission Control

* Scenario switching
* Dashboard data
* WebSocket behavior
* Reset behavior

---

# 🔍 Test Research Boundaries

For research-related changes, tests should also consider **what the implementation must not do**.

For example:

```text
Ground-truth label
       ↓
      ❌
Inference feature
```

Similarly:

```text
Future information
       ↓
      ❌
Historical prediction
```

And:

```text
Memory match
       ↓
      ❌
Automatic guarantee of safety
```

Negative tests can be just as important as positive tests.

---

# 🧹 Code Quality

Run:

```bash
ruff check .
```

before submitting.

Contributions should:

* Follow existing project conventions.
* Prefer clear code over clever code.
* Avoid unnecessary duplication.
* Keep functions focused.
* Validate external inputs.
* Handle failure paths explicitly.
* Avoid hidden state where possible.
* Document non-obvious assumptions.

If a transformation is research-critical, document why it exists.

---

# 🔬 Research Contributions

ASTRA welcomes research contributions.

Examples include:

* New anomaly detectors
* Alternative event-signature representations
* Memory-matching approaches
* Temporal evaluation methods
* Context-enrichment strategies
* New metrics
* Ablation studies
* Baseline comparisons
* Leakage detection
* Robustness experiments

However, research contributions must clearly distinguish:

```text
Implementation
      ≠
Experiment
      ≠
Result
      ≠
Conclusion
```

A new algorithm being implemented does not mean that it has been validated.

---

# 📊 Experiment Contributions

When adding an experiment, document:

```text
Dataset
Labels
Features
Split
Parameters
Configuration
Metrics
Metric Denominators
Results
Limitations
```

Where relevant, include:

* Experiment identifier
* Configuration hash
* Dataset hash
* Code/configuration version
* Dependency information
* Temporal boundaries

Do not report only the most favorable result.

---

# ⏳ Temporal Leakage

ASTRA uses chronological evaluation to reduce temporal leakage.

Contributors must be especially careful when introducing:

* Feature engineering
* Aggregations
* Rolling statistics
* Event windows
* Telecommand context
* Memory updates
* Validation procedures
* Normalization
* Imputation

Ask:

> **Could information from the future influence a decision about the past?**

If yes, the implementation needs to be redesigned or explicitly justified.

---

# 🧠 Machine Learning Contributions

When adding or changing a detector, document:

### Inputs

What data does the detector consume?

### Features

How are features calculated?

### Parameters

Which parameters affect behavior?

### Training

If applicable, what data is used for training?

### Evaluation

What temporal split is used?

### Metrics

Which metrics are calculated?

### Limitations

What does the detector not establish?

Avoid introducing opaque behavior without explaining its role in the research pipeline.

---

# 🧬 Event Signature Contributions

Event signatures are used to represent telemetry and operational context.

When changing event signatures, document:

```text
Input channels
       ↓
Windowing
       ↓
Statistics
       ↓
Context
       ↓
Normalization
       ↓
Signature Vector
```

A change to the signature representation may invalidate comparisons with previously generated memory entries.

Therefore, consider whether a signature version should be recorded.

---

# 🧠 Memory System Contributions

The adaptive memory is security- and research-sensitive.

Changes affecting memory should consider:

* Similarity threshold
* Vector normalization
* Memory insertion
* Memory retrieval
* Duplicate entries
* Memory provenance
* Operator identity
* Feedback validation
* Anomaly protection
* Persistence behavior

Never introduce behavior where:

```text
Similar historical event
        ↓
        =
Current event is safe
```

That violates ASTRA's core design philosophy.

---

# 🛡️ Anomaly Protection

Changes to the anomaly-protection guard require particular care.

The intended relationship is:

```text
Memory Evidence
      +
Current Anomaly Evidence
      ↓
Contextual Decision
```

not:

```text
Memory Evidence
      ↓
Suppress Everything
```

If a contribution changes suppression or escalation behavior, include tests for both:

### Known operational event

and:

### Genuine anomaly

A memory improvement should not silently weaken anomaly protection.

---

# 🔌 API Contributions

When modifying an API endpoint, consider:

* Request validation
* Response format
* Error handling
* Authentication requirements
* Authorization implications
* Logging
* Rate limiting
* Resource consumption
* Backward compatibility

Document new endpoints in the relevant documentation.

For example:

```text
GET  /api/example
POST /api/example
```

should have a clearly defined:

```text
Purpose
Inputs
Outputs
Errors
Security considerations
```

---

# 🛰️ Mission Control Contributions

Mission Control is a demonstrator for ASTRA's research concepts.

Changes should preserve the distinction between:

```text
DEMONSTRATION
```

and:

```text
SCIENTIFIC RESULT
```

For example, a scenario producing:

```text
KNOWN OPERATIONAL PATTERN
```

does not demonstrate a measured percentage reduction in real-world alarm volume.

Do not add UI language that implies scientific validation unless documented experiments support it.

---

# 🌍 External Data Sources

ASTRA can use external providers such as:

* CelesTrak
* SatNOGS

When modifying provider integrations:

* Handle unavailable sources.
* Validate responses.
* Preserve source provenance.
* Preserve cache status.
* Avoid treating cached information as fresh.
* Avoid assuming external data is always available.

The UI and API should make the distinction between:

```text
Fresh
Cached
Unavailable
```

clear.

---

# 💾 Data Contributions

Raw research data should **not** normally be committed to Git.

The repository expects raw and generated data to remain outside version control.

Do not commit:

```text
data/raw/
data/interim/
data/processed/
```

unless a specific project policy explicitly requires a small fixture.

For tests, prefer:

```text
Small
Synthetic
Deterministic
Purpose-built
```

fixtures.

---

# 🧪 Synthetic Test Data

When possible, create minimal synthetic datasets for tests.

For example:

```text
Normal Event
      +
Rare Operational Event
      +
Repeated Operational Event
      +
Genuine Anomaly
```

This makes tests:

* Fast
* Reproducible
* Portable
* Easy to understand
* Independent of the full ESA archive

Large mission datasets should not be required just to execute the normal test suite.

---

# 📚 Documentation Contributions

Documentation is considered part of the implementation.

Update documentation when changing:

* APIs
* Configuration
* Dataset preparation
* Research methodology
* Experiments
* Memory behavior
* Mission Control behavior
* Deployment
* Security
* Reproducibility

Relevant documents include:

```text
README.md
SECURITY.md
CONTRIBUTING.md

docs/ARCHITECTURE.md
docs/DATASET.md
docs/RESEARCH_SPEC.md
docs/EXPERIMENTS.md
docs/PRODUCTION_QUALITY_GATE.md
docs/SIH_PITCH.md
```

---

# 🧾 Document Assumptions

If your implementation depends on an assumption, document it.

For example:

```text
Assumption:
Telecommand context is temporally associated with an event.

Not established:
Telecommand activity causally produced the telemetry pattern.
```

This distinction is important.

Document what the system **observes** separately from what researchers **infer**.

---

# ❌ Do Not Hide Uncertainty

If you discover an unresolved issue:

```text
Don't:
"Fix" it silently.
```

Instead:

```text
Document:
- What is known
- What is uncertain
- Why it matters
- What evidence is missing
- What should happen next
```

ASTRA explicitly values transparent uncertainty over unsupported certainty.

---

# 🔐 Security Contributions

Security issues should be handled according to:

```text
SECURITY.md
```

Security-sensitive contributions include:

* Authentication
* Authorization
* Input validation
* Rate limiting
* Secret handling
* WebSocket security
* Memory access control
* Audit logging
* Dependency security
* Dataset integrity

Do not include real credentials or sensitive data in issues or pull requests.

---

# 📦 What Not to Commit

Never commit:

```text
.env
API keys
Passwords
Private keys
Database credentials
Access tokens
Raw mission datasets
Generated Parquet datasets
Large caches
Model checkpoints
Experiment artifacts
Temporary files
Local virtual environments
IDE configuration containing secrets
```

Check your changes before committing:

```bash
git status
```

and:

```bash
git diff
```

---

# 🔍 Pull Requests

When opening a pull request, explain:

### What changed?

A short technical summary.

### Why?

Explain the motivation.

### What was tested?

Include commands and relevant results.

### Does it affect research?

State whether the change affects:

* Dataset interpretation
* Features
* Labels
* Temporal splits
* Models
* Memory
* Metrics
* Research claims

### Does it affect security?

Mention any changes to:

* API exposure
* Authentication
* Authorization
* Data handling
* Secrets
* External providers

---

# 📝 Pull Request Template

A useful pull request description can follow:

```markdown
## Summary

Describe what this PR changes.

## Motivation

Explain why the change is needed.

## Changes

- Change 1
- Change 2
- Change 3

## Testing

- [ ] `pytest`
- [ ] `ruff check .`

## Research Impact

- [ ] No research impact
- [ ] Changes feature extraction
- [ ] Changes evaluation
- [ ] Changes detector behavior
- [ ] Changes memory behavior
- [ ] Changes experiment configuration

Explain any research implications here.

## Data Impact

- [ ] No dataset changes
- [ ] Dataset preparation changed
- [ ] Schema changed
- [ ] New derived artifact

## Security Impact

- [ ] No security impact
- [ ] Input validation
- [ ] API behavior
- [ ] Authentication/authorization
- [ ] Data handling
- [ ] Other

## Documentation

- [ ] Documentation updated
- [ ] No documentation required
```

---

# ✅ Pull Request Checklist

Before submitting a PR:

### Code

* [ ] Change is focused.
* [ ] Existing architecture is respected.
* [ ] No unnecessary dependencies were added.
* [ ] External input is validated where appropriate.

### Tests

* [ ] Tests added or updated where appropriate.
* [ ] `pytest` passes.
* [ ] `ruff check .` passes.

### Research

* [ ] No temporal leakage introduced.
* [ ] Ground-truth labels are not accidentally used as inference features.
* [ ] Dataset observations are not presented as model results.
* [ ] Demonstrator behavior is not presented as scientific evidence.
* [ ] Research assumptions are documented.

### Data

* [ ] No raw dataset committed.
* [ ] No generated large artifacts committed.
* [ ] Dataset semantics remain documented.

### Security

* [ ] No credentials committed.
* [ ] No sensitive information exposed.
* [ ] Security implications considered.

### Documentation

* [ ] Relevant documentation updated.
* [ ] Configuration changes documented.
* [ ] New behavior explained.

---

# 🧪 Definition of Done

A contribution is considered ready when:

```text
                ┌────────────────────┐
                │ Implementation     │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Tests               │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Code Quality        │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Documentation       │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Research Review     │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Security Review     │
                └─────────┬──────────┘
                          │
                          ▼
                    READY FOR PR
```

Not every contribution requires every stage to the same depth, but the relevant dimensions should be considered.

---

# 🚨 Research Integrity Rules

These rules are especially important for ASTRA.

## Rule 1 — Do Not Manufacture Results

Never modify an experiment simply because the result is inconvenient.

---

## Rule 2 — Do Not Hide Negative Results

A failed experiment is still useful information.

Document it.

---

## Rule 3 — Do Not Mix Demonstration and Evidence

A working dashboard scenario does not establish real-world performance.

---

## Rule 4 — Do Not Introduce Leakage

Future information must not accidentally influence historical predictions.

---

## Rule 5 — Do Not Collapse Semantics Without Justification

Source categories such as:

```text
Anomaly
Rare Event
Communication Gap
```

should not be silently converted into a simpler representation without documenting why.

---

## Rule 6 — Do Not Treat Correlation as Causation

Observed telecommand context may be useful without proving causal influence.

---

## Rule 7 — Do Not Overstate the System

ASTRA should not claim:

* Production spacecraft readiness
* Guaranteed anomaly detection
* Guaranteed alarm reduction
* Operational safety
* Generalization
* Scientific superiority

unless those claims are supported by reproducible evidence.

---

# 🛰️ Contribution Areas

There are many ways to contribute.

### 🔬 Research

* Detector experiments
* Memory algorithms
* Temporal evaluation
* Metrics
* Ablations
* Robustness studies

### 🧮 Data Engineering

* Archive inspection
* Streaming extraction
* Parquet preparation
* Integrity verification
* Dataset tooling

### 🧠 Machine Learning

* Feature engineering
* Anomaly detection
* Similarity methods
* Evaluation

### 👨‍🚀 Mission Control

* Dashboard improvements
* Telemetry visualization
* Orbit visualization
* Scenario UX
* Operator workflows

### 🌍 Space Data

* Catalog integrations
* Orbit propagation
* Ground-station analysis
* SatNOGS integrations

### 🔐 Security

* Authentication
* Authorization
* Input validation
* Rate limiting
* Audit trails
* Memory protection

### 📚 Documentation

* Architecture
* Research methodology
* Tutorials
* API documentation
* Reproducibility guides

---

# 🗺️ Roadmap Contributions

ASTRA's current roadmap includes:

```text
[x] Archive inspection
[x] Integrity-checked dataset preparation
[x] Temporal split foundations
[x] Interpretable detectors
[x] Adaptive event memory
[x] Orbit/source demonstrator

[ ] Complete baseline execution protocol
[ ] Run documented baseline comparisons
[ ] Predeclare anomaly-recall tolerance
[ ] Evaluate context without feedback leakage
[ ] Evaluate memory without feedback leakage
[ ] Expand dataset coverage
```

Contributions toward these items are especially valuable when they preserve the project's research boundaries.

---

# 🤝 How to Make a High-Quality Contribution

The best ASTRA contributions are:

### Small

A focused change is easier to review.

### Reproducible

Someone else should be able to reproduce the behavior.

### Tested

Important behavior should have automated coverage.

### Documented

Future contributors should understand why it exists.

### Honest

Claims should match evidence.

### Traceable

A reviewer should be able to follow:

```text
Change
  ↓
Reason
  ↓
Implementation
  ↓
Test
  ↓
Result
```

---

# 🌌 Final Principle

ASTRA is ultimately a research project.

That means the most valuable contribution isn't necessarily the biggest feature.

Sometimes the most important contribution is:

```text
A better test.
A clearer assumption.
A reproducible experiment.
A discovered limitation.
A corrected dataset issue.
A stronger security boundary.
A more honest conclusion.
```

All of these move the project forward.

---

<div align="center">

# 🛰️ Thank You for Contributing to ASTRA

### **Detect carefully. Remember responsibly. Protect aggressively.**

<br/>

> *Unusual does not always mean unsafe. Evidence should decide.*

<br/>

**ASTRA • SIH 2026**

</div>
