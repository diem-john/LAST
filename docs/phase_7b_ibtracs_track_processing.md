# IBTrACS-first storm-track processing

## Purpose

This phase establishes a reproducible storm-track table from the repository's
per-instance metadata CSV files. It is intentionally independent of ERA5,
GLDAS, TRMM, and NASA POWER ingestion.

The existing project audit recorded 322 metadata instances, 62,401 metadata
rows, and 322 corresponding image folders. The per-instance schema includes
`year`, `month`, `day`, `hour`, `lat`, `lng`, `grade`, `pressure`,
`wind`, and optional wind-radius/image metadata. Re-run the audit locally
before treating these counts as the current local inventory.

## Run

From the repository root:

```bash
python scripts/process_ibtracs_tracks.py
```

The default inputs are:

- `data/ibtracs/metadata/`
- `reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv`
  (optional; if absent, track processing continues without grid proximity)

To skip grid proximity explicitly:

```bash
python scripts/process_ibtracs_tracks.py --no-grid-proximity
```

To select paths:

```bash
python scripts/process_ibtracs_tracks.py \
  --metadata-dir data/ibtracs/metadata \
  --bus-locations reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv \
  --output-dir reports/ibtracs
```

## Outputs

The default output directory is `reports/ibtracs/`:

- `ibtracs_tracks.csv`: valid timestamp/coordinate records, sorted by storm and time.
- `ibtracs_rejected_records.csv`: source rows excluded from the track table, with a rejection reason.
- `ibtracs_storm_summary.csv`: per-storm observation range, coordinate bounds, duplicate count, and maximum translation speed.
- `ibtracs_track_audit.json`: aggregate counts, processing conventions, grid-proximity status, and per-storm summaries.

The source fields are retained. Standardized fields include UTC-interpreted timestamp,
latitude, longitude, source row number, duplicate timestamp flag, elapsed time,
segment distance, translation speed, and heading.

## Calculation and data policies

- Timestamps are constructed from `year/month/day/hour` and interpreted as UTC,
  consistent with the repository's existing IBTrACS quality audit. Confirm the
  provider's time convention from source documentation before formal publication.
- Longitudes in (180, 360] are converted to [-180, 0]. The original `lng` field
  remains in the output, and a flag records this conversion.
- Invalid timestamps and out-of-range/missing coordinates are written to the
  rejected-records file; they are not silently discarded.
- Duplicate timestamps are retained and flagged. Segment speed is left missing
  when elapsed time is zero or no previous observation exists.
- Translation speed is derived from successive valid positions using great-circle
  distance and actual elapsed time. It is reported in km/h.
- Heading is the initial bearing from the preceding valid observation, in degrees
  clockwise from true north. It is missing for the first observation and for
  zero-distance segments.
- No temporal interpolation, coordinate interpolation, or measurement imputation
  is performed.
- `wind` and `pressure` are retained as raw source values. Their units and
  agency-specific semantics must be verified before converting them or using
  them in a fragility model.

## Synthetic Minxiong grid proximity

If the synthetic 33-bus coordinate CSV is present, each storm observation is
associated with its nearest synthetic bus using great-circle distance. The
per-observation output records the nearest bus ID and distance in kilometres.
The storm summary records the minimum distance and time of closest approach.

This is a proximity descriptor, not a measured wind exposure, asset-failure
probability, or damage estimate. Bus coordinates are synthetic study samples,
not verified Taipower asset coordinates. It does not yet calculate exposure
duration within a selected radius, branch-corridor proximity, or a physical
wind field over the network.

## Next stages

1. Verify the upstream dataset identity, release/version, time convention, and
   units for wind, pressure, and wind-radius fields.
2. Validate the processed tracks against selected known storms and map tracks
   in the western North Pacific / Taiwan region.
3. Select and justify a study-area approach radius; calculate storm-to-grid
   approach windows without calling them measured damage.
4. Add a calibrated wind-field or wind-to-infrastructure fragility model before
   converting storm intensity into branch outage probabilities.
5. Feed explicitly defined contingency scenarios into LAST-Q. Keep topology
   feasibility distinct from electrical feasibility and AC power-flow validation.

This phase does not claim forecast capability, utility-grade asset exposure,
empirical failure probabilities, or quantum advantage.
