"""
Builds the Desk dashboard (cross-product snapshot + spark calculator).

Usage: python dashboard.py [output_path]  (default: index.html)

Assembles a lean payload from lake/sibling parquet when present; missing
sources yield empty charts with short notes. Publishes payload.json.gz via
data_kit.write_and_publish_artifact("desk", ...).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402
from build_payload import build_payload  # noqa: E402

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "index.html"

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Desk — GasBrazil.com</title>
<meta name="description" content="Cross-product Brazil gas and power desk: PLD, CMO, CVU, GUS, ANP, flows, spark.">
<link rel="canonical" href="https://gasbrazil.com/desk/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_pld_se: __KPI_PLD_SE__
     kpi_gen_gas: __KPI_GEN_GAS__
     data_through: __DATA_THROUGH__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; font-weight: 300; }
/* Single-row header: wordmark-menu · title … Wiki/About · PT · theme */
header.dash-head { display: flex; flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; width: auto; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 16px 0 0; }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }
.lede { font-size: 13px; color: var(--muted2); font-weight: 300; margin: 0 0 var(--gap); line-height: 1.45; max-width: 54em; }
.gap-note { font-size: 12px; color: var(--muted); margin: 0 0 var(--gap); font-weight: 200; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(108px, 1fr)); gap: 8px; margin-bottom: var(--gap); }
.kpi-cell { padding: 2px 0 6px; border-bottom: 1px solid var(--border); text-decoration: none; color: inherit; display: block; }
a.kpi-cell:hover { border-bottom-color: var(--border-strong); }
a.kpi-cell:hover .lbl { color: var(--text); }
.kpi-cell .lbl { font-size: 11px; color: var(--muted2); font-weight: 400; }
.kpi-cell .val { font-size: 18px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 4px; letter-spacing: -.01em; }
.kpi-cell .unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.desk-grid { display: grid; grid-template-columns: 1.35fr 1fr; gap: var(--gap); margin-bottom: var(--gap); align-items: start; }
@media (max-width: 900px) { .desk-grid { grid-template-columns: 1fr; } }
.panel { background: transparent; border: none; padding: 0; margin: 0 0 var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; display: flex; align-items: baseline; gap: 8px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; max-width: 52em; }
.infodot { display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 14px; border-radius: 50%; border: 1px solid var(--border-strong); font-size: 10px; color: var(--muted2); cursor: help; font-weight: 400; flex: none; }
.infodot:hover { background: var(--accent-soft); color: var(--text); }
.series-picker { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.compare-tools { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 10px; }
.sm-pick { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted2); font-weight: 400; }
.sm-pick select { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 4px 8px; color: var(--text); font: 400 12.5px var(--font); }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.desk-tabbar { display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; margin: 0 0 var(--gap); border-bottom: 1px solid var(--border); padding-bottom: 0; flex-wrap: wrap; }
.desk-tab-actions { display: flex; align-items: center; gap: 8px; padding-bottom: 6px; }
.desk-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.desk-tabs button { border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted2); font: 400 13px var(--font); padding: 8px 14px 10px; cursor: pointer; border-radius: 5px 5px 0 0; }
.desk-tabs button[aria-pressed="true"] { color: var(--text); background: var(--panel); border-bottom-color: var(--accent); }
.desk-tabs button:hover { background: var(--accent-soft); }
.desk-tabs button[aria-pressed="true"]:hover { background: var(--panel-grad-hover, var(--panel)); }
body.desk-analysis-active footer { margin-top: 12px; }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
.analysis-workspace { margin: 0 0 var(--gap); width: 100%; }
.analysis-workspace-inner {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: calc(100vh - 168px);
  min-height: 480px;
  max-height: calc(100vh - 168px);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg);
  position: relative;
}
.analysis-sidebar {
  width: var(--desk-sidebar-w, 290px);
  min-width: 200px;
  max-width: 600px;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border-right: 0;
  background: var(--panel);
  overflow: hidden;
}
.analysis-sidebar-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--border);
}
.analysis-sidebar-title { font-size: 13px; font-weight: 400; margin: 0; }
.analysis-pick-count { font-size: 11px; color: var(--muted2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.analysis-sidebar-tools {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.analysis-sidebar-tools .sm-pick { flex: 1 1 auto; min-width: 120px; }
.analysis-filter {
  flex: 0 0 auto;
  box-sizing: border-box;
  width: calc(100% - 24px);
  margin: 8px 12px;
  padding: 7px 10px;
  font: 400 12.5px var(--font);
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
}
.analysis-filter::placeholder { color: var(--muted); }
.analysis-catalog {
  flex: 1 1 0;
  min-height: 0;
  height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 8px 12px;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}
.analysis-catalog::-webkit-scrollbar {
  width: 6px;
}
.analysis-catalog::-webkit-scrollbar-track {
  background: transparent;
}
.analysis-catalog::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 3px;
}
.analysis-catalog::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}
.analysis-resizer {
  width: 9px;
  margin: 0 -4px;
  flex: 0 0 9px;
  position: relative;
  z-index: 5;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  background: transparent;
}
.analysis-resizer::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 4px;
  width: 1px;
  background: var(--border);
  transition: background 0.15s ease, width 0.15s ease, left 0.15s ease;
}
.analysis-resizer:hover::before,
.analysis-resizer:focus-visible::before,
.analysis-resizer.is-dragging::before {
  background: var(--accent);
  left: 3px;
  width: 3px;
}
.analysis-resizer:focus-visible {
  outline: none;
}
.analysis-resizer-handle {
  width: 3px;
  height: 28px;
  border-radius: 2px;
  background: var(--border-strong);
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease;
  pointer-events: none;
  position: relative;
  z-index: 1;
}
.analysis-resizer:hover .analysis-resizer-handle,
.analysis-resizer.is-dragging .analysis-resizer-handle {
  opacity: 1;
  background: var(--accent);
}
body.is-resizing {
  cursor: col-resize !important;
  user-select: none !important;
  -webkit-user-select: none !important;
}
body.is-resizing iframe,
body.is-resizing svg {
  pointer-events: none;
}
.analysis-group { margin: 0 0 4px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); overflow: hidden; }
.analysis-group[open] { border-color: var(--border-strong); }
.analysis-group summary {
  list-style: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted2);
  font-weight: 400;
  user-select: none;
}
.analysis-group summary::-webkit-details-marker { display: none; }
.analysis-group summary:hover { background: var(--accent-soft); color: var(--text); }
.analysis-group-meta { font-size: 10px; color: var(--muted); text-transform: none; letter-spacing: 0; font-weight: 300; }
.analysis-group-actions { display: inline-flex; gap: 6px; margin-left: auto; }
.analysis-group-actions button {
  border: 0;
  background: none;
  padding: 0 2px;
  font-size: 10px;
  color: var(--accent);
  cursor: pointer;
  font-family: var(--font);
  text-transform: none;
  letter-spacing: 0;
}
.analysis-group-actions button:hover { text-decoration: underline; }
.analysis-series-list { padding: 2px 4px 6px; }
.analysis-series-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.35;
  color: var(--text);
}
.analysis-series-row:hover { background: var(--accent-soft); }
.analysis-series-row.is-on { background: var(--accent-soft); }
.analysis-series-row input { margin: 2px 0 0; flex: none; accent-color: var(--accent); cursor: pointer; }
.analysis-series-row .sw { width: 8px; height: 8px; border-radius: 2px; flex: none; margin-top: 4px; background: var(--border-strong); }
.analysis-series-row .lbl { flex: 1; min-width: 0; }
.analysis-series-row .unit { display: block; font-size: 10px; color: var(--muted); font-weight: 300; margin-top: 1px; }
.analysis-stage {
  flex: 1 1 0;
  min-width: 0;
  width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.analysis-stage-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px 16px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
.analysis-stage-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px 14px; width: 100%; }
.analysis-axis-hint { font-size: 11px; color: var(--muted); font-weight: 300; margin-right: auto; }
.analysis-series-row .axis-pick {
  flex: none;
  margin-left: auto;
  font: 400 10px var(--font);
  color: var(--muted2);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 4px;
  max-width: 72px;
}
.analysis-series-row:not(.is-on) .axis-pick { display: none; }
.analysis-stage[data-pane="split"] .analysis-chart-panel { flex: 1 1 55%; }
.analysis-stage[data-pane="split"] .analysis-table-panel { flex: 1 1 45%; }
.analysis-stage[data-pane="chart"] .analysis-table-panel { display: none !important; }
.analysis-stage[data-pane="chart"] .analysis-chart-panel { flex: 1 1 100%; min-height: 280px; }
.analysis-stage[data-pane="table"] .analysis-chart-panel { display: none !important; }
.analysis-stage[data-pane="table"] .analysis-table-panel { flex: 1 1 100%; border-top: 0; }
.analysis-chart-panel .chart-legend-dual { font-size: 10px; color: var(--muted); margin-top: 4px; }
.analysis-pane-toggle { display: inline-flex; border: 1px solid var(--border-strong); border-radius: 6px; overflow: hidden; }
.analysis-pane-toggle button {
  border: 0;
  background: var(--bg);
  color: var(--muted2);
  font: 400 11px var(--font);
  padding: 5px 12px;
  cursor: pointer;
}
.analysis-pane-toggle button + button { border-left: 1px solid var(--border); }
.analysis-pane-toggle button[aria-pressed="true"] { background: var(--accent-soft); color: var(--text); }
.analysis-chart-panel {
  flex: 1 1 52%;
  min-height: 200px;
  width: 100%;
  padding: 8px 12px 4px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.analysis-chart-panel .chart-host { flex: 1 1 auto; min-height: 180px; width: 100%; }
.analysis-table-panel {
  flex: 1 1 48%;
  min-height: 140px;
  width: 100%;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
  overflow: hidden;
}
.analysis-table-panel .table-wrap {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  width: 100%;
  border: 0;
  overflow: auto;
}
.analysis-table-panel[data-hidden="true"],
.analysis-chart-panel[data-hidden="true"] { display: none; }
.btn-clear { font-size: 12px; color: var(--muted2); background: var(--bg); border: 1px solid var(--border-strong); border-radius: 5px; padding: 4px 10px; cursor: pointer; font-family: var(--font); font-weight: 400; white-space: nowrap; }
.btn-clear:hover { background: var(--accent-soft); color: var(--text); }
@media (max-width: 960px) {
  .analysis-workspace-inner {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 168px);
    max-height: none;
  }
  .analysis-sidebar {
    width: 100% !important;
    max-width: none;
    min-width: 0;
    height: 38vh;
    max-height: 38vh;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .analysis-resizer {
    display: none;
  }
  .analysis-stage {
    min-height: 400px;
    height: auto;
  }
}
@media (max-width: 720px) {
  .sources, .series-picker { flex-direction: column; align-items: stretch; }
}
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
/* Chart tooltip (.tt) styles live in shared/theme.css */
.spark-form { display: flex; flex-direction: column; gap: 12px; margin-bottom: 14px; }
.spark-field { display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: var(--muted2); font-weight: 400; }
.spark-field-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 22px; }
.spark-field select { width: 100%; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 7px 10px; color: var(--text); font-size: 13px; font-family: var(--font); font-weight: 400; }
.spark-gas-readout { font-size: 15px; font-weight: 500; color: var(--text); font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
.spark-gas-readout .hint { font-size: 11px; font-weight: 400; color: var(--muted); margin-left: 6px; }
.spark-unit { display: inline-flex; }
.spark-unit button { background: var(--panel); border: 1px solid var(--border); padding: 1px 7px; font-size: 10px; color: var(--muted2); cursor: pointer; font-family: var(--font); font-weight: 400; line-height: 1.4; }
.spark-unit button + button { border-left: 0; }
.spark-unit button:first-child { border-radius: 4px 0 0 4px; }
.spark-unit button:last-child { border-radius: 0 4px 4px 0; }
.spark-unit button.active { color: var(--text); border-color: var(--border-strong); background: var(--accent-soft); }
.spark-out { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
@media (max-width: 520px) { .spark-out { grid-template-columns: 1fr; } }
.spark-metric .lbl { font-size: 11px; color: var(--muted2); }
.spark-metric .val { font-size: 20px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 2px; letter-spacing: -.01em; }
.spark-metric .unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.spark-metric.pos .val { color: var(--accent); }
.spark-metric.neg .val { color: var(--muted2); }
.table-wrap { overflow: auto; max-height: 40vh; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
table.util { width: 100%; font-size: var(--table-font-size); }
table.util th, table.util td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); font-weight: 300; }
table.util th { color: var(--muted2); font-weight: 400; background: var(--panel); }
th .th-label { cursor: pointer; }
table.util .num { text-align: right; font-variant-numeric: tabular-nums; }
table.util tbody tr:hover { background: var(--accent-soft); }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
@media (max-width: 720px) {
  .sources, .series-picker { flex-direction: column; align-items: stretch; }
}
.chart-host svg { display: block; overflow: hidden; width: 100%; height: auto; max-width: 100%; }
__SHARED_TYPO_WEIGHT_CSS__
</style>
</head>
<body>
<a class="skip-link" href="#main-chart" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  __SHARED_MASTHEAD__
  <div class="header-right">
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>

<div class="desk-tabbar">
  <div class="desk-tabs" id="desk-tabs" role="tablist" aria-label="Desk views"></div>
  <div class="desk-tab-actions">__SHARED_SHARE_BUTTON__</div>
</div>

<div id="desk-view-overview">
<div class="kpi-row" id="kpi-row"></div>
<div class="desk-grid">
  <section class="panel" aria-labelledby="compare-title">
    <p class="panel-title" id="compare-title" data-i18n="deskCompareTitle">PLD · CMO · CVU</p>
    <div class="compare-tools">
      <label class="sm-pick"><span data-i18n="deskSubmarket">Submarket</span>
        <select id="compare-sm">
          <option value="SE">SE</option>
          <option value="S">S</option>
          <option value="NE">NE</option>
          <option value="N">N</option>
        </select>
      </label>
    </div>
    <div class="series-picker" id="picker-compare"></div>
    <div class="chart-host" id="main-chart"></div>
  </section>
  <section class="panel" aria-labelledby="spark-title">
    <p class="panel-title" id="spark-title">
      <span data-i18n="deskSparkTitle">Spark</span>
      <span class="infodot" id="spark-info" title="" aria-label="Formula">i</span>
    </p>
    <div class="spark-form">
      <div class="spark-field">
        <div class="spark-field-head">
          <span data-i18n="deskGasPrice">Gas price</span>
          <span class="spark-unit" id="spark-unit" role="group" aria-label="Unit">
            <button type="button" data-unit="m3">R$/m³</button>
            <button type="button" data-unit="mmbtu">R$/MMBtu</button>
          </span>
        </div>
        <select id="spark-gas-preset" aria-describedby="spark-gas-readout"></select>
        <div class="spark-gas-readout" id="spark-gas-readout" aria-live="polite"></div>
      </div>
      <label class="spark-field"><span data-i18n="deskHeatRate">Heat rate</span> (kcal/kWh)
        <select id="spark-hr-preset">
          <option value="ccgt" data-i18n="deskHrCcgt">CCGT 1800</option>
          <option value="ocgt" data-i18n="deskHrOcgt">OCGT 2500</option>
        </select>
      </label>
      <label class="spark-field"><span data-i18n="deskCvuBasis">CVU basis</span>
        <select id="spark-cvu-mode">
          <option value="implied" data-i18n="deskCvuImplied">Implied from gas + heat rate</option>
          <option value="ons" data-i18n="deskCvuOns">Latest ONS CVU (submarket)</option>
        </select>
      </label>
    </div>
    <div class="spark-out">
      <div class="spark-metric"><div class="lbl" data-i18n="deskImpliedCvu">Implied CVU</div><div class="val" id="spark-implied">—</div><div class="unit">R$/MWh</div></div>
      <div class="spark-metric" id="spark-vs-pld-wrap"><div class="lbl" data-i18n="deskVsPld">vs PLD</div><div class="val" id="spark-vs-pld">—</div><div class="unit">R$/MWh</div></div>
      <div class="spark-metric" id="spark-vs-cmo-wrap"><div class="lbl" data-i18n="deskVsCmo">vs CMO</div><div class="val" id="spark-vs-cmo">—</div><div class="unit">R$/MWh</div></div>
    </div>
  </section>
</div>

<section class="panel" aria-labelledby="poc-anp-title">
  <p class="panel-title" id="poc-anp-title" data-i18n="deskPocAnpTitle">POC · ANP — monthly</p>
  <div class="series-picker" id="picker-poc-anp"></div>
  <div class="chart-host" id="poc-anp-chart"></div>
</section>

<section class="panel" aria-labelledby="util-title">
  <p class="panel-title" id="util-title" data-i18n="deskUtilTitle">Capacity vs flows</p>
  <div class="table-wrap">
    <table class="util" id="util-table">
      <thead><tr id="util-thead"></tr></thead>
      <tbody id="util-body"></tbody>
    </table>
  </div>
</section>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a href="../ons/">ONS</a>
  <a href="../pld/">CCEE</a>
  <a href="../precos/">ANP</a>
  <a href="../poc/">POC</a>
  <a href="../contratos/">Contracts</a>
  <a href="../flows/">Flows</a>
  <a href="../supply/">Supply</a>
</div>
</div>

<section class="analysis-workspace" id="desk-view-analysis" aria-labelledby="analysis-title" hidden>
  <h2 class="visually-hidden" id="analysis-title" data-i18n="deskAnalysisTitle">Analysis</h2>
  <div class="analysis-workspace-inner">
    <aside class="analysis-sidebar" aria-label="Series catalog">
      <div class="analysis-sidebar-head">
        <p class="analysis-sidebar-title" data-i18n="deskAnalysisCatalog">Series catalog</p>
        <span class="analysis-pick-count" id="analysis-pick-count" aria-live="polite"></span>
      </div>
      <div class="analysis-sidebar-tools">
        <label class="sm-pick"><span data-i18n="deskAnalysisRange">Range</span>
          <select id="analysis-range">
            <option value="90d">90 days</option>
            <option value="1y">1 year</option>
          </select>
        </label>
        <button type="button" class="btn-clear" id="analysis-clear" data-i18n="deskAnalysisClear">Clear all</button>
      </div>
      <input type="search" class="analysis-filter" id="analysis-filter" autocomplete="off"
        data-i18n-placeholder="deskAnalysisFilterPh" placeholder="Filter series…">
      <div class="analysis-catalog" id="picker-analysis"></div>
    </aside>
    <div class="analysis-resizer" id="analysis-resizer" role="separator" aria-orientation="vertical"
      aria-label="Resize series catalog" tabindex="0" title="Drag to resize (double-click to reset)">
      <div class="analysis-resizer-handle"></div>
    </div>
    <div class="analysis-stage" id="analysis-stage" data-pane="split">
      <div class="analysis-stage-head">
        <div class="analysis-stage-toolbar">
          <span class="analysis-axis-hint" id="analysis-axis-hint" hidden></span>
          <div class="analysis-pane-toggle" role="group" aria-label="View">
          <button type="button" id="analysis-pane-split" aria-pressed="true" data-i18n="deskAnalysisPaneSplit">Split</button>
          <button type="button" id="analysis-pane-chart" aria-pressed="false" data-i18n="deskAnalysisPaneChart">Chart</button>
          <button type="button" id="analysis-pane-table" aria-pressed="false" data-i18n="deskAnalysisPaneTable">Table</button>
          </div>
        </div>
      </div>
      <div class="analysis-chart-panel" id="analysis-chart-panel">
        <div class="chart-host" id="analysis-chart"></div>
      </div>
      <div class="analysis-table-panel" id="analysis-table-panel">
        <div class="table-wrap">
          <table class="util" id="analysis-table">
            <thead><tr id="analysis-thead"></tr></thead>
            <tbody id="analysis-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="asof-strip asof-footer" id="asof-strip">
    <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
    <span class="asof-val" id="asof-refreshed">&mdash;</span>
    <span class="asof-label" data-i18n="dataThrough">Data through</span>
    <span class="asof-val" id="asof-through">&mdash;</span>
  </div>
  __SHARED_METHODOLOGY__
  &copy; <span id="year"></span> GasBrazil.com
  &middot; <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
  &middot; <a href="../about/" data-i18n="footerAbout">About</a>
</footer>
</div>
<div class="tt" id="chart-tt"></div>
<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";

__SHARED_JS_DECODE__
__SHARED_JS_ESCAPE_HTML__
__SHARED_JS_TABLE_SORT__
__SHARED_JS_CHART_PALETTE__
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__
__SHARED_SITE_LINKS_JS__
__SHARED_JS_QUERY_STATE__

GB_I18N.en.deskCompareTitle = "PLD · CMO · CVU";
GB_I18N.en.deskSubmarket = "Submarket";
GB_I18N.en.deskSparkTitle = "Spark";
GB_I18N.en.deskGasPrice = "Gas price";
GB_I18N.en.deskHeatRate = "Heat rate";
GB_I18N.en.deskHrCcgt = "CCGT 1800";
GB_I18N.en.deskHrOcgt = "OCGT 2500";
GB_I18N.en.deskCvuBasis = "CVU basis";
GB_I18N.en.deskCvuImplied = "Implied from gas + heat rate";
GB_I18N.en.deskCvuOns = "Latest ONS CVU (submarket)";
GB_I18N.en.deskSparkGasGus = "Last GUS trade (POC)";
GB_I18N.en.deskSparkGasPoc7d = "POC 7-day average";
GB_I18N.en.deskSparkGasSantos = "ANP Santos (monthly)";
GB_I18N.en.deskImpliedCvu = "Implied CVU";
GB_I18N.en.deskVsPld = "vs PLD";
GB_I18N.en.deskVsCmo = "vs CMO";
GB_I18N.en.deskPocAnpTitle = "POC · ANP — monthly";
GB_I18N.en.deskUtilTitle = "Capacity vs flows";
GB_I18N.en.deskUtilTso = "TSO";
GB_I18N.en.deskUtilCap = "Contracted";
GB_I18N.en.deskUtilReal = "Realized avg";
GB_I18N.en.deskUtilPct = "Utilization";
GB_I18N.en.deskUtilTariff = "Tariff";
GB_I18N.en.deskUtilGus = "GUS";
GB_I18N.en.deskEmptyChart = "No data";
GB_I18N.en.deskEmpty = "No data";
GB_I18N.en.deskPickSeries = "Select series";
GB_I18N.en.deskSeriesPld = "PLD";
GB_I18N.en.deskSeriesCmo = "CMO";
GB_I18N.en.deskSeriesCvu = "CVU gas med";
GB_I18N.en.deskSeriesPoc = "POC avg";
GB_I18N.en.deskSeriesAnpSantos = "ANP Santos";
GB_I18N.en.deskSeriesAnpNtSe = "ANP non-thermal SE";
GB_I18N.en.deskKpiGen = "Gas gen SIN";
GB_I18N.en.deskKpiPld = "PLD SE";
GB_I18N.en.deskKpiCmo = "CMO SE";
GB_I18N.en.deskKpiGus = "GUS last";
GB_I18N.en.deskKpiPoc = "POC 7d";
GB_I18N.en.deskKpiFlows = "Flows 7d";
GB_I18N.en.deskKpiSantos = "Santos";
GB_I18N.en.deskAnalysisTitle = "Analysis";
GB_I18N.en.deskAnalysisNote = "Compare any site-wide series on one timeline. Monthly values repeat across their calendar month; the chart is indexed to 100 at the start of the range.";
GB_I18N.en.deskAnalysisRange = "Range";
GB_I18N.en.deskAnalysisClear = "Clear all";
GB_I18N.en.deskTabOverview = "Overview";
GB_I18N.en.deskTabAnalysis = "Analysis";
GB_I18N.en.deskAnalysisCatalog = "Series catalog";
GB_I18N.en.deskAnalysisFilterPh = "Filter series…";
GB_I18N.en.deskAnalysisSelected = "{n} selected";
GB_I18N.en.deskAnalysisGroupAll = "All";
GB_I18N.en.deskAnalysisGroupNone = "None";
GB_I18N.en.deskAnalysisPaneSplit = "Split";
GB_I18N.en.deskAnalysisPaneChart = "Chart";
GB_I18N.en.deskAnalysisPaneTable = "Table";
GB_I18N.en.deskAnalysisAxisHint = "Multiple units — assign Y-axis per series (Auto uses left for the main unit).";
GB_I18N.en.deskAnalysisAxisAuto = "Auto";
GB_I18N.en.deskAnalysisAxisLeft = "Left";
GB_I18N.en.deskAnalysisAxisRight = "Right";

GB_I18N.pt.deskCompareTitle = "PLD · CMO · CVU";
GB_I18N.pt.deskSubmarket = "Submercado";
GB_I18N.pt.deskSparkTitle = "Spark";
GB_I18N.pt.deskGasPrice = "Preço do gás";
GB_I18N.pt.deskHeatRate = "Heat rate";
GB_I18N.pt.deskHrCcgt = "CCGT 1800";
GB_I18N.pt.deskHrOcgt = "OCGT 2500";
GB_I18N.pt.deskCvuBasis = "Base do CVU";
GB_I18N.pt.deskCvuImplied = "Implícito (gás + heat rate)";
GB_I18N.pt.deskCvuOns = "Último CVU ONS (submercado)";
GB_I18N.pt.deskSparkGasGus = "Último GUS (POC)";
GB_I18N.pt.deskSparkGasPoc7d = "Média POC 7 dias";
GB_I18N.pt.deskSparkGasSantos = "ANP Santos (mensal)";
GB_I18N.pt.deskImpliedCvu = "CVU implícito";
GB_I18N.pt.deskVsPld = "vs PLD";
GB_I18N.pt.deskVsCmo = "vs CMO";
GB_I18N.pt.deskPocAnpTitle = "POC · ANP — mensal";
GB_I18N.pt.deskUtilTitle = "Capacidade vs fluxos";
GB_I18N.pt.deskUtilTso = "TSO";
GB_I18N.pt.deskUtilCap = "Contratada";
GB_I18N.pt.deskUtilReal = "Realizado méd.";
GB_I18N.pt.deskUtilPct = "Utilização";
GB_I18N.pt.deskUtilTariff = "Tarifa";
GB_I18N.pt.deskUtilGus = "GUS";
GB_I18N.pt.deskEmptyChart = "Sem dados";
GB_I18N.pt.deskEmpty = "Sem dados";
GB_I18N.pt.deskPickSeries = "Selecione séries";
GB_I18N.pt.deskSeriesPld = "PLD";
GB_I18N.pt.deskSeriesCmo = "CMO";
GB_I18N.pt.deskSeriesCvu = "CVU gás méd.";
GB_I18N.pt.deskSeriesPoc = "POC méd.";
GB_I18N.pt.deskSeriesAnpSantos = "ANP Santos";
GB_I18N.pt.deskSeriesAnpNtSe = "ANP não térmico SE";
GB_I18N.pt.deskKpiGen = "Geração a gás SIN";
GB_I18N.pt.deskKpiPld = "PLD SE";
GB_I18N.pt.deskKpiCmo = "CMO SE";
GB_I18N.pt.deskKpiGus = "GUS último";
GB_I18N.pt.deskKpiPoc = "POC 7d";
GB_I18N.pt.deskKpiFlows = "Fluxos 7d";
GB_I18N.pt.deskKpiSantos = "Santos";
GB_I18N.pt.deskAnalysisTitle = "Análise";
GB_I18N.pt.deskAnalysisNote = "Compare séries de todo o site na mesma linha do tempo. Valores mensais se repetem no mês; o gráfico usa índice 100 no início do intervalo.";
GB_I18N.pt.deskAnalysisRange = "Intervalo";
GB_I18N.pt.deskAnalysisClear = "Limpar tudo";
GB_I18N.pt.deskTabOverview = "Visão geral";
GB_I18N.pt.deskTabAnalysis = "Análise";
GB_I18N.pt.deskAnalysisCatalog = "Catálogo de séries";
GB_I18N.pt.deskAnalysisFilterPh = "Filtrar séries…";
GB_I18N.pt.deskAnalysisSelected = "{n} selecionadas";
GB_I18N.pt.deskAnalysisGroupAll = "Todas";
GB_I18N.pt.deskAnalysisGroupNone = "Nenhuma";
GB_I18N.pt.deskAnalysisPaneSplit = "Dividido";
GB_I18N.pt.deskAnalysisPaneChart = "Gráfico";
GB_I18N.pt.deskAnalysisPaneTable = "Tabela";
GB_I18N.pt.deskAnalysisAxisHint = "Várias unidades — escolha o eixo Y por série (Auto usa esquerda para a unidade principal).";
GB_I18N.pt.deskAnalysisAxisAuto = "Auto";
GB_I18N.pt.deskAnalysisAxisLeft = "Esquerda";
GB_I18N.pt.deskAnalysisAxisRight = "Direita";

const COMPARE_META = [
  { key: "pld", labelKey: "deskSeriesPld", field: "pld" },
  { key: "cmo", labelKey: "deskSeriesCmo", field: "cmo" },
  { key: "cvu", labelKey: "deskSeriesCvu", field: "cvu" },
];
const POC_ANP_META = [
  { key: "poc", labelKey: "deskSeriesPoc", field: "poc" },
  { key: "anpSantos", labelKey: "deskSeriesAnpSantos", field: "anpSantos" },
  { key: "anpNtSe", labelKey: "deskSeriesAnpNtSe", field: "anpNonThermalSe" },
];
const DESK_VIEWS = [
  { id: "overview", labelKey: "deskTabOverview" },
  { id: "analysis", labelKey: "deskTabAnalysis" },
];
const ANALYSIS_GROUP_ORDER = [
  "PLD", "CMO", "CVU", "Gas generation", "Gas consumption", "Flows", "POC", "ANP & prices",
];

let DATA = null;
let chartResizeTimer = null;
let compareSm = "SE";
let pickedCompare = new Set();
let pickedPocAnp = new Set();
let compareSlots = new Map();
let pocAnpSlots = new Map();
let pickedAnalysis = new Set(["pld_se", "poc_gus_m3", "ons_gas_gen_sin"]);
let analysisRange = "90d";
let analysisFilter = "";
let analysisPane = "split";
let analysisAxisPref = new Map();
let deskTab = "overview";
let utilSortState = { col: "tso", dir: 1 };
const utilDefaultSort = { col: "tso", dir: 1 };
let utilFilters = {};
let sparkUnit = "mmbtu";
let sparkGasM3 = 1.2;
let sparkGasPresetId = "gus";

/** PLD=yellow, CMO=green, CVU=blue (palette indices 1,0,2). */
const DESK_FLAG_SERIES = { pld: 1, cmo: 0, cvu: 2 };
const DESK_POC_ANP_SERIES = { poc: 1, anpSantos: 0, anpNtSe: 2 };

function deskSeriesColor(key, map) {
  const pal = chartPalette();
  const i = map[key];
  if (i != null && pal[i]) return pal[i];
  return pal[0] || "var(--accent)";
}
function compareSeriesColor(key) {
  return deskSeriesColor(key, DESK_FLAG_SERIES);
}
function pocAnpSeriesColor(key) {
  return deskSeriesColor(key, DESK_POC_ANP_SERIES);
}

function analysisColorIndex(id) {
  const m = String(id).match(/^(pld|cmo|cvu)_(se|s|ne|n|sin)$/);
  if (m) {
    const metricOff = { pld: 0, cmo: 2, cvu: 4 }[m[1]] || 0;
    const smOff = { se: 0, s: 1, ne: 2, n: 3, sin: 4 }[m[2]] || 0;
    return (metricOff + smOff) % 8;
  }
  const ons = String(id).match(/^ons_(gas_gen|est_gas)_(se|s|ne|n|sin)$/);
  if (ons) {
    const base = ons[1] === "gas_gen" ? 1 : 3;
    const smOff = { se: 0, s: 1, ne: 2, n: 3, sin: 4 }[ons[2]] || 0;
    return (base + smOff) % 8;
  }
  const fixed = {
    poc_gus_m3: 6,
    poc_all_m3: 7,
    flows_vol_sin: 5,
    monthly_poc: 3,
    monthly_anpSantos: 4,
    monthly_anpNonThermalSe: 2,
  };
  if (fixed[id] != null) return fixed[id] % 8;
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % 8;
}

function analysisSeriesColor(id) {
  const pal = chartPalette();
  if (!pal.length) return "var(--accent)";
  const idx = analysisColorIndex(id);
  return pal[idx % pal.length] || "var(--accent)";
}

function fmtNum(v, d) {
  if (v === null || v === undefined || (typeof v === "number" && isNaN(v))) return "—";
  const loc = currentLang() === "pt" ? "pt-BR" : "en-US";
  return Number(v).toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d });
}

function colorOf(slots, key) {
  const pal = chartPalette();
  if (!slots.has(key)) slots.set(key, slots.size % Math.max(1, pal.length));
  return pal[slots.get(key) % pal.length] || "var(--accent)";
}

function buildPicker(hostId, meta, picked, slots, onToggle, getColor) {
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  meta.forEach(m => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "series-btn" + (picked.has(m.key) ? " active" : "");
    btn.innerHTML = '<span class="sw"></span>' + escapeHtml(t(m.labelKey));
    const swColor = picked.has(m.key)
      ? (getColor ? getColor(m.key) : colorOf(slots, m.key))
      : "";
    btn.querySelector(".sw").style.background = swColor;
    btn.addEventListener("click", () => {
      if (picked.has(m.key)) {
        picked.delete(m.key);
        if (!getColor) slots.delete(m.key);
      } else {
        picked.add(m.key);
        if (!getColor) colorOf(slots, m.key);
      }
      onToggle();
    });
    host.appendChild(btn);
  });
}

function refreshCompare() {
  buildPicker("picker-compare", COMPARE_META, pickedCompare, compareSlots, refreshCompare, compareSeriesColor);
  renderCompareChart();
  writeDeskQuery();
}
function refreshPocAnp() {
  buildPicker("picker-poc-anp", POC_ANP_META, pickedPocAnp, pocAnpSlots, refreshPocAnp, pocAnpSeriesColor);
  renderPocAnpChart();
  writeDeskQuery();
}
function buildPickers() {
  buildPicker("picker-compare", COMPARE_META, pickedCompare, compareSlots, refreshCompare, compareSeriesColor);
  buildPicker("picker-poc-anp", POC_ANP_META, pickedPocAnp, pocAnpSlots, refreshPocAnp, pocAnpSeriesColor);
}

// Shareable view state: compare submarket + both picked series sets.
// Unknown params degrade to defaults via the shared gb* query helpers
// (see shared/dashboard_kit.py JS_QUERY_STATE). Spark inputs and the
// utilization table stay local.
function applyDeskQuery() {
  const sp = gbQueryParams();
  const by = ((DATA.compareSe || {}).bySubmarket) || {};
  const smAllow = Object.keys(by).length ? Object.keys(by) : ["SE", "S", "NE", "N"];
  const sm = gbValidEnum(sp.get("sm"), smAllow);
  if (sm) compareSm = sm;
  const series = gbValidList(sp.get("series"), COMPARE_META.map(m => m.key));
  if (series) {
    pickedCompare = new Set(series);
  }
  const poc = gbValidList(sp.get("poc"), POC_ANP_META.map(m => m.key));
  if (poc) {
    pickedPocAnp = new Set(poc);
  }
  const ar = gbValidEnum(sp.get("arange"), ["90d", "1y"]);
  if (ar) analysisRange = ar;
  const tv = gbValidEnum(sp.get("tab"), ["overview", "analysis"]);
  if (tv) {
    deskTab = tv;
  } else {
    try {
      const saved = localStorage.getItem("desk-tab");
      if (saved === "analysis" || saved === "overview") deskTab = saved;
    } catch (e) {}
  }
  const ids = (DATA.analysisSeries || []).map(s => s.id);
  const apick = gbValidList(sp.get("analysis"), ids);
  if (apick) {
    pickedAnalysis = new Set(apick);
  }
  const axR = gbValidList(sp.get("axR"), ids);
  const axL = gbValidList(sp.get("axL"), ids);
  if (axR || axL) {
    analysisAxisPref = new Map();
    if (axL) axL.forEach(id => analysisAxisPref.set(id, "left"));
    if (axR) axR.forEach(id => analysisAxisPref.set(id, "right"));
  }
  const pane = gbValidEnum(sp.get("apane"), ["split", "chart", "table"]);
  if (pane) analysisPane = pane;
}
function writeDeskQuery() {
  if (!DATA) return;
  gbWriteQuery({
    sm: compareSm,
    series: [...pickedCompare],
    poc: [...pickedPocAnp],
    analysis: [...pickedAnalysis],
    arange: analysisRange,
    tab: deskTab === "overview" ? null : deskTab,
    apane: analysisPane === "split" ? null : analysisPane,
    axL: [...analysisAxisPref.entries()].filter(([, v]) => v === "left").map(([k]) => k),
    axR: [...analysisAxisPref.entries()].filter(([, v]) => v === "right").map(([k]) => k),
  });
  try { localStorage.setItem("desk-tab", deskTab); } catch (e) {}
}

function buildDeskTabs() {
  const host = document.getElementById("desk-tabs");
  if (!host) return;
  host.innerHTML = "";
  DESK_VIEWS.forEach(v => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.role = "tab";
    btn.dataset.tab = v.id;
    btn.textContent = t(v.labelKey);
    btn.setAttribute("aria-pressed", deskTab === v.id ? "true" : "false");
    btn.addEventListener("click", () => setDeskTab(v.id));
    host.appendChild(btn);
  });
}

function setDeskTab(id) {
  if (!DESK_VIEWS.some(v => v.id === id)) id = "overview";
  deskTab = id;
  document.body.classList.toggle("desk-analysis-active", deskTab === "analysis");
  const ov = document.getElementById("desk-view-overview");
  const an = document.getElementById("desk-view-analysis");
  if (ov) ov.hidden = deskTab !== "overview";
  if (an) an.hidden = deskTab !== "analysis";
  document.querySelectorAll("#desk-tabs button").forEach(btn => {
    btn.setAttribute("aria-pressed", btn.dataset.tab === deskTab ? "true" : "false");
  });
  if (deskTab === "analysis") {
    syncAnalysisPaneUi();
    renderAnalysis();
  }
  writeDeskQuery();
}

function paintAsof() {
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated, currentLang() === "pt" ? "pt-BR" : undefined);
  document.getElementById("asof-through").textContent = DATA.dataThrough || "—";
  initStalenessBadgeFor("desk", DATA.dataThrough);
}

function renderNotes() {
  // Intentionally quiet — chart empty-states carry the detail.
}

function siteHref(slug) {
  try {
    const h = location.hostname;
    if (h === "127.0.0.1" || h === "localhost") return "../" + slug + "/";
    const flavor = siteFlavor();
    const base = (SITE_LINKS[slug] || {})[flavor];
    if (base) return base;
  } catch (e) {}
  return "../" + slug + "/";
}

function pocFilterHref(keys) {
  const q = (keys || []).filter(Boolean).join(",");
  return siteHref("poc") + (q ? "?qf=" + q : "");
}

function gusKpiHref() {
  const k = DATA.kpi || {};
  const keys = ["gus"];
  const tso = k.gusTso ? String(k.gusTso).toUpperCase() : "";
  if (tso === "TAG" || tso === "NTS" || tso === "TBG") keys.push("tso-" + tso);
  return pocFilterHref(keys);
}

function renderKpis() {
  const k = DATA.kpi || {};
  const gusUnit = "R$/m³" + (k.gusWhen ? " · " + k.gusWhen : "") + (k.gusTso ? " · " + k.gusTso : "");
  const cells = [
    { lbl: t("deskKpiGen"), val: fmtNum(k.genGasSin, 0), unit: "MWmed" + (k.genGasWhen ? " · " + k.genGasWhen : ""), href: siteHref("ons") },
    { lbl: t("deskKpiPld"), val: fmtNum(k.pldSe, 2), unit: "R$/MWh" + (k.pldWhen ? " · " + k.pldWhen : ""), href: siteHref("pld") },
    { lbl: t("deskKpiCmo"), val: fmtNum(k.cmoSe, 2), unit: "R$/MWh" + (k.cmoWhen ? " · " + k.cmoWhen : ""), href: siteHref("ons") },
    { lbl: t("deskKpiGus"), val: fmtNum(k.gusLast, 3), unit: gusUnit, href: gusKpiHref() },
    { lbl: t("deskKpiPoc"), val: fmtNum(k.pocAvg7d, 3), unit: "R$/m³" + (k.pocTrades7d != null ? " · " + k.pocTrades7d : ""), href: pocFilterHref(["last7"]) },
    { lbl: t("deskKpiFlows"), val: fmtNum(k.flowsTotal7d, 0), unit: "000 m³" + (k.flowsWhen ? " · " + k.flowsWhen : ""), href: siteHref("flows") },
    { lbl: t("deskKpiSantos"), val: fmtNum(k.anpSantos, 3), unit: "R$/m³" + (k.anpSantosMonth ? " · " + k.anpSantosMonth : ""), href: siteHref("precos") },
  ];
  const host = document.getElementById("kpi-row");
  host.innerHTML = cells.map(c => {
    const inner = '<div class="lbl">' + escapeHtml(c.lbl) + '</div>' +
      '<div class="val">' + escapeHtml(c.val) + '</div>' +
      '<div class="unit">' + escapeHtml(c.unit) + '</div>';
    return '<a class="kpi-cell" href="' + escapeHtml(c.href) + '">' + inner + '</a>';
  }).join("");
}

function impliedCvu(gasM3, hr, natgas) {
  if (gasM3 == null || hr == null || !(natgas > 0)) return null;
  return gasM3 * hr * 1000 / natgas;
}

function m3PerMmbtu() {
  return Number((DATA && DATA.spark && DATA.spark.m3PerMmbtu) || 26.8081);
}

function displayGasFromM3(m3) {
  if (m3 == null || isNaN(m3)) return "";
  return sparkUnit === "mmbtu" ? (m3 * m3PerMmbtu()).toFixed(2) : Number(m3).toFixed(3);
}

function m3FromDisplay(raw) {
  const gas = parseFloat(raw);
  if (isNaN(gas)) return null;
  return sparkUnit === "mmbtu" ? gas / m3PerMmbtu() : gas;
}

function paintSparkUnit() {
  document.querySelectorAll("#spark-unit [data-unit]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.unit === sparkUnit);
  });
}

function sparkGasPresets() {
  const k = DATA.kpi || {};
  const presets = [];
  if (k.gusLast != null && !isNaN(k.gusLast)) {
    presets.push({ id: "gus", label: t("deskSparkGasGus"), m3: Number(k.gusLast) });
  }
  if (k.pocAvg7d != null && !isNaN(k.pocAvg7d)) {
    presets.push({ id: "poc7d", label: t("deskSparkGasPoc7d"), m3: Number(k.pocAvg7d) });
  }
  if (k.anpSantos != null && !isNaN(k.anpSantos)) {
    presets.push({ id: "santos", label: t("deskSparkGasSantos"), m3: Number(k.anpSantos) });
  }
  return presets;
}

function sparkGasM3FromPreset(id) {
  const hit = sparkGasPresets().find(p => p.id === id);
  return hit ? hit.m3 : null;
}

function paintSparkGasPresetSelect() {
  const sel = document.getElementById("spark-gas-preset");
  if (!sel) return;
  const presets = sparkGasPresets();
  sel.innerHTML = presets.map(p =>
    '<option value="' + escapeHtml(p.id) + '">' + escapeHtml(p.label) + "</option>"
  ).join("");
  if (!presets.length) {
    sel.innerHTML = '<option value="">' + escapeHtml(t("deskEmpty")) + "</option>";
    return;
  }
  const s = DATA.spark || {};
  const prefer = s.gasPriceSource === "poc_7d" ? "poc7d"
    : s.gasPriceSource === "gus_last" ? "gus" : presets[0].id;
  if (!presets.some(p => p.id === sparkGasPresetId)) sparkGasPresetId = prefer;
  sel.value = sparkGasPresetId;
  const m3 = sparkGasM3FromPreset(sparkGasPresetId);
  if (m3 != null) sparkGasM3 = m3;
}

function paintSparkGasReadout() {
  const el = document.getElementById("spark-gas-readout");
  if (!el) return;
  if (sparkGasM3 == null || isNaN(sparkGasM3)) {
    el.textContent = "—";
    return;
  }
  const unit = sparkUnit === "mmbtu" ? "R$/MMBtu" : "R$/m³";
  el.innerHTML = escapeHtml(displayGasFromM3(sparkGasM3)) +
    ' <span class="hint">' + escapeHtml(unit) + "</span>";
}

function sparkHeatRateKcal() {
  const s = DATA.spark || {};
  const preset = document.getElementById("spark-hr-preset");
  if (!preset) return s.heatRateCcgt || 1800;
  return preset.value === "ocgt" ? (s.heatRateOcgt || 2500) : (s.heatRateCcgt || 1800);
}

function lastLiveCvu() {
  const c = compareBlock();
  const vals = c.cvu || [];
  for (let i = vals.length - 1; i >= 0; i--) {
    if (vals[i] != null && !isNaN(vals[i])) return Number(vals[i]);
  }
  return null;
}

function setSparkUnit(unit) {
  if (!unit || unit === sparkUnit) return;
  sparkUnit = unit;
  paintSparkGasReadout();
  paintSparkUnit();
  renderSpark();
}

function renderSpark() {
  if (!DATA) return;
  const s = DATA.spark || {};
  const cvuMode = document.getElementById("spark-cvu-mode");
  const gas = sparkGasM3;
  const hr = sparkHeatRateKcal();
  const calc = impliedCvu(gas, hr, s.natgasKcalPerM3);
  const mode = cvuMode ? cvuMode.value : "implied";
  const liveCvu = lastLiveCvu();
  const cost = mode === "ons" && liveCvu != null ? liveCvu : calc;
  document.getElementById("spark-implied").textContent = fmtNum(cost, 1);
  const vsPld = (cost != null && s.pldSe != null) ? (s.pldSe - cost) : null;
  const vsCmo = (cost != null && s.cmoSe != null) ? (s.cmoSe - cost) : null;
  const pldEl = document.getElementById("spark-vs-pld");
  const cmoEl = document.getElementById("spark-vs-cmo");
  pldEl.textContent = fmtNum(vsPld, 1);
  cmoEl.textContent = fmtNum(vsCmo, 1);
  const pldWrap = document.getElementById("spark-vs-pld-wrap");
  const cmoWrap = document.getElementById("spark-vs-cmo-wrap");
  pldWrap.classList.toggle("pos", vsPld != null && vsPld > 0);
  pldWrap.classList.toggle("neg", vsPld != null && vsPld < 0);
  cmoWrap.classList.toggle("pos", vsCmo != null && vsCmo > 0);
  cmoWrap.classList.toggle("neg", vsCmo != null && vsCmo < 0);
  const info = document.getElementById("spark-info");
  const formula = currentLang() === "pt" ? (s.formulaPt || "") : (s.formulaEn || "");
  info.title = formula;
  info.setAttribute("aria-label", formula);
  paintSparkGasReadout();
  paintSparkUnit();
}

function initSparkForm() {
  sparkUnit = "mmbtu";
  const s = DATA.spark || {};
  sparkGasPresetId = s.gasPriceSource === "poc_7d" ? "poc7d" : "gus";
  paintSparkGasPresetSelect();
  document.getElementById("spark-hr-preset").value = "ccgt";
  document.getElementById("spark-cvu-mode").value = "implied";
  document.getElementById("spark-gas-preset").addEventListener("change", e => {
    sparkGasPresetId = e.target.value;
    const m3 = sparkGasM3FromPreset(sparkGasPresetId);
    if (m3 != null) sparkGasM3 = m3;
    renderSpark();
  });
  document.getElementById("spark-hr-preset").addEventListener("change", renderSpark);
  document.getElementById("spark-cvu-mode").addEventListener("change", renderSpark);
  document.querySelectorAll("#spark-unit [data-unit]").forEach(btn => {
    btn.addEventListener("click", () => setSparkUnit(btn.dataset.unit));
  });
  renderSpark();
}

function drawLineChart(hostId, dates, seriesList, emptyMsg) {
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  if (!seriesList.length) {
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = emptyMsg || t("deskPickSeries");
    host.appendChild(empty);
    return;
  }
  const has = seriesList.some(s => (s.values || []).some(v => v != null));
  if (!dates.length || !has) {
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = emptyMsg || t("deskEmptyChart");
    host.appendChild(empty);
    return;
  }
  const pal = chartPalette();
  const W = Math.max(320, host.clientWidth || 640);
  let H = 260;
  if (hostId === "analysis-chart") {
    const panel = host.closest(".analysis-chart-panel");
    const panelH = panel ? panel.clientHeight : 0;
    H = Math.max(200, Math.min(440, (panelH || host.clientHeight || 280) - 36));
  }
  const pad = { t: 16, r: 16, b: 36, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  let lo = Infinity, hi = -Infinity;
  seriesList.forEach(s => s.values.forEach(v => {
    if (v == null) return;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }));
  if (!(hi > lo)) { lo = 0; hi = 1; }
  const padY = (hi - lo) * 0.08;
  lo -= padY; hi += padY;
  const xAt = i => pad.l + (dates.length <= 1 ? iw / 2 : i / (dates.length - 1) * iw);
  const yAt = v => pad.t + (1 - (v - lo) / (hi - lo)) * ih;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);

  for (let g = 0; g <= 4; g++) {
    const y = pad.t + ih * g / 4;
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", pad.l); line.setAttribute("x2", pad.l + iw);
    line.setAttribute("y1", y); line.setAttribute("y2", y);
    line.setAttribute("stroke", "var(--border)"); line.setAttribute("stroke-width", "1");
    svg.appendChild(line);
    const lab = document.createElementNS(svg.namespaceURI, "text");
    const val = hi - (hi - lo) * g / 4;
    lab.textContent = fmtNum(val, 0);
    lab.setAttribute("x", pad.l - 8); lab.setAttribute("y", y + 3);
    lab.setAttribute("text-anchor", "end"); lab.setAttribute("fill", "var(--muted)");
    lab.setAttribute("font-size", "10"); lab.setAttribute("font-family", "var(--font)");
    svg.appendChild(lab);
  }

  seriesList.forEach((s, si) => {
    const color = s.color || pal[si % pal.length] || "var(--accent)";
    let d = "";
    let drawing = false;
    s.values.forEach((v, i) => {
      if (v == null) { drawing = false; return; }
      const cmd = drawing ? "L" : "M";
      d += cmd + " " + xAt(i) + " " + yAt(v) + " ";
      drawing = true;
    });
    if (!d) return;
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", d.trim());
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "1.75");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
  });

  const nLabel = Math.min(5, dates.length);
  for (let i = 0; i < nLabel; i++) {
    const idx = nLabel === 1 ? 0 : Math.round(i * (dates.length - 1) / (nLabel - 1));
    const lab = document.createElementNS(svg.namespaceURI, "text");
    lab.textContent = dates[idx];
    lab.setAttribute("x", xAt(idx)); lab.setAttribute("y", H - 10);
    lab.setAttribute("text-anchor", "middle"); lab.setAttribute("fill", "var(--muted)");
    lab.setAttribute("font-size", "10"); lab.setAttribute("font-family", "var(--font)");
    svg.appendChild(lab);
  }

  const tt = document.getElementById("chart-tt");
  const hit = document.createElementNS(svg.namespaceURI, "rect");
  hit.setAttribute("x", pad.l); hit.setAttribute("y", pad.t);
  hit.setAttribute("width", iw); hit.setAttribute("height", ih);
  hit.setAttribute("fill", "transparent");
  svg.appendChild(hit);
  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    let best = 0, bestDist = Infinity;
    for (let i = 0; i < dates.length; i++) {
      const dist = Math.abs(xAt(i) - px);
      if (dist < bestDist) { bestDist = dist; best = i; }
    }
    let rows = "";
    seriesList.forEach((s, si) => {
      const v = s.values[best];
      if (v == null) return;
      const color = s.color || pal[si % pal.length] || "var(--accent)";
      rows += '<tr><td><span class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
        color + '"></span> ' + escapeHtml(s.label) + '</td><td class="v">' + fmtNum(v, 2) + '</td></tr>';
    });
    tt.innerHTML = '<div class="d">' + escapeHtml(dates[best]) + '</div><table>' + rows + '</table>';
    placeChartTooltip(tt, ev.clientX, ev.clientY);
  });
  hit.addEventListener("pointerleave", () => { tt.style.display = "none"; });

  host.appendChild(svg);
  const lg = document.createElement("div");
  lg.className = "legend";
  seriesList.forEach((s, si) => {
    const span = document.createElement("span");
    const color = s.color || pal[si % pal.length] || "var(--accent)";
    span.innerHTML = '<span class="sw" style="background:' + color + '"></span>' + escapeHtml(s.label);
    lg.appendChild(span);
  });
  host.appendChild(lg);
}

function analysisAxisExtents(list) {
  let lo = Infinity;
  let hi = -Infinity;
  list.forEach(s => (s.values || []).forEach(v => {
    if (v == null || isNaN(v)) return;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }));
  if (!(hi > lo)) { lo = 0; hi = 1; }
  const padY = (hi - lo) * 0.08;
  return { lo: lo - padY, hi: hi + padY };
}

function drawAnalysisChart(days, plotSeries, dualMeta) {
  const host = document.getElementById("analysis-chart");
  if (!host) return;
  host.innerHTML = "";
  if (!plotSeries.length) {
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = t("deskPickSeries");
    host.appendChild(empty);
    return;
  }
  const has = plotSeries.some(s => (s.values || []).some(v => v != null));
  if (!days.length || !has) {
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = t("deskEmptyChart");
    host.appendChild(empty);
    return;
  }
  const pal = chartPalette();
  const W = Math.max(320, host.clientWidth || 640);
  const panel = host.closest(".analysis-chart-panel");
  const panelH = panel ? panel.clientHeight : 0;
  let H = analysisPane === "chart"
    ? Math.max(280, Math.min(560, (panelH || host.clientHeight || 360) - 24))
    : Math.max(200, Math.min(440, (panelH || host.clientHeight || 280) - 36));
  const useDual = dualMeta && dualMeta.dual;
  const pad = { t: 16, r: useDual ? 52 : 16, b: 36, l: 48 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const leftSeries = plotSeries.filter(s => s.axis !== "right");
  const rightSeries = plotSeries.filter(s => s.axis === "right");
  const leftExt = analysisAxisExtents(leftSeries.length ? leftSeries : plotSeries);
  const rightExt = analysisAxisExtents(rightSeries.length ? rightSeries : plotSeries);
  const xAt = i => pad.l + (days.length <= 1 ? iw / 2 : (i / (days.length - 1)) * iw);
  const yLeft = v => pad.t + (1 - (v - leftExt.lo) / (leftExt.hi - leftExt.lo)) * ih;
  const yRight = v => pad.t + (1 - (v - rightExt.lo) / (rightExt.hi - rightExt.lo)) * ih;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);

  for (let g = 0; g <= 4; g++) {
    const y = pad.t + ih * g / 4;
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", pad.l);
    line.setAttribute("x2", pad.l + iw);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("stroke", "var(--border)");
    line.setAttribute("stroke-width", "1");
    svg.appendChild(line);
    const labL = document.createElementNS(svg.namespaceURI, "text");
    labL.textContent = fmtNum(leftExt.hi - (leftExt.hi - leftExt.lo) * g / 4, 0);
    labL.setAttribute("x", pad.l - 8);
    labL.setAttribute("y", y + 3);
    labL.setAttribute("text-anchor", "end");
    labL.setAttribute("fill", "var(--muted)");
    labL.setAttribute("font-size", "10");
    labL.setAttribute("font-family", "var(--font)");
    svg.appendChild(labL);
    if (useDual && rightSeries.length) {
      const labR = document.createElementNS(svg.namespaceURI, "text");
      labR.textContent = fmtNum(rightExt.hi - (rightExt.hi - rightExt.lo) * g / 4, 0);
      labR.setAttribute("x", pad.l + iw + 8);
      labR.setAttribute("y", y + 3);
      labR.setAttribute("text-anchor", "start");
      labR.setAttribute("fill", "var(--muted)");
      labR.setAttribute("font-size", "10");
      labR.setAttribute("font-family", "var(--font)");
      svg.appendChild(labR);
    }
  }

  plotSeries.forEach((s, si) => {
    const color = s.color || pal[si % pal.length] || "var(--accent)";
    const yAt = useDual && s.axis === "right" ? yRight : yLeft;
    let d = "";
    let drawing = false;
    (s.values || []).forEach((v, i) => {
      if (v == null) { drawing = false; return; }
      d += (drawing ? "L" : "M") + " " + xAt(i) + " " + yAt(v) + " ";
      drawing = true;
    });
    if (!d) return;
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", d.trim());
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "1.75");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    if (useDual && s.axis === "right") path.setAttribute("stroke-dasharray", "5 3");
    svg.appendChild(path);
  });

  const nLabel = Math.min(5, days.length);
  for (let i = 0; i < nLabel; i++) {
    const idx = nLabel === 1 ? 0 : Math.round(i * (days.length - 1) / (nLabel - 1));
    const lab = document.createElementNS(svg.namespaceURI, "text");
    lab.textContent = days[idx];
    lab.setAttribute("x", xAt(idx));
    lab.setAttribute("y", H - 10);
    lab.setAttribute("text-anchor", "middle");
    lab.setAttribute("fill", "var(--muted)");
    lab.setAttribute("font-size", "10");
    lab.setAttribute("font-family", "var(--font)");
    svg.appendChild(lab);
  }

  const tt = document.getElementById("chart-tt");
  const hit = document.createElementNS(svg.namespaceURI, "rect");
  hit.setAttribute("x", pad.l);
  hit.setAttribute("y", pad.t);
  hit.setAttribute("width", iw);
  hit.setAttribute("height", ih);
  hit.setAttribute("fill", "transparent");
  svg.appendChild(hit);
  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < days.length; i++) {
      const dist = Math.abs(xAt(i) - px);
      if (dist < bestDist) { bestDist = dist; best = i; }
    }
    let rows = "";
    plotSeries.forEach((s, si) => {
      const v = s.values[best];
      if (v == null) return;
      const color = s.color || pal[si % pal.length] || "var(--accent)";
      const ax = useDual && s.axis === "right" ? " · R" : useDual ? " · L" : "";
      rows += '<tr><td><span class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
        color + '"></span> ' + escapeHtml(s.label) + ax + '</td><td class="v">' + fmtNum(v, 2) + "</td></tr>";
    });
    tt.innerHTML = '<div class="d">' + escapeHtml(days[best]) + '</div><table>' + rows + "</table>";
    placeChartTooltip(tt, ev.clientX, ev.clientY);
  });
  hit.addEventListener("pointerleave", () => { tt.style.display = "none"; });

  host.appendChild(svg);
  const lg = document.createElement("div");
  lg.className = "legend";
  plotSeries.forEach((s, si) => {
    const span = document.createElement("span");
    const color = s.color || pal[si % pal.length] || "var(--accent)";
    const dash = useDual && s.axis === "right" ? " (R)" : useDual ? " (L)" : "";
    span.innerHTML = '<span class="sw" style="background:' + color + '"></span>' + escapeHtml(s.label + dash);
    lg.appendChild(span);
  });
  host.appendChild(lg);
  if (useDual && dualMeta.leftUnit && dualMeta.rightUnit) {
    const note = document.createElement("div");
    note.className = "chart-legend-dual";
    note.textContent = "L: " + dualMeta.leftUnit + " · R: " + dualMeta.rightUnit + " (indexed to 100 at range start)";
    host.appendChild(note);
  }
}

function compareBlock() {
  const c = DATA.compareSe || {};
  const by = c.bySubmarket || {};
  const sm = by[compareSm] ? compareSm : (c.defaultSubmarket || "SE");
  compareSm = sm;
  const block = by[sm] || {};
  return {
    dates: c.dates || [],
    note: c.note || null,
    pld: block.pld || c.pld || [],
    cmo: block.cmo || c.cmo || [],
    cvu: block.cvu || c.cvu || [],
  };
}

function renderCompareChart() {
  if (!DATA) return;
  const c = compareBlock();
  if (!pickedCompare.size) {
    drawLineChart("main-chart", [], [], t("deskPickSeries"));
    return;
  }
  const series = COMPARE_META.filter(m => pickedCompare.has(m.key)).map(m => ({
    label: t(m.labelKey),
    values: c[m.field] || [],
    color: compareSeriesColor(m.key),
  }));
  drawLineChart("main-chart", c.dates || [], series, c.note || t("deskEmptyChart"));
}

function renderPocAnpChart() {
  if (!DATA) return;
  const c = DATA.pocAnpMonthly || {};
  if (!pickedPocAnp.size) {
    drawLineChart("poc-anp-chart", [], [], t("deskPickSeries"));
    return;
  }
  const series = POC_ANP_META.filter(m => pickedPocAnp.has(m.key)).map(m => ({
    label: t(m.labelKey),
    values: c[m.field] || [],
    color: pocAnpSeriesColor(m.key),
  }));
  drawLineChart("poc-anp-chart", c.months || [], series, c.note || t("deskEmptyChart"));
}

function analysisCatalog() {
  return (DATA && DATA.analysisSeries) || [];
}

function analysisValueAt(series, dayKey) {
  if (!series) return null;
  if (series.freq === "daily") {
    const i = series.timeline.indexOf(dayKey);
    return i >= 0 ? series.values[i] : null;
  }
  const month = dayKey.slice(0, 7);
  const i = series.timeline.indexOf(month);
  return i >= 0 ? series.values[i] : null;
}

function analysisDays() {
  const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
  if (!seriesList.length) return [];
  let max = null;
  seriesList.forEach(s => {
    const last = s.timeline[s.timeline.length - 1];
    if (!last) return;
    const day = s.freq === "daily" ? last : (last.length === 7 ? last + "-01" : last);
    if (!max || day > max) max = day;
  });
  if (!max) return [];
  const minDate = new Date(max + "T00:00:00Z");
  if (analysisRange === "90d") minDate.setUTCDate(minDate.getUTCDate() - 89);
  else minDate.setUTCFullYear(minDate.getUTCFullYear() - 1);
  const min = minDate.toISOString().slice(0, 10);
  const out = [];
  const cur = new Date(min + "T00:00:00Z");
  const end = new Date(max + "T00:00:00Z");
  while (cur <= end) {
    out.push(cur.toISOString().slice(0, 10));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return out;
}

const ANALYSIS_REGION_ORDER = { SIN: 0, SE: 1, S: 2, NE: 3, N: 4 };

function analysisSortSeries(a, b) {
  const ra = ANALYSIS_REGION_ORDER[a.region] != null ? ANALYSIS_REGION_ORDER[a.region] : 9;
  const rb = ANALYSIS_REGION_ORDER[b.region] != null ? ANALYSIS_REGION_ORDER[b.region] : 9;
  if (ra !== rb) return ra - rb;
  return String(a.label).localeCompare(String(b.label));
}

function analysisMatchesFilter(s, q) {
  if (!q) return true;
  const hay = (s.label + " " + (s.group || "") + " " + (s.unit || "") + " " + s.id).toLowerCase();
  return hay.indexOf(q) >= 0;
}

function paintAnalysisPickCount() {
  const el = document.getElementById("analysis-pick-count");
  if (!el) return;
  const n = pickedAnalysis.size;
  let msg = t("deskAnalysisSelected");
  el.textContent = msg.indexOf("{n}") >= 0 ? msg.replace("{n}", String(n)) : (n + " selected");
}

function syncAnalysisPaneUi() {
  const stage = document.getElementById("analysis-stage");
  if (stage) stage.dataset.pane = analysisPane;
  [["split", "analysis-pane-split"], ["chart", "analysis-pane-chart"], ["table", "analysis-pane-table"]].forEach(([mode, id]) => {
    const btn = document.getElementById(id);
    if (btn) btn.setAttribute("aria-pressed", analysisPane === mode ? "true" : "false");
  });
}

function analysisSelectedUnits() {
  const u = new Set();
  analysisCatalog().forEach(s => {
    if (pickedAnalysis.has(s.id) && s.unit) u.add(s.unit);
  });
  return u;
}

function primaryAnalysisUnit(seriesList) {
  const counts = {};
  seriesList.forEach(s => {
    const u = s.unit || "";
    counts[u] = (counts[u] || 0) + 1;
  });
  let best = "";
  let n = 0;
  Object.keys(counts).forEach(u => {
    if (counts[u] > n) { n = counts[u]; best = u; }
  });
  return best;
}

function resolveSeriesAxis(seriesList) {
  const units = analysisSelectedUnits();
  const primary = primaryAnalysisUnit(seriesList);
  const dual = units.size > 1;
  return seriesList.map(s => {
    const pref = analysisAxisPref.get(s.id);
    let axis = "left";
    if (pref === "right") axis = "right";
    else if (pref === "left") axis = "left";
    else if (dual && s.unit !== primary) axis = "right";
    return axis;
  });
}

function paintAnalysisAxisHint(seriesList) {
  const el = document.getElementById("analysis-axis-hint");
  if (!el) return;
  const dual = analysisSelectedUnits().size > 1;
  if (!dual || !seriesList.length) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = t("deskAnalysisAxisHint");
}

function setAnalysisPane(mode) {
  if (mode !== "split" && mode !== "chart" && mode !== "table") mode = "split";
  analysisPane = mode;
  syncAnalysisPaneUi();
  if (deskTab === "analysis") renderAnalysis();
  writeDeskQuery();
}

function setAnalysisGroupPicked(items, on) {
  items.forEach(s => {
    if (on) pickedAnalysis.add(s.id);
    else pickedAnalysis.delete(s.id);
  });
  renderAnalysis();
  writeDeskQuery();
}

function mountAnalysisGroup(host, groupName, items) {
  const q = analysisFilter.trim().toLowerCase();
  const visible = items.filter(s => analysisMatchesFilter(s, q));
  if (!visible.length) return;
  visible.sort(analysisSortSeries);
  const pickedN = visible.filter(s => pickedAnalysis.has(s.id)).length;
  const details = document.createElement("details");
  details.className = "analysis-group";
  details.open = !!q || pickedN > 0 || visible.length <= 6;
  const summary = document.createElement("summary");
  summary.innerHTML = '<span>' + escapeHtml(groupName) + '</span>' +
    '<span class="analysis-group-meta">' + pickedN + "/" + visible.length + "</span>" +
    '<span class="analysis-group-actions">' +
    '<button type="button" data-act="all">' + escapeHtml(t("deskAnalysisGroupAll")) + "</button>" +
    '<button type="button" data-act="none">' + escapeHtml(t("deskAnalysisGroupNone")) + "</button>" +
    "</span>";
  summary.querySelector('[data-act="all"]').addEventListener("click", ev => {
    ev.preventDefault();
    ev.stopPropagation();
    setAnalysisGroupPicked(visible, true);
  });
  summary.querySelector('[data-act="none"]').addEventListener("click", ev => {
    ev.preventDefault();
    ev.stopPropagation();
    setAnalysisGroupPicked(visible, false);
  });
  details.appendChild(summary);
  const list = document.createElement("div");
  list.className = "analysis-series-list";
  visible.forEach(s => {
    const row = document.createElement("label");
    row.className = "analysis-series-row" + (pickedAnalysis.has(s.id) ? " is-on" : "");
    const sw = analysisSeriesColor(s.id);
    const pref = analysisAxisPref.get(s.id) || "auto";
    const multiUnit = analysisSelectedUnits().size > 1;
    row.innerHTML =
      '<input type="checkbox"' + (pickedAnalysis.has(s.id) ? " checked" : "") + ">" +
      '<span class="sw" style="background:' + sw + '"></span>' +
      '<span class="lbl">' + escapeHtml(s.label) +
      '<span class="unit">' + escapeHtml(s.unit) + "</span></span>" +
      (multiUnit
        ? ('<select class="axis-pick" aria-label="Y-axis">' +
          '<option value="auto"' + (pref === "auto" ? " selected" : "") + ">" + escapeHtml(t("deskAnalysisAxisAuto")) + "</option>" +
          '<option value="left"' + (pref === "left" ? " selected" : "") + ">" + escapeHtml(t("deskAnalysisAxisLeft")) + "</option>" +
          '<option value="right"' + (pref === "right" ? " selected" : "") + ">" + escapeHtml(t("deskAnalysisAxisRight")) + "</option>" +
          "</select>")
        : "");
    row.querySelector("input").addEventListener("change", ev => {
      ev.stopPropagation();
      if (ev.target.checked) pickedAnalysis.add(s.id);
      else pickedAnalysis.delete(s.id);
      renderAnalysis();
      writeDeskQuery();
    });
    const axSel = row.querySelector(".axis-pick");
    if (axSel) {
      axSel.addEventListener("click", ev => ev.stopPropagation());
      axSel.addEventListener("change", ev => {
        ev.stopPropagation();
        const v = axSel.value;
        if (v === "auto") analysisAxisPref.delete(s.id);
        else analysisAxisPref.set(s.id, v);
        renderAnalysis();
        writeDeskQuery();
      });
    }
    list.appendChild(row);
  });
  details.appendChild(list);
  host.appendChild(details);
}

function buildAnalysisPicker() {
  const host = document.getElementById("picker-analysis");
  if (!host) return;
  const scrollTop = host.scrollTop;
  host.innerHTML = "";
  const byGroup = new Map();
  analysisCatalog().forEach(s => {
    const g = s.group || "Other";
    if (!byGroup.has(g)) byGroup.set(g, []);
    byGroup.get(g).push(s);
  });
  let any = false;
  ANALYSIS_GROUP_ORDER.forEach(g => {
    const items = byGroup.get(g);
    if (!items || !items.length) return;
    mountAnalysisGroup(host, g, items);
    byGroup.delete(g);
    any = true;
  });
  byGroup.forEach((items, g) => {
    if (!items.length) return;
    mountAnalysisGroup(host, g, items);
    any = true;
  });
  if (!any) {
    host.innerHTML = '<p style="padding:12px;color:var(--muted);font-size:12px;margin:0">' +
      escapeHtml(t("deskEmptyChart")) + "</p>";
  }
  host.scrollTop = scrollTop;
  paintAnalysisPickCount();
}

function renderAnalysisTable(days, seriesList) {
  const head = document.getElementById("analysis-thead");
  const body = document.getElementById("analysis-body");
  if (!head || !body) return;
  if (!days.length || !seriesList.length) {
    head.innerHTML = "";
    body.innerHTML = '<tr><td colspan="2" style="color:var(--muted)">' + escapeHtml(t("deskPickSeries")) + "</td></tr>";
    return;
  }
  head.innerHTML = "<th>Date</th>" + seriesList.map(s =>
    '<th class="num">' + escapeHtml(s.label) + ' <span style="color:var(--muted);font-weight:300">(' + escapeHtml(s.unit) + ")</span></th>"
  ).join("");
  body.innerHTML = days.map(d => {
    const cells = seriesList.map(s => {
      const v = analysisValueAt(s, d);
      return '<td class="num">' + (v == null ? "—" : fmtNum(v, 2)) + "</td>";
    }).join("");
    return "<tr><td>" + escapeHtml(d) + "</td>" + cells + "</tr>";
  }).join("");
}

function renderAnalysisChart(days, seriesList) {
  paintAnalysisAxisHint(seriesList);
  if (!pickedAnalysis.size) {
    drawAnalysisChart(days, [], null);
    return;
  }
  const axes = resolveSeriesAxis(seriesList);
  const plotSeries = seriesList.map((s, i) => {
    const vals = days.map(d => analysisValueAt(s, d));
    let base = null;
    for (const v of vals) { if (v != null) { base = v; break; } }
    const norm = (base != null && base !== 0)
      ? vals.map(v => v == null ? null : Math.round((v / base) * 1000) / 10)
      : vals;
    return {
      label: s.label + " (index)",
      values: norm,
      color: analysisSeriesColor(s.id),
      axis: axes[i],
      unit: s.unit || "",
    };
  });
  const leftUnits = new Set(plotSeries.filter(s => s.axis !== "right").map(s => s.unit));
  const rightUnits = new Set(plotSeries.filter(s => s.axis === "right").map(s => s.unit));
  const dual = leftUnits.size > 0 && rightUnits.size > 0 &&
    plotSeries.some(s => s.axis === "right") && plotSeries.some(s => s.axis !== "right");
  drawAnalysisChart(days, plotSeries, {
    dual,
    leftUnit: [...leftUnits].filter(Boolean).join(", ") || plotSeries[0].unit,
    rightUnit: [...rightUnits].filter(Boolean).join(", "),
  });
}

function renderAnalysis() {
  if (!DATA) return;
  buildAnalysisPicker();
  syncAnalysisPaneUi();
  const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
  const days = analysisDays();
  if (analysisPane === "chart" || analysisPane === "split") {
    renderAnalysisChart(days, seriesList);
  } else {
    const host = document.getElementById("analysis-chart");
    if (host) host.innerHTML = "";
  }
  if (analysisPane === "table" || analysisPane === "split") {
    renderAnalysisTable(days, seriesList);
  }
}

function gusForTso(tso) {
  const k = DATA.kpi || {};
  if (k.gusLast == null || !k.gusTso || !tso) return null;
  return String(k.gusTso).toUpperCase() === String(tso).toUpperCase() ? k.gusLast : null;
}

function utilRawRows() {
  const u = DATA.utilization || {};
  return (u.rows || []).map(r => ({
    tso: r.tso,
    contracted: r.contracted,
    realized: r.realized,
    utilization: r.utilization == null ? null : r.utilization * 100,
    tariffM3: r.tariffM3 == null ? null : r.tariffM3,
    gusM3: gusForTso(r.tso),
  }));
}

function utilCols() {
  const rows = DATA.utilization && DATA.utilization.rows || [];
  const cols = [
    { key: "tso", label: t("deskUtilTso") },
    { key: "contracted", label: t("deskUtilCap"), num: true },
    { key: "realized", label: t("deskUtilReal"), num: true },
    { key: "utilization", label: t("deskUtilPct"), num: true },
  ];
  if (rows.some(r => r.tariffM3 != null)) cols.push({ key: "tariffM3", label: t("deskUtilTariff"), num: true });
  if (rows.some(r => gusForTso(r.tso) != null)) cols.push({ key: "gusM3", label: t("deskUtilGus"), num: true });
  return cols;
}

function utilTableRows() {
  return utilRawRows().filter(r => {
    for (const [col, q] of Object.entries(utilFilters)) {
      if (!q) continue;
      const v = r[col];
      if (String(v == null ? "" : v).toLowerCase().indexOf(q) < 0) return false;
    }
    return true;
  }).sort((a, b) => {
    const av = a[utilSortState.col], bv = b[utilSortState.col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * utilSortState.dir;
    return String(av).localeCompare(String(bv)) * utilSortState.dir;
  });
}

function utilFmt(col, r) {
  const v = r[col.key];
  if (col.key === "tso") return escapeHtml(v == null ? "" : v);
  if (col.key === "utilization") return v == null ? "—" : escapeHtml(fmtNum(v, 0) + "%");
  if (v == null) return "—";
  const d = (col.key === "tariffM3" || col.key === "gusM3") ? 3 : 1;
  return escapeHtml(fmtNum(v, d));
}

function renderUtil() {
  if (!DATA) return;
  const u = DATA.utilization || {};
  const thead = document.getElementById("util-thead");
  const body = document.getElementById("util-body");
  const cols = utilCols();
  withFocusPreserved(thead.parentElement.parentElement, () => {
    thead.innerHTML = "";
    cols.forEach(col => {
      thead.appendChild(buildSortFilterTh(col, utilSortState, utilDefaultSort, utilFilters, (s, f) => {
        utilSortState = s; utilFilters = f; renderUtil();
      }, col.num ? "num" : ""));
    });
    body.innerHTML = "";
    const rows = utilTableRows();
    if (!(u.rows || []).length) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="' + cols.length + '" style="color:var(--muted)">' + escapeHtml(u.note || t("deskEmptyChart")) + "</td>";
      body.appendChild(tr);
      return;
    }
    rows.forEach(r => {
      const tr = document.createElement("tr");
      tr.innerHTML = cols.map(col => {
        const tdClass = col.num ? ' class="num"' : "";
        return "<td" + tdClass + ">" + utilFmt(col, r) + "</td>";
      }).join("");
      body.appendChild(tr);
    });
  });
}

function renderAll() {
  paintAsof();
  renderKpis();
  buildPickers();
  renderCompareChart();
  renderPocAnpChart();
  if (deskTab === "analysis") renderAnalysis();
  renderUtil();
  renderSpark();
  buildDeskTabs();
  setDeskTab(deskTab);
  applyI18n();
}

function initAnalysisResizer() {
  const inner = document.querySelector(".analysis-workspace-inner");
  const resizer = document.getElementById("analysis-resizer");
  const sidebar = document.querySelector(".analysis-sidebar");
  if (!inner || !resizer || !sidebar) return;

  const STORAGE_KEY = "gasbrazil-desk-sidebar-w";
  const DEFAULT_WIDTH = 290;
  const MIN_WIDTH = 200;

  function getMaxWidth() {
    const total = inner.clientWidth || 1000;
    return Math.max(MIN_WIDTH + 100, total - 360);
  }

  function setWidth(w, save) {
    const maxW = getMaxWidth();
    const clamped = Math.round(Math.max(MIN_WIDTH, Math.min(maxW, w)));
    inner.style.setProperty("--desk-sidebar-w", clamped + "px");
    resizer.setAttribute("aria-valuenow", clamped);
    resizer.setAttribute("aria-valuemin", MIN_WIDTH);
    resizer.setAttribute("aria-valuemax", maxW);
    if (save) {
      try { localStorage.setItem(STORAGE_KEY, String(clamped)); } catch (_) {}
    }
  }

  try {
    const saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
    if (isFinite(saved) && saved >= MIN_WIDTH) {
      setWidth(saved, false);
    } else {
      setWidth(DEFAULT_WIDTH, false);
    }
  } catch (_) {
    setWidth(DEFAULT_WIDTH, false);
  }

  let isDragging = false;
  let startX = 0;
  let startW = 0;
  let rafId = null;

  function onPointerMove(e) {
    if (!isDragging) return;
    const delta = e.clientX - startX;
    const newW = startW + delta;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(() => {
      setWidth(newW, false);
      if (deskTab === "analysis" && (analysisPane === "chart" || analysisPane === "split")) {
        const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
        renderAnalysisChart(analysisDays(), seriesList);
      }
    });
  }

  function onPointerUp(e) {
    if (!isDragging) return;
    isDragging = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    resizer.classList.remove("is-dragging");
    document.body.classList.remove("is-resizing");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    const finalW = sidebar.getBoundingClientRect().width;
    setWidth(finalW, true);
    if (deskTab === "analysis" && (analysisPane === "chart" || analysisPane === "split")) {
      const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
      renderAnalysisChart(analysisDays(), seriesList);
    }
  }

  resizer.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.preventDefault();
    isDragging = true;
    startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    resizer.classList.add("is-dragging");
    document.body.classList.add("is-resizing");
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
  });

  resizer.addEventListener("dblclick", () => {
    setWidth(DEFAULT_WIDTH, true);
    if (deskTab === "analysis" && (analysisPane === "chart" || analysisPane === "split")) {
      const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
      renderAnalysisChart(analysisDays(), seriesList);
    }
  });

  resizer.addEventListener("keydown", e => {
    const curW = sidebar.getBoundingClientRect().width;
    const step = e.shiftKey ? 60 : 20;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setWidth(curW - step, true);
      renderAnalysis();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setWidth(curW + step, true);
      renderAnalysis();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setWidth(DEFAULT_WIDTH, true);
      renderAnalysis();
    }
  });
}

let analysisChartRo = null;
function observeAnalysisResize() {
  const panel = document.getElementById("analysis-chart-panel");
  if (!panel || analysisChartRo || typeof ResizeObserver === "undefined") return;
  let lastW = 0;
  analysisChartRo = new ResizeObserver(entries => {
    for (const entry of entries) {
      const w = Math.round(entry.contentRect.width);
      if (w > 0 && Math.abs(w - lastW) >= 4) {
        lastW = w;
        if (deskTab === "analysis" && (analysisPane === "chart" || analysisPane === "split")) {
          const seriesList = analysisCatalog().filter(s => pickedAnalysis.has(s.id));
          renderAnalysisChart(analysisDays(), seriesList);
        }
      }
    }
  });
  analysisChartRo.observe(panel);
}

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  initThemeToggle("theme-toggle", () => {
    if (DATA) {
      buildPickers();
      renderCompareChart();
      renderPocAnpChart();
      renderAnalysis();
    }
  });
  initLangToggle("lang-toggle", () => {
    if (DATA) renderAll();
    else applyI18n();
  });
  initCrossLinks();
  gbCopyLink("btn-share");
  applyI18n();
  const tabFromUrl = gbValidEnum(gbQueryParams().get("tab"), ["overview", "analysis"]);
  if (tabFromUrl) deskTab = tabFromUrl;
  buildDeskTabs();
  setDeskTab(deskTab);
  initAnalysisResizer();
  observeAnalysisResize();
  try {
    const json = await inflateGzipUrl(PAYLOAD_URL);
    DATA = JSON.parse(json);
    // Payloads built before poc_energy v2 stored R$/m³ as MMBtu × 28.8081 / 1000.
    // Rescale those fields so this shell is correct against the still-published
    // artifact; v2+ payloads set spark.energyVersion and skip this.
    (function migrateLegacyM3Prices(data) {
      if (!data || ((data.spark || {}).energyVersion >= 2)) return;
      const rescale = v => {
        if (v == null || v === "" || !isFinite(Number(v))) return v;
        return Math.round(Number(v) * 1000 / (28.8081 * 26.8081) * 1000) / 1000;
      };
      const kpi = data.kpi || {};
      ["gusLast", "anpSantos", "anpNonThermalSe", "pocAvg7d"].forEach(k => {
        if (kpi[k] != null) kpi[k] = rescale(kpi[k]);
      });
      if (data.spark && data.spark.defaultGasPrice != null)
        data.spark.defaultGasPrice = rescale(data.spark.defaultGasPrice);
      const monthly = data.pocAnpMonthly || {};
      ["poc", "anpSantos", "anpNonThermalSe"].forEach(k => {
        if (Array.isArray(monthly[k])) monthly[k] = monthly[k].map(v => v == null ? v : rescale(v));
      });
    })(DATA);
    COMPARE_META.forEach(m => pickedCompare.add(m.key));
    POC_ANP_META.forEach(m => pickedPocAnp.add(m.key));
    const smSel = document.getElementById("compare-sm");
    const c0 = DATA.compareSe || {};
    compareSm = c0.defaultSubmarket || "SE";
    applyDeskQuery();
    const arSel = document.getElementById("analysis-range");
    if (arSel) {
      arSel.value = analysisRange;
      arSel.addEventListener("change", () => {
        analysisRange = arSel.value;
        renderAnalysis();
        writeDeskQuery();
      });
    }
    const clearBtn = document.getElementById("analysis-clear");
    if (clearBtn && clearBtn.dataset.bound !== "1") {
      clearBtn.dataset.bound = "1";
      clearBtn.addEventListener("click", () => {
        pickedAnalysis.clear();
        renderAnalysis();
        writeDeskQuery();
      });
    }
    const filterEl = document.getElementById("analysis-filter");
    if (filterEl && filterEl.dataset.bound !== "1") {
      filterEl.dataset.bound = "1";
      filterEl.addEventListener("input", () => {
        analysisFilter = filterEl.value || "";
        buildAnalysisPicker();
      });
    }
    [["split", "analysis-pane-split"], ["chart", "analysis-pane-chart"], ["table", "analysis-pane-table"]].forEach(([mode, id]) => {
      const btn = document.getElementById(id);
      if (!btn || btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => setAnalysisPane(mode));
    });
    syncAnalysisPaneUi();
    if (smSel) {
      smSel.value = compareSm;
      smSel.addEventListener("change", () => {
        compareSm = smSel.value;
        renderCompareChart();
        renderSpark();
        writeDeskQuery();
      });
    }
    initSparkForm();
    renderAll();
    writeDeskQuery();
    window.addEventListener("resize", () => {
      clearTimeout(chartResizeTimer);
      chartResizeTimer = setTimeout(() => {
        renderCompareChart();
        renderPocAnpChart();
        renderAnalysis();
      }, 140);
    });
  } catch (err) {
    console.error(err);
    showBootError(err, () => init());
  }
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    import os

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
    import data_kit as dk  # noqa: E402

    here = HERE.resolve()
    out_path = Path(out_path)
    lake_root = here.parent / "lake"
    sibling_poc = here.parent / "poc" / "data" / "poc_results.parquet"
    desk_parquets = [
        lake_root / "electric" / "ons_daily.parquet",
        lake_root / "electric" / "pld_hourly.parquet",
        lake_root / "gas" / "anp_prices.parquet",
        sibling_poc,
    ]
    has_local = any(p.exists() for p in desk_parquets)
    # CI ships an empty lake/ (parquet is gitignored). build_payload() calls
    # ensure_lake() to pull sibling mirrors from R2 — so lake credentials mean
    # we *can* rebuild even with no local files. Gating only on local parquet
    # (post-#17) made scheduled Desk runs reuse a week-old published payload.
    lake_ready = bool(os.environ.get("GASBRAZIL_LAKE_BUCKET", "").strip()) and dk.r2_configured()
    if has_local or lake_ready:
        payload = build_payload()
        payload_path, payload_href = dk.write_and_publish_artifact("desk", payload, here)
        kpi = payload.get("kpi") or {}
        generated = payload["generated"]
        kpi_pld = "" if kpi.get("pldSe") is None else str(kpi["pldSe"])
        kpi_gas = "" if kpi.get("genGasSin") is None else str(kpi["genGasSin"])
        data_through = payload.get("dataThrough") or ""
        notes = payload.get("notes") or []
        size_note = f"{payload_path.name} ({payload_path.stat().st_size:,} bytes)"
    else:
        shell = out_path if out_path.exists() else DEFAULT_OUT
        payload_href = dk.published_payload_url(shell)
        markers = dk.published_teaser_markers(shell)
        generated = markers.get("generated") or ""
        kpi_pld = markers.get("kpi_pld_se") or ""
        kpi_gas = markers.get("kpi_gen_gas") or ""
        data_through = markers.get("data_through") or ""
        notes = []
        size_note = "reused published payload (no local lake)"
        print("No desk lake/parquet; rebuilding HTML shell against the published payload.")
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=generated,
        KPI_PLD_SE=kpi_pld,
        KPI_GEN_GAS=kpi_gas,
        DATA_THROUGH=data_through,
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_TYPO_WEIGHT_CSS=kit.typo_weight_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_TABLE_SORT=kit.JS_TABLE_SORT,
        SHARED_JS_QUERY_STATE=kit.JS_QUERY_STATE,
        SHARED_SHARE_BUTTON=kit.share_link_button_html(css_class="series-btn"),
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_ASOF=kit.refreshed_local_js(),
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("desk"),
        SHARED_MASTHEAD=kit.masthead_html("desk"),
        SHARED_METHODOLOGY=kit.methodology_html("desk"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote dashboard shell ({len(html):,} bytes) + {size_note} -> {payload_href}")
    if notes:
        print("  notes:", "; ".join(notes).encode("ascii", "replace").decode("ascii"))
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
