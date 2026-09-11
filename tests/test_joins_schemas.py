from __future__ import annotations

import pandas as pd
import pytest

import joins
import schemas


def test_join_pld_cmo_keeps_null_entity_rows():
    pld = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01", "2026-09-01"]),
        "submarket": ["SE", "S"],
        "pld": [100.0, 90.0],
    })
    ons = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01", "2026-09-01", "2026-09-01"]),
        "subsystem": ["SE", "S", "SE"],
        "series": ["cmo", "cmo", "cmo"],
        "value": [80.0, 70.0, 999.0],
        "entity": [None, None, "UTE Foo"],
    })
    out = joins.join_pld_cmo(pld, ons)
    assert len(out) == 2
    se = out[out["submarket"] == "SE"].iloc[0]
    assert se["cmo"] == 80.0
    assert se["spread_pld_minus_cmo"] == 20.0


def test_utilization_null_when_capacity_zero():
    contratos = pd.DataFrame({
        "Transporter (TSO)": ["NTS"],
        "Status": ["Active"],
        "Contracted Capacity (000 m3/d)": [0.0],
    })
    flows = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01"]),
        "tso": ["NTS"],
        "variable": ["Actual Volume (thousand m3)"],
        "value": [10.0],
        "source": ["anp"],
    })
    out = joins.join_capacity_vs_flows(contratos, flows)
    assert len(out) == 1
    assert pd.isna(out.loc[0, "utilization"])


def test_schema_rejects_bad_submarket():
    df = pd.DataFrame({"date": ["2026-09-01"], "submarket": ["XX"], "pld": [1.0]})
    with pytest.raises(ValueError, match="unexpected submarket"):
        schemas.validate_pld_daily(df)


def test_schema_rejects_non_numeric_pld():
    df = pd.DataFrame({"date": ["2026-09-01"], "submarket": ["SE"], "pld": ["nope"]})
    with pytest.raises(ValueError, match="non-numeric"):
        schemas.validate_pld_daily(df)


def test_schema_rejects_hourly_hour_out_of_range():
    df = pd.DataFrame({
        "date": ["2026-09-01"],
        "hour": [25],
        "submarket": ["SE"],
        "pld": [1.0],
    })
    with pytest.raises(ValueError, match="0–23"):
        schemas.validate_pld_hourly(df)
