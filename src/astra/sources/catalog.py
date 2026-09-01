"""OrbitCatalogProvider, OrbitPropagationEngine, and OrbitStateStore for Global Orbital Awareness."""

import json
from datetime import UTC, datetime
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
    """Retrieves and manages CelesTrak GP/OMM orbital elements with disk caching and offline fallback."""

    def __init__(self, cache_dir: str = "data/cache", cache_ttl_seconds: int = 7200):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_seconds
        self.base_url = "https://celestrak.org/NORAD/elements/gp.php"
        self._catalog_cache_file = self.cache_dir / "celestrak_active_catalog.json"
        self._objects_by_norad: dict[int, SpaceObject] = {}
        self.is_offline = False
        self.last_update: datetime | None = None
        self.load_initial_catalog()

    def load_initial_catalog(self) -> None:
        """Loads cached catalog or initializes default catalog objects."""
        if self._catalog_cache_file.exists():
            try:
                with open(self._catalog_cache_file, encoding="utf-8") as f:
                    payload = json.load(f)
                self.last_update = datetime.fromisoformat(payload.get("last_update"))
                items = payload.get("objects", [])
                for item in items:
                    obj = SpaceObject.model_validate(item)
                    self._objects_by_norad[obj.norad_id] = obj
            except Exception:
                pass

        if not self._objects_by_norad:
            self._init_default_catalog()

    def _init_default_catalog(self) -> None:
        """Populates baseline catalog with key active earth satellites."""
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
                    "epoch": datetime.now(UTC).isoformat(),
                    "mean_motion": 15.489,
                    "eccentricity": 0.0005,
                    "inclination_deg": 51.64,
                    "raan_deg": 280.0,
                    "arg_perigee_deg": 90.0,
                    "mean_anomaly_deg": 260.0,
                    "bstar": 0.00008,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": datetime.now(UTC).isoformat(),
                },
                "telemetry_authorization": True,
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
                    "epoch": datetime.now(UTC).isoformat(),
                    "mean_motion": 14.95,
                    "eccentricity": 0.0002,
                    "inclination_deg": 97.4,
                    "raan_deg": 200.0,
                    "arg_perigee_deg": 60.0,
                    "mean_anomaly_deg": 100.0,
                    "bstar": 0.00001,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": datetime.now(UTC).isoformat(),
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
                    "epoch": datetime.now(UTC).isoformat(),
                    "mean_motion": 14.82,
                    "eccentricity": 0.0001,
                    "inclination_deg": 97.5,
                    "raan_deg": 120.0,
                    "arg_perigee_deg": 45.0,
                    "mean_anomaly_deg": 180.0,
                    "bstar": 0.00001,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": datetime.now(UTC).isoformat(),
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
                    "epoch": datetime.now(UTC).isoformat(),
                    "mean_motion": 15.08,
                    "eccentricity": 0.0003,
                    "inclination_deg": 28.47,
                    "raan_deg": 110.0,
                    "arg_perigee_deg": 80.0,
                    "mean_anomaly_deg": 220.0,
                    "bstar": 0.00002,
                    "mean_motion_dot": 0.0,
                    "source": "CELESTRAK_OMM",
                    "refresh_timestamp": datetime.now(UTC).isoformat(),
                },
                "telemetry_authorization": False,
            },
        ]
        for d in defaults:
            obj = SpaceObject.model_validate(d)
            self._objects_by_norad[obj.norad_id] = obj

    def fetch_online_catalog(self, group: str = "active") -> bool:
        """Fetches active satellite orbital elements from CelesTrak OMM endpoint."""
        url = f"{self.base_url}?GROUP={group}&FORMAT=json"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    raw_list = resp.json()
                    now_utc = datetime.now(UTC)
                    for item in raw_list[:500]:  # Up to 500 active objects
                        norad_id = int(item.get("NORAD_CAT_ID", 0))
                        if norad_id <= 0:
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

                        # Determine regime
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
                            telemetry_authorization=(norad_id == 25544),
                        )
                        self._objects_by_norad[norad_id] = obj

                    self.last_update = now_utc
                    self.is_offline = False
                    self._save_cache()
                    return True
        except Exception:
            self.is_offline = True
            return False
        return False

    def _save_cache(self) -> None:
        try:
            payload = {
                "last_update": self.last_update.isoformat() if self.last_update else datetime.now(UTC).isoformat(),
                "objects": [obj.model_dump(mode="json") for obj in self._objects_by_norad.values()],
            }
            with open(self._catalog_cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def get_object(self, norad_id: int) -> SpaceObject | None:
        return self._objects_by_norad.get(norad_id)

    def list_objects(
        self,
        query: str | None = None,
        regime: OrbitRegime | None = None,
        obj_type: ObjectType | None = None,
        authorized_only: bool = False,
    ) -> list[SpaceObject]:
        results = list(self._objects_by_norad.values())
        if authorized_only:
            results = [o for o in results if o.telemetry_authorization]
        if regime:
            results = [o for o in results if o.orbit_regime == regime]
        if obj_type:
            results = [o for o in results if o.object_type == obj_type]
        if query:
            q = query.lower()
            results = [
                o
                for o in results
                if q in o.name.lower() or q in str(o.norad_id) or (o.cospar_id and q in o.cospar_id.lower())
            ]
        return results


class OrbitPropagationEngine:
    """Local SGP4 propagation engine for calculating current state vectors from orbital elements."""

    @staticmethod
    def propagate_object(space_obj: SpaceObject, current_dt: datetime | None = None) -> OrbitState:
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
    """In-memory state store maintaining catalog objects, propagated states, and provider status."""

    def __init__(self, catalog_provider: OrbitCatalogProvider):
        self.catalog = catalog_provider
        self.engine = OrbitPropagationEngine()

    def get_all_propagated_states(self) -> list[OrbitState]:
        now = datetime.now(UTC)
        objects = self.catalog.list_objects()
        return [self.engine.propagate_object(obj, now) for obj in objects]

    def get_propagated_state(self, norad_id: int) -> OrbitState | None:
        obj = self.catalog.get_object(norad_id)
        if not obj:
            return None
        return self.engine.propagate_object(obj, datetime.now(UTC))
