# ASTRA Production Quality Gate Documentation

## Overview

This document specifies the engineering design, background service architecture, data provenance controls, and semantic scope definitions introduced during the **ASTRA Production Quality Gate**.

The objective of this gate is to elevate ASTRA from an experimental research pipeline to a technically credible, production-oriented spacecraft operational intelligence platform suitable for flight operations teams (such as ISRO/ISTRAC or commercial mission control centers).

---

## 1. Operational Scope & Data Provenance Architecture

ASTRA strictly distinguishes between **Global Orbital Awareness** and **Authorized Fleet Operations**.

```
+-----------------------------------------------------------------------+
|                         ASTRA PLATFORM SCOPES                         |
+-----------------------------------------------------------------------+
|                                                                       |
|  1. GLOBAL ORBITAL AWARENESS (Public Catalog & Ephemeris)             |
|     - Active Satellites, Inactive Satellites, Debris, Rocket Bodies     |
|     - Dynamic GP / OMM Ingestion with Atomic Cache Replacement        |
|     - Fast Analytical SGP4 Propagation (TEME -> Geodetic)             |
|     - Unauthenticated, Read-Only Public Awareness Layer               |
|                                                                       |
|  2. AUTHORIZED FLEET OPERATIONS (Connected Spacecraft)                |
|     - Active Telemetry Streams & Telecommand Log Ingestion            |
|     - Operational Telemetry Health Monitoring                         |
|     - Displays "NO AUTHORIZED FLEET CONNECTED" if no endpoint set     |
|                                                                       |
|  3. RESEARCH / VALIDATION WORKSPACE (Historical Benchmarks)           |
|     - ESA Mission-1 Anonymized Research Dataset (65 Test Events)       |
|     - ASTRA Adaptive Event Memory & Baseline Benchmark Suite          |
|     - Completely Decoupled from Live Operational Fleet Status         |
|                                                                       |
+-----------------------------------------------------------------------+
```

### Semantic Separation Rules

- **ESA Mission-1** is designated exclusively as `HISTORICAL_RESEARCH_DATA` and categorized under `RESEARCH_VALIDATION_DATA`. It is never listed as an operational fleet asset.
- **Fleet Endpoint** returns `authorized_count: 0` and status `NO AUTHORIZED FLEET CONNECTED` unless an authentic telemetry streaming interface is configured.
- **Derived Orbital Values**: Propagated geodetic positions (`latitude`, `longitude`, `altitude_km`) are explicitly designated as derived metrics, separate from raw source elements (`mean_motion`, `inclination_deg`, `bstar`).

---

## 2. Background Service Architecture & Lifecycle

ASTRA implements a concurrent background service architecture managed via the FastAPI `lifespan` context manager.

```
                              FastAPI Lifespan Startup
                                         |
                       +-----------------+-----------------+
                       |                                   |
                       v                                   v
         [Background Refresh Task]           [Background Propagation Task]
               (Cadence: 2h)                       (Cadence: 3s)
                       |                                   |
           Fetch CelesTrak GP/OMM               Propagate Active Catalog
                       |                                   |
           Atomic Cache Replacement             Snapshot to OrbitStateStore
                       |                                   |
                       +-----------------+-----------------+
                                         |
                               Wait for App Shutdown
```

### Key Service Engine Specifications

1. **`background_catalog_refresh_loop`**:
   - **Interval**: 7,200 seconds (2 hours), strictly respecting upstream CelesTrak rate-limit policies.
   - **Atomic Ingestion**: Fetches active catalog objects and atomically replaces the local disk cache (`data/cache/catalog_active.json`).
   - **Fault Tolerance**: If upstream requests fail or return malformed JSON, the engine retains existing valid cached elements and marks `is_offline: true`.

2. **`background_propagation_loop`**:
   - **Interval**: 3.0 seconds.
   - **Lock-Free State Snapshot**: Computes current TEME vectors and geodetic coordinates for all catalog objects, updating an in-memory `OrbitStateStore` snapshot.
   - **Response Performance**: REST endpoints (`GET /api/v1/global/states`) serve pre-computed state vectors instantly without blocking incoming requests.

---

## 3. Global Catalog Search & Ranking Rules

The `GET /api/v1/global/catalog` endpoint implements deterministic, exact-ranked search to ensure mission operators can locate space objects instantaneously:

1. **Rank 1 (Exact NORAD ID Match)**: Direct numerical match on NORAD Catalog ID (e.g. `25544`).
2. **Rank 2 (Exact COSPAR ID Match)**: Case-insensitive match on International Designator (e.g. `1998-067A`).
3. **Rank 3 (Exact Name Match)**: Exact case-insensitive match on spacecraft name.
4. **Rank 4 (Prefix/Substring Match)**: Substring search sorted alphabetically.

---

## 4. REST & WebSocket API Contract Reference

### Production V1 Endpoints

| Endpoint | Method | Scope | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/global/catalog` | `GET` | Global | Query trackable orbital objects with ranking and filters |
| `/api/v1/global/states` | `GET` | Global | Real-time 3-second state snapshot of all catalog objects |
| `/api/v1/global/object/{id}` | `GET` | Global | Detailed orbital elements & live SGP4 state vector |
| `/api/v1/fleet` | `GET` | Fleet | Authorized production fleet spacecraft overview |
| `/api/v1/spacecraft/{id}/overview` | `GET` | Research/Fleet | Spacecraft configuration & channel listings |
| `/api/v1/sources/status` | `GET` | Operations | Operational health, age, and freshness of all data sources |
| `/api/v1/research/summary` | `GET` | Research | ESA Mission-1 validation metrics & Adaptive Event Memory status |

---

## 5. Performance & Benchmark Summary

As verified in `reports/global_orbit_performance.md`:

- **Catalog Parse Latency**: `0.17 ms`
- **SGP4 Propagation Speed**: `~ 0.011 ms` per object (11.7 ms for 1,000 satellites)
- **Selected Object Latency**: `0.010 ms`
- **Cached State Read**: `0.0016 ms`
- **Test Suite Health**: **85 / 85 tests passing** (100% pass rate)
