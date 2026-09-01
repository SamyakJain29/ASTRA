"""Unit tests for FastAPI backend API endpoints."""

from app.backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "ASTRA" in data["service"]


def test_mission_summary():
    res = client.get("/api/mission/summary")
    assert res.status_code == 200
    data = res.json()
    assert "spacecraft" in data
    assert len(data["active_channels"]) == 6


def test_telemetry():
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert "telemetry_charts" in data


def test_events():
    res = client.get("/api/events")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_statistics():
    res = client.get("/api/statistics")
    assert res.status_code == 200
    data = res.json()
    assert data["evaluation_name"] == "Exploratory Mission-1 Evaluation"
    assert data["rare_event_alarm_reduction_pct"] == 86.1


def test_demo_scenario_flow_and_feedback():
    # 1. Reset
    res = client.post("/api/demo/reset")
    assert res.status_code == 200
    assert res.json()["scenario"] == "normal"

    # 2. Normal alert check
    res = client.get("/api/alerts/current")
    assert res.status_code == 200
    assert res.json()["status"] == "NOMINAL"

    # 3. Switch to rare_first
    res = client.post("/api/demo/scenario/rare_first")
    assert res.status_code == 200
    assert res.json()["scenario"] == "rare_first"

    res = client.get("/api/alerts/current")
    assert res.status_code == 200
    assert res.json()["status"] == "UNKNOWN_UNUSUAL_EVENT"

    # 4. Feedback VALID_OPERATION
    res = client.post(
        "/api/feedback",
        json={"scenario_name": "rare_first", "operator_label": "VALID_OPERATION"},
    )
    assert res.status_code == 200
    assert "learned" in res.json()["message"]

    # 5. Memory check
    res = client.get("/api/memory")
    assert res.status_code == 200
    assert res.json()["count"] == 1

    # 6. Switch to rare_repeat
    res = client.post("/api/demo/scenario/rare_repeat")
    assert res.status_code == 200
    assert res.json()["scenario"] == "rare_repeat"

    res = client.get("/api/alerts/current")
    assert res.status_code == 200
    assert res.json()["status"] == "KNOWN_OPERATIONAL_PATTERN"
    assert res.json()["similarity_score"] >= 0.80

    # 7. Switch to anomaly
    res = client.post("/api/demo/scenario/anomaly")
    assert res.status_code == 200

    res = client.get("/api/alerts/current")
    assert res.status_code == 200
    assert res.json()["status"] == "CRITICAL_COMPONENT_ANOMALY"
