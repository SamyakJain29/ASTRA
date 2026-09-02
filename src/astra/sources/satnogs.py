"""SatNOGS live-observation and public telemetry provider with caching and offline resilience."""

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/satnogs")
DEFAULT_CACHE_TTL_SECONDS = 300.0  # 5 minutes
DEFAULT_OBSERVATION_RECENCY_HOURS = 24


def parse_timestamp(ts_val: Any) -> datetime | None:
    if isinstance(ts_val, (int, float)):
        return datetime.fromtimestamp(ts_val, tz=UTC)
    if isinstance(ts_val, str):
        try:
            ts_str = ts_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except Exception:
            return None
    return None


def is_observation_recent(
    obs_timestamp: Any,
    recency_hours: float = 24.0,
    now_dt: datetime | None = None,
) -> bool:
    if now_dt is None:
        now_dt = datetime.now(UTC)
    dt = parse_timestamp(obs_timestamp)
    if dt is None:
        return False
    age_seconds = (now_dt - dt).total_seconds()
    return 0 <= age_seconds <= recency_hours * 3600.0


class SatnogsObservationProvider:
    """Retrieves live RF observations, telemetry frames, and availability metadata from SatNOGS public APIs."""

    def __init__(
        self,
        db_base_url: str = "https://db.satnogs.org/api",
        network_base_url: str = "https://network.satnogs.org/api",
        cache_dir: Path = CACHE_DIR,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        observation_recency_hours: int = DEFAULT_OBSERVATION_RECENCY_HOURS,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.db_base_url = db_base_url.rstrip("/")
        self.network_base_url = network_base_url.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_ttl_seconds = cache_ttl_seconds
        self.observation_recency_hours = observation_recency_hours
        self.timeout_seconds = timeout_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[int, dict[str, Any]] = {}
        self._recent_rf_index_cache: set[int] | None = None
        self._recent_rf_index_epoch: float = 0.0

    def _cache_path_for_norad(self, norad_id: int) -> Path:
        return self.cache_dir / f"{norad_id}.json"

    def _load_disk_cache(self, norad_id: int) -> dict[str, Any] | None:
        path = self._cache_path_for_norad(norad_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(f"Malformed SatNOGS cache for NORAD {norad_id}: not a dict")
                return None
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
        temp_path: str | None = None
        try:
            payload["cache_timestamp_epoch"] = datetime.now(UTC).timestamp()
            payload["cache_timestamp_iso"] = datetime.now(UTC).isoformat()

            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.cache_dir,
                prefix=f"tmp_{norad_id}_",
                suffix=".json",
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_path, path)
        except Exception as e:
            logger.warning(f"Failed to write SatNOGS cache for NORAD {norad_id}: {e}")
            if temp_path and os.path.exists(temp_path):
                with contextlib.suppress(Exception):
                    os.remove(temp_path)

    def get_recent_rf_norad_ids(self, force_refresh: bool = False) -> set[int]:
        """Builds a cached recent-RF NORAD set without performing per-satellite N+1 requests."""
        now_ts = datetime.now(UTC).timestamp()

        # 1. Check memory cache
        if (
            not force_refresh
            and self._recent_rf_index_cache is not None
            and (now_ts - self._recent_rf_index_epoch) < self.cache_ttl_seconds
        ):
            return self._recent_rf_index_cache

        recent_ids: set[int] = set()

        # 2. Try single bounded network call for recent observations
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                obs_url = f"{self.network_base_url}/observations/?limit=100"
                obs_resp = client.get(obs_url)
                if obs_resp.status_code == 200:
                    raw_obs = obs_resp.json()
                    if isinstance(raw_obs, list):
                        now_dt = datetime.now(UTC)
                        for o in raw_obs:
                            norad_id = o.get("norad_cat_id") or o.get("norad_id")
                            ts = o.get("start") or o.get("end") or o.get("timestamp")
                            if norad_id and is_observation_recent(
                                ts,
                                recency_hours=self.observation_recency_hours,
                                now_dt=now_dt,
                            ):
                                with contextlib.suppress(ValueError, TypeError):
                                    recent_ids.add(int(norad_id))
        except Exception as e:
            logger.info(f"Failed to fetch global recent RF observation index from network: {e}")

        # 3. Augment with local disk cache files
        try:
            now_dt = datetime.now(UTC)
            for path in self.cache_dir.glob("*.json"):
                if path.name.startswith("tmp_") or path.name == "recent_rf_index.json":
                    continue
                try:
                    norad_id = int(path.stem)
                    data = self._load_disk_cache(norad_id)
                    if data:
                        obs_list = data.get("observations") or []
                        if any(
                            is_observation_recent(
                                o.get("timestamp"),
                                recency_hours=self.observation_recency_hours,
                                now_dt=now_dt,
                            )
                            for o in obs_list
                        ):
                            recent_ids.add(norad_id)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Error scanning local SatNOGS cache directory: {e}")

        self._recent_rf_index_cache = recent_ids
        self._recent_rf_index_epoch = now_ts
        return recent_ids

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
        if (
            not force_refresh
            and disk_cache
            and disk_cache.get("cache_age_seconds", 999999) < self.cache_ttl_seconds
        ):
            self._memory_cache[norad_id] = disk_cache
            return disk_cache

        # 3. Attempt live HTTP network calls
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                sat_resp = client.get(f"{self.db_base_url}/satellites/?norad_cat_id={norad_id}")
                if sat_resp.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Satellites API HTTP {sat_resp.status_code}",
                        request=sat_resp.request,
                        response=sat_resp,
                    )
                sats = sat_resp.json()
                if not isinstance(sats, list):
                    raise ValueError("Satellites payload must be a JSON array")
                sat_meta = sats[0] if len(sats) > 0 else {}
                sat_id = sat_meta.get("sat_id")

                tx_url = (
                    f"{self.db_base_url}/transmitters/?sat_id={sat_id}"
                    if sat_id
                    else f"{self.db_base_url}/transmitters/?norad_cat_id={norad_id}"
                )
                tx_resp = client.get(tx_url)
                if tx_resp.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Transmitters API HTTP {tx_resp.status_code}",
                        request=tx_resp.request,
                        response=tx_resp,
                    )
                txs = tx_resp.json()
                if not isinstance(txs, list):
                    raise ValueError("Transmitters payload must be a JSON array")

                obs_url = (
                    f"{self.network_base_url}/observations/?sat_id={sat_id}&limit=10"
                    if sat_id
                    else f"{self.network_base_url}/observations/?norad_cat_id={norad_id}&limit=10"
                )
                obs_resp = client.get(obs_url)
                if obs_resp.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Observations API HTTP {obs_resp.status_code}",
                        request=obs_resp.request,
                        response=obs_resp,
                    )
                observations = obs_resp.json()
                if not isinstance(observations, list):
                    raise ValueError("Observations payload must be a JSON array")

                tm_url = (
                    f"{self.db_base_url}/telemetry/?sat_id={sat_id}&limit=5"
                    if sat_id
                    else f"{self.db_base_url}/telemetry/?norad_cat_id={norad_id}&limit=5"
                )
                tm_resp = client.get(tm_url)
                if tm_resp.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Telemetry API HTTP {tm_resp.status_code}",
                        request=tm_resp.request,
                        response=tm_resp,
                    )
                tm_frames = tm_resp.json()
                if not isinstance(tm_frames, list):
                    raise ValueError("Telemetry payload must be a JSON array")

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
            disk_cache["source_status"] = "USING CACHED SATNOGS DATA"
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
            "has_recent_observations": False,
            "has_decoder": False,
            "has_telemetry_frames": False,
            "observation_recency_hours": self.observation_recency_hours,
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
        now_dt = datetime.now(UTC)

        formatted_obs = []
        recent_obs = []
        for o in observations:
            station_id = o.get("station") or o.get("ground_station")
            station_name = o.get("station_name")
            if station_name and station_id:
                st_ident = f"{station_name} (Node #{station_id})"
            elif station_name:
                st_ident = str(station_name)
            elif station_id:
                st_ident = f"Node #{station_id}"
            else:
                st_ident = None

            obs_ts = o.get("start") or o.get("end") or o.get("timestamp")
            obs_obj = {
                "observation_id": o.get("id"),
                "timestamp": obs_ts,
                "ground_station_id": station_id,
                "ground_station_name": station_name,
                "ground_station_identity": st_ident,
                "status": o.get("status"),
                "frequency_hz": o.get("frequency"),
                "mode": o.get("mode") or o.get("demod_type"),
                "has_demoddata": bool(o.get("demoddata")),
            }
            formatted_obs.append(obs_obj)
            if is_observation_recent(obs_ts, recency_hours=self.observation_recency_hours, now_dt=now_dt):
                recent_obs.append(obs_obj)

        latest_obs = formatted_obs[0] if len(formatted_obs) > 0 else None
        has_recent_obs = len(recent_obs) > 0

        formatted_tm = []
        has_structured_decoded = False

        for tm in telemetry_frames:
            raw_frame = tm.get("frame") or tm.get("raw")
            if not raw_frame and isinstance(tm.get("payload"), str):
                raw_frame = tm.get("payload")

            raw_decoded = tm.get("decoded_data") or tm.get("extra")
            if isinstance(raw_decoded, str):
                try:
                    raw_decoded = json.loads(raw_decoded)
                except Exception:
                    raw_decoded = None

            if isinstance(raw_decoded, dict) and len(raw_decoded) > 0:
                decoded_fields = raw_decoded
                has_structured_decoded = True
            else:
                decoded_fields = None

            tm_frame = {
                "timestamp": tm.get("timestamp") or tm.get("created"),
                "observer": tm.get("observer") or tm.get("station_id"),
                "raw_frame": raw_frame,
                "decoded_fields": decoded_fields,
            }
            formatted_tm.append(tm_frame)

        has_decoder = bool(sat_meta.get("telemetry_metadata")) or has_structured_decoded

        if not sat_meta and not has_tx and not has_obs and not has_tm:
            overall_status = "NO RECENT DATA"
        elif not has_tx:
            overall_status = "NO TRANSMITTER"
        elif not has_recent_obs:
            overall_status = "NO RECENT DATA"
        elif not has_decoder:
            overall_status = "NO DECODER"
        else:
            overall_status = "AVAILABLE"

        return {
            "norad_id": norad_id,
            "overall_status": overall_status,
            "source_citation": "SATNOGS COMMUNITY GROUND NETWORK",
            "observation_recency_hours": self.observation_recency_hours,
            "satellite_metadata": {
                "sat_id": sat_meta.get("sat_id"),
                "name": sat_meta.get("name"),
                "norad_cat_id": norad_id,
                "status": sat_meta.get("status"),
                "citation": "SATNOGS COMMUNITY GROUND NETWORK",
            },
            "transmitters": [
                {
                    "description": tx.get("description"),
                    "type": tx.get("type"),
                    "mode": tx.get("mode"),
                    "frequency_hz": tx.get("frequency"),
                    "baud": tx.get("baud"),
                    "status": tx.get("status"),
                }
                for tx in transmitters
            ],
            "observations": formatted_obs,
            "telemetry_frames": formatted_tm,
            "latest_observation": latest_obs,
            "has_transmitters": has_tx,
            "has_observations": has_obs,
            "has_recent_observations": has_recent_obs,
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
            "observation_recency_hours": self.observation_recency_hours,
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
            "observation_recency_hours": self.observation_recency_hours,
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
            "observation_recency_hours": self.observation_recency_hours,
            "has_transmitters": full["has_transmitters"],
            "has_observations": full["has_observations"],
            "has_recent_observations": full.get("has_recent_observations", False),
            "has_decoder": full["has_decoder"],
            "has_telemetry_frames": full["has_telemetry_frames"],
            "latest_observation_timestamp": latest_ts,
            "latest_ground_station": latest_station,
            "source_status": full["source_status"],
        }


# Compatibility alias
SatNOGSProvider = SatnogsObservationProvider
