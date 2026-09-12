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
    end = data["end_to_end"]
    recurrence = data["memory_stage_recurrence"]
    assert end["labelled_genuine_anomalies"] == 29
    assert end["genuine_anomalies_detected_before_memory"] == 25
    assert end["genuine_anomalies_detected_after_memory"] == 25
    assert end["genuine_anomaly_detection_pct"] == 86.2
    assert end["labelled_rare_event_windows"] == 36
    assert end["rare_event_detector_alarms_before_memory"] == 5
    assert end["rare_event_detector_alarms_after_memory"] == 4
    assert end["rare_event_detector_alarm_reduction_pct"] == 20.0
    assert end["genuine_detector_detections_suppressed_by_memory"] == 0
    assert end["genuine_suppression_denominator"] == 25
    assert end["similarity_threshold"] == recurrence["similarity_threshold"] == 0.80
    assert recurrence["labelled_rare_event_windows"] == 36
    assert recurrence["subsequently_recognized_windows"] == 27
    assert recurrence["review_required_windows"] == 9
    assert recurrence["repeated_review_reduction_pct"] == 75.0
    assert "RETROSPECTIVE LABEL-CONDITIONED" in recurrence["evaluation_type"]
    assert not any("alarm" in key for key in recurrence)
    assert not any("alarm" in key for key in data)
    overview = client.get("/api/v1/research/overview").json()
    assert overview["end_to_end"] == end
    assert overview["memory_stage_recurrence"] == recurrence
    assert "benchmark_results" not in overview



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
    from app.backend.main import catalog_provider

    summary = catalog_provider.status_summary
    assert data["provider"] == summary["provider"]
    assert data["total_catalog_objects"] == summary["catalog_object_count"]
    assert "cache_age_seconds" in data
    for item in data["states"]:
        assert item["cospar_id"] == catalog_provider.get_object(item["norad_id"]).cospar_id

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
    assert [p["name"] for p in sc["parameters"]] == [f"CH_{n}" for n in range(41, 47)]
    assert all(p["unit"] == "N/A" for p in sc["parameters"])
    assert all("Anonymized" in p["subsystem"] for p in sc["parameters"])

    res_src = client.get("/api/v1/sources/status")
    assert res_src.status_code == 200
    srcs = res_src.json()
    assert len(srcs["sources"]) >= 2


def test_satnogs_source_status_uses_cache_without_fabricated_metrics(monkeypatch):
    from app.backend.main import satnogs_provider

    for cache, expected in [
        ({}, "SOURCE UNAVAILABLE"),
        ({1: {"source_status": "SOURCE UNAVAILABLE"}}, "SOURCE UNAVAILABLE"),
        ({1: {"source_status": "LIVE_ONLINE"}}, "USING CACHED DATA"),
        ({1: {"source_status": "USING CACHED SATNOGS DATA"}}, "USING CACHED DATA"),
    ]:
        monkeypatch.setattr(satnogs_provider, "_memory_cache", cache)
        sources = client.get("/api/v1/sources/status").json()["sources"]
        source = next(s for s in sources if s["source_id"] == "satnogs_ground_station")
        assert source["status"] == expected
        for key in ("http_status", "objects_retrieved", "objects_loaded", "records_count"):
            assert source[key] == "N/A"
        for key in ("last_success", "last_attempt", "refresh_duration_ms", "age_seconds"):
            assert source[key] is None


