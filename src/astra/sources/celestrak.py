"""CelesTrak GP orbital elements retriever with caching and offline resilience."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml


class CelesTrakProvider:
    """Manages fetching, caching, and offline fallback for CelesTrak orbital elements."""

    def __init__(
        self,
        config_path: str = "configs/orbit.yaml",
        cache_dir: str = "data/cache",
    ) -> None:
        self.config_path = Path(config_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def _load_config(self) -> None:
        if self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                self.cache_ttl = cfg.get("cache_ttl_seconds", 7200)
                self.base_url = cfg.get(
                    "celestrak_base_url",
                    "https://celestrak.org/NORAD/elements/gp.php",
                )
                self.satellites = cfg.get("satellites", [])
                self.ground_station = cfg.get("ground_station", {})
        else:
            self.cache_ttl = 7200
            self.base_url = "https://celestrak.org/NORAD/elements/gp.php"
            self.satellites = [
                {"norad_id": 44804, "name": "CARTOSAT-3"},
                {"norad_id": 51656, "name": "EOS-04"},
                {"norad_id": 25544, "name": "ISS"},
            ]
            self.ground_station = {
                "name": "DEMO GROUND STATION",
                "latitude": 17.3850,
                "longitude": 78.4867,
                "altitude_km": 0.545,
            }

    def _cache_file_path(self, norad_id: int) -> Path:
        return self.cache_dir / f"celestrak_gp_{norad_id}.json"

    def get_orbital_elements(self, norad_id: int) -> tuple[dict[str, Any] | None, bool]:
        """Returns (elements_dict, is_offline).

        Checks cache freshness first. If cache is stale or missing, fetches from CelesTrak.
        Falls back to cache if network is offline or fails.
        """
        cache_path = self._cache_file_path(norad_id)
        now_ts = datetime.now(UTC).timestamp()

        # Check if cache exists and is fresh (< 2 hours)
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached_data = json.load(f)
                fetch_ts = cached_data.get("_cached_at", 0)
                if (now_ts - fetch_ts) < self.cache_ttl:
                    return cached_data["elements"], cached_data.get("_is_offline", False)
            except Exception:
                pass

        # Attempt to fetch online
        url = f"{self.base_url}?CATNR={norad_id}&FORMAT=json"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        elements = data[0]
                        # Cache payload
                        cache_payload = {
                            "_cached_at": now_ts,
                            "_is_offline": False,
                            "elements": elements,
                        }
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(cache_payload, f, indent=2)
                        return elements, False
        except Exception:
            pass

        # Network failed: Fall back to existing cached elements
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached_data = json.load(f)
                return cached_data["elements"], True
            except Exception:
                pass

        # Ultimate fallback if no internet and no cache exists: return deterministic element structure
        fallback_elements = self._get_fallback_elements(norad_id)
        return fallback_elements, True

    def _get_fallback_elements(self, norad_id: int) -> dict[str, Any]:
        """Provides deterministic fallback GP orbital elements when network and cache are unavailable."""
        now_iso = datetime.now(UTC).isoformat()
        if norad_id == 25544:
            return {
                "OBJECT_NAME": "ISS (ZARYA)",
                "NORAD_CAT_ID": 25544,
                "EPOCH": now_iso,
                "MEAN_MOTION": 15.489,
                "ECCENTRICITY": 0.0005,
                "INCLINATION": 51.64,
                "RA_OF_ASC_NODE": 280.0,
                "ARG_OF_PERICENTER": 90.0,
                "MEAN_ANOMALY": 260.0,
                "BSTAR": 0.00008,
            }
        elif norad_id == 51656:
            return {
                "OBJECT_NAME": "EOS-04",
                "NORAD_CAT_ID": 51656,
                "EPOCH": now_iso,
                "MEAN_MOTION": 14.82,
                "ECCENTRICITY": 0.0001,
                "INCLINATION": 97.5,
                "RA_OF_ASC_NODE": 120.0,
                "ARG_OF_PERICENTER": 45.0,
                "MEAN_ANOMALY": 180.0,
                "BSTAR": 0.00001,
            }
        else:
            return {
                "OBJECT_NAME": "CARTOSAT-3",
                "NORAD_CAT_ID": 44804,
                "EPOCH": now_iso,
                "MEAN_MOTION": 14.95,
                "ECCENTRICITY": 0.0002,
                "INCLINATION": 97.4,
                "RA_OF_ASC_NODE": 200.0,
                "ARG_OF_PERICENTER": 60.0,
                "MEAN_ANOMALY": 100.0,
                "BSTAR": 0.00001,
            }
