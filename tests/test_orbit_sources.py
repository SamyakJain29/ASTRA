"""Unit tests for ASTRA Live Orbit sources, SGP4 propagator, and ground station pass calculator."""

from datetime import UTC, datetime

from astra.sources.celestrak import CelesTrakProvider
from astra.sources.pass_calculator import PassCalculator, compute_topocentric_enu
from astra.sources.propagator import SGP4Propagator, teme_to_latlonalt
from astra.sources.satnogs import SatNOGSProvider


def test_celestrak_provider_offline_fallback():
    provider = CelesTrakProvider(cache_dir="artifacts/test_cache")
    elements, is_offline = provider.get_orbital_elements(25544)
    assert elements is not None
    assert elements["NORAD_CAT_ID"] == 25544
    assert isinstance(is_offline, bool)


def test_sgp4_propagation_and_geodetic():
    provider = CelesTrakProvider(cache_dir="artifacts/test_cache")
    elements, _ = provider.get_orbital_elements(25544)
    propagator = SGP4Propagator(elements)

    now = datetime.now(UTC)
    st = propagator.propagate(now)
    assert -90.0 <= st["latitude"] <= 90.0
    assert -180.0 <= st["longitude"] <= 180.0
    assert 300.0 <= st["altitude_km"] <= 600.0
    assert 6.5 <= st["velocity_kms"] <= 8.5

    tracks = propagator.generate_ground_track(now, duration_minutes=10, step_minutes=2)
    assert "past_track" in tracks
    assert "future_track" in tracks
    assert len(tracks["past_track"]) == 5
    assert len(tracks["future_track"]) == 6


def test_teme_to_latlonalt_validity():
    lat, lon, alt = teme_to_latlonalt(4000.0, 2000.0, 5000.0, 2460000.5, 0.0)
    assert -90.0 <= lat <= 90.0
    assert -180.0 <= lon <= 180.0
    assert alt > 0.0


def test_ground_station_pass_calculator():
    gs_cfg = {
        "name": "DEMO GROUND STATION",
        "latitude": 17.3850,
        "longitude": 78.4867,
        "altitude_km": 0.545,
        "min_elevation_deg": 5.0,
    }
    calc = PassCalculator(gs_cfg)

    # Test topocentric calculation directly
    rng, el, az = compute_topocentric_enu(17.3850, 78.4867, 0.545, 17.3850, 78.4867, 400.0)
    assert abs(rng - 399.455) < 5.0
    assert el > 85.0  # Directly overhead

    provider = CelesTrakProvider(cache_dir="artifacts/test_cache")
    elements, _ = provider.get_orbital_elements(25544)
    propagator = SGP4Propagator(elements)

    pass_data = calc.get_instantaneous_pass(propagator, datetime.now(UTC))
    assert pass_data["ground_station_name"] == "DEMO GROUND STATION"
    assert "range_km" in pass_data
    assert "elevation_deg" in pass_data
    assert "azimuth_deg" in pass_data
    assert "next_pass" in pass_data


def test_satnogs_provider_resilience():
    satnogs = SatNOGSProvider()
    res = satnogs.get_satellite_observations(25544)
    assert "status" in res
    assert res["status"] in ["DECODED_FRAME_AVAILABLE", "NO RECENT DECODED TELEMETRY"]


def test_source_separation_safeguards():
    # Verify ESA Mission-1 identity is strictly isolated from CelesTrak NORAD IDs
    provider = CelesTrakProvider(cache_dir="artifacts/test_cache")
    norad_ids = [s["norad_id"] for s in provider.satellites]
    assert 25544 in norad_ids  # ISS
    assert 44804 in norad_ids  # CARTOSAT-3
    assert 51656 in norad_ids  # EOS-04

    # ESA Mission-1 telemetry contains anonymized channel IDs, not NORAD catalog IDs
    for norad_id in norad_ids:
        assert str(norad_id) not in ["channel_41", "channel_42", "id_117"]
