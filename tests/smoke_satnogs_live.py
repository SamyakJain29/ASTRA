"""Optional manual live smoke test for SatNOGS provider.

Run manually to check live upstream SatNOGS connectivity:
    python tests/smoke_satnogs_live.py
"""

import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from astra.sources.satnogs import SatnogsObservationProvider


def main():
    print("=== ASTRA SatNOGS Live Smoke Test ===")
    provider = SatnogsObservationProvider(timeout_seconds=5.0)

    norad_id = 25544  # ISS
    print(f"Fetching live SatNOGS data for NORAD {norad_id}...")
    res = provider.fetch_all(norad_id, force_refresh=True)

    print(f"Overall Status: {res.get('overall_status')}")
    print(f"Source Status:  {res.get('source_status')}")
    print(f"Transmitters:   {len(res.get('transmitters', []))}")
    print(f"Observations:   {len(res.get('observations', []))}")
    print(f"Telemetry:      {len(res.get('telemetry_frames', []))}")
    print(f"Has Decoder:    {res.get('has_decoder')}")

    print("\nRecent RF NORAD IDs query...")
    recent = provider.get_recent_rf_norad_ids(force_refresh=True)
    print(f"Found {len(recent)} recent RF NORAD IDs across public network.")

    print("\nSmoke test complete.")


if __name__ == "__main__":
    main()
