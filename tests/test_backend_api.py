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


def test_orbit_satellites():
    res = client.get("/api/orbit/satellites")
    assert res.status_code == 200
    data = res.json()
    assert "satellites" in data
    assert len(data["satellites"]) >= 3
    assert data["ground_station"]["name"] == "ASTRA REFERENCE GROUND STATION"


def test_orbit_state():
    res = client.get("/api/orbit/state/25544")
    assert res.status_code == 200
    data = res.json()
    assert data["norad_id"] == 25544
    assert "current_position" in data
    assert "latitude" in data["current_position"]
    assert "ground_tracks" in data
    assert "ground_station_pass" in data


def test_orbit_satnogs():
    res = client.get("/api/orbit/satnogs/25544")
    assert res.status_code == 200
    data = res.json()
    assert "overall_status" in data or "source_status" in data


def test_orbit_websocket():
    with client.websocket_connect("/ws/orbit/25544") as websocket:
        data = websocket.receive_json()
        assert data["norad_id"] == 25544
        assert "current_position" in data


def test_v1_global_catalog_and_summary():
    res = client.get("/api/v1/global/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_catalog_objects"] >= 4
    assert "LEO" in summary["orbit_regimes"]

    res_cat = client.get("/api/v1/global/catalog?q=ISS")
    assert res_cat.status_code == 200
    catalog = res_cat.json()
    assert catalog["count"] >= 1
    assert catalog["objects"][0]["norad_id"] == 25544


def test_v1_global_states_and_fleet():
    res = client.get("/api/v1/global/states")
    assert res.status_code == 200
    data = res.json()
    assert "states" in data
    assert len(data["states"]) >= 4

    res_fleet = client.get("/api/v1/fleet")
    assert res_fleet.status_code == 200
    fleet = res_fleet.json()
    assert fleet["authorized_count"] == 0
    assert fleet["status_message"] == "NO AUTHORIZED FLEET CONNECTED"


def test_v1_spacecraft_overview_and_sources_status():
    res = client.get("/api/v1/spacecraft/ESA_MISSION_1/overview")
    assert res.status_code == 200
    sc = res.json()
    assert "ESA Mission-1" in sc["name"]
    assert len(sc["parameters"]) == 6

    res_src = client.get("/api/v1/sources/status")
    assert res_src.status_code == 200
    srcs = res_src.json()
    assert len(srcs["sources"]) >= 2



