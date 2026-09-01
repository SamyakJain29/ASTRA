"""ASTRA Mission Control Backend API (FastAPI)."""

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from astra.features.event_signature import EventSignature
from astra.memory.event_memory import AdaptiveEventMemory

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


# Mount Frontend Static Assets
frontend_dir = Path("app/frontend")
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
