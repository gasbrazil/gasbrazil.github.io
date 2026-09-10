from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pld"))
import pld_pipeline as pp  # noqa: E402

sys.path.insert(0, str(ROOT / "flows"))
import flows_pipeline as fp  # noqa: E402


def test_pld_read_csv_decimal_and_submarket(tmp_path):
    path = tmp_path / "pld_media_diaria_2026.csv"
    path.write_text(
        "MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA\n"
        "202609;SUDESTE;06/09/2026;118,04\n"
        "202609;SUL;06/09/2026;110.50\n",
        encoding="latin-1",
    )
    df = pp._read_csv(path)
    se = df[df["submarket"] == "SE"].iloc[0]
    assert abs(float(se["pld"]) - 118.04) < 1e-6
    sul = df[df["submarket"] == "S"].iloc[0]
    assert abs(float(sul["pld"]) - 110.50) < 1e-6


def test_flows_clean_numeric():
    assert fp._clean_numeric("1.234,56") == 1234.56
    assert fp._clean_numeric("- 10,5") == -10.5
    assert fp._clean_numeric("-") is None
    assert fp._clean_numeric("") is None
    assert fp._clean_numeric("12.5") == 12.5


def test_flows_staleness_days_accepts_naive_and_aware():
    # Regression: tz-naive parquet dates vs tz-aware "now" raised TypeError.
    today = pd.Timestamp.now("UTC").normalize()
    assert fp._staleness_days(today.tz_localize(None)) == 0
    assert fp._staleness_days(today) == 0
    assert fp._staleness_days((today - pd.Timedelta(days=10)).tz_localize(None)) == 10
    assert fp._staleness_days(today.strftime("%Y-%m-%d")) == 0
