"""OrbitCatalogProvider, OrbitPropagationEngine, and OrbitStateStore for Global Orbital Awareness."""

import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from astra.domain.space_object import (
    ObjectType,
    OrbitalElements,
    OrbitRegime,
    OrbitState,
    SpaceObject,
)
from astra.sources.propagator import SGP4Propagator


class OrbitCatalogProvider:
    """Retrieves and manages CelesTrak GP/OMM orbital elements with atomic caching and offline fallback."""

    def __init__(self, cache_dir: str = "data/cache", cache_ttl_seconds: int = 7200):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_seconds
        self.provider_name = "CelesTrak GP/OMM (General Perturbations)"
        self.base_url = "https://celestrak.org/NORAD/elements/gp.php"
        self._catalog_cache_file = self.cache_dir / "celestrak_active_catalog.json"
        self._objects_by_norad: dict[int, SpaceObject] = {}

        self.is_offline = False
        self.last_successful_refresh: datetime | None = None
        self.last_attempt_timestamp: datetime | None = None
        self.last_error: str | None = None
        self.objects_retrieved = 0
        self.objects_loaded = 0
        self.objects_skipped_by_limit = 0
        self.objects_invalid = 0
        self.objects_accepted = 0
        self.objects_rejected = 0
        self.refresh_duration_ms = 0.0
        self.last_http_status: str | None = None

        self.load_initial_catalog()

    @property
    def cache_age_seconds(self) -> float:
        """Returns seconds elapsed since last successful catalog refresh."""
        if not self.last_successful_refresh:
            return -1.0
        return max(0.0, (datetime.now(UTC) - self.last_successful_refresh).total_seconds())

    @property
    def source_epoch(self) -> str | None:
        """Returns the freshest element epoch string across catalog objects."""
        if not self._objects_by_norad:
            return None
        epochs = [obj.elements.epoch for obj in self._objects_by_norad.values() if obj.elements]
        return max(epochs).isoformat() if epochs else None

    @property
    def cache_file_timestamp(self) -> str | None:
        """Returns the ISO timestamp of the cache file on disk."""
        if self._catalog_cache_file.exists():
            mtime = datetime.fromtimestamp(self._catalog_cache_file.stat().st_mtime, tz=UTC)
            return mtime.isoformat()
        return None

    @property
    def cache_state(self) -> str:
        """Determines explicit catalog cache state without ambiguous terms."""
        if not self._objects_by_norad:
            return "SOURCE UNAVAILABLE"
        if not self.is_offline:
            return "LIVE_ONLINE"
        return "USING CACHED ORBITAL ELEMENTS"

    @property
    def status_summary(self) -> dict[str, Any]:
        """Provides full catalog operational state and provenance metadata."""
        return {
            "provider": self.provider_name,
            "source_url": f"{self.base_url}?GROUP=active&FORMAT=json",
            "status": self.cache_state,
            "cache_state": self.cache_state,
            "is_offline": self.is_offline,
            "http_status": self.last_http_status or ("200 OK" if not self.is_offline else "SOURCE OFFLINE"),
            "catalog_object_count": len(self._objects_by_norad),
            "objects_retrieved": self.objects_retrieved,
            "objects_loaded": self.objects_loaded,
            "objects_skipped_by_limit": self.objects_skipped_by_limit,
            "objects_invalid": self.objects_invalid,
            "objects_accepted": self.objects_accepted,
            "objects_rejected": self.objects_rejected,
            "cache_path": str(self._catalog_cache_file),
            "cache_file_timestamp": self.cache_file_timestamp,
            "last_successful_refresh": self.last_successful_refresh.isoformat() if self.last_successful_refresh else None,
            "last_attempt_timestamp": self.last_attempt_timestamp.isoformat() if self.last_attempt_timestamp else None,
            "refresh_duration_ms": round(self.refresh_duration_ms, 2),
            "source_epoch": self.source_epoch,
            "cache_age_seconds": round(self.cache_age_seconds, 1),
            "last_error": self.last_error,
        }

    def load_initial_catalog(self) -> None:
        """Loads cached catalog or flags catalog as unavailable if no cache exists."""
        if self._catalog_cache_file.exists():
            try:
                with open(self._catalog_cache_file, encoding="utf-8") as f:
                    payload = json.load(f)
                if payload.get("last_update"):
                    self.last_successful_refresh = datetime.fromisoformat(payload["last_update"])
                items = payload.get("objects", [])
                for item in items:
                    obj = SpaceObject.model_validate(item)
                    self._objects_by_norad[obj.norad_id] = obj
                self.objects_retrieved = len(items)
                self.objects_loaded = len(self._objects_by_norad)
                self.objects_skipped_by_limit = 0
                self.objects_invalid = max(0, len(items) - len(self._objects_by_norad))
                self.objects_accepted = self.objects_loaded
                self.objects_rejected = self.objects_invalid
                self.last_http_status = "200 OK (CACHED SNAPSHOT)"
                self.is_offline = True
            except Exception as e:
                self.last_error = f"Cache parse error: {e}"
                self.is_offline = True

        if not self._objects_by_norad:
            self.is_offline = True
            self.last_error = "No disk cache available and online retrieval pending"
            self.last_http_status = "404 CACHE MISS"

    def _init_default_catalog(self) -> None:
        """Populates baseline catalog with key trackable Earth satellite objects."""
        now_dt = datetime.now(UTC)
        defaults = [
            {
                "norad_id": 25544,
                "cospar_id": "1998-067A",
                "name": "ISS (ZARYA)",
                "object_type": ObjectType.ACTIVE_SPACECRAFT,
                "elements": {
                    "norad_id": 25544,
                    "cospar_id": "1998-067A",
                    "name": "ISS (ZARYA)",
                    "object_type": "ACTIVE_SPACECRAFT",
                    "epoch": now_dt.isoformat(),
                    "mean_motion": 15.489,
                    "eccentricity": 0.0005,
                    "inclination_deg": 51.64,
                    "raan_deg": 280.0,
                    "arg_perigee_deg": 90.0,
                    "mean_anomaly_deg": 260.0,
                    "bstar": 0.00008,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": now_dt.isoformat(),
                },
                "telemetry_authorization": False,
            },
            {
                "norad_id": 44804,
                "cospar_id": "2019-089A",
                "name": "CARTOSAT-3",
                "object_type": ObjectType.ACTIVE_SPACECRAFT,
                "elements": {
                    "norad_id": 44804,
                    "cospar_id": "2019-089A",
                    "name": "CARTOSAT-3",
                    "object_type": "ACTIVE_SPACECRAFT",
                    "epoch": now_dt.isoformat(),
                    "mean_motion": 14.95,
                    "eccentricity": 0.0002,
                    "inclination_deg": 97.4,
                    "raan_deg": 200.0,
                    "arg_perigee_deg": 60.0,
                    "mean_anomaly_deg": 100.0,
                    "bstar": 0.00001,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": now_dt.isoformat(),
                },
                "telemetry_authorization": False,
            },
            {
                "norad_id": 51656,
                "cospar_id": "2022-013A",
                "name": "EOS-04",
                "object_type": ObjectType.ACTIVE_SPACECRAFT,
                "elements": {
                    "norad_id": 51656,
                    "cospar_id": "2022-013A",
                    "name": "EOS-04",
                    "object_type": "ACTIVE_SPACECRAFT",
                    "epoch": now_dt.isoformat(),
                    "mean_motion": 14.82,
                    "eccentricity": 0.0001,
                    "inclination_deg": 97.5,
                    "raan_deg": 120.0,
                    "arg_perigee_deg": 45.0,
                    "mean_anomaly_deg": 180.0,
                    "bstar": 0.00001,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": now_dt.isoformat(),
                },
                "telemetry_authorization": False,
            },
            {
                "norad_id": 20580,
                "cospar_id": "1990-037B",
                "name": "HUBBLE SPACE TELESCOPE",
                "object_type": ObjectType.ACTIVE_SPACECRAFT,
                "elements": {
                    "norad_id": 20580,
                    "cospar_id": "1990-037B",
                    "name": "HUBBLE SPACE TELESCOPE",
                    "object_type": "ACTIVE_SPACECRAFT",
                    "epoch": now_dt.isoformat(),
                    "mean_motion": 15.08,
                    "eccentricity": 0.0003,
                    "inclination_deg": 28.47,
                    "raan_deg": 110.0,
                    "arg_perigee_deg": 80.0,
                    "mean_anomaly_deg": 220.0,
                    "bstar": 0.00002,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": now_dt.isoformat(),
                },
                "telemetry_authorization": False,
            },
        ]
        for d in defaults:
            obj = SpaceObject.model_validate(d)
            self._objects_by_norad[obj.norad_id] = obj
        if self.last_successful_refresh is None:
            self.last_successful_refresh = now_dt
        self.objects_retrieved = len(defaults)
        self.objects_accepted = len(defaults)
        self.objects_rejected = 0
        self.last_http_status = "200 OK (BASELINE CATALOG)"

    def fetch_online_catalog(self, group: str = "active") -> bool:
        """Atomic catalog refresh: fetches upstream OMM data without mutating active cache on failure."""
        start_time = time.perf_counter()
        now_utc = datetime.now(UTC)
        self.last_attempt_timestamp = now_utc
        url = f"{self.base_url}?GROUP={group}&FORMAT=json"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                self.last_http_status = f"{resp.status_code} {resp.reason_phrase}"
                if resp.status_code != 200:
                    self.is_offline = True
                    self.last_error = f"HTTP status {resp.status_code} from upstream provider"
                    self.refresh_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    return False

                raw_list = resp.json()
                if not isinstance(raw_list, list) or len(raw_list) == 0:
                    self.is_offline = True
                    self.last_error = "Empty or malformed JSON array received from upstream provider"
                    self.refresh_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    return False

                self.objects_retrieved = len(raw_list)
                rejected = 0
                temp_catalog: dict[int, SpaceObject] = {}
                for item in raw_list[:500]:
                    norad_id = int(item.get("NORAD_CAT_ID", 0))
                    if norad_id <= 0:
                        rejected += 1
                        continue

                    epoch_str = str(item.get("EPOCH", ""))
                    try:
                        epoch_dt = datetime.fromisoformat(epoch_str.replace("Z", "+00:00"))
                    except Exception:
                        epoch_dt = now_utc

                    elems = OrbitalElements(
                        norad_id=norad_id,
                        cospar_id=item.get("OBJECT_ID"),
                        name=str(item.get("OBJECT_NAME", f"OBJECT {norad_id}")),
                        object_type=ObjectType.ACTIVE_SPACECRAFT,
                        epoch=epoch_dt,
                        mean_motion=float(item.get("MEAN_MOTION", 15.0)),
                        eccentricity=float(item.get("ECCENTRICITY", 0.001)),
                        inclination_deg=float(item.get("INCLINATION", 51.6)),
                        raan_deg=float(item.get("RA_OF_ASC_NODE", 0.0)),
                        arg_perigee_deg=float(item.get("ARG_OF_PERICENTER", 0.0)),
                        mean_anomaly_deg=float(item.get("MEAN_ANOMALY", 0.0)),
                        bstar=float(item.get("BSTAR", 0.0)),
                        mean_motion_dot=float(item.get("MEAN_MOTION_DOT", 0.0)),
                        source="CELESTRAK_OMM",
                        refresh_timestamp=now_utc,
                    )

                    mm = elems.mean_motion
                    regime = OrbitRegime.LEO
                    if mm < 1.5:
                        regime = OrbitRegime.GEO
                    elif mm < 10.0:
                        regime = OrbitRegime.MEO

                    obj = SpaceObject(
                        norad_id=norad_id,
                        cospar_id=item.get("OBJECT_ID"),
                        name=elems.name,
                        object_type=ObjectType.ACTIVE_SPACECRAFT,
                        orbit_regime=regime,
                        elements=elems,
                        telemetry_authorization=False,
                    )
                    temp_catalog[norad_id] = obj

                if not temp_catalog:
                    self.is_offline = True
                    self.last_error = "No valid orbital elements parsed from upstream payload"
                    self.refresh_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    return False

                self.objects_loaded = len(temp_catalog)
                self.objects_skipped_by_limit = max(0, self.objects_retrieved - 500)
                self.objects_invalid = rejected
                self.objects_accepted = self.objects_loaded
                self.objects_rejected = self.objects_invalid
                self._objects_by_norad = temp_catalog
                self.last_successful_refresh = now_utc
                self.is_offline = False
                self.last_error = None
                self.refresh_duration_ms = (time.perf_counter() - start_time) * 1000.0
                self._save_cache()
                return True

        except Exception as e:
            self.is_offline = True
            self.last_error = f"Network or IO exception: {e}"
            self.refresh_duration_ms = (time.perf_counter() - start_time) * 1000.0
            return False

    def _save_cache(self) -> None:
        """Atomically saves verified catalog snapshot to disk cache."""
        try:
            payload = {
                "last_update": self.last_successful_refresh.isoformat() if self.last_successful_refresh else datetime.now(UTC).isoformat(),
                "objects": [obj.model_dump(mode="json") for obj in self._objects_by_norad.values()],
            }
            tmp_cache = self.cache_dir / "celestrak_active_catalog.tmp"
            with open(tmp_cache, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_cache.replace(self._catalog_cache_file)
        except Exception as e:
            self.last_error = f"Disk cache save error: {e}"

    def get_object(self, norad_id: int) -> SpaceObject | None:
        return self._objects_by_norad.get(norad_id)

    def list_objects(
        self,
        query: str | None = None,
        regime: OrbitRegime | None = None,
        obj_type: ObjectType | None = None,
        authorized_only: bool = False,
    ) -> list[SpaceObject]:
        """Lists catalog objects with exact match priority ranking for search queries."""
        results = list(self._objects_by_norad.values())

        if authorized_only:
            results = [o for o in results if o.telemetry_authorization]
        if regime:
            results = [o for o in results if o.orbit_regime == regime]
        if obj_type:
            results = [o for o in results if o.object_type == obj_type]

        if not query or not query.strip():
            return results

        q = query.strip().lower()

        # Exact match ranking algorithm
        exact_norad: list[SpaceObject] = []
        exact_cospar: list[SpaceObject] = []
        exact_name: list[SpaceObject] = []
        prefix_name: list[SpaceObject] = []
        fuzzy_match: list[SpaceObject] = []

        for obj in results:
            norad_str = str(obj.norad_id)
            cospar_str = (obj.cospar_id or "").lower()
            name_str = obj.name.lower()

            if q == norad_str:
                exact_norad.append(obj)
            elif cospar_str and q == cospar_str:
                exact_cospar.append(obj)
            elif name_str == q:
                exact_name.append(obj)
            elif name_str.startswith(q):
                prefix_name.append(obj)
            elif q in name_str or q in norad_str or (cospar_str and q in cospar_str):
                fuzzy_match.append(obj)

        return exact_norad + exact_cospar + exact_name + prefix_name + fuzzy_match


class OrbitPropagationEngine:
    """Local SGP4 propagation engine for calculating state vectors and derived orbital metrics."""

    @staticmethod
    def calculate_derived_metrics(elems: OrbitalElements) -> dict[str, float]:
        """Derives orbital period, apogee, and perigee altitude from mean motion and eccentricity."""
        # Mean motion n (rev/day) -> Period T (minutes)
        mm = elems.mean_motion if elems.mean_motion > 0 else 15.0
        period_min = 1440.0 / mm

        # Semi-major axis a (km) using Kepler's Third Law: n^2 * a^3 = mu
        # mu = 398600.4418 km^3/s^2. rev/day -> rad/s:
        n_rad_s = mm * (2 * math.pi) / 86400.0
        a_km = (398600.4418 / (n_rad_s**2)) ** (1.0 / 3.0)

        # Apogee & Perigee altitudes above Earth mean radius R_E = 6378.137 km
        r_earth = 6378.137
        ecc = min(max(elems.eccentricity, 0.0), 0.99)
        apogee_km = a_km * (1.0 + ecc) - r_earth
        perigee_km = a_km * (1.0 - ecc) - r_earth

        return {
            "period_minutes": round(period_min, 2),
            "semi_major_axis_km": round(a_km, 2),
            "apogee_km": round(max(0.0, apogee_km), 2),
            "perigee_km": round(max(0.0, perigee_km), 2),
        }

    @classmethod
    def calculate_orbit_path(
        cls,
        space_obj: SpaceObject,
        current_dt: datetime | None = None,
        past_minutes: int = 45,
        future_minutes: int = 90,
        step_minutes: int = 3,
    ) -> list[dict[str, float]]:
        """Calculates finite past and future orbit path trajectory coordinates for a space object."""
        if current_dt is None:
            current_dt = datetime.now(UTC)

        elems = space_obj.elements
        gp_dict: dict[str, Any] = {
            "NORAD_CAT_ID": elems.norad_id,
            "OBJECT_NAME": elems.name,
            "EPOCH": elems.epoch.isoformat(),
            "INCLINATION": elems.inclination_deg,
            "RA_OF_ASC_NODE": elems.raan_deg,
            "ECCENTRICITY": elems.eccentricity,
            "ARG_OF_PERICENTER": elems.arg_perigee_deg,
            "MEAN_ANOMALY": elems.mean_anomaly_deg,
            "MEAN_MOTION": elems.mean_motion,
            "BSTAR": elems.bstar,
        }

        propagator = SGP4Propagator(gp_dict)
        points = []
        start_dt = current_dt - timedelta(minutes=past_minutes)
        total_minutes = past_minutes + future_minutes
        steps = int(total_minutes / step_minutes) + 1

        for i in range(steps):
            dt = start_dt + timedelta(minutes=i * step_minutes)
            st = propagator.propagate(dt)
            points.append({
                "lat": round(st["latitude"], 4),
                "lon": round(st["longitude"], 4),
                "alt_km": round(st["altitude_km"], 1),
                "minute_offset": -past_minutes + (i * step_minutes),
            })
        return points

    @classmethod
    def propagate_object(cls, space_obj: SpaceObject, current_dt: datetime | None = None) -> OrbitState:
        if current_dt is None:
            current_dt = datetime.now(UTC)

        elems = space_obj.elements
        gp_dict: dict[str, Any] = {
            "NORAD_CAT_ID": elems.norad_id,
            "OBJECT_NAME": elems.name,
            "EPOCH": elems.epoch.isoformat(),
            "INCLINATION": elems.inclination_deg,
            "RA_OF_ASC_NODE": elems.raan_deg,
            "ECCENTRICITY": elems.eccentricity,
            "ARG_OF_PERICENTER": elems.arg_perigee_deg,
            "MEAN_ANOMALY": elems.mean_anomaly_deg,
            "MEAN_MOTION": elems.mean_motion,
            "BSTAR": elems.bstar,
        }

        propagator = SGP4Propagator(gp_dict)
        pos = propagator.propagate(current_dt)
        age_hours = (current_dt - elems.epoch.replace(tzinfo=UTC)).total_seconds() / 3600.0

        return OrbitState(
            norad_id=space_obj.norad_id,
            name=space_obj.name,
            cospar_id=space_obj.cospar_id,
            object_type=space_obj.object_type,
            orbit_regime=space_obj.orbit_regime,
            propagated_timestamp=current_dt,
            latitude=pos["latitude"],
            longitude=pos["longitude"],
            altitude_km=pos["altitude_km"],
            velocity_kms=pos["velocity_kms"],
            element_epoch=elems.epoch,
            element_age_hours=max(0.0, age_hours),
            source_provenance="SGP4 (WGS72) Local Propagation",
        )


class OrbitStateStore:
    """In-memory state store maintaining cached propagation snapshots for full catalog scalability."""

    def __init__(self, catalog_provider: OrbitCatalogProvider, cache_cadence_seconds: float = 3.0):
        self.catalog = catalog_provider
        self.engine = OrbitPropagationEngine()
        self.cache_cadence = cache_cadence_seconds
        self._cached_states: list[OrbitState] = []
        self._last_propagation_dt: datetime | None = None

    def update_snapshot(self, force: bool = False) -> list[OrbitState]:
        """Calculates or reuses cached propagated states according to cadence policy."""
        now = datetime.now(UTC)
        if (
            not force
            and self._last_propagation_dt
            and (now - self._last_propagation_dt).total_seconds() < self.cache_cadence
        ):
            return self._cached_states

        objects = self.catalog.list_objects()
        self._cached_states = [self.engine.propagate_object(obj, now) for obj in objects]
        self._last_propagation_dt = now
        return self._cached_states

    def get_all_propagated_states(self) -> list[OrbitState]:
        """Returns cached propagated state vectors for catalog visualization."""
        if not self._cached_states or self._last_propagation_dt is None:
            return self.update_snapshot(force=True)
        return self.update_snapshot(force=False)

    def get_propagated_state(self, norad_id: int) -> OrbitState | None:
        """High-frequency real-time propagation on demand for individual selected object."""
        obj = self.catalog.get_object(norad_id)
        if not obj:
            return None
        return self.engine.propagate_object(obj, datetime.now(UTC))
