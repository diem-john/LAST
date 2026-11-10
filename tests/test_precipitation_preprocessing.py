import pandas as pd
import pytest
from forecasting.data.preprocessing import normalize_precipitation, validate_time_series

def test_gldas_conversion():
    frame = pd.DataFrame({"timestamp": ["2010-01-01 00:00:00"], "value": [0.001]})
    result = normalize_precipitation(frame, source_id="GLDAS_NOAH025_3H")
    assert result.loc[0, "precipitation_rate_mm_hr"] == pytest.approx(3.6)
    assert result.loc[0, "precipitation_3h_mm"] == pytest.approx(10.8)

def test_trmm_fill_value_becomes_missing():
    frame = pd.DataFrame({"timestamp": ["2010-01-01 00:00:00"], "value": [-9999.9]})
    result = normalize_precipitation(frame, source_id="TRMM_3B42_V7", fill_value=-9999.9)
    assert pd.isna(result.loc[0, "precipitation_rate_mm_hr"])
    assert bool(result.loc[0, "is_missing"])

def test_trmm_accumulation():
    frame = pd.DataFrame({"value": [2.5]})
    result = normalize_precipitation(frame, source_id="TRMM_3B42_V7")
    assert result.loc[0, "precipitation_3h_mm"] == pytest.approx(7.5)

def test_time_series_reports_duplicates_and_gaps():
    frame = pd.DataFrame({"timestamp": ["2010-01-01T00:00:00Z", "2010-01-01T03:00:00Z", "2010-01-01T03:00:00Z", "2010-01-01T09:00:00Z"]})
    report = validate_time_series(frame)
    assert report["duplicate_timestamps"] == 1
    assert report["nonconforming_intervals"] == 1

def test_unknown_source_is_rejected():
    with pytest.raises(ValueError):
        normalize_precipitation(pd.DataFrame({"value": [1.0]}), source_id="UNKNOWN")
