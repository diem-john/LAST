"""Build chronological storm tracks and optional Minxiong synthetic-grid proximity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from forecasting.data.ibtracs_tracks import build_ibtracs_tracks, write_ibtracs_outputs

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata-dir", type=Path, default=ROOT / "data/ibtracs/metadata",
        help="Directory containing one metadata CSV per storm instance.",
    )
    parser.add_argument(
        "--bus-locations", type=Path,
        default=ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv",
        help="Optional 33-bus synthetic coordinate CSV used for proximity metrics.",
    )
    parser.add_argument(
        "--no-grid-proximity", action="store_true",
        help="Process storm tracks without calculating distance to synthetic bus points.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "reports/ibtracs",
        help="Directory for normalized tracks, rejected rows, summaries, and audit JSON.",
    )
    args = parser.parse_args()

    bus_path = None if args.no_grid_proximity else args.bus_locations
    tracks, rejected, summaries, audit = build_ibtracs_tracks(
        args.metadata_dir, bus_locations_csv=bus_path
    )
    outputs = write_ibtracs_outputs(
        tracks, rejected, summaries, audit, args.output_dir
    )
    print(json.dumps({
        "status": audit["status"],
        "metadata_file_count": audit["metadata_file_count"],
        "storm_instance_count": audit["storm_instance_count"],
        "source_row_count": audit["source_row_count"],
        "valid_track_row_count": audit["valid_track_row_count"],
        "rejected_row_count": audit["rejected_row_count"],
        "duplicate_timestamp_count": audit["duplicate_timestamp_count"],
        "grid_proximity_status": audit["grid_proximity_status"],
        "outputs": outputs,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
