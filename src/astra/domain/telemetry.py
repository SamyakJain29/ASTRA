"""TelemetryProvider abstract interface and ESA Mission-1 provider implementation."""

from abc import ABC, abstractmethod
from typing import Any

from astra.domain.spacecraft import Spacecraft, TelemetryPoint, TelemetryStreamStatus


class TelemetryProvider(ABC):
    """Abstract interface for all authorized spacecraft telemetry sources."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier of the provider."""
        ...

    @property
    @abstractmethod
    def stream_status(self) -> TelemetryStreamStatus:
        """Current stream status (LIVE_TELEMETRY, HISTORICAL, UNAVAILABLE, etc.)."""
        ...

    @abstractmethod
    def get_spacecraft_metadata(self) -> Spacecraft:
        """Returns spacecraft domain metadata for authorized operations."""
        ...

    @abstractmethod
    def fetch_latest_telemetry(self) -> dict[str, list[TelemetryPoint]]:
        """Returns the latest telemetry window for all authorized parameters."""
        ...

    @abstractmethod
    def get_provider_status(self) -> dict[str, Any]:
        """Returns telemetry source health, coverage, and provenance details."""
        ...


class EsaMission1TelemetryProvider(TelemetryProvider):
    """TelemetryProvider implementation for ESA Mission-1 historical research dataset."""

    def __init__(self, dataset_path: str = "data/processed/mission1/processed_features.parquet"):
        self._path = dataset_path
        self._provider_id = "ESA_MISSION_1_ARCHIVE"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def stream_status(self) -> TelemetryStreamStatus:
        return TelemetryStreamStatus.HISTORICAL

    def get_spacecraft_metadata(self) -> Spacecraft:
        return Spacecraft(
            spacecraft_id="ESA_MISSION_1",
            norad_id=None,
            name="ESA Mission-1 Satellite",
            mission_id="ESA_MISSION_1",
            telemetry_stream_status=TelemetryStreamStatus.HISTORICAL,
            authorized_channels=["channel_41", "channel_42", "channel_43", "channel_44", "channel_45", "channel_46"],
        )

    def fetch_latest_telemetry(self) -> dict[str, list[TelemetryPoint]]:
        # Provided by backend state or historical parquet stream
        return {}

    def get_provider_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "availability": "AVAILABLE (HISTORICAL REPLAY)",
            "telemetry_type": "ESA ADB Telemetry Dataset",
            "channels_count": 6,
            "coverage": "65 Labelled Test Events",
            "last_successful_update": "N/A (Historical Archive)",
            "error_state": None,
        }
