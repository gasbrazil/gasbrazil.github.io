"""Tests for Pipeline Monitor dashboard (/monitor/), unified layout, and redirects."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "monitor"))


def test_monitor_dashboard_rendered():
    html_path = ROOT / "monitor" / "index.html"
    assert html_path.exists(), "monitor/index.html must exist"
    content = html_path.read_text(encoding="utf-8")

    # Brand and chrome
    assert "Pipeline Monitor" in content
    assert 'class="masthead"' in content
    assert 'id="theme-toggle"' in content
    assert 'id="lang-toggle"' in content
    assert 'class="flagbar"' in content
    assert 'class="wrap"' in content

    # Tabs and dual views
    assert 'class="monitor-tabbar"' in content
    assert 'id="monitor-tabs"' in content
    assert 'id="tab-btn-tag"' in content
    assert 'id="tab-btn-nts"' in content
    assert 'id="monitor-view-tag"' in content
    assert 'id="monitor-view-nts"' in content

    # Client-side tab switching
    assert "setMonitorTab" in content
    assert "gbWriteQuery" in content

    # Both subpages' charts and tables
    assert 'id="chart-lp"' in content
    assert 'id="linepack-chart"' in content
    assert 'id="telemetry-table"' in content
    assert 'id="lp-table"' in content

    # Teaser markers
    assert "home-page teaser marker, read by ../build_home.py:" in content
    assert "kpi_tag_lp:" in content
    assert "kpi_nts_lp:" in content

    # Payloads
    assert 'id="nts-payload"' in content
    assert "fetchMagoPayloadJson" in content

    # No unreplaced placeholders
    unreplaced = [m for m in re.findall(r"__[A-Z0-9_]+__", content) if m != "__GB_I18N_END__"]
    assert not unreplaced, f"Found unreplaced tokens: {unreplaced}"


def test_monitor_visual_consistency_typography():
    html_path = ROOT / "monitor" / "index.html"
    content = html_path.read_text(encoding="utf-8")

    # Refined font hierarchy and consistent card heights
    assert ".kpi .val { font-size: 1.15rem;" in content
    assert ".kpi .label { color: var(--muted); font-size: .7rem;" in content
    assert "min-height: 68px;" in content
    assert ".data-table th, .lp-table th" in content
    assert "font-size: 11px;" in content
    assert "font-variant-numeric: tabular-nums;" in content

    # Headers and tooltips
    assert "TAG Line Pack — Integrated Network" in content
    assert "NTS Line Pack — Transmission Network" in content
    assert 'class="infodot"' in content

    # Collapsed by default tolerance bands
    assert '<details class="panel-fold" id="faixas-panel">' in content
    assert '<details class="panel-fold" id="faixas-panel" open>' not in content

    # Standardized 260px chart boxes
    assert 'viewBox="0 0 1000 260"' in content
    assert ".chart-box.chart-lp-box { min-height: 260px; height: 260px; }" in content


def test_mago_and_nts_redirects():
    mago_html = (ROOT / "mago" / "index.html").read_text(encoding="utf-8")
    assert 'http-equiv="refresh"' in mago_html
    assert 'content="0; url=../monitor/?tab=tag"' in mago_html
    assert 'location.replace(\'../monitor/?tab=tag\'' in mago_html
    assert 'Pipeline Monitor' in mago_html

    nts_html = (ROOT / "nts" / "index.html").read_text(encoding="utf-8")
    assert 'http-equiv="refresh"' in nts_html
    assert 'content="0; url=../monitor/?tab=nts"' in nts_html
    assert 'location.replace(\'../monitor/?tab=nts\'' in nts_html
    assert 'Pipeline Monitor' in nts_html


def test_home_hub_and_sitemap_include_monitor():
    home_html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'data-slug="monitor"' in home_html
    assert 'href="monitor/"' in home_html

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://gasbrazil.com/monitor/" in sitemap

    import publish_teasers as pt

    teasers = pt.collect()
    items = teasers.get("items", {})
    assert "monitor" in items
    assert "TAG" in items["monitor"]["kpiEn"] or "NTS" in items["monitor"]["kpiEn"]


def test_build_dashboard_execution(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("monitor_dashboard_mod", ROOT / "monitor" / "dashboard.py")
    mon_dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mon_dash)

    out = tmp_path / "index.html"
    res = mon_dash.build_dashboard(out)
    assert res.exists()
    text = res.read_text(encoding="utf-8")
    assert "Pipeline Monitor" in text
    assert 'id="monitor-view-tag"' in text
    assert 'id="monitor-view-nts"' in text


def test_monitor_national_grid_and_health_pulse():
    html_path = ROOT / "monitor" / "index.html"
    content = html_path.read_text(encoding="utf-8")

    # Health pulse elements in tabbar
    assert 'class="health-pulse-group"' in content
    assert 'id="health-tag-pill"' in content
    assert 'id="health-nts-pill"' in content
    assert 'id="health-tag-dot"' in content
    assert 'id="health-nts-dot"' in content
    assert "pulse-dot" in content

    # Symmetrical 4-card KPI row on both TAG and NTS
    assert 'id="tag-nat-lp-val"' in content
    assert 'id="tag-nat-pack-val"' in content
    assert 'id="nts-nat-lp-val"' in content
    assert 'id="nts-nat-pack-val"' in content
    assert 'data-i18n="gridKpiNationalPack"' in content
    assert 'data-i18n="gridKpiNetBalance"' in content

    # JavaScript dynamic updates
    assert "function updateTelemetryHealth()" in content
    assert "function updateNationalGridKpis()" in content
    assert "setInterval(updateTelemetryHealth, 60000)" in content

    # Bilingual i18n keys
    assert 'gridKpiNationalPack: "National Grid Pack"' in content
    assert 'gridKpiNationalPack: "Empacotamento Nacional"' in content
    assert 'gridKpiNetBalance: "Net System Balance"' in content
    assert 'gridKpiNetBalance: "Balanço Líquido do Sistema"' in content
    assert 'gridStatusPacking: "Grid Packing"' in content
    assert 'gridStatusPacking: "Sistema Empacotando"' in content

