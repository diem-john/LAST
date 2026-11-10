"""Data ingestion and preprocessing for LAST-FE."""
from .ingestion import load_area_averaged_precipitation, load_generic_csv
from .preprocessing import normalize_precipitation
__all__ = ["load_area_averaged_precipitation", "load_generic_csv", "normalize_precipitation"]
