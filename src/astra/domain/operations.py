"""Production Domain Models for Operational Events, Alerts, Event Memory, and Data Sources."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class OperationalEvent(BaseModel):
    event_id: str
    spacecraft_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category: str = Field("Nominal", description="Nominal, Rare Maneuver, Anomaly")
    description: str = ""
    affected_channels: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    alert_id: str
    spacecraft_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field("NOMINAL", description="NOMINAL, UNKNOWN_UNUSUAL_EVENT, KNOWN_OPERATIONAL_PATTERN, CRITICAL_ANOMALY")
    severity: str = Field("INFO", description="INFO, WARNING, CRITICAL")
    unusualness_score: float = 0.0
    classification: str = "NOMINAL_TELEMETRY"
    affected_channels: list[str] = Field(default_factory=list)
    top_contributing_channels: list[str] = Field(default_factory=list)
    recent_tc_count_5m: int = 0
    nearest_pattern_id: str | None = None
    similarity_score: float = 0.0
    explanation: str = ""
    recommended_action: str = ""


class EventMemoryRecord(BaseModel):
    memory_id: str
    source_event_id: str
    event_timestamp: str
    operator_label: str
    affected_channels: list[str]
    creation_timestamp: str


class DataSourceStatus(BaseModel):
    provider_name: str
    data_scope: str = Field(..., description="GLOBAL_ORBITAL_AWARENESS or AUTHORIZED_SPACECRAFT_OPERATIONS")
    status: str = Field("ONLINE", description="ONLINE, OFFLINE_CACHED, STALE, UNAVAILABLE, RESTRICTED")
    last_successful_update: str
    source_epoch: str | None = None
    age_hours: float = 0.0
    availability_pct: float = 100.0
    coverage_summary: str = ""
    error_message: str | None = None
