"""ONS Reservoirs tab: region EAR chart + zero-capacity REE filter."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = (ROOT / "ons" / "dashboard.py").read_text(encoding="utf-8")


def test_reservoirs_tab_has_region_ear_chart():
    assert "function renderReservoirRegionChart" in DASH
    assert "renderReservoirRegionChart(extra)" in DASH
    assert 'drawPanel("%","Hydro reservoirs by region"' in DASH
    assert 'order=["SIN","SE","S","NE","N"]' in DASH
    assert "function subColor" in DASH
    # Stable subsystem colors, not picker claimSlot hues.
    assert "colorFn:k=>subColor" in DASH


def test_ree_table_omits_zero_capacity_rows():
    assert "function reeHasCapacity" in DASH
    assert "r.cap!=null && r.cap>0" in DASH
    assert "all.filter(reeHasCapacity)" in DASH
    assert "zero-capacity REE" in DASH
    # Still builds the REE table; just filters empty-capacity rows.
    assert "function renderReeTable" in DASH


def test_draw_panel_accepts_label_and_color_overrides():
    assert "function drawPanel(unit,title,keys,W,opts)" in DASH
    assert "const colorFn=opts.colorFn" in DASH
    assert "const labelFn=opts.labelFn" in DASH
    assert "opts.directMax" in DASH


def test_wiki_documents_region_chart_and_ree_filter():
    wiki = (ROOT / "wiki-src" / "ons" / "Using-the-Dashboard.md").read_text(
        encoding="utf-8"
    )
    assert "line chart plots the same regional EAR%" in wiki
    assert "zero reported capacity" in wiki
