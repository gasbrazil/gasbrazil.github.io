from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import schemas

from nts import dashboard, nts_client


def test_nts_client_parses_live_payload():
    mock_payload = {
        "tag": "NTS-ESTOQ",
        "unit": "m3",
        "range": "today",
        "from": "2026-09-21T00:00:00-03:00",
        "to": "2026-09-21T20:00:00-03:00",
        "count": 2,
        "points": [
            {"t": "2026-09-21T00:00:17-03:00", "v": 48326856},
            {"t": "2026-09-21T20:00:17-03:00", "v": 47522290},
        ],
        "stats": {
            "atual": 47522290,
            "min": 47444180,
            "max": 49421910,
            "media": 48621786.2,
            "delta": -804566,
            "delta_pct": -1.66,
            "taxa_m3h": -39442.7,
        },
    }

    with patch.object(nts_client, "_request_json", return_value=mock_payload):
        snap = nts_client.fetch_live()
        assert snap.tag == "NTS-ESTOQ"
        assert snap.unit == "m3"
        assert snap.range_name == "today"
        assert len(snap.points) == 2
        assert snap.points[0].value_m3 == 48326856.0
        assert snap.points[0].value_mm3 == 48.3269
        assert snap.stats.atual_m3 == 47522290.0
        assert snap.stats.taxa_m3h == -39442.7


def test_nts_client_rejects_invalid_preset():
    with pytest.raises(ValueError, match="Unknown preset"):
        nts_client.fetch_preset("invalid_preset")


def test_nts_schema_validation_accepts_valid_frame():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-21 12:00:00+00:00", "2026-09-21 13:00:00+00:00"]),
        "value_m3": [47000000.0, 47100000.0],
        "value_mm3": [47.0, 47.1],
        "rate_m3_h": [0.0, 100000.0],
        "observed_at": pd.to_datetime(["2026-09-21 13:05:00+00:00", "2026-09-21 13:05:00+00:00"]),
        "source": ["nts", "nts"],
    })
    schemas.validate_nts_ontime_series(df)


def test_nts_schema_validation_rejects_missing_column():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-21 12:00:00+00:00"]),
        "value_m3": [47000000.0],
    })
    with pytest.raises(ValueError, match="missing columns"):
        schemas.validate_nts_ontime_series(df)


def test_nts_schema_validation_rejects_non_numeric_values():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-21 12:00:00+00:00"]),
        "value_m3": ["invalid_numeric"],
        "value_mm3": [47.0],
        "rate_m3_h": [0.0],
        "observed_at": pd.to_datetime(["2026-09-21 13:00:00+00:00"]),
        "source": ["nts"],
    })
    with pytest.raises(ValueError, match="non-numeric"):
        schemas.validate_nts_ontime_series(df)


def test_nts_dashboard_generation(tmp_path: Path):
    mock_pq = tmp_path / "mock.parquet"
    base_time = pd.Timestamp.now(tz="UTC").floor("h")
    timestamps = [base_time - pd.Timedelta(hours=i) for i in range(48, -1, -1)]
    values_m3 = [47_000_000.0 + (i % 7) * 100_000.0 for i in range(len(timestamps))]
    df = pd.DataFrame({
        "timestamp": timestamps,
        "value_m3": values_m3,
        "value_mm3": [v / 1_000_000.0 for v in values_m3],
        "rate_m3_h": [15_000.0 if i % 2 == 0 else -10_000.0 for i in range(len(timestamps))],
        "observed_at": [ts + pd.Timedelta(minutes=5) for ts in timestamps],
        "source": ["nts"] * len(timestamps),
    })
    df.to_parquet(mock_pq)

    out_html = tmp_path / "index.html"
    res = dashboard.build_dashboard(out_path=out_html, parquet_path=mock_pq)
    assert res.exists()
    content = res.read_text(encoding="utf-8")

    # Critical structure checks
    assert "<!doctype html>" in content.lower()
    assert "<html" in content
    assert "NTS OnTime" in content
    assert 'class="masthead"' in content
    assert "header.dash-head" in content
    assert 'id="theme-toggle"' in content
    assert 'id="lang-toggle"' in content
    assert "GasBrazil.com shared design tokens" in content
    assert 'class="wrap"' in content
    assert 'id="linepack-chart"' in content
    assert 'id="telemetry-table"' in content
    assert 'id="kpi-cur-mm3"' in content
    assert 'id="nts-payload"' in content
    assert "generated:" in content
    assert "kpi_linepack:" in content
    assert "7d Avg:" in content
    assert "avg_7d" in content

    # Ensure no unreplaced template placeholders
    import re

    unreplaced = [m for m in re.findall(r"__[A-Z0-9_]+__", content) if m != "__GB_I18N_END__"]
    assert not unreplaced, f"Found unreplaced tokens: {unreplaced}"
