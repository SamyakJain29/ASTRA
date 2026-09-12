"""Deployment shell, asset availability, and public research contract checks."""

import json
from pathlib import Path

import pytest
from app.backend import main as backend
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/", "/index.html", "/app.js", "/styles.css"])
def test_frontend_shell_never_reuses_stale_validators(path):
    client = TestClient(backend.app)
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    repeated = client.get(path, headers={
        "If-None-Match": response.headers["etag"],
        "If-Modified-Since": response.headers["last-modified"],
    })
    assert repeated.status_code == 200
    assert repeated.headers["cache-control"] == "no-store, max-age=0"


def test_other_assets_and_apis_keep_normal_cache_behavior(tmp_path):
    (tmp_path / "other.txt").write_text("test asset", encoding="utf-8")
    app = FastAPI()
    app.mount("/", backend.SafeStaticFiles(directory=tmp_path))
    client = TestClient(app)
    response = client.get("/other.txt")
    assert response.status_code == 200
    assert "cache-control" not in response.headers
    assert client.get("/other.txt", headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    assert "cache-control" not in TestClient(backend.app).get("/api/statistics").headers


def test_version_environment_is_optional(monkeypatch):
    client = TestClient(backend.app)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    assert client.get("/api/version").json() == {"commit": "local/unknown"}
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "test-commit")
    assert client.get("/api/version").json() == {"commit": "test-commit"}


def test_esa_status_follows_complete_partial_and_demo_assets(monkeypatch, tmp_path):
    research = tmp_path / "mission1"
    demo = tmp_path / "demo_scenarios.json"
    monkeypatch.setattr(backend, "RESEARCH_DATA_DIR", research)
    monkeypatch.setattr(backend, "DEMO_SCENARIOS_PATH", demo)
    client = TestClient(backend.app)

    def status():
        source = next(s for s in client.get("/api/v1/sources/status").json()["sources"]
                      if s["source_id"] == "esa_mission1_archive")
        assert source["http_status"] == "N/A"
        assert source["last_success"] is None
        return source

    assert status()["status"] == "RESEARCH DATA NOT BUNDLED"
    assert status()["cache_path"] == "N/A"
    demo.write_text("{}", encoding="utf-8")
    assert status()["status"] == "PREPARED RESEARCH SCENARIOS AVAILABLE"
    assert status()["type"] == "HISTORICAL / PREPARED ARTIFACT"
    assert status()["cache_path"] == str(demo)
    (research / "channels").mkdir(parents=True)
    (research / "events.parquet").touch()
    (research / "telecommands.parquet").touch()
    for n in range(41, 46):
        (research / "channels" / f"channel_{n}.parquet").touch()
    assert status()["status"] == "PREPARED RESEARCH SCENARIOS AVAILABLE"
    (research / "channels" / "channel_46.parquet").touch()
    assert status()["status"] == "HISTORICAL RESEARCH ARCHIVE AVAILABLE"
    assert status()["cache_path"] == str(research)
    (research / "channels" / "channel_46.parquet").unlink()
    demo.unlink()
    assert status()["status"] == "RESEARCH DATA NOT BUNDLED"


def test_public_snapshots_match_locally_reproduced_studies():
    directory = Path("artifacts/experiments")
    end_path = directory / "astra_memory_experiment.json"
    recurrence_path = directory / "astra_memory_stage_recurrence.json"
    if not end_path.exists() or not recurrence_path.exists():
        pytest.skip("Local research artifacts are not bundled in Git.")
    measured = json.loads(end_path.read_text(encoding="utf-8"))
    recurrence = json.loads(recurrence_path.read_text(encoding="utf-8"))
    public = backend.get_statistics()
    end = public["end_to_end"]
    assert end["rare_event_detector_alarms_before_memory"] == measured["rare_event_alarms_before_memory"]
    assert end["rare_event_detector_alarms_after_memory"] == measured["rare_event_alarms_after_memory"]
    assert end["rare_event_detector_alarm_reduction_pct"] == measured["rare_event_alarm_reduction_percentage"]
    assert end["genuine_anomalies_detected_before_memory"] == measured["genuine_anomalies_detected_before_memory"]
    assert end["genuine_anomalies_detected_after_memory"] == measured["genuine_anomalies_detected_after_memory"]
    assert end["genuine_suppression_denominator"] == measured["genuine_anomaly_suppression_denominator"]
    assert end["genuine_detector_detections_suppressed_by_memory"] == measured["genuine_anomalies_incorrectly_suppressed"]
    assert end["similarity_threshold"] == measured["similarity_threshold"]
    for key in ("labelled_rare_event_windows", "review_required_windows",
                "subsequently_recognized_windows", "repeated_review_reduction_pct", "similarity_threshold"):
        assert public["memory_stage_recurrence"][key] == recurrence[key]
