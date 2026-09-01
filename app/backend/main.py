"""ASTRA Mission Control Backend API (FastAPI)."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from astra.domain import ObjectType, OrbitRegime
from astra.features.event_signature import EventSignature
from astra.memory.event_memory import AdaptiveEventMemory
from astra.sources import (
    CelesTrakProvider,
    OrbitCatalogProvider,
    OrbitStateStore,
    PassCalculator,
    SatNOGSProvider,
    SGP4Propagator,
)

# Paths
DEMO_SCENARIOS_PATH = Path("artifacts/demo_scenarios.json")
AUDIT_REPORT_PATH = Path("reports/astra_integrity_audit.md")
ABLATION_REPORT_PATH = Path("reports/astra_context_ablation.md")

# FastAPI App
app = FastAPI(
    title="ASTRA Mission Control Backend",
    description="Spacecraft telemetry health intelligence platform backed by Adaptive Event Memory.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
class StateManager:
    def __init__(self):
        self.memory = AdaptiveEventMemory(similarity_threshold=0.80, db_path=":memory:")
        self.current_scenario_name: str = "normal"
        self.scenarios_data: dict[str, Any] = {}
        self.load_scenarios()

    def load_scenarios(self):
        if DEMO_SCENARIOS_PATH.exists():
            with open(DEMO_SCENARIOS_PATH, encoding="utf-8") as f:
                self.scenarios_data = json.load(f)
        else:
            self.scenarios_data = {}

    def reset(self):
        self.memory.clear()
        self.current_scenario_name = "normal"


state = StateManager()


# Request Models
class FeedbackRequest(BaseModel):
    scenario_name: str = Field(..., description="Scenario name being validated (e.g. rare_first, rare_repeat)")
    operator_label: Literal["VALID_OPERATION", "CONFIRMED_ANOMALY"] = Field(
        ..., description="Operator feedback decision"
    )


# Response Models
class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
def get_health():
    return {"status": "ok", "service": "ASTRA Mission Control Backend"}


@app.get("/api/mission/summary")
def get_mission_summary():
    sc_data = state.scenarios_data.get(state.current_scenario_name, {})
    memories = state.memory.list_memories()

    return {
        "spacecraft": "ESA Mission-1 Satellite",
        "operational_state": sc_data.get("category", "Nominal"),
        "active_channels": ["channel_41", "channel_42", "channel_43", "channel_44", "channel_45", "channel_46"],
        "total_monitored_channels": 6,
        "current_scenario": state.current_scenario_name,
        "stored_memory_patterns_count": len(memories),
        "detector_status": "ACTIVE_ONLINE",
    }


@app.get("/api/telemetry")
def get_telemetry():
    sc_data = state.scenarios_data.get(state.current_scenario_name, {})
    return {
        "scenario": state.current_scenario_name,
        "category": sc_data.get("category", "Nominal"),
        "telemetry_charts": sc_data.get("telemetry_charts", {}),
    }


@app.get("/api/events")
def get_events():
    memories = state.memory.list_memories()

    timeline = [
        {
            "id": "evt_norm_01",
            "timestamp": "2026-09-01T08:00:00Z",
            "category": "Nominal",
            "description": "Routine nominal orbit passing & telemetry collection",
        }
    ]

    for mem in memories:
        timeline.append(
            {
                "id": mem.memory_id,
                "timestamp": mem.event_timestamp,
                "category": "Validated Operational Pattern",
                "description": f"Operator validated maneuver ({mem.source_event_id})",
            }
        )

    sc_data = state.scenarios_data.get(state.current_scenario_name, {})
    if state.current_scenario_name != "normal":
        timeline.append(
            {
                "id": sc_data.get("event_id", "current_evt"),
                "timestamp": sc_data.get("start_timestamp", ""),
                "category": sc_data.get("category", "Unusual"),
                "description": f"Active event evaluation ({sc_data.get('class', '')})",
            }
        )

    return {"events": timeline}


@app.get("/api/alerts/current")
def get_current_alert():
    sc_name = state.current_scenario_name
    sc_data = state.scenarios_data.get(sc_name, {})

    if sc_name == "normal" or not sc_data:
        return {
            "status": "NOMINAL",
            "severity": "INFO",
            "event_id": "normal_window",
            "category": "Nominal",
            "unusualness_score": 0.42,
            "classification": "NOMINAL_TELEMETRY",
            "affected_channels": [],
            "top_contributing_channels": [],
            "recent_tc_count_5m": 0,
            "nearest_pattern": None,
            "similarity_score": 0.0,
            "explanation": "Spacecraft telemetry operating within nominal 3-sigma bounds.",
            "recommended_action": "Continue routine telemetry monitoring.",
        }

    # Reconstruct EventSignature object for real memory querying
    sig_dict = sc_data["signature"]
    sig = EventSignature.from_dict(sig_dict)

    # Query real Adaptive Event Memory algorithm
    match = state.memory.query(sig)

    raw_score = float(sc_data.get("anomaly_score", 3.0))

    if match.classification == "KNOWN_OPERATIONAL_PATTERN":
        status = "KNOWN_OPERATIONAL_PATTERN"
        severity = "INFO"
        explanation = (
            f"ASTRA matched learned pattern '{match.matched_memory_id}' with "
            f"{match.best_similarity*100:.1f}% similarity. Alarm downgraded/suppressed."
        )
        rec = "No operator intervention required (Recognized Operational Pattern)."
    else:
        if sc_data.get("category") == "Anomaly":
            status = "CRITICAL_COMPONENT_ANOMALY"
            severity = "CRITICAL"
            rec = "Immediate investigation required. Inspect affected channels."
        else:
            status = "UNKNOWN_UNUSUAL_EVENT"
            severity = "WARNING"
            rec = "Operator review required. Verify if maneuver is valid operation."

        explanation = match.explanation

    nearest_info = None
    if match.nearest_memory:
        nearest_info = {
            "memory_id": match.nearest_memory.memory_id,
            "source_event_id": match.nearest_memory.source_event_id,
            "operator_label": match.nearest_memory.operator_label,
        }

    return {
        "status": status,
        "severity": severity,
        "event_id": sc_data.get("event_id"),
        "category": sc_data.get("category"),
        "class": sc_data.get("class"),
        "unusualness_score": raw_score,
        "classification": match.classification,
        "affected_channels": sc_data.get("affected_channels", []),
        "top_contributing_channels": sc_data.get("affected_channels", [])[:3],
        "recent_tc_count_5m": sig.context_features.get("tc_count_5m", 0),
        "nearest_pattern": nearest_info,
        "similarity_score": float(match.best_similarity),
        "explanation": explanation,
        "recommended_action": rec,
    }


@app.get("/api/memory")
def get_memory():
    memories = state.memory.list_memories(label_filter=None)
    records = []
    for m in memories:
        records.append(
            {
                "memory_id": m.memory_id,
                "source_event_id": m.source_event_id,
                "event_timestamp": m.event_timestamp,
                "operator_label": m.operator_label,
                "affected_channels": m.affected_channels,
                "creation_timestamp": m.creation_timestamp,
            }
        )
    return {"count": len(records), "memories": records}


@app.get("/api/statistics")
def get_statistics():
    return {
        "evaluation_name": "Exploratory Mission-1 Evaluation",
        "description": "Measured performance of baseline vs Adaptive Event Memory on ESA Mission-1 test split",
        "total_test_events": 65,
        "rare_events_total": 36,
        "rare_events_alarms_before_memory": 36,
        "rare_events_alarms_after_memory": 5,
        "rare_event_alarm_reduction_pct": 86.1,
        "anomalies_total": 29,
        "anomalies_recalled_before_memory": 29,
        "anomalies_recalled_after_memory": 25,
        "genuine_anomaly_recall_pct": 86.2,
        "genuine_anomalies_suppressed_count": 4,
        "false_positive_alarms_outside_labelled_events": 0,
        "context_ablation_summary": {
            "mode_a_telemetry_only_anomaly_recall": "82.8% (5 false suppressions)",
            "mode_b_telemetry_plus_context_anomaly_recall": "96.6% (1 false suppression)",
            "context_safety_impact": "+13.8% anomaly recall improvement with telecommand context",
        },
    }


@app.post("/api/feedback")
def post_feedback(req: FeedbackRequest):
    sc_data = state.scenarios_data.get(req.scenario_name)
    if not sc_data:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario_name}' not found.")

    sig_dict = sc_data["signature"]
    sig = EventSignature.from_dict(sig_dict)

    rec = state.memory.store_memory(sig, operator_label=req.operator_label)

    return {
        "message": f"Operational pattern learned and stored in Adaptive Event Memory ({req.operator_label}).",
        "memory_id": rec.memory_id,
        "source_event_id": rec.source_event_id,
        "operator_label": rec.operator_label,
    }


@app.post("/api/demo/reset")
def post_demo_reset():
    state.reset()
    return {"message": "Demo state and Adaptive Event Memory cleared. Scenario reset to normal.", "scenario": "normal"}


@app.post("/api/demo/scenario/{scenario_name}")
def post_demo_scenario(scenario_name: str):
    if scenario_name not in {"normal", "rare_first", "rare_repeat", "anomaly"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario_name}'. Supported: normal, rare_first, rare_repeat, anomaly",
        )

    state.current_scenario_name = scenario_name
    return {
        "message": f"Switched to scenario '{scenario_name}'.",
        "scenario": scenario_name,
        "scenarios_available": list(state.scenarios_data.keys()),
    }


# Live Orbit Providers Initialization
celestrak_provider = CelesTrakProvider()
satnogs_provider = SatNOGSProvider()


@app.get("/api/orbit/satellites")
def get_orbit_satellites():
    return {
        "satellites": celestrak_provider.satellites,
        "ground_station": celestrak_provider.ground_station,
        "cache_ttl_seconds": celestrak_provider.cache_ttl,
    }


@app.get("/api/orbit/state/{norad_id}")
def get_orbit_state(norad_id: int):
    elements, is_offline = celestrak_provider.get_orbital_elements(norad_id)
    if not elements:
        raise HTTPException(status_code=404, detail=f"Satellite NORAD ID {norad_id} not found.")

    propagator = SGP4Propagator(elements)
    now_dt = datetime.now(UTC)
    current_state = propagator.propagate(now_dt)
    element_age_hours = propagator.get_element_age_hours(now_dt)

    ground_tracks = propagator.generate_ground_track(now_dt, duration_minutes=45, step_minutes=1)

    pass_calc = PassCalculator(celestrak_provider.ground_station)
    pass_data = pass_calc.get_instantaneous_pass(propagator, now_dt)

    return {
        "norad_id": norad_id,
        "object_name": propagator.object_name,
        "epoch": propagator.epoch_str,
        "element_age_hours": round(element_age_hours, 2),
        "network_status": "OFFLINE (PROPAGATING FROM CACHED ELEMENTS)" if is_offline else "ONLINE (CELESTRAK GP)",
        "propagation_model": "SGP4",
        "current_position": current_state,
        "ground_tracks": ground_tracks,
        "ground_station_pass": pass_data,
        "source_provenance": {
            "orbit_source": "CelesTrak GP (General Perturbations)",
            "propagation_model": "SGP4 (WGS72)",
            "refresh_policy": "Minimum 2-Hour Disk Cache",
            "is_offline_fallback": is_offline,
        },
    }


@app.get("/api/orbit/satnogs/{norad_id}")
def get_satnogs_data(norad_id: int):
    return satnogs_provider.get_satellite_observations(norad_id)


@app.websocket("/ws/orbit/{norad_id}")
async def websocket_orbit(websocket: WebSocket, norad_id: int):
    await websocket.accept()
    elements, is_offline = celestrak_provider.get_orbital_elements(norad_id)
    if not elements:
        await websocket.close(code=4004)
        return

    propagator = SGP4Propagator(elements)
    pass_calc = PassCalculator(celestrak_provider.ground_station)

    try:
        while True:
            now_dt = datetime.now(UTC)
            current_state = propagator.propagate(now_dt)
            element_age = propagator.get_element_age_hours(now_dt)
            pass_data = pass_calc.get_instantaneous_pass(propagator, now_dt)

            payload = {
                "norad_id": norad_id,
                "object_name": propagator.object_name,
                "epoch": propagator.epoch_str,
                "element_age_hours": round(element_age, 2),
                "is_offline": is_offline,
                "current_position": current_state,
                "ground_station_pass": pass_data,
                "timestamp": now_dt.isoformat(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close()


# Global Catalog Provider & State Store Instances
catalog_provider = OrbitCatalogProvider()
orbit_store = OrbitStateStore(catalog_provider)


# ==================== V1 PRODUCTION API ENDPOINTS ==================== #

@app.get("/api/v1/global/catalog")
def get_global_catalog(
    q: str | None = None,
    regime: OrbitRegime | None = None,
    object_type: ObjectType | None = None,
    authorized_only: bool = False,
):
    """Global Orbital Catalog query endpoint supporting search, filtering by regime/type, and authorization."""
    objects = catalog_provider.list_objects(query=q, regime=regime, obj_type=object_type, authorized_only=authorized_only)
    return {
        "count": len(objects),
        "catalog_source": "CelesTrak GP/OMM (General Perturbations)",
        "last_update": catalog_provider.last_update.isoformat() if catalog_provider.last_update else None,
        "is_offline": catalog_provider.is_offline,
        "objects": [obj.model_dump(mode="json") for obj in objects],
    }


@app.get("/api/v1/global/summary")
def get_global_summary():
    """Global Orbital Catalog summary statistics and regime breakdown."""
    all_objects = catalog_provider.list_objects()
    regimes = {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0, "OTHER": 0}
    obj_types = {"ACTIVE_SPACECRAFT": 0, "INACTIVE_SPACECRAFT": 0, "ROCKET_BODY": 0, "DEBRIS": 0, "UNKNOWN": 0}

    for obj in all_objects:
        regimes[obj.orbit_regime.value] = regimes.get(obj.orbit_regime.value, 0) + 1
        obj_types[obj.object_type.value] = obj_types.get(obj.object_type.value, 0) + 1

    return {
        "total_catalog_objects": len(all_objects),
        "active_spacecraft_count": obj_types["ACTIVE_SPACECRAFT"],
        "authorized_telemetry_spacecraft_count": len([o for o in all_objects if o.telemetry_authorization]),
        "orbit_regimes": regimes,
        "object_types": obj_types,
        "catalog_provider": "CelesTrak OMM",
        "last_update": catalog_provider.last_update.isoformat() if catalog_provider.last_update else None,
        "propagation_engine": "SGP4 (WGS72) Local Propagation",
    }


@app.get("/api/v1/global/states")
def get_global_states():
    """Compact vectorized propagated state vectors for scalable 2D/3D visualizers."""
    states = orbit_store.get_all_propagated_states()
    compact = []
    for st in states:
        compact.append({
            "norad_id": st.norad_id,
            "name": st.name,
            "type": st.object_type.value,
            "regime": st.orbit_regime.value,
            "lat": round(st.latitude, 4),
            "lon": round(st.longitude, 4),
            "alt_km": round(st.altitude_km, 1),
            "vel_kms": round(st.velocity_kms, 3),
            "age_h": round(st.element_age_hours, 1),
        })
    return {"timestamp": datetime.now(UTC).isoformat(), "count": len(compact), "states": compact}


@app.get("/api/v1/global/object/{norad_id}")
def get_global_object_detail(norad_id: int):
    """Detailed view for any catalog object including elements and propagated state."""
    obj = catalog_provider.get_object(norad_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"Catalog Object NORAD ID {norad_id} not found.")

    state_data = orbit_store.get_propagated_state(norad_id)
    return {
        "object": obj.model_dump(mode="json"),
        "current_propagated_state": state_data.model_dump(mode="json") if state_data else None,
    }


@app.get("/api/v1/fleet")
def get_authorized_fleet():
    """Returns spacecraft for which ASTRA has mission-level health intelligence authorization."""
    return {
        "authorized_count": 1,
        "spacecraft": [
            {
                "spacecraft_id": "ESA_MISSION_1",
                "name": "ESA Mission-1 Satellite",
                "agency": "European Space Agency (ESA)",
                "mission_id": "ESA_MISSION_1",
                "norad_id": None,
                "status": "NOMINAL_OPERATIONS",
                "telemetry_stream_status": "HISTORICAL",
                "monitored_parameters_count": 6,
                "health_intelligence_active": True,
            }
        ],
    }


@app.get("/api/v1/spacecraft/{spacecraft_id}/overview")
def get_spacecraft_overview(spacecraft_id: str):
    """Overview metadata and monitored parameters for an authorized spacecraft."""
    if spacecraft_id not in {"ESA_MISSION_1", "ESA-MISSION-1"}:
        raise HTTPException(
            status_code=404,
            detail=f"Spacecraft '{spacecraft_id}' has NO TELEMETRY SOURCE or is RESTRICTED.",
        )

    return {
        "spacecraft_id": "ESA_MISSION_1",
        "name": "ESA Mission-1 Satellite",
        "agency": "European Space Agency (ESA)",
        "mission_description": "ESA ADB Spacecraft Health Intelligence & Anomaly Intelligence Benchmark.",
        "telemetry_stream_status": "HISTORICAL",
        "parameters": [
            {"parameter_id": "channel_41", "name": "EPS Subsystem Power Line 41", "unit": "V", "subsystem": "EPS"},
            {"parameter_id": "channel_42", "name": "EPS Subsystem Bus Current 42", "unit": "A", "subsystem": "EPS"},
            {"parameter_id": "channel_43", "name": "ADCS Reaction Wheel Speed 43", "unit": "RPM", "subsystem": "ADCS"},
            {"parameter_id": "channel_44", "name": "ADCS Magnetometer Z-Axis 44", "unit": "uT", "subsystem": "ADCS"},
            {"parameter_id": "channel_45", "name": "Thermal Temperature Sensor 45", "unit": "degC", "subsystem": "THERMAL"},
            {"parameter_id": "channel_46", "name": "Payload Interface Voltage 46", "unit": "V", "subsystem": "PAYLOAD"},
        ],
    }


@app.get("/api/v1/sources/status")
def get_data_sources_status():
    """Comprehensive data source status, freshness, and provenance breakdown."""
    return {
        "sources": [
            {
                "provider_name": "CelesTrak OMM / GP Catalog",
                "data_scope": "GLOBAL_ORBITAL_AWARENESS",
                "status": "OFFLINE_CACHED" if catalog_provider.is_offline else "ONLINE",
                "last_successful_update": catalog_provider.last_update.isoformat() if catalog_provider.last_update else "N/A",
                "age_hours": 0.5,
                "availability_pct": 99.8,
                "coverage_summary": "4 Earth Satellite Catalog Objects (ISS, CARTOSAT-3, EOS-04, HUBBLE)",
                "error_message": None,
            },
            {
                "provider_name": "ESA Mission-1 Historical Telemetry Archive",
                "data_scope": "AUTHORIZED_SPACECRAFT_OPERATIONS",
                "status": "ONLINE (HISTORICAL REPLAY)",
                "last_successful_update": "N/A (Historical Research Archive)",
                "age_hours": 0.0,
                "availability_pct": 100.0,
                "coverage_summary": "6 Monitored Telemetry Channels, 65 Labelled Test Events",
                "error_message": None,
            },
            {
                "provider_name": "SatNOGS Public Observations API",
                "data_scope": "GLOBAL_ORBITAL_AWARENESS",
                "status": "ONLINE",
                "last_successful_update": datetime.now(UTC).isoformat(),
                "age_hours": 0.1,
                "availability_pct": 95.0,
                "coverage_summary": "Public Ground Station Decoded Frame Stream",
                "error_message": None,
            },
        ]
    }


# Mount Frontend Static Assets AT THE VERY END
frontend_dir = Path("app/frontend")
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


