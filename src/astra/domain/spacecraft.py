"""Production Domain Models for Authorized Spacecraft & Telemetry."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SpacecraftStatus(StrEnum):
    NOMINAL_OPERATIONS = "NOMINAL_OPERATIONS"
    DEGRADED = "DEGRADED"
    CRITICAL_ANOMALY = "CRITICAL_ANOMALY"
    SAFE_MODE = "SAFE_MODE"
    DECOMMISSIONED = "DECOMMISSIONED"


class TelemetryStreamStatus(StrEnum):
    LIVE_TELEMETRY = "LIVE_TELEMETRY"
    CURRENT_PROPAGATED = "CURRENT_PROPAGATED"
    NEAR_REAL_TIME_SOURCE = "NEAR_REAL_TIME_SOURCE"
    HISTORICAL_RESEARCH_DATA = "HISTORICAL_RESEARCH_DATA"
    NO_TELEMETRY_SOURCE = "NO_TELEMETRY_SOURCE"
    RESTRICTED = "RESTRICTED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class Mission(BaseModel):
    mission_id: str = Field(..., description="Unique mission code (e.g. ESA-MISSION-1)")
    name: str = Field(..., description="Mission Title")
    agency: str = Field(..., description="Operating Organization / Space Agency (e.g. ESA, ISRO)")
    description: str = Field("", description="Overview of mission objectives")


class Spacecraft(BaseModel):
    spacecraft_id: str = Field(..., description="Unique internal spacecraft identifier")
    norad_id: int | None = Field(None, description="NORAD Catalog ID if tracked globally")
    name: str = Field(..., description="Spacecraft Name")
    mission_id: str = Field(..., description="Associated Mission ID")
    status: SpacecraftStatus = Field(SpacecraftStatus.NOMINAL_OPERATIONS, description="Operational Status")
    telemetry_stream_status: TelemetryStreamStatus = Field(
        TelemetryStreamStatus.HISTORICAL_RESEARCH_DATA, description="Active Telemetry Source Mode"
    )
    authorized_channels: list[str] = Field(default_factory=list, description="Monitored telemetry parameters")


class TelemetryParameter(BaseModel):
    parameter_id: str = Field(..., description="Telemetry Mnemonic / ID (e.g. TM_41_PWR)")
    name: str = Field(..., description="Descriptive Parameter Name")
    subsystem: str = Field("EPS", description="Subsystem (EPS, ADCS, THERMAL, COMM, PAYLOAD)")
    unit: str = Field("V", description="Measurement Unit")
    nominal_min: float | None = None
    nominal_max: float | None = None


class TelemetryPoint(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    parameter_id: str
    value: float
    is_anomaly: bool = False
