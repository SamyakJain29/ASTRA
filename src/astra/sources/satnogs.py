"""SatNOGS public database observation retriever with fallback resilience."""

from typing import Any

import httpx


class SatNOGSProvider:
    """Retrieves optional satellite observation metadata from SatNOGS DB API."""

    def __init__(self, base_url: str = "https://db.satnogs.org/api") -> None:
        self.base_url = base_url

    def get_satellite_observations(self, norad_id: int) -> dict[str, Any]:
        """Fetches latest decoded telemetry observation frame for norad_id.

        Never raises exceptions to guarantee LIVE ORBIT stability. Returns 'NO RECENT DECODED TELEMETRY' if missing.
        """
        url = f"{self.base_url}/observations/?norad_cat_id={norad_id}&limit=1"
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    results = resp.json()
                    if isinstance(results, list) and len(results) > 0:
                        obs = results[0]
                        return {
                            "norad_cat_id": norad_id,
                            "observation_id": obs.get("id"),
                            "ground_station_id": obs.get("station"),
                            "observation_timestamp": obs.get("start"),
                            "transmitter_frequency": obs.get("frequency"),
                            "demodulator_status": obs.get("status", "GOOD"),
                            "telemetry_frame_decoded": obs.get("demoddata") is not None,
                            "status": "DECODED_FRAME_AVAILABLE" if obs.get("demoddata") else "NO RECENT DECODED TELEMETRY",
                        }
        except Exception:
            pass

        return {
            "norad_cat_id": norad_id,
            "status": "NO RECENT DECODED TELEMETRY",
            "observation_timestamp": None,
            "transmitter_frequency": "437.500 MHz",
            "telemetry_frame_decoded": False,
        }
