"""Unit tests for SatNOGS provider with mocked network responses and offline verification."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from astra.sources.satnogs import SatnogsObservationProvider, is_observation_recent, parse_timestamp


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    cache = tmp_path / "satnogs_cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


@pytest.fixture
def provider(temp_cache_dir: Path) -> SatnogsObservationProvider:
    return SatnogsObservationProvider(
        cache_dir=temp_cache_dir,
        cache_ttl_seconds=300.0,
        observation_recency_hours=24,
        timeout_seconds=1.0,
    )


def test_timestamp_parsing():
    now_dt = datetime.now(UTC)
    iso_str = now_dt.isoformat()
    parsed = parse_timestamp(iso_str)
    assert parsed is not None
    assert is_observation_recent(iso_str, recency_hours=24, now_dt=now_dt)

    old_dt = now_dt - timedelta(hours=30)
    assert not is_observation_recent(old_dt.isoformat(), recency_hours=24, now_dt=now_dt)


@patch("httpx.Client.get")
def test_successful_observation(mock_get: MagicMock, provider: SatnogsObservationProvider):
    now_iso = datetime.now(UTC).isoformat()
    mock_sat_resp = MagicMock(status_code=200)
    mock_sat_resp.json.return_value = [{"sat_id": "SAT-25544", "name": "ISS", "telemetry_metadata": True}]

    mock_tx_resp = MagicMock(status_code=200)
    mock_tx_resp.json.return_value = [{"description": "Beacon", "frequency": 145800000}]

    mock_obs_resp = MagicMock(status_code=200)
    mock_obs_resp.json.return_value = [{"id": 1001, "start": now_iso, "station": 42, "status": "Good"}]

    mock_tm_resp = MagicMock(status_code=200)
    mock_tm_resp.json.return_value = []

    mock_get.side_effect = [mock_sat_resp, mock_tx_resp, mock_obs_resp, mock_tm_resp]

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "AVAILABLE"
    assert res["has_recent_observations"] is True
    assert res["latest_observation"]["ground_station_identity"] == "Node #42"
    assert res["source_status"] == "LIVE_ONLINE"
    assert res["observations"][0]["status"] == "Good"


@patch("httpx.Client.get")
def test_observation_older_than_24h(mock_get: MagicMock, provider: SatnogsObservationProvider):
    old_iso = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    mock_sat_resp = MagicMock(status_code=200)
    mock_sat_resp.json.return_value = [{"sat_id": "SAT-25544"}]

    mock_tx_resp = MagicMock(status_code=200)
    mock_tx_resp.json.return_value = [{"description": "Beacon"}]

    mock_obs_resp = MagicMock(status_code=200)
    mock_obs_resp.json.return_value = [{"id": 1002, "start": old_iso, "station": 42}]

    mock_tm_resp = MagicMock(status_code=200)
    mock_tm_resp.json.return_value = []

    mock_get.side_effect = [mock_sat_resp, mock_tx_resp, mock_obs_resp, mock_tm_resp]

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["has_recent_observations"] is False
    assert res["overall_status"] == "NO RECENT DATA"


@patch("httpx.Client.get")
def test_raw_frame_without_decoded_telemetry(mock_get: MagicMock, provider: SatnogsObservationProvider):
    now_iso = datetime.now(UTC).isoformat()
    mock_sat_resp = MagicMock(status_code=200)
    mock_sat_resp.json.return_value = [{"sat_id": "SAT-25544"}]  # no telemetry_metadata

    mock_tx_resp = MagicMock(status_code=200)
    mock_tx_resp.json.return_value = [{"description": "CW"}]

    mock_obs_resp = MagicMock(status_code=200)
    mock_obs_resp.json.return_value = [{"id": 1003, "start": now_iso}]

    mock_tm_resp = MagicMock(status_code=200)
    mock_tm_resp.json.return_value = [{"timestamp": now_iso, "frame": "8B9C0012FF", "decoded_data": None}]

    mock_get.side_effect = [mock_sat_resp, mock_tx_resp, mock_obs_resp, mock_tm_resp]

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["has_decoder"] is False
    assert res["overall_status"] == "NO DECODER"
    assert res["telemetry_frames"][0]["raw_frame"] == "8B9C0012FF"
    assert res["telemetry_frames"][0]["decoded_fields"] is None


@patch("httpx.Client.get")
def test_structured_decoded_telemetry(mock_get: MagicMock, provider: SatnogsObservationProvider):
    now_iso = datetime.now(UTC).isoformat()
    mock_sat_resp = MagicMock(status_code=200)
    mock_sat_resp.json.return_value = [{"sat_id": "SAT-25544"}]

    mock_tx_resp = MagicMock(status_code=200)
    mock_tx_resp.json.return_value = [{"description": "FSK"}]

    mock_obs_resp = MagicMock(status_code=200)
    mock_obs_resp.json.return_value = [{"id": 1004, "start": now_iso}]

    mock_tm_resp = MagicMock(status_code=200)
    mock_tm_resp.json.return_value = [{
        "timestamp": now_iso,
        "frame": "AABBCC",
        "decoded_data": {"vbat": 3.92, "temp_c": 21.4},
    }]

    mock_get.side_effect = [mock_sat_resp, mock_tx_resp, mock_obs_resp, mock_tm_resp]

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["has_decoder"] is True
    assert res["overall_status"] == "AVAILABLE"
    assert res["telemetry_frames"][0]["decoded_fields"]["vbat"] == 3.92


@patch("httpx.Client.get")
def test_http_429_error(mock_get: MagicMock, provider: SatnogsObservationProvider):
    mock_get.return_value = MagicMock(status_code=429, request=MagicMock())

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "SOURCE UNAVAILABLE"
    assert res["source_status"] == "SOURCE UNAVAILABLE"


@patch("httpx.Client.get")
def test_http_500_error(mock_get: MagicMock, provider: SatnogsObservationProvider):
    mock_get.return_value = MagicMock(status_code=500, request=MagicMock())

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "SOURCE UNAVAILABLE"
    assert res["source_status"] == "SOURCE UNAVAILABLE"


@patch("httpx.Client.get")
def test_timeout_error(mock_get: MagicMock, provider: SatnogsObservationProvider):
    mock_get.side_effect = httpx.TimeoutException("Connection timed out")

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "SOURCE UNAVAILABLE"
    assert res["source_status"] == "SOURCE UNAVAILABLE"


@patch("httpx.Client.get")
def test_malformed_json(mock_get: MagicMock, provider: SatnogsObservationProvider):
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")
    mock_get.return_value = mock_resp

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "SOURCE UNAVAILABLE"
    assert res["source_status"] == "SOURCE UNAVAILABLE"


@patch("httpx.Client.get")
def test_cache_fallback(mock_get: MagicMock, provider: SatnogsObservationProvider):
    # Seed cache
    cached_payload = {
        "norad_id": 25544,
        "overall_status": "AVAILABLE",
        "observations": [{"id": 99, "timestamp": datetime.now(UTC).isoformat()}],
        "telemetry_frames": [],
        "latest_observation": {"id": 99},
        "has_transmitters": True,
        "has_observations": True,
        "has_recent_observations": True,
        "has_decoder": True,
        "has_telemetry_frames": False,
        "source_status": "LIVE_ONLINE",
        "cache_timestamp_epoch": datetime.now(UTC).timestamp(),
    }
    provider._save_disk_cache(25544, cached_payload)

    # Force network failure
    mock_get.side_effect = httpx.ConnectError("Network unreachable")

    res = provider.fetch_all(25544, force_refresh=True)
    assert res["overall_status"] == "AVAILABLE"
    assert res["source_status"] == "USING CACHED SATNOGS DATA"


def test_bad_cache_file(provider: SatnogsObservationProvider, temp_cache_dir: Path):
    bad_file = temp_cache_dir / "99999.json"
    bad_file.write_text("CORRUPTED NOT JSON{{{", encoding="utf-8")

    loaded = provider._load_disk_cache(99999)
    assert loaded is None


@patch("httpx.Client.get")
def test_recent_rf_filtering_no_per_satellite_http_calls(
    mock_get: MagicMock,
    provider: SatnogsObservationProvider,
):
    now_iso = datetime.now(UTC).isoformat()
    mock_obs_resp = MagicMock(status_code=200)
    mock_obs_resp.json.return_value = [
        {"norad_cat_id": 25544, "start": now_iso},
        {"norad_cat_id": 43013, "start": now_iso},
    ]
    mock_get.return_value = mock_obs_resp

    recent_ids = provider.get_recent_rf_norad_ids(force_refresh=True)
    assert 25544 in recent_ids
    assert 43013 in recent_ids

    # Verify only ONE network call was made to /observations/?limit=100
    assert mock_get.call_count == 1
    call_url = mock_get.call_args[0][0]
    assert "/observations/?limit=100" in call_url
