"""SatNOGS live-observation and public telemetry provider with caching and offline resilience."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/satnogs")
DEFAULT_CACHE_TTL_SECONDS = 300.0  # 5 minutes


class SatnogsObservationProvider:
    """Retrieves live RF observations, telemetry frames, and availability metadata from SatNOGS public APIs."""

    def __init__(
        self,
        db_base_url: str = "https://db.satnogs.org/api",
        network_base_url: str = "https://network.satnogs.org/api",
        cache_dir: Path = CACHE_DIR,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.db_base_url = db_base_url.rstrip("/")
        self.network_base_url = network_base_url.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[int, dict[str, Any]] = {}

    def _cache_path_for_norad(self, norad_id: int) -> Path:
        return self.cache_dir / f"{norad_id}.json"

    def _load_disk_cache(self, norad_id: int) -> dict[str, Any] | None:
        path = self._cache_path_for_norad(norad_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_ts = data.get("cache_timestamp_epoch", 0)
            age = datetime.now(UTC).timestamp() - cached_ts
            data["cache_age_seconds"] = max(0.0, age)
            data["is_cached"] = True
            return data
        except Exception as e:
            logger.warning(f"Failed to read SatNOGS cache for NORAD {norad_id}: {e}")
            return None

    def _save_disk_cache(self, norad_id: int, payload: dict[str, Any]) -> None:
        path = self._cache_path_for_norad(norad_id)
        try:
            payload["cache_timestamp_epoch"] = datetime.now(UTC).timestamp()
            payload["cache_timestamp_iso"] = datetime.now(UTC).isoformat()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write SatNOGS cache for NORAD {norad_id}: {e}")

    def fetch_all(self, norad_id: int, force_refresh: bool = False) -> dict[str, Any]:
        """Fetches full SatNOGS metadata, transmitters, observations, and telemetry frames for a NORAD ID."""

        # 1. Check memory cache
        if not force_refresh and norad_id in self._memory_cache:
            mem = self._memory_cache[norad_id]
            age = datetime.now(UTC).timestamp() - mem.get("cache_timestamp_epoch", 0)
            if age < self.cache_ttl_seconds:
                return mem

        # 2. Check disk cache if fresh
        disk_cache = self._load_disk_cache(norad_id)
        if not force_refresh and disk_cache:
            if disk_cache.get("cache_age_seconds", 999999) < self.cache_ttl_seconds:
                self._memory_cache[norad_id] = disk_cache
                return disk_cache

        # 3. Attempt live HTTP network calls
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                # Satellites endpoint
                sat_resp = client.get(f"{self.db_base_url}/satellites/?norad_cat_id={norad_id}")
                sats = sat_resp.json() if sat_resp.status_code == 200 else []
                sat_meta = sats[0] if isinstance(sats, list) and len(sats) > 0 else {}
                sat_id = sat_meta.get("sat_id")

                # Transmitters endpoint
                tx_url = f"{self.db_base_url}/transmitters/?norad_cat_id={norad_id}"
                if sat_id:
                    tx_url = f"{self.db_base_url}/transmitters/?sat_id={sat_id}"
                tx_resp = client.get(tx_url)
                txs = tx_resp.json() if tx_resp.status_code == 200 else []
                if not isinstance(txs, list):
                    txs = []

                # Observations endpoint
                obs_url = f"{self.network_base_url}/observations/?norad_cat_id={norad_id}&limit=10"
                if sat_id:
                    obs_url = f"{self.network_base_url}/observations/?sat_id={sat_id}&limit=10"
                obs_resp = client.get(obs_url)
                observations = obs_resp.json() if obs_resp.status_code == 200 else []
                if not isinstance(observations, list):
                    observations = []

                # Telemetry endpoint
                tm_url = f"{self.db_base_url}/telemetry/?norad_cat_id={norad_id}&limit=5"
                if sat_id:
                    tm_url = f"{self.db_base_url}/telemetry/?sat_id={sat_id}&limit=5"
                tm_resp = client.get(tm_url)
                tm_frames = tm_resp.json() if tm_resp.status_code == 200 else []
                if not isinstance(tm_frames, list):
                    tm_frames = []

                parsed = self._parse_satnogs_response(
                    norad_id=norad_id,
                    sat_meta=sat_meta,
                    transmitters=txs,
                    observations=observations,
                    telemetry_frames=tm_frames,
                    source_status="LIVE_ONLINE",
                )
                self._save_disk_cache(norad_id, parsed)
                self._memory_cache[norad_id] = parsed
                return parsed

        except Exception as e:
            logger.info(f"SatNOGS live network fetch failed for NORAD {norad_id} ({e}). Falling back to cache.")

        # 4. Fallback to stale disk cache if present
        if disk_cache:
            disk_cache["source_status"] = "USING_CACHED_OBSERVATIONS"
            self._memory_cache[norad_id] = disk_cache
            return disk_cache

        # 5. Return explicit SOURCE UNAVAILABLE state if no network and no cache
        unavailable = {
            "norad_id": norad_id,
            "overall_status": "SOURCE UNAVAILABLE",
            "source_citation": "SATNOGS COMMUNITY GROUND NETWORK",
            "satellite_metadata": {},
            "transmitters": [],
            "observations": [],
            "telemetry_frames": [],
            "latest_observation": None,
            "has_transmitters": False,
            "has_observations": False,
            "has_decoder": False,
            "has_telemetry_frames": False,
            "source_status": "SOURCE UNAVAILABLE",
            "is_cached": False,
            "error_detail": "SatNOGS API unreachable and no offline cache snapshot exists.",
        }
        return unavailable

    def _parse_satnogs_response(
        self,
        norad_id: int,
        sat_meta: dict[str, Any],
        transmitters: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        telemetry_frames: list[dict[str, Any]],
        source_status: str,
    ) -> dict[str, Any]:
        """Parses raw SatNOGS payload into normalized ASTRA observability data structures."""
        has_tx = len(transmitters) > 0
        has_obs = len(observations) > 0
        has_tm = len(telemetry_frames) > 0

        # Check decoder availability from satellite metadata or telemetry frames
        has_decoder = bool(sat_meta.get("telemetry_metadata")) or has_tm

        # Determine explicit overall status
        if not sat_meta and not has_tx and not has_obs and not has_tm:
            overall_status = "NO RECENT DATA"
        elif not has_tx:
            overall_status = "NO TRANSMITTER"
        elif not has_obs:
            overall_status = "NO RECENT DATA"
        elif not has_decoder:
            overall_status = "NO DECODER"
        else:
            overall_status = "AVAILABLE"

        # Format latest observation
        latest_obs = None
        formatted_obs = []
        for o in observations:
            station_id = o.get("station") or o.get("ground_station") or "SatNOGS Node"
            station_name = o.get("station_name") or f"SatNOGS Station {station_id}"
            st_ident = f"{station_name} (Node #{station_id})"

            obs_obj = {
                "observation_id": o.get("id"),
                "timestamp": o.get("start") or o.get("end") or o.get("timestamp"),
                "ground_station_id": station_id,
                "ground_station_identity": st_ident,
                "status": o.get("status", "Good"),
                "frequency_hz": o.get("frequency"),
                "mode": o.get("mode") or o.get("demod_type") or "FM / FSK",
                "has_demoddata": bool(o.get("demoddata")),
            }
            formatted_obs.append(obs_obj)

        if len(formatted_obs) > 0:
            latest_obs = formatted_obs[0]

        # Format decoded telemetry frames preserving raw field names and units
        formatted_tm = []
        for tm in telemetry_frames:
            raw_decoded = tm.get("decoded_data") or tm.get("extra") or tm.get("payload") or {}
            if isinstance(raw_decoded, str):
                try:
                    raw_decoded = json.loads(raw_decoded)
                except Exception:
                    raw_decoded = {"raw_payload": raw_decoded}

            tm_frame = {
                "timestamp": tm.get("timestamp") or tm.get("created"),
                "observer": tm.get("observer") or tm.get("station_id") or "SatNOGS Network",
                "raw_frame_hex": tm.get("frame") or tm.get("raw"),
                "decoded_fields": raw_decoded if isinstance(raw_decoded, dict) else {"value": raw_decoded},
            }
            formatted_tm.append(tm_frame)

        return {
            "norad_id": norad_id,
            "overall_status": overall_status,
            "source_citation": "SATNOGS COMMUNITY GROUND NETWORK",
            "satellite_metadata": {
                "sat_id": sat_meta.get("sat_id"),
                "name": sat_meta.get("name"),
                "norad_cat_id": norad_id,
                "status": sat_meta.get("status", "active"),
                "citation": "SATNOGS COMMUNITY GROUND NETWORK",
            },
            "transmitters": [
                {
                    "description": tx.get("description"),
                    "type": tx.get("type"),
                    "mode": tx.get("mode"),
                    "frequency_hz": tx.get("frequency"),
                    "baud": tx.get("baud"),
                    "status": tx.get("status", "active"),
                }
                for tx in transmitters
            ],
            "observations": formatted_obs,
            "telemetry_frames": formatted_tm,
            "latest_observation": latest_obs,
            "has_transmitters": has_tx,
            "has_observations": has_obs,
            "has_decoder": has_decoder,
            "has_telemetry_frames": has_tm,
            "source_status": source_status,
            "is_cached": False,
        }

    def get_satellite_observations(self, norad_id: int) -> dict[str, Any]:
        """Alias for backwards compatibility with legacy routes."""
        return self.fetch_all(norad_id)

    def get_observations(self, norad_id: int) -> dict[str, Any]:
        """API contract for GET /api/v1/global/object/{norad_id}/observations."""
        full = self.fetch_all(norad_id)
        return {
            "norad_id": norad_id,
            "overall_status": full["overall_status"],
            "source_citation": full["source_citation"],
            "latest_observation": full["latest_observation"],
            "count": len(full["observations"]),
            "observations": full["observations"],
            "source_status": full["source_status"],
        }

    def get_telemetry(self, norad_id: int) -> dict[str, Any]:
        """API contract for GET /api/v1/global/object/{norad_id}/telemetry."""
        full = self.fetch_all(norad_id)
        return {
            "norad_id": norad_id,
            "overall_status": full["overall_status"],
            "source_citation": full["source_citation"],
            "has_decoder": full["has_decoder"],
            "count": len(full["telemetry_frames"]),
            "telemetry_frames": full["telemetry_frames"],
            "source_status": full["source_status"],
        }

    def get_data_availability(self, norad_id: int) -> dict[str, Any]:
        """API contract for GET /api/v1/global/object/{norad_id}/data-availability."""
        full = self.fetch_all(norad_id)
        latest_ts = full["latest_observation"]["timestamp"] if full["latest_observation"] else None
        latest_station = full["latest_observation"]["ground_station_identity"] if full["latest_observation"] else None

        return {
            "norad_id": norad_id,
            "overall_status": full["overall_status"],
            "source_citation": full["source_citation"],
            "has_transmitters": full["has_transmitters"],
            "has_observations": full["has_observations"],
            "has_decoder": full["has_decoder"],
            "has_telemetry_frames": full["has_telemetry_frames"],
            "latest_observation_timestamp": latest_ts,
            "latest_ground_station": latest_station,
            "source_status": full["source_status"],
        }


# Compatibility alias
SatNOGSProvider = SatnogsObservationProvider
