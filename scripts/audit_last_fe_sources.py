"""Generate schema-first audit reports for the checked-in LAST datasets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from forecasting.data.audit import audit_csv, audit_raster, write_audit_report
from forecasting.data.ingestion import load_area_averaged_precipitation

ROOT = Path(__file__).resolve().parents[1]
CSV_SOURCES = {
    "era5_sfc": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-sfcnhk6q2bv.csv",
    "era5_wav": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-wavxnvtuiin.csv",
    "ibtracs": ROOT / "data/ibtracs/typhoon_data.csv",
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
    summary = {"csv": {}, "precipitation": {}, "rasters": {}, "errors": []}
    for source_id, path in CSV_SOURCES.items():
        if not path.exists():
            summary["errors"].append({"source": source_id, "error": f"Missing file: {path}"})
            continue
        try:
            result = audit_csv(path, sample_rows=args.sample_rows)
            summary["csv"][source_id] = result
            write_audit_report(result, args.output_dir / f"{source_id}.json")
        except Exception as exc:
            summary["errors"].append({"source": source_id, "error": str(exc)})
    for report_id, (path, canonical_source_id) in PRECIP_SOURCES.items():
        if not path.exists():
            summary["errors"].append({"source": report_id, "error": f"Missing file: {path}"})
            continue
        try:
            frame, metadata = load_area_averaged_precipitation(path, source_id=canonical_source_id)
            result = {"metadata": metadata, "columns": list(frame.columns), "sample": frame.head(args.sample_rows).astype(str).to_dict(orient="records")[:20]}
            summary["precipitation"][report_id] = result
            write_audit_report(result, args.output_dir / f"{report_id}.json")
        except Exception as exc:
            summary["errors"].append({"source": report_id, "error": str(exc)})
    if args.include_rasters:
        for path in sorted((ROOT / "data/globalflooddb").rglob("*.tif")):
            try:
                result = audit_raster(path)
                key = path.parent.name
                summary["rasters"][key] = result
                write_audit_report(result, args.output_dir / f"{key}_raster.json")
            except Exception as exc:
                summary["errors"].append({"source": str(path), "error": str(exc)})
    write_audit_report(summary, args.output_dir / "summary.json")
    print(json.dumps({"output_dir": str(args.output_dir), "csv_audited": len(summary["csv"]), "precipitation_audited": len(summary["precipitation"]), "rasters_audited": len(summary["rasters"]), "errors": summary["errors"]}, indent=2))

if __name__ == "__main__":
    main()
