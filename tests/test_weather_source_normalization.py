from __future__ import annotations

import pandas as pd
import pytest

from scripts.normalize_weather_sources import normalize_era5, normalize_giovanni, normalize_nasa


def test_era5_normalizer_keeps_grid_coordinates_and_units(tmp_path):
    path = tmp_path / "era5.csv"
    pd.DataFrame({
        "valid_time": ["2026-11-12T00:00:00"],
        "latitude": [23.5], "longitude": [120.4],
        "t2m": [300.0], "unknown_measurement": [7.0],
    }).to_csv(path, index=False)
    rows = normalize_era5(path, "era5_sfc", {})
    assert len(rows) == 1
    assert rows[0]["variable"] == "t2m"
    assert rows[0]["unit"] == "K"
    assert rows[0]["time_basis"] == "UTC"
    assert rows[0]["spatial_scope"] == "point"
    assert rows[0]["latitude"] == 23.5


def test_era5_no_numeric_variables_reports_source_schema(tmp_path):
    path = tmp_path / "era5_wave.csv"
    pd.DataFrame({
        "valid_time": ["2026-11-12T00:00:00"],
        "latitude": [23.5], "longitude": [120.4],
        "unexpected_wave_field": ["not-numeric"],
    }).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Columns=.*unexpected_wave_field"):
        normalize_era5(path, "era5_wav", {})


def test_era5_unknown_variable_requires_explicit_unit(tmp_path):
    path = tmp_path / "era5.csv"
    pd.DataFrame({
        "valid_time": ["2026-11-12T00:00:00"],
        "latitude": [23.5], "longitude": [120.4],
        "custom_var": [1.0],
    }).to_csv(path, index=False)
    with pytest.raises(ValueError, match="no recognized variables"):
        normalize_era5(path, "era5_sfc", {})
    rows = normalize_era5(path, "era5_sfc", {"custom_var": "m s-1"})
    assert rows[0]["unit"] == "m s-1"


def test_giovanni_sources_preserve_regional_scope_and_utc(tmp_path):
    path = tmp_path / "gldas.csv"
    path.write_text(
        'Title:,"Area average precipitation"\n'
        'User Bounding Box:,"119.9,22.8,121,23.8"\n'
        'Data Bounding Box:,"120.125,22.875,120.875,23.625"\n'
        'Fill Value (Rainf):,-9999\n'
        'time,Rainf\n'
        '2026-11-12 00:00:00,0.0001\n',
        encoding="utf-8",
    )
    rows = normalize_giovanni(path, "GLDAS_NOAH025_3H")
    assert len(rows) == 1
    assert rows[0]["spatial_scope"] == "regional"
    assert rows[0]["time_basis"] == "UTC"
    assert rows[0]["unit"] == "kg m-2 s-1"


def test_nasa_requires_explicit_coordinates(tmp_path):
    path = tmp_path / "nasa.csv"
    path.write_text(
        "-BEGIN HEADER-\nLocation: 23.5, 120.4\n- Date(s): 01/01/2026\n"
        "Parameter(s):\nALLSKY_SFC_SW_DWN\n-END HEADER-\n"
        "YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\n2026,1,1,0,2.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="explicit --nasa-latitude"):
        normalize_nasa(path, latitude=None, longitude=None)
    rows = normalize_nasa(path, latitude=23.5, longitude=120.4)
    assert rows[0]["time_basis"] == "LST"
    assert rows[0]["spatial_scope"] == "point"
