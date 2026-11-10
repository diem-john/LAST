import pandas as pd
from forecasting.data.audit import audit_csv

def test_csv_audit_reports_columns_and_sample(tmp_path):
    path = tmp_path / "sample.csv"
    pd.DataFrame({"time": ["2020-01-01", "2020-01-02"], "rain": [1.0, None]}).to_csv(path, index=False)
    report = audit_csv(path)
    assert report["sample_rows_read"] == 2
    assert "time" in report["columns"]
    assert report["columns"]["rain"]["sample_null"] == 1
