"""Generate the deterministic temporal split manifest for ESA Mission-1 telemetry and events."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from astra.data.preparation import write_json_deterministic
from astra.data.splits import build_split_manifest, mission1_temporal_split

PROCESSED_DIR = Path("data/processed/mission1")
EVENTS_PATH = PROCESSED_DIR / "events.parquet"
CHANNEL_PATH = PROCESSED_DIR / "channels" / "channel_41.parquet"
OUTPUT_PATH = Path("artifacts/data/mission1_split_manifest.json")
MANIFEST_PATH = Path("artifacts/data/mission1_subset_manifest.json")

def main() -> None:
    print("Loading events...")
    events = pq.read_table(EVENTS_PATH).to_pandas()
    print("Loading channel timestamps...")
    timestamps = pq.read_table(CHANNEL_PATH, columns=["timestamp"])["timestamp"].to_pandas()
    timestamps = pd.to_datetime(timestamps, utc=True)
    
    start_ts = timestamps.min()
    end_ts = timestamps.max()
    print(f"Dataset extent: {start_ts} to {end_ts}")
    
    split = mission1_temporal_split(start_ts, end_ts)
    
    # Read subset manifest sha256
    import json
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        subset_manifest = json.load(f)
    dataset_sha256 = subset_manifest.get("code_version", "unknown")
    
    manifest = build_split_manifest(
        events,
        split,
        dataset_manifest_sha256=dataset_sha256,
        telemetry_timestamps=timestamps,
    )
    
    write_json_deterministic(manifest, OUTPUT_PATH)
    print(f"Split manifest written to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
