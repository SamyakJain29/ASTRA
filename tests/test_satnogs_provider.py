"""Unit and API integration tests for SatnogsObservationProvider."""

from fastapi.testclient import TestClient
from astra.sources.satnogs import SatnogsObservationProvider
from app.backend.main import app

client = TestClient(app)


def test_satnogs_provider_cache_load():
    provider = SatnogsObservationProvider()
    data = provider.fetch_all(25544)
    assert data["norad_id"] == 25544
    assert data["overall_status"] in ["AVAILABLE", "NO RECENT DATA", "NO DECODER", "NO TRANSMITTER", "SOURCE UNAVAILABLE"]
    assert data["source_citation"] == "SATNOGS COMMUNITY GROUND NETWORK"
    assert "observations" in data
    assert "telemetry_frames" in data


def test_satnogs_provider_source_unavailable():
    provider = SatnogsObservationProvider()
    # Uncached invalid norad ID should return SOURCE UNAVAILABLE or NO TRANSMITTER safely
    data = provider.fetch_all(9999999)
    assert data["overall_status"] in ["SOURCE UNAVAILABLE", "NO TRANSMITTER", "NO RECENT DATA"]
    assert data["source_citation"] == "SATNOGS COMMUNITY GROUND NETWORK"


def test_satnogs_observations_api_endpoint():
    resp = client.get("/api/v1/global/object/25544/observations")
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data["norad_id"] == 25544
    assert json_data["source_citation"] == "SATNOGS COMMUNITY GROUND NETWORK"
    assert "observations" in json_data
    assert "overall_status" in json_data


def test_satnogs_telemetry_api_endpoint():
    resp = client.get("/api/v1/global/object/25544/telemetry")
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data["norad_id"] == 25544
    assert json_data["source_citation"] == "SATNOGS COMMUNITY GROUND NETWORK"
    assert "telemetry_frames" in json_data
    assert "has_decoder" in json_data


def test_satnogs_data_availability_api_endpoint():
    resp = client.get("/api/v1/global/object/25544/data-availability")
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data["norad_id"] == 25544
    assert json_data["source_citation"] == "SATNOGS COMMUNITY GROUND NETWORK"
    assert json_data["overall_status"] in ["AVAILABLE", "NO RECENT DATA", "NO DECODER", "NO TRANSMITTER", "SOURCE UNAVAILABLE"]
    assert "has_transmitters" in json_data
    assert "has_observations" in json_data
    assert "has_decoder" in json_data
    assert "has_telemetry_frames" in json_data


def test_recent_rf_only_catalog_filter():
    resp = client.get("/api/v1/global/catalog?recent_rf_only=true")
    assert resp.status_code == 200
    json_data = resp.json()
    assert "objects" in json_data
