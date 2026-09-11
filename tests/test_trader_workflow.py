"""Trader-workflow UI contracts: hub hint gone, Desk/POC/Contracts defaults."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import transforms as xf

ROOT = Path(__file__).resolve().parents[1]


def _load_desk_payload():
    path = ROOT / "desk" / "build_payload.py"
    spec = importlib.util.spec_from_file_location("desk_build_payload", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_home_template_has_no_hub_hint():
    src = (ROOT / "build_home.py").read_text(encoding="utf-8")
    assert "hub-hint" not in src
    assert "Every card below opens a live dashboard" not in src
    assert 'data-i18n="hubHint"' not in src


def test_desk_kpis_are_links_with_santos_and_unit_toggle():
    src = (ROOT / "desk" / "dashboard.py").read_text(encoding="utf-8")
    assert 'return \'<a class="kpi-cell" href="' in src
    assert 't("deskKpiSantos")' in src
    assert 'href="../contratos/">Contracts</a>' in src
    assert 'href="../supply/">Supply</a>' in src
    assert 'data-unit="mmbtu"' in src
    assert 'let sparkUnit = "mmbtu"' in src
    assert '"000 m³"' in src
    assert '"mil m³"' not in src


def test_poc_hides_no_trade_and_exposes_gus_chip():
    src = (ROOT / "poc" / "dashboard.py").read_text(encoding="utf-8")
    assert 'let showNoTrade = false' in src
    assert '{ key: "gus", label: "GUS"' in src
    assert 'r["Trade Timing"] === "No Trade"' in src
    assert 'notrade: showNoTrade ? "1" : null' in src
    assert "showNoTrade = false" in src


def test_contracts_default_hidden_cols_v3():
    src = (ROOT / "contratos" / "dashboard.py").read_text(encoding="utf-8")
    assert 'COL_PREFS_KEY = "pocContratosDashboard.columnPrefs.v3"' in src
    start = src.index("const DEFAULT_HIDDEN_COLS")
    end = src.index("const COL_PREFS_KEY")
    block = src[start:end]
    for col in (
        "Contract Number",
        "Contract Category",
        "Product Type",
        "Quality",
        "Tariff Multiplier",
        "Transporter Ownership %",
        "Amendment",
    ):
        assert f'"{col}"' in block


def test_util_table_attaches_capacity_weighted_tariff_m3():
    desk = _load_desk_payload()
    contratos = pd.DataFrame(
        {
            "Transporter (TSO)": ["TAG", "TAG", "NTS"],
            "Status": ["Active", "Active", "Active"],
            "Contracted Capacity (000 m3/d)": [100.0, 300.0, 50.0],
            "Allocated Tariff (R$/MMBtu)": [20.0, 40.0, 10.0],
        }
    )
    flows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-09-01"] * 3),
            "tso": ["TAG", "NTS", "TAG"],
            "variable": ["Actual Volume (thousand m3)"] * 3,
            "value": [10.0, 5.0, 20.0],
            "source": ["anp"] * 3,
        }
    )
    out = desk._util_table(contratos, flows)
    by_tso = {r["tso"]: r for r in out["rows"]}
    assert by_tso["TAG"]["tariffM3"] == xf.brl_per_m3(35.0, 3)
    assert by_tso["NTS"]["tariffM3"] == xf.brl_per_m3(10.0, 3)


def test_util_table_omits_tariff_when_column_missing():
    desk = _load_desk_payload()
    contratos = pd.DataFrame(
        {
            "Transporter (TSO)": ["NTS"],
            "Status": ["Active"],
            "Contracted Capacity (000 m3/d)": [10.0],
        }
    )
    flows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-09-01"]),
            "tso": ["NTS"],
            "variable": ["Actual Volume (thousand m3)"],
            "value": [4.0],
            "source": ["anp"],
        }
    )
    out = desk._util_table(contratos, flows)
    assert out["rows"][0]["tariffM3"] is None
