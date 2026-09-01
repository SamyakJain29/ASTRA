"""Production Domain Models for Global Orbital Awareness & Space Objects."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ObjectType(StrEnum):
    ACTIVE_SPACECRAFT = "ACTIVE_SPACECRAFT"
    INACTIVE_SPACECRAFT = "INACTIVE_SPACECRAFT"
    ROCKET_BODY = "ROCKET_BODY"
    DEBRIS = "DEBRIS"
    UNKNOWN = "UNKNOWN"


class OrbitRegime(StrEnum):
    LEO = "LEO"  # Low Earth Orbit (< 2000 km)
    MEO = "MEO"  # Medium Earth Orbit (2000 - 35786 km)
    GEO = "GEO"  # Geostationary Earth Orbit (~ 35786 km)
    HEO = "HEO"  # High Earth / Highly Elliptical Orbit (> 35786 km or high ecc)
    OTHER = "OTHER"


class OrbitalElements(BaseModel):
    norad_id: int = Field(..., description="NORAD Catalog Number")
    cospar_id: str | None = Field(None, description="International Designator / COSPAR ID")
    name: str = Field(..., description="Object Name")
    object_type: ObjectType = Field(ObjectType.ACTIVE_SPACECRAFT, description="Category of space object")
    epoch: datetime = Field(..., description="Element Set Epoch UTC")
    mean_motion: float = Field(..., description="Mean motion in revs/day")
    eccentricity: float = Field(..., description="Eccentricity")
    inclination_deg: float = Field(..., description="Inclination in degrees")
    raan_deg: float = Field(..., description="Right Ascension of Ascending Node in degrees")
    arg_perigee_deg: float = Field(..., description="Argument of Perigee in degrees")
    mean_anomaly_deg: float = Field(..., description="Mean Anomaly in degrees")
    bstar: float = Field(0.0, description="BSTAR drag term")
    mean_motion_dot: float = Field(0.0, description="First derivative of mean motion")
    source: str = Field("CELESTRAK_OMM", description="Source of orbital elements")
    refresh_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Local cache time")


class SpaceObject(BaseModel):
    norad_id: int
    cospar_id: str | None = None
    name: str
    object_type: ObjectType = ObjectType.ACTIVE_SPACECRAFT
    orbit_regime: OrbitRegime = OrbitRegime.LEO
    elements: OrbitalElements
    telemetry_authorization: bool = Field(
        False, description="True if ASTRA has authorized mission-level telemetry access"
    )


class OrbitState(BaseModel):
    norad_id: int
    name: str
    cospar_id: str | None = None
    object_type: ObjectType = ObjectType.ACTIVE_SPACECRAFT
    orbit_regime: OrbitRegime = OrbitRegime.LEO
    propagated_timestamp: datetime = Field(..., description="Current UTC timestamp of SGP4 propagation")
    latitude: float = Field(..., description="Geodetic Latitude [-90, +90]")
    longitude: float = Field(..., description="Geodetic Longitude [-180, +180]")
    altitude_km: float = Field(..., description="Altitude above WGS72 ellipsoid (km)")
    velocity_kms: float = Field(..., description="Orbital speed magnitude (km/s)")
    element_epoch: datetime = Field(..., description="Orbital element epoch UTC")
    element_age_hours: float = Field(..., description="Age of elements at propagation time in hours")
    source_provenance: str = Field("SGP4 (WGS72) Local Propagation", description="Propagation model description")
