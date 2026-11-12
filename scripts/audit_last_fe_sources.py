"""Generate schema-first audit reports for the checked-in LAST datasets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from forecasting.data.audit import audit_csv, audit_raster, audit_ibtracs_instances, write_audit_report
from forecasting.data.ingestion import load_area_averaged_precipitation, load_nasa_power
from forecasting.data.quality import (
    audit_frame_quality,
    audit_precipitation_frame,
    audit_ibtracs_quality,
    audit_raster_full,
    audit_raster_integrity,
    audit_raster_spatial_coverage,
)
from forecasting.data.physical_validation import audit_era5_physical_frame
from forecasting.data.raster_consistency import audit_raster_collection_consistency

ROOT = Path(__file__).resolve().parents[1]
CSV_SOURCES = {
    "era5_sfc": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-sfcnhk6q2bv.csv",
    "era5_wav": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-wavxnvtuiin.csv",
    "nasa_power": ROOT / "data/nasapower/nasapow.csv",
}
PRECIP_SOURCES = {
    "gldas_noah_3h": (ROOT / "data/imerg/g4.areaAvgTimeSeries.GLDAS_NOAH025_3H_2_0_Rainf_f_tavg.20100101-20261130.119E_22N_121E_23N.csv", "GLDAS_NOAH025_3H"),
    "trmm_3b42_v7": (ROOT / "data/imerg/g4.areaAvgTimeSeries.TRMM_3B42_7_precipitation.20100101-20261130.119E_22N_121E_23N.csv", "TRMM_3B42_V7"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/data_audit")
    parser.add_argument("--sample-rows", type=int, default=1000)
    parser.add_argument("--include-rasters", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"csv": {}, "ibtracs": {}, "ibtracs_quality": {}, "precipitation": {}, "precipitation_quality": {}, "rasters": {}, "errors": []}
    quality_dir = args.output_dir / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    for source_id, path in CSV_SOURCES.items():
        if source_id == "nasa_power":
            continue  # NASA POWER has a metadata block and a source-specific reader below.
        if not path.exists():
            summary["errors"].append({"source": source_id, "error": f"Missing file: {path}"})
            continue
        try:
            result = audit_csv(path, sample_rows=args.sample_rows)
            summary["csv"][source_id] = result
            write_audit_report(result, args.output_dir / f"{source_id}.json")
            full_frame = pd.read_csv(path, low_memory=False)
            quality = audit_frame_quality(
                full_frame, timestamp_column="valid_time", expected_frequency="1h",
                exclude_numeric=("latitude", "longitude"),
            )
            quality["source_id"] = source_id
            summary["csv"].setdefault("full_record_quality", {})[source_id] = quality
            if source_id == "era5_sfc":
                physical = audit_era5_physical_frame(full_frame)
                summary["era5_physical_screening"] = physical
                write_audit_report(physical, quality_dir / "era5_sfc_physical_screening.json")
            write_audit_report(quality, quality_dir / f"{source_id}_full_quality.json")
        except Exception as exc:
            summary["errors"].append({"source": source_id, "error": str(exc)})
    try:
        ibtracs = audit_ibtracs_instances(
            ROOT / "data/ibtracs/metadata",
            ROOT / "data/ibtracs/image",
        )
        summary["ibtracs"] = ibtracs
        write_audit_report(ibtracs, args.output_dir / "ibtracs_instances.json")
        ibtracs_quality = audit_ibtracs_quality(ROOT / "data/ibtracs/metadata")
        summary["ibtracs_quality"] = ibtracs_quality
        write_audit_report(ibtracs_quality, quality_dir / "ibtracs_quality.json")
    except Exception as exc:
        summary["errors"].append({"source": "ibtracs", "error": str(exc)})

    nasa_path = CSV_SOURCES["nasa_power"]
    if not nasa_path.exists():
        summary["errors"].append({"source": "nasa_power", "error": f"Missing file: {nasa_path}"})
    else:
        try:
            frame, metadata = load_nasa_power(nasa_path)
            result = {
                "metadata": metadata,
                "columns": list(frame.columns),
                "sample": frame.head(args.sample_rows).astype(str).to_dict(orient="records")[:20],
            }
            summary["csv"]["nasa_power"] = result
            write_audit_report(result, args.output_dir / "nasa_power.json")
            nasa_quality = audit_frame_quality(
                frame, timestamp_column="timestamp_lst", expected_frequency="1h",
                exclude_numeric=("YEAR", "MO", "DY", "HR"), timestamp_timezone="NAIVE",
            )
            nasa_quality["source_id"] = "nasa_power"
            nasa_quality["time_convention"] = "LST; timezone-naive; not converted to UTC"
            summary["csv"].setdefault("full_record_quality", {})["nasa_power"] = nasa_quality
            write_audit_report(nasa_quality, quality_dir / "nasa_power_full_quality.json")
        except Exception as exc:
            summary["errors"].append({"source": "nasa_power", "error": str(exc)})

    for report_id, (path, canonical_source_id) in PRECIP_SOURCES.items():
        if not path.exists():
            summary["errors"].append({"source": report_id, "error": f"Missing file: {path}"})
            continue
        try:
            frame, metadata = load_area_averaged_precipitation(path, source_id=canonical_source_id)
            result = {"metadata": metadata, "columns": list(frame.columns), "sample": frame.head(args.sample_rows).astype(str).to_dict(orient="records")[:20]}
            summary["precipitation"][report_id] = result
            write_audit_report(result, args.output_dir / f"{report_id}.json")
            fill_value = pd.to_numeric(pd.Series([metadata.get("fill_value")]), errors="coerce").iloc[0]
            quality = audit_precipitation_frame(
                frame, source_id=canonical_source_id,
                fill_value=float(fill_value) if pd.notna(fill_value) else None,
            )
            quality["source_variable"] = metadata.get("source_variable")
            quality["requested_bbox"] = metadata.get("requested_bbox")
            quality["data_bbox"] = metadata.get("data_bbox")
            summary["precipitation_quality"][report_id] = quality
            write_audit_report(quality, quality_dir / f"{report_id}_quality.json")
        except Exception as exc:
            summary["errors"].append({"source": report_id, "error": str(exc)})
    if args.include_rasters:
        raster_paths = sorted((ROOT / "data/globalflooddb").rglob("*.tif"))
        for path in raster_paths:
            try:
                result = audit_raster(path)
                key = path.parent.name
                summary["rasters"][key] = result
                write_audit_report(result, args.output_dir / f"{key}_raster.json")
                full_result = audit_raster_full(path)
                summary.setdefault("raster_full_quality", {})[key] = full_result
                write_audit_report(full_result, quality_dir / f"{key}_full_raster_quality.json")
                integrity = audit_raster_integrity(path)
                summary.setdefault("raster_integrity", {})[key] = integrity
                write_audit_report(integrity, quality_dir / f"{key}_raster_integrity.json")
                spatial_coverage = audit_raster_spatial_coverage(path)
                summary.setdefault("raster_spatial_coverage", {})[key] = {
                    "event_properties_status": spatial_coverage["event_properties_status"],
                    "band_summaries": spatial_coverage["band_summaries"],
                    "pairwise_finite_mask_overlap": spatial_coverage["pairwise_finite_mask_overlap"],
                    "overview_rows": spatial_coverage["spatial_overview"]["rows"],
                    "overview_columns": spatial_coverage["spatial_overview"]["columns"],
                }
                write_audit_report(
                    spatial_coverage,
                    quality_dir / f"{key}_raster_spatial_coverage.json",
                )
            except Exception as exc:
                summary["errors"].append({"source": str(path), "error": str(exc)})
        try:
            consistency = audit_raster_collection_consistency(raster_paths)
            summary["raster_collection_consistency"] = {
                "raster_count": consistency["raster_count"],
                "exact_duplicate_pairs": consistency["exact_duplicate_pairs"],
                "pairwise_comparison_count": len(consistency["pairwise_comparisons"]),
            }
            write_audit_report(
                consistency,
                quality_dir / "raster_collection_consistency.json",
            )
        except Exception as exc:
            summary["errors"].append({"source": "raster_collection_consistency", "error": str(exc)})
    write_audit_report(summary, args.output_dir / "summary.json")
    print(json.dumps({"output_dir": str(args.output_dir), "csv_audited": len([key for key in summary["csv"] if key != "full_record_quality"]), "ibtracs_instances_audited": summary.get("ibtracs", {}).get("metadata_instance_count", 0), "precipitation_audited": len(summary["precipitation"]), "rasters_audited": len(summary["rasters"]), "errors": summary["errors"]}, indent=2))

if __name__ == "__main__":
    main()
