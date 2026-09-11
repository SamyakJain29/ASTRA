# 🔐 ASTRA Security Policy

## Spacecraft Telemetry Health Intelligence Platform

> **Security principle:** Protect the data, protect the system, protect the operator.

ASTRA is a research-driven spacecraft telemetry health intelligence platform developed for **SIH 2026**.

Because ASTRA works with spacecraft telemetry, operational context, orbital information, operator feedback, and external data providers, security is treated as a fundamental part of the system architecture rather than an afterthought.

This document describes the current security model, protected assets, trust boundaries, security practices, known limitations, and responsible vulnerability reporting process.

---

# 📋 Table of Contents

* [Security Philosophy](#-security-philosophy)
* [Security Scope](#-security-scope)
* [Protected Assets](#-protected-assets)
* [Threat Model](#-threat-model)
* [Trust Boundaries](#-trust-boundaries)
* [Data Security](#-data-security)
* [Archive & Dataset Security](#-archive--dataset-security)
* [API Security](#-api-security)
* [Operator Feedback Security](#-operator-feedback-security)
* [Memory Security](#-memory-security)
* [External Data Sources](#-external-data-sources)
* [WebSocket Security](#-websocket-security)
* [Secrets & Credentials](#-secrets--credentials)
* [File System Security](#-file-system-security)
* [Research Integrity & Security](#-research-integrity--security)
* [Known Limitations](#-known-limitations)
* [Security Checklist](#-security-checklist)
* [Responsible Disclosure](#-responsible-disclosure)
* [Security Roadmap](#-security-roadmap)

---

# 🛡️ Security Philosophy

ASTRA follows a simple security principle:

```text
                ┌──────────────────────┐
                │       ASTRA          │
                └──────────┬───────────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
        Protect Data   Protect System  Protect Operator
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    Trustworthy Evidence
```

The system should never treat:

> **"The data exists"**

as equivalent to:

> **"The data is trustworthy."**

Similarly:

> **"An event was seen before"**

must not automatically mean:

> **"The event is safe."**

Security and research integrity therefore overlap in several parts of ASTRA.

---

# 🎯 Security Scope

Security considerations currently cover:

* Research datasets
* Raw spacecraft telemetry
* Extracted telemetry subsets
* Telecommand context
* Event signatures
* Operator feedback
* Adaptive event memory
* FastAPI endpoints
* WebSocket connections
* External data providers
* Cached provider data
* Configuration files
* API credentials
* Generated research artifacts
* Local filesystem contents
* Demonstrator scenarios

The repository is a **research demonstrator**, not a certified spacecraft flight system.

It should therefore **not** be deployed as a spacecraft command-and-control system without a separate security, safety, reliability, authentication, authorization, and operational certification process.

---

# 🔒 Protected Assets

The following assets should be considered sensitive or security-relevant.

| Asset                 | Risk                                  |
| --------------------- | ------------------------------------- |
| Raw telemetry archive | Data exposure / integrity             |
| Processed telemetry   | Data exposure / manipulation          |
| Telecommand records   | Operational-context exposure          |
| Event signatures      | Pattern disclosure / manipulation     |
| Operator feedback     | Trust and classification manipulation |
| Event memory          | Incorrect future classification       |
| Configuration files   | Research/system manipulation          |
| API credentials       | Unauthorized external access          |
| Database contents     | Integrity / confidentiality           |
| Cached orbital data   | Stale or manipulated information      |
| Generated reports     | Research integrity                    |
| Logs                  | Information disclosure                |
| `.env` files          | Credential exposure                   |

---

# 🧠 Threat Model

ASTRA considers several broad threat categories.

## 1. Malicious Input

An attacker may attempt to provide:

* malformed requests,
* oversized payloads,
* unexpected JSON structures,
* malicious strings,
* invalid identifiers,
* manipulated scenario names,
* unexpected file content.

The application should treat all externally supplied values as **untrusted input**.

---

## 2. Credential Exposure

API credentials may provide access to external services.

Examples include:

```text
NVIDIA_API_KEY
PICSART_API_KEY
```

These credentials must never be committed to Git.

They should be supplied through environment configuration or an equivalent secret-management mechanism.

---

## 3. Data Manipulation

An attacker or accidental process could modify:

* telemetry,
* event signatures,
* memory entries,
* configuration,
* generated research artifacts.

For a research system, this is particularly important because silent modification can affect both system behavior and scientific conclusions.

---

## 4. Operator Feedback Manipulation

ASTRA's memory mechanism depends on operator validation.

If an unauthorized party could inject fake validation events, the system could learn an incorrect pattern.

Conceptually:

```text
Attacker
   │
   ▼
Fake "VALID_OPERATION"
   │
   ▼
Memory Updated
   │
   ▼
Future Similar Event
   │
   ▼
Incorrect Contextual Downgrade
```

Therefore, operator feedback must be treated as a **trusted security boundary**.

---

## 5. External Provider Failure

External data sources may be:

* unavailable,
* delayed,
* stale,
* incomplete,
* malformed,
* rate-limited.

ASTRA explicitly exposes source/cache status so cached information is not silently presented as fresh provider data.

---

# 🚧 Trust Boundaries

ASTRA contains several distinct trust boundaries.

```text
                    INTERNET
                       │
          ┌────────────┴────────────┐
          │                         │
      CelesTrak                  SatNOGS
          │                         │
          └────────────┬────────────┘
                       │
                       ▼
              External Data Layer
                       │
                       ▼
              ┌────────────────┐
              │ FastAPI Backend│
              └───────┬────────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
      Telemetry    Memory      Orbit Data
          │           │           │
          └───────────┼───────────┘
                      ▼
               Mission Control
```

Additional trust boundaries exist between:

```text
Raw Archive → Extraction
Extraction → Processed Dataset
Client → API
API → Memory Store
API → External Providers
Operator → Feedback Endpoint
```

Every boundary should be treated as a location where validation and integrity checks matter.

---

# 📦 Archive & Dataset Security

ASTRA uses a locally supplied ESA Mission-1 archive.

The repository does **not** bundle the raw archive.

Raw datasets are Git-ignored and should remain outside version control.

The configured archive is identified using cryptographic hashes:

```text
SHA-256:
8c81edb1e81af9084f38a3cc06fa06dbea73b504c99ce1b0fb92bda996b801a7

MD5:
80750189d171f5f398fb3d96c49df12b
```

The SHA-256 value should be treated as the stronger integrity identifier.

---

## 🔍 Archive Validation

ASTRA performs trust-boundary validation before processing archive contents.

The project specifically treats nested Pickle payloads as untrusted until the relevant archive and member checks have been completed.

The security principle is:

```text
Archive
   ↓
Verify Identity
   ↓
Verify Structure
   ↓
Verify Member Information
   ↓
Validate Expected Payload
   ↓
Process
```

Never assume that a file is safe merely because its filename or extension looks correct.

---

# 🧬 Data Integrity

ASTRA follows these data-handling principles:

* Raw archives are never modified.
* Processing outputs are generated separately.
* Telemetry order is preserved.
* Generated files are replaced atomically.
* Manifests are written last.
* Dataset hashes are recorded.
* Schemas are recorded.
* Row counts are recorded.
* Configuration identifiers are recorded.

These controls help detect accidental or unauthorized changes to research artifacts.

---

# 🔌 API Security

ASTRA exposes a FastAPI backend.

Example routes include:

```text
GET  /health
GET  /api/mission/summary
GET  /api/telemetry
GET  /api/alerts/current
GET  /api/memory

POST /api/feedback
POST /api/demo/scenario/{scenario_name}
POST /api/demo/reset
```

The API should be considered an **untrusted-input boundary**.

Every request should be validated before being used by:

* data processing,
* memory operations,
* scenario selection,
* provider requests,
* filesystem operations,
* database operations.

---

# ⚠️ Production Authentication

The current research demonstrator should **not be interpreted as providing production-grade authentication or authorization**.

In particular, operator feedback is a security-sensitive action because it can influence adaptive memory.

A production implementation should introduce:

```text
Authentication
      ↓
Identity Verification
      ↓
Authorization
      ↓
Operator Role
      ↓
Feedback Validation
      ↓
Audit Log
      ↓
Memory Update
```

No external user should be assumed to be an authorized spacecraft operator merely because they can reach the API.

---

# 👨‍🚀 Operator Feedback Security

Operator feedback is one of ASTRA's highest-value trust boundaries.

The conceptual flow is:

```text
Telemetry Event
      ↓
Unusual Pattern
      ↓
Operator Review
      ↓
Operator Validation
      ↓
Memory Entry
```

A compromised feedback mechanism could therefore affect future classifications.

Production deployments should consider:

* Strong authentication
* Role-based authorization
* Operator identity
* Immutable audit records
* Timestamped validation
* Reason/comment fields
* Review history
* Feedback revocation
* Memory-entry provenance
* Multi-person approval for high-impact classifications

---

# 🧠 Memory Security

ASTRA's adaptive memory uses a SQLite-backed store and normalized vector similarity.

A match requires the configured similarity threshold.

The memory system should therefore be protected against:

### Memory Poisoning

An attacker inserts intentionally misleading patterns.

### Unauthorized Modification

Existing validated patterns are changed.

### Unauthorized Deletion

Useful historical knowledge is removed.

### Replay

Old feedback is submitted repeatedly.

### Over-Trust

A historical match is treated as proof that the current event is safe.

The final case is particularly important.

ASTRA intentionally includes an anomaly-protection guard so a strong current anomaly signal can remain actionable even when a superficially similar memory exists.

---

# 🛡️ Anomaly Protection

The conceptual security rule is:

```text
              Memory Match
                   │
                   ▼
           ┌───────────────┐
           │ Current Event │
           │ Anomaly Score │
           └───────┬───────┘
                   │
          ┌────────┴────────┐
          │                 │
       Acceptable         Strong
       candidate          anomaly
          │                 │
          ▼                 ▼
    Contextualize      Protection Guard
          │                 │
          ▼                 ▼
    Memory evidence     Keep actionable
                          signal
```

This is a defense against the dangerous assumption:

> **"We have seen something similar before, therefore it must be safe."**

Similarity is evidence.

It is not authorization.

---

# 🌐 External Data Sources

ASTRA may interact with external providers such as:

* CelesTrak
* SatNOGS

External systems should be treated as **untrusted upstream sources**.

Potential issues include:

* temporary outages,
* stale responses,
* malformed responses,
* unavailable observations,
* changed schemas,
* rate limiting,
* network errors.

ASTRA's offline-aware behavior can fall back to cached information.

However:

> **Cached information must never be silently interpreted as fresh information.**

Source and cache status should remain visible to downstream consumers.

---

# 🛰️ Orbital Data Security

Orbital data can influence the context presented to operators.

Therefore:

```text
External Orbital Data
        ↓
Provider Validation
        ↓
Cache / Source Metadata
        ↓
Propagation
        ↓
Mission Control
```

The system should maintain enough provenance to distinguish:

```text
LIVE / FRESH
```

from:

```text
CACHED / HISTORICAL
```

and:

```text
UNAVAILABLE
```

This prevents stale orbital information from being mistaken for current state.

---

# ⚡ WebSocket Security

ASTRA exposes an orbit streaming endpoint:

```text
/ws/orbit/{norad_id}
```

The demonstrator uses this to provide approximately one-second orbit-state updates.

Production deployments should consider:

* connection limits,
* authentication,
* authorization,
* rate limiting,
* malformed identifiers,
* connection timeout,
* resource exhaustion,
* concurrent connection limits.

A public WebSocket endpoint should never be assumed to be safe simply because it only exposes telemetry or derived orbital state.

---

# 🔑 Secrets & Credentials

Never commit secrets into the repository.

### 🚫 Never commit

```text
.env
API keys
Passwords
Database credentials
Private certificates
Private keys
Access tokens
Cloud credentials
Provider credentials
```

Examples of environment variables that may contain sensitive information:

```text
NVIDIA_API_KEY
PICSART_API_KEY
DATABASE_URL
PGPASSWORD
PGUSER
```

---

## ✅ Recommended Development Pattern

Use:

```text
.env
```

locally and keep it outside Git.

Provide a sanitized:

```text
.env.example
```

containing placeholders only.

Example:

```env
NVIDIA_API_KEY=your_key_here
PICSART_API_KEY=your_key_here
DATABASE_URL=your_database_url_here
```

Never replace placeholders with real credentials in committed files.

---

# 💾 File System Security

ASTRA works with:

```text
data/raw/
data/interim/
data/processed/
artifacts/
reports/
```

These directories may contain large or sensitive research artifacts.

Recommended principles:

### Raw

Immutable and Git-ignored.

### Interim

Temporary extraction products.

### Processed

Reproducible research assets.

### Artifacts

Generated manifests and machine-readable outputs.

### Reports

Human-readable research records.

Generated files should not be trusted merely because they exist inside the repository directory.

---

# 🧪 Research Integrity & Security

For ASTRA, security also means protecting the **integrity of conclusions**.

A malicious modification to a dataset could produce a technically functioning system while invalidating the research.

Therefore:

```text
DATA INTEGRITY
      +
CODE INTEGRITY
      +
CONFIGURATION INTEGRITY
      +
EXPERIMENT INTEGRITY
      =
RESEARCH INTEGRITY
```

ASTRA explicitly distinguishes:

> **Dataset observations ≠ Model results**

> **Demo responses ≠ Live spacecraft conclusions**

> **Cached orbital data ≠ Fresh observations**

> **Similarity ≠ Causality**

> **Memory match ≠ Proof of safety**

This boundary should remain intact even as the platform becomes more sophisticated.

---

# 📊 Experiment Security

Research experiments should preserve:

* Dataset identity
* Dataset hash
* Configuration
* Feature definitions
* Model parameters
* Temporal split boundaries
* Dependency versions
* Output hashes
* Metric definitions
* Metric denominators

Experiments should not be manually edited after the fact to produce a desired result.

When practical, generated experiment outputs should be accompanied by immutable or cryptographically identifiable metadata.

---

# 🚨 Logging & Auditability

Security-relevant actions should be observable.

Examples include:

```text
API request
Operator feedback
Memory update
Memory deletion
Scenario change
Dataset preparation
Configuration change
External provider failure
Authentication failure
```

A production implementation should record enough information to answer:

> Who performed this action?

> When did it happen?

> What changed?

> What evidence was available?

> What configuration was active?

> What classification resulted?

---

# ⚠️ Known Limitations

ASTRA is currently a **research core and demonstrator**.

The existing project documentation does not establish that the system is production-hardened or suitable for direct spacecraft operational deployment.

Important areas requiring further hardening include:

* Production authentication
* Fine-grained authorization
* Operator identity management
* API rate limiting
* WebSocket access control
* Audit logging
* Memory access controls
* Secure deployment configuration
* Secret management
* Database hardening
* Dependency security scanning
* Container hardening
* Network segmentation
* Security monitoring
* Incident response
* Penetration testing
* Formal security review

These should be treated as engineering requirements for a future production system rather than silently assumed to already exist.

---

# ✅ Security Checklist

Before deploying an ASTRA instance beyond local research use:

### Secrets

* [ ] No API keys committed
* [ ] No passwords committed
* [ ] No `.env` files committed
* [ ] Production secrets stored securely

### API

* [ ] Authentication enabled
* [ ] Authorization configured
* [ ] Input validation implemented
* [ ] Rate limiting enabled
* [ ] Error messages reviewed for information leakage

### Operator Controls

* [ ] Operator identities verified
* [ ] Feedback permissions restricted
* [ ] Memory updates audited
* [ ] High-impact changes reviewed

### Data

* [ ] Raw datasets protected
* [ ] Dataset integrity verified
* [ ] Generated artifacts tracked
* [ ] Sensitive logs protected

### External Providers

* [ ] Provider failures handled
* [ ] Cached data clearly identified
* [ ] External responses validated
* [ ] Provider credentials protected

### WebSockets

* [ ] Authentication enabled
* [ ] Connection limits configured
* [ ] Rate limiting configured
* [ ] Resource exhaustion protections enabled

### Deployment

* [ ] HTTPS/TLS enabled
* [ ] Firewall rules reviewed
* [ ] Database access restricted
* [ ] Containers hardened
* [ ] Dependencies scanned
* [ ] Logs monitored

---

# 🔎 Dependency Security

ASTRA depends on a Python ecosystem and external services.

Dependencies should be kept current and reviewed for known vulnerabilities.

Recommended practices include:

```text
Dependency Pinning
        ↓
Automated Vulnerability Scanning
        ↓
Regular Updates
        ↓
Regression Tests
        ↓
Security Review
```

Do not blindly upgrade security-sensitive dependencies in production without running the project's test suite and reviewing behavior changes.

---

# 🚨 Responsible Disclosure

If you discover a security vulnerability in ASTRA, please **do not publicly disclose the vulnerability before the maintainers have had a reasonable opportunity to investigate it**.

When reporting a vulnerability, provide:

```text
1. Vulnerability description
2. Affected component
3. Reproduction steps
4. Expected behavior
5. Actual behavior
6. Potential impact
7. Relevant logs or screenshots
8. Suggested mitigation, if known
```

Please avoid including:

* real API credentials,
* passwords,
* private keys,
* private telemetry,
* sensitive operator information,
* confidential mission information.

---

# 🧑‍💻 Security Contributions

Security improvements are welcome.

Useful contributions include:

* Input validation
* Authentication
* Authorization
* Rate limiting
* Secure logging
* Dependency auditing
* Secret-management improvements
* Memory integrity controls
* Audit trails
* WebSocket hardening
* Dataset integrity validation
* Container hardening
* Security documentation
* Automated security tests

Security-related pull requests should explain:

```text
Threat
  ↓
Current Weakness
  ↓
Mitigation
  ↓
Security Impact
  ↓
Testing
```

---

# 🗺️ Security Roadmap

## Phase 1 — Research Security

* [x] Raw dataset Git exclusion
* [x] Archive identity validation
* [x] Dataset integrity metadata
* [x] Trust-boundary validation
* [x] Explicit source/cache distinction
* [x] Research integrity boundary

## Phase 2 — Application Hardening

* [ ] Authentication
* [ ] Role-based authorization
* [ ] API rate limiting
* [ ] Request-size limits
* [ ] WebSocket controls
* [ ] Structured security logging
* [ ] Memory access controls

## Phase 3 — Operational Security

* [ ] Secure secret management
* [ ] TLS enforcement
* [ ] Database hardening
* [ ] Container security
* [ ] Dependency vulnerability scanning
* [ ] Security monitoring
* [ ] Incident-response procedures

## Phase 4 — Mission-Grade Security Research

* [ ] Formal threat model
* [ ] Independent security review
* [ ] Penetration testing
* [ ] Adversarial memory-poisoning evaluation
* [ ] Adversarial telemetry testing
* [ ] Security regression suite
* [ ] Formal operational security requirements

---

# 🧠 Security Principles

ASTRA follows these principles:

### 01 — Never Trust Unvalidated Input

Every external input is potentially malformed or malicious.

### 02 — Never Treat Memory as Authority

Historical similarity provides context, not permission.

### 03 — Protect Strong Anomalies

A genuine anomaly should not disappear merely because a similar event was previously observed.

### 04 — Preserve Provenance

Know where data came from and whether it is fresh or cached.

### 05 — Protect Operator Trust

Operator feedback is a high-value security boundary.

### 06 — Protect Research Integrity

An incorrect dataset can be as damaging as an incorrect algorithm.

### 07 — Fail Transparently

Unavailable or cached information should be distinguishable from fresh information.

### 08 — Do Not Overclaim

A research demonstrator must not be represented as a production spacecraft safety system.

---

# 🌌 Final Principle

ASTRA is built around a simple idea:

> **Anomaly detection should help humans understand spacecraft behavior — not blindly decide what is safe.**

Security follows the same philosophy.

```text
                  ┌─────────────────┐
                  │      ASTRA      │
                  └────────┬────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
       Detect          Contextualize     Remember
           │               │               │
           └───────────────┼───────────────┘
                           ▼
                       Protect
                           │
                           ▼
                        Explain
                           │
                           ▼
                 ┌───────────────────┐
                 │  HUMAN OPERATOR   │
                 └───────────────────┘
```

## **Detect carefully. Remember responsibly. Protect aggressively.**

> *Unusual does not always mean unsafe. Evidence should decide.*

---

<div align="center">

### 🛰️ ASTRA — Spacecraft Telemetry Health Intelligence Platform

**Research-first • Context-aware • Operator-in-the-loop**

**SIH 2026**

</div>
