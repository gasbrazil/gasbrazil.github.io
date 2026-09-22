"""Build unified Pipeline Monitor dashboard (/monitor/).

Integrates TAG Mago operational line pack & zone forecasts with NTS OnTime
real-time SCADA telemetry into a single tabbed dashboard: [TAG Mago] [NTS OnTime].
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "mago"))
sys.path.insert(0, str(ROOT / "nts"))

import dashboard_kit as kit  # noqa: E402
import data_kit as dk  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "index.html"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_ts(ts_str: str | None) -> dt.datetime | None:
    if not ts_str:
        return None
    s = ts_str.strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        val = dt.datetime.fromisoformat(s)
        if val.tzinfo is None:
            val = val.replace(tzinfo=dt.UTC)
        return val
    except Exception:
        return None


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__HEAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_tag_lp: __KPI_TAG_LP__
     kpi_nts_lp: __KPI_NTS_LP__
     kpi_nts_rate: __KPI_NTS_RATE__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; font-weight: 300; }
header.dash-head { display: flex; flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; width: auto; }

.monitor-tabbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 12px;
  padding-bottom: 0;
  border-bottom: 1px solid var(--border);
}
.monitor-tabs {
  display: inline-flex;
  gap: 4px;
}
.monitor-tabs button {
  appearance: none;
  border: 1px solid transparent;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-display, var(--font));
  font-size: 12.5px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: var(--radius-sm, 4px) var(--radius-sm, 4px) 0 0;
  cursor: pointer;
  transition: color 120ms ease, background 120ms ease, border-color 120ms ease;
}
.monitor-tabs button[aria-pressed="true"] { color: var(--text); background: var(--panel); border-bottom-color: var(--accent); }
.monitor-tabs button:hover { background: var(--accent-soft); }
.monitor-tabs button[aria-pressed="true"]:hover { background: var(--panel-grad-hover, var(--panel)); }
.monitor-tab-actions { display: inline-flex; align-items: center; gap: 8px; }
@media (max-width: 680px) {
  .monitor-tabbar { flex-wrap: wrap; gap: 6px; }
  .monitor-tab-actions { width: 100%; justify-content: space-between; padding-bottom: 4px; }
}

.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 16px 0 0; }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }

.panel { margin: 0 0 10px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.panel-tight { padding: 10px 12px; }
.panel h2 { margin: 0 0 .2rem; font-size: .98rem; font-weight: 500; }
.panel p.sub { margin: 0 0 .5rem; color: var(--muted); font-size: .8rem; font-weight: 200; line-height: 1.35; }
.panel p.sub.compact { margin-bottom: .35rem; }
.panel-head-row { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }

/* KPI Grid & Cards */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 6px; margin-bottom: 10px; }
.kpi { padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--panel); position: relative; min-height: 68px; display: flex; flex-direction: column; justify-content: space-between; }
.kpi .label { color: var(--muted); font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; }
.kpi .val { font-size: 1.15rem; margin-top: 2px; font-variant-numeric: tabular-nums; font-weight: 400; color: var(--text); display: flex; align-items: baseline; gap: 4px; }
.kpi .val .unit { font-size: .85rem; font-weight: 300; color: var(--muted); }
.kpi .sub-val { font-size: 11px; color: var(--muted); margin-top: 2px; font-variant-numeric: tabular-nums; display: flex; align-items: center; gap: 4px; }

/* Badges */
.badge-target { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.badge-success { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.badge-warning { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.badge-danger { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.badge-unknown { background: rgba(156, 163, 175, 0.15); color: #9ca3af; }
.zone-pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; border: 1px solid transparent; }
.zone-pill.badge-target { background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
.zone-pill.badge-success { background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.25); color: #10b981; }
.zone-pill.badge-warning { background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.3); color: #f59e0b; }
.zone-pill.badge-danger { background: rgba(239, 68, 68, 0.14); border-color: rgba(239, 68, 68, 0.35); color: #ef4444; }

.badge-pack { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.badge-pack.packing { background: rgba(16, 185, 129, 0.14); color: #10b981; }
.badge-pack.unpacking { background: rgba(245, 158, 11, 0.14); color: #f59e0b; }

/* Charts & Toolbars */
.chart-box { position: relative; width: 100%; min-height: 220px; }
.chart-box.chart-sm { min-height: 200px; }
.chart-box.chart-lp-box { min-height: 260px; height: 260px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11px; margin-top: 6px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend span::before { content: ""; display: inline-block; width: 14px; height: 2px; background: currentColor; }
.legend span.dash::before { border-top: 2px dashed currentColor; background: transparent; height: 0; }

.range-toggle-group { display: inline-flex; border: 1px solid var(--border-strong); border-radius: 4px; padding: 1px; gap: 2px; }
.range-btn { background: transparent; border: none; padding: 3px 8px; font-size: 11px; font-weight: 400; color: var(--muted); cursor: pointer; border-radius: 3px; font-family: var(--font); transition: all 0.15s ease; }
.range-btn:hover { background: var(--accent-soft); color: var(--text); }
.range-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text); font-weight: 600; }

.seg-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; }
.seg button { background: var(--panel); color: var(--muted); border: none; padding: 4px 10px; font-size: 11px; cursor: pointer; font-family: var(--font); }
.seg button.on { background: var(--accent-soft); color: var(--text); font-weight: 600; }

.filter-bar { display: flex; align-items: center; gap: 8px; margin: 8px 0 6px; flex-wrap: wrap; }
.btn-clear { border: 1px solid var(--border-strong); background: var(--panel); color: var(--muted); font-size: 11px; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-family: var(--font); }
.btn-clear:hover { background: var(--accent-soft); color: var(--text); }
.filter-matrix { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.filter-chip { border: 1px solid var(--border); background: var(--panel); color: var(--muted); font-size: 11px; padding: 2px 7px; border-radius: 3px; cursor: pointer; font-family: var(--font); }
.filter-chip.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text); font-weight: 600; }
.is-hidden { display: none !important; }

/* Tables & Folds */
.panel-fold { margin: 0 0 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.panel-fold summary { padding: 8px 12px; font-size: .98rem; font-weight: 500; cursor: pointer; user-select: none; }
.panel-fold .fold-body { padding: 8px 12px 12px; }
.data-table-wrap { overflow-x: auto; max-height: 440px; border: 1px solid var(--border); border-radius: 4px; margin-top: 6px; }
.data-table, .lp-table, .faixas-table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
.data-table th, .lp-table th, .faixas-table th { position: sticky; top: 0; background: var(--bg); color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; padding: 6px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; z-index: 5; }
.data-table td, .lp-table td, .faixas-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; font-variant-numeric: tabular-nums; }
.data-table tr:hover td, .lp-table tr:hover td, .faixas-table tr:hover td { background: var(--accent-soft); }
.lp-table th.num, .lp-table td.num, .data-table th.num, .data-table td.num { text-align: right; }

/* Heatmap Grids */
.hm-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 8px 0; }
.hm-stat-card { padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); }
.hm-stat-label { font-size: 10px; text-transform: uppercase; color: var(--muted); letter-spacing: .04em; }
.hm-stat-val { font-size: 1.1rem; font-weight: 500; margin-top: 1px; font-variant-numeric: tabular-nums; }
.hm-calendar-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(36px, 1fr)); gap: 3px; margin-top: 8px; }
.hm-day-cell { height: 32px; border-radius: 3px; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 10px; cursor: pointer; position: relative; border: 1px solid transparent; }
.hm-day-cell:hover { border-color: var(--text); }
.hm-day-cell .num { font-weight: 600; line-height: 1; }
.hm-day-cell .tag { font-size: 8px; opacity: .85; }

/* NTS Chart Specific */
.chart-svg-box { width: 100%; height: 260px; min-height: 260px; position: relative; user-select: none; }
.chart-svg { width: 100%; height: 100%; overflow: visible; }
.chart-tooltip { position: absolute; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 11.5px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); opacity: 0; transition: opacity 0.12s ease; z-index: 20; transform: translate(-50%, -115%); white-space: nowrap; }
.chart-tooltip b { color: var(--accent); }

.asof-footer { font-size: 11.5px; color: var(--muted); margin-bottom: 8px; display: flex; gap: 12px; align-items: center; }
.asof-label { text-transform: uppercase; font-size: 10px; letter-spacing: .05em; color: var(--muted2); }
.asof-val { font-variant-numeric: tabular-nums; }
footer { margin-top: 24px; padding: 14px 0 28px; font-size: 12px; color: var(--muted); border-top: 1px solid var(--border); }
__SHARED_TYPO_WEIGHT_CSS__
</style>
</head>
<body>
<a class="skip-link" href="#monitor-tabs" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  __SHARED_MASTHEAD__
  <div class="header-right">
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>

<div class="monitor-tabbar">
  <div class="monitor-tabs" id="monitor-tabs" role="tablist" aria-label="Pipeline monitor views">
    <button type="button" role="tab" data-tab="tag" id="tab-btn-tag" aria-pressed="true" data-i18n="monitorTabTag">TAG Mago</button>
    <button type="button" role="tab" data-tab="nts" id="tab-btn-nts" aria-pressed="false" data-i18n="monitorTabNts">NTS OnTime</button>
  </div>
  <div class="monitor-tab-actions">
    <div class="health-pulse-group" id="health-pulse-group">
      <span class="health-pill" id="health-tag-pill" title="TAG Mago telemetry status">
        <span class="__TAG_DOT_CLASS__" id="health-tag-dot"></span>
        <span class="tso-code">TAG</span>
        <span class="health-time" id="health-tag-time">__TAG_HEALTH_TIME__</span>
      </span>
      <span class="health-pill" id="health-nts-pill" title="NTS OnTime telemetry status">
        <span class="__NTS_DOT_CLASS__" id="health-nts-dot"></span>
        <span class="tso-code">NTS</span>
        <span class="health-time" id="health-nts-time">__NTS_HEALTH_TIME__</span>
      </span>
    </div>
    __SHARED_SHARE_BUTTON__
  </div>
</div>

<!-- ======================= TAG MAGO SUBPAGE ======================= -->
<div id="monitor-view-tag">
  <div class="kpi-row">
    <div class="kpi">
      <div class="label" data-i18n="magoKpiLinepack">TAG Line Pack</div>
      <div class="val" id="kpi-lp">—</div>
      <div class="sub-val" id="kpi-lp-m3">—</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="magoKpiZone">Operating Zone</div>
      <div class="val" id="kpi-zone">—</div>
      <div class="sub-val" id="kpi-zone-sub" data-i18n="magoKpiZoneSub">Commercial tolerance tier</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="gridKpiNationalPack">National Grid Pack</div>
      <div class="val" id="tag-nat-lp-val"><span id="tag-nat-lp-num">__NAT_LP_VAL__</span> <span class="unit">Mm³</span></div>
      <div class="sub-val" id="tag-nat-lp-sub">__NAT_LP_SUB__</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="gridKpiNetBalance">Net System Balance</div>
      <div class="val" id="tag-nat-pack-val"><span class="badge-pack __NAT_PACK_CLASS__" id="tag-nat-pack-badge">__NAT_PACK_ARROW__ <span id="tag-nat-pack-state" data-i18n="__NAT_PACK_I18N__">__NAT_PACK_STATE__</span></span></div>
      <div class="sub-val" id="tag-nat-bal-sub">__NAT_BAL_SUB__</div>
    </div>
  </div>

  <section class="panel panel-tight">
    <div class="panel-head-row">
      <div style="display:flex;align-items:center;">
        <h2 data-i18n="magoLinepackTitle">TAG Line Pack — Integrated Network</h2>
        <button type="button" class="infodot" data-info="Hourly actual (solid) and short-horizon forecast (dashed) with TAG commercial tolerance risk bands." title="Hourly actual (solid) and short-horizon forecast (dashed) with TAG commercial tolerance risk bands." aria-label="Info">i</button>
      </div>
      <div id="linepack-zone-pill" class="zone-pill">—</div>
    </div>
    <div class="chart-box chart-lp-box"><div id="chart-lp"></div></div>
    <div class="legend">
      <span style="color:var(--tso-tag,#0066cc)" data-i18n="magoLegendActual">Actual</span>
      <span class="dash" style="color:#888" data-i18n="magoLegendForecast">Forecast</span>
    </div>
  </section>

  <details class="panel-fold" id="faixas-panel">
    <summary style="display:flex;align-items:center;">
      <span data-i18n="magoFaixasTitle">Operating Risk & Imbalance Tolerance Bands</span>
      <button type="button" class="infodot" data-info="Commercial balancing tolerance thresholds established for TAG's integrated pipeline system. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions." title="Commercial balancing tolerance thresholds established for TAG's integrated pipeline system. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions." aria-label="Info" onclick="event.stopPropagation()">i</button>
    </summary>
    <div class="fold-body">
      <div id="faixas-grid"></div>
    </div>
  </details>

  <section class="panel panel-tight" id="heatmap-panel">
    <div class="panel-head-row">
      <div>
        <h2 data-i18n="magoHeatmapTitle">Operating Risk & Imbalance Breach Heatmap</h2>
        <p class="sub compact" data-i18n="magoHeatmapSub">Daily historical tracking of TAG integrated inventory across commercial tolerance tiers and correlation with transport balancing actions.</p>
      </div>
      <div class="hist-filter-group">
        <button type="button" id="btn-hm-all" class="range-btn active" data-i18n="magoHmAll">All Days</button>
        <button type="button" id="btn-hm-alerts" class="range-btn" data-i18n="magoHmAlerts">Alerts & Breaches</button>
        <button type="button" id="btn-hm-critical" class="range-btn" data-i18n="magoHmCritical">Critical Only</button>
      </div>
    </div>
    <div class="hm-summary-grid" id="hm-summary-grid"></div>
    <div class="hm-calendar-grid" id="hm-calendar-grid"></div>
    <div class="hm-poc-callout" id="hm-poc-callout"></div>
  </section>

  <details class="panel-fold">
    <summary data-i18n="magoLinepackHistTitle">Line pack history</summary>
    <div class="fold-body">
      <p class="sub compact" data-i18n="magoLinepackHistSub">Hourly integrated inventory from cached snapshots (newest wins on overlap).</p>
      <div id="hm-selected-day-indicator" style="display:none;margin-bottom:8px;padding:4px 10px;background:var(--accent-soft);border:1px solid var(--accent);border-radius:4px;font-size:11px;align-items:center;justify-content:space-between;">
        <span><strong id="hm-filter-day-text"></strong></span>
        <button type="button" id="btn-clear-day-filter" style="border:none;background:none;color:var(--accent);font-weight:600;cursor:pointer;font-size:11px;">✕ Clear</button>
      </div>
      <div class="chart-box chart-sm"><div id="chart-lp-hist"></div></div>
      <div class="filter-bar">
        <button type="button" id="btn-lp-csv" class="btn-clear" data-i18n="magoLpCsv">Download line pack CSV</button>
        <div class="hist-filter-group" style="margin-left:auto;">
          <button type="button" id="btn-hist-all" class="range-btn active" data-i18n="magoHistAll">All Hours</button>
          <button type="button" id="btn-hist-alerts" class="range-btn" data-i18n="magoHistAlerts">Alerts & Breaches Only</button>
        </div>
      </div>
      <div class="data-table-wrap">
        <table class="lp-table" id="lp-table">
          <thead><tr>
            <th data-col="observedAt" data-i18n="magoColObserved">Observed (UTC)</th>
            <th data-col="valueMm3" class="num" data-i18n="magoColMm3">Mm³</th>
            <th data-col="valueM3" class="num" data-i18n="magoColM3">m³</th>
            <th data-col="zone" data-i18n="magoColZone">Operating Zone</th>
            <th data-col="snapshotAt" data-i18n="magoColSnapshot">Source snapshot</th>
          </tr></thead>
          <tbody id="lp-tbody"></tbody>
        </table>
      </div>
    </div>
  </details>

  <section class="panel panel-tight" id="consume-panel">
    <div class="panel-head-row">
      <div>
        <h2 data-i18n="magoZonesTitle">TAG Consumption Estimate Analysis</h2>
      </div>
      <div class="seg-row" role="group" aria-label="Chart options">
        <div class="seg">
          <button type="button" data-gran="state" class="on" data-i18n="magoByState">States</button>
          <button type="button" data-gran="zone" data-i18n="magoByZone">Zones</button>
        </div>
        <div class="seg">
          <button type="button" data-mode="line" class="on" data-i18n="magoChartLine">Lines</button>
          <button type="button" data-mode="stack" data-i18n="magoChartStack">Stack</button>
        </div>
      </div>
    </div>
    <div class="chart-box"><div id="chart-zones"></div></div>
    <div class="filter-bar">
      <button type="button" id="btn-select-zones" class="btn-clear" data-i18n="magoSelectAll">Select all</button>
      __SHARED_CLEAR_SELECTION__
      <span id="selection-hint" class="hint" style="font-size:11px;color:var(--muted);margin-left:auto;"></span>
    </div>
    <div id="filter-state" class="filter-matrix"></div>
    <div id="filter-zone" class="filter-matrix zone-grid is-hidden"></div>
  </section>

  <div class="sources">
    <span class="sources-label" data-i18n="sources">Sources</span>
    <a class="pill" href="https://mago.ntag.com.br/empacotamento" target="_blank" rel="noopener">TAG Mago<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  </div>
</div>

<!-- ======================= NTS ONTIME SUBPAGE ======================= -->
<div id="monitor-view-nts" hidden>
  <div class="kpi-row">
    <div class="kpi">
      <div class="label" data-i18n="ntsKpiCurrent">NTS Line Pack</div>
      <div class="val" id="nts-kpi-cur"><span id="nts-cur-mm3">__CUR_MM3__</span> <span class="unit">Mm³</span></div>
      <div class="sub-val" id="nts-cur-m3">__CUR_M3__ m³</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="ntsKpiState">Packing State & Rate</div>
      <div class="val" id="nts-kpi-state"><span class="badge-pack __PACK_CLASS__" id="nts-pack-badge">__PACK_ARROW__ <span id="nts-pack-state" data-i18n="__PACK_STATE_I18N__">__PACK_STATE__</span></span></div>
      <div class="sub-val" id="nts-rate-sub"><span id="nts-rate-val">__RATE_VAL__</span> m³/h · <span id="nts-rate-daily">__RATE_DAILY__</span> Mm³/d eq.</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="gridKpiNationalPack">National Grid Pack</div>
      <div class="val" id="nts-nat-lp-val"><span id="nts-nat-lp-num">__NAT_LP_VAL__</span> <span class="unit">Mm³</span></div>
      <div class="sub-val" id="nts-nat-lp-sub">__NAT_LP_SUB__</div>
    </div>
    <div class="kpi">
      <div class="label" data-i18n="gridKpiNetBalance">Net System Balance</div>
      <div class="val" id="nts-nat-pack-val"><span class="badge-pack __NAT_PACK_CLASS__" id="nts-nat-pack-badge">__NAT_PACK_ARROW__ <span id="nts-nat-pack-state" data-i18n="__NAT_PACK_I18N__">__NAT_PACK_STATE__</span></span></div>
      <div class="sub-val" id="nts-nat-bal-sub">__NAT_BAL_SUB__</div>
    </div>
  </div>

  <section class="panel panel-tight">
    <div class="panel-head-row">
      <div style="display:flex;align-items:center;">
        <h2 data-i18n="ntsLinepackTitle">NTS Line Pack — Transmission Network</h2>
        <button type="button" class="infodot" data-info="SCADA line pack telemetry (solid amber) with historical mean guideline (dashed)." title="SCADA line pack telemetry (solid amber) with historical mean guideline (dashed)." aria-label="Info">i</button>
      </div>
      <div class="range-toggle-group" role="group" aria-label="Chart time window">
        <button type="button" class="range-btn active" data-range="24h" onclick="setNtsChartRange('24h')">24H</button>
        <button type="button" class="range-btn" data-range="7d" onclick="setNtsChartRange('7d')">7D</button>
        <button type="button" class="range-btn" data-range="all" onclick="setNtsChartRange('all')" data-i18n="rangeAll">All</button>
      </div>
    </div>
    <div class="chart-svg-box chart-lp-box" id="nts-chart-box">
      <svg class="chart-svg" id="linepack-chart" viewBox="0 0 1000 260" preserveAspectRatio="none"></svg>
      <div class="chart-tooltip" id="nts-chart-tooltip"></div>
    </div>
  </section>

  <details class="panel-fold">
    <summary data-i18n="tableTitle">Line pack observations history</summary>
    <div class="fold-body">
      <div class="filter-bar">
        <button type="button" class="btn-clear" onclick="exportNtsTableCsv()" data-i18n="btnExportCsv">Download CSV</button>
      </div>
      <div class="data-table-wrap">
        <table class="data-table" id="telemetry-table">
          <thead>
            <tr>
              <th data-i18n="thObservedUtc">Observed (UTC)</th>
              <th data-i18n="thObservedBrt">Observed (BRT)</th>
              <th data-i18n="thVolumeMm3" class="num">Volume (Mm³)</th>
              <th data-i18n="thVolumeM3" class="num">Volume (m³)</th>
              <th data-i18n="thRate" class="num">Rate (m³/h)</th>
              <th data-i18n="thStatus">Status</th>
            </tr>
          </thead>
          <tbody id="telemetry-tbody"></tbody>
        </table>
      </div>
    </div>
  </details>

  <div class="sources">
    <span class="sources-label" data-i18n="sources">Sources</span>
    <a class="pill" href="https://ntsbrasil.com/ontime" target="_blank" rel="noopener">NTS OnTime<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  </div>
</div>

<footer>
  <div class="asof-strip asof-footer" id="asof-strip">
    <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
    <span class="asof-val" id="asof-refreshed">&mdash;</span>
    <span class="asof-label" data-i18n="dataThrough">Data through</span>
    <span class="asof-val" id="asof-through">&mdash;</span>
  </div>
  __SHARED_METHODOLOGY__
  &copy; <span id="year"></span> GasBrazil.com &middot;
  <span data-i18n="monitorFooter">Pipeline Monitor: Real-time and operational linepack telemetry across Brazilian gas transmission systems.</span>
  &middot; <a href="../flows/" data-i18n="navFlows">Pipeline Flows</a>
  &middot; <a href="../desk/" data-i18n="navDesk">The Desk</a>
  &middot; <a href="../about/" data-i18n="footerAbout">About</a>
  &middot; <button type="button" class="footer-link-btn" id="link-shortcuts" data-i18n="shortcutsBtn">Shortcuts (?)</button>
</footer>
<div class="tt" id="chart-tt"></div>
</div>

<script id="nts-payload" type="application/json">
__NTS_PAYLOAD_JSON__
</script>

<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";
const MAGO_PAYLOAD_R2 = "https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev/mago/payload.json.gz";

__SHARED_JS_DECODE__
__SHARED_JS_ESCAPE_HTML__
__SHARED_JS_CSV__
__SHARED_JS_CHART_PALETTE__
__SHARED_SITE_LINKS_JS__
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__
__SHARED_JS_QUERY_STATE__

if (typeof GB_I18N !== "undefined") {
  Object.assign(GB_I18N.en, {
    monitorTabTag: "TAG Mago",
    monitorTabNts: "NTS OnTime",
    magoLinepackTitle: "TAG Line Pack — Integrated Network",
    ntsLinepackTitle: "NTS Line Pack — Transmission Network",
    magoKpiZoneSub: "Commercial tolerance tier",
    magoKpiSnapSub: "Cached Mago telemetry",
    magoKpiLinepack: "TAG Line Pack",
    ntsKpiCurrent: "NTS Line Pack",
    ntsKpiState: "Packing State & Rate",
    gridKpiNationalPack: "National Grid Pack",
    gridKpiNetBalance: "Net System Balance",
    gridStatusPacking: "Grid Packing",
    gridStatusDrafting: "Grid Drafting",
    gridStatusBalanced: "In-Balance",
    healthTag: "TAG Telemetry",
    healthNts: "NTS Telemetry",
    kpiDelta24h: "24h Change",
    kpiEnvelope24h: "24h Range",
    chartDesc: "SCADA line pack telemetry (solid amber) with historical mean guideline (dashed).",
    rangeAll: "All",
    tableTitle: "Line pack observations history",
    btnExportCsv: "Download CSV",
    thObservedUtc: "Observed (UTC)",
    thObservedBrt: "Observed (BRT)",
    thVolumeMm3: "Volume (Mm³)",
    thVolumeM3: "Volume (m³)",
    thRate: "Rate (m³/h)",
    thStatus: "Status",
    magoLinepackHistTitle: "Line pack history",
    magoLinepackHistSub: "Continuous hourly integrated inventory from cached Mago snapshots.",
    magoByState: "States",
    magoByZone: "Zones",
    magoChartLine: "Lines",
    magoChartStack: "Stack",
    magoSelectAll: "Select all",
    magoZonesTitle: "TAG Consumption Estimate Analysis",
    magoLpCsv: "Download line pack CSV",
    magoColObserved: "Observed (UTC)",
    magoColMm3: "Mm³",
    magoColM3: "m³",
    magoColZone: "Operating Zone",
    magoColSnapshot: "Source snapshot",
    magoFaixasTitle: "Operating Risk & Imbalance Tolerance Bands",
    magoFaixasSub: "TAG commercial balancing tolerance thresholds. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions.",
    magoHistAll: "All Hours",
    magoHistAlerts: "Alerts & Breaches Only",
  });
  Object.assign(GB_I18N.pt, {
    monitorTabTag: "TAG Mago",
    monitorTabNts: "NTS OnTime",
    magoLinepackTitle: "TAG Line Pack — Malha Integrada",
    ntsLinepackTitle: "NTS Line Pack — Malha de Transporte",
    magoKpiZoneSub: "Faixa de tolerância comercial",
    magoKpiSnapSub: "Telemetria em cache do Mago",
    magoKpiLinepack: "Line Pack TAG",
    ntsKpiCurrent: "Line Pack NTS",
    ntsKpiState: "Estado e Taxa de Empacotamento",
    gridKpiNationalPack: "Empacotamento Nacional",
    gridKpiNetBalance: "Balanço Líquido do Sistema",
    gridStatusPacking: "Sistema Empacotando",
    gridStatusDrafting: "Sistema Desempacotando",
    gridStatusBalanced: "Em Equilíbrio",
    healthTag: "Telemetria TAG",
    healthNts: "Telemetria NTS",
    kpiDelta24h: "Variação 24h",
    kpiEnvelope24h: "Faixa 24h",
    chartDesc: "Telemetria SCADA de empacotamento (âmbar) com linha-guia da média histórica (tracejado).",
    rangeAll: "Tudo",
    tableTitle: "Histórico de observações de empacotamento",
    btnExportCsv: "Baixar CSV",
    thObservedUtc: "Observado (UTC)",
    thObservedBrt: "Observado (BRT)",
    thVolumeMm3: "Volume (Mm³)",
    thVolumeM3: "Volume (m³)",
    thRate: "Taxa (m³/h)",
    thStatus: "Status",
    magoLinepackHistTitle: "Histórico de empacotamento",
    magoLinepackHistSub: "Inventário integrado horário de snapshots Mago em cache.",
    magoByState: "Estados",
    magoByZone: "Zonas",
    magoChartLine: "Linhas",
    magoChartStack: "Empilhado",
    magoSelectAll: "Selecionar tudo",
    magoZonesTitle: "Análise de Estimativa de Consumo TAG",
    magoLpCsv: "Baixar CSV de empacotamento",
    magoColObserved: "Observado (UTC)",
    magoColMm3: "Mm³",
    magoColM3: "m³",
    magoColZone: "Faixa Operacional",
    magoColSnapshot: "Snapshot de origem",
    magoFaixasTitle: "Faixas de Tolerância e Risco Operacional",
    magoFaixasSub: "Limites comerciais de tolerância da TAG. Desvios fora da faixa marginal geram penalidades ou ações operacionais.",
    magoHistAll: "Todas as Horas",
    magoHistAlerts: "Apenas Alertas e Violações",
  });
}

/* ==================== MONITOR TAB SWITCHING ==================== */
let monitorTab = "tag";

function setMonitorTab(tab) {
  if (tab !== "tag" && tab !== "nts") tab = "tag";
  monitorTab = tab;
  const tagEl = document.getElementById("monitor-view-tag");
  const ntsEl = document.getElementById("monitor-view-nts");
  if (tagEl) tagEl.hidden = (tab !== "tag");
  if (ntsEl) ntsEl.hidden = (tab !== "nts");

  document.querySelectorAll("#monitor-tabs button").forEach(b => {
    b.setAttribute("aria-pressed", b.dataset.tab === tab ? "true" : "false");
  });

  if (tab === "nts") {
    renderNtsChart();
    populateNtsTable();
  } else {
    packLinepack();
    packLinepackHistory();
    packZones();
  }
  gbWriteQuery({ tab: monitorTab === "tag" ? null : monitorTab });
  try { localStorage.setItem("monitor-tab", monitorTab); } catch (e) {}
}

function buildMonitorTabs() {
  document.querySelectorAll("#monitor-tabs button").forEach(b => {
    b.addEventListener("click", () => setMonitorTab(b.dataset.tab));
  });
}

/* ==================== NTS ONTIME LOGIC ==================== */
let NTS_PAYLOAD = {};
try {
  NTS_PAYLOAD = JSON.parse(document.getElementById("nts-payload").textContent);
} catch (e) {
  console.error("Failed to parse NTS payload:", e);
}

let ntsActiveRange = "24h";

function fmtNumNts(n, decimals) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toLocaleString("pt-BR", {
    minimumFractionDigits: decimals !== undefined ? decimals : 0,
    maximumFractionDigits: decimals !== undefined ? decimals : 0
  });
}

function filterNtsSeries(range) {
  const allPts = (NTS_PAYLOAD.series || []);
  if (!allPts.length) return [];
  const latestTs = allPts[allPts.length - 1][0];
  let cutoff = 0;
  if (range === "24h") cutoff = latestTs - 24 * 3600;
  else if (range === "7d") cutoff = latestTs - 7 * 86400;
  else cutoff = 0;
  return allPts.filter(p => p[0] >= cutoff);
}

function setNtsChartRange(range) {
  ntsActiveRange = range;
  document.querySelectorAll(".range-btn[data-range]").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-range") === range);
  });
  renderNtsChart();
}

function renderNtsChart() {
  const pts = filterNtsSeries(ntsActiveRange);
  const svg = document.getElementById("linepack-chart");
  if (!svg || !pts.length) return;

  const W = 1000, H = 260;
  const L = 56, R = 24, T = 16, B = 32;
  const vals = pts.map(p => p[1]);
  let minV = Math.min(...vals);
  let maxV = Math.max(...vals);

  const pad = (maxV - minV) * 0.12 || 1.0;
  minV = Math.floor((minV - pad) * 2) / 2;
  maxV = Math.ceil((maxV + pad) * 2) / 2;

  const n = pts.length;
  const x = i => L + (i / (n - 1)) * (W - L - R);
  const y = v => T + (1 - (v - minV) / (maxV - minV)) * (H - T - B);

  let gridSvg = "";
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = minV + ((maxV - minV) * i) / ticks;
    const yPos = y(v);
    gridSvg += `<line x1="${L}" y1="${yPos}" x2="${W - R}" y2="${yPos}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3"/>`;
    gridSvg += `<text x="${L - 8}" y="${yPos + 4}" fill="var(--muted)" font-size="11" font-family="var(--font)" text-anchor="end">${fmtNumNts(v, 1)}</text>`;
  }

  const refMean = (NTS_PAYLOAD.ref && NTS_PAYLOAD.ref.mean) || 46.2;
  let refSvg = "";
  if (refMean >= minV && refMean <= maxV) {
    const yMean = y(refMean);
    refSvg = `
      <line x1="${L}" y1="${yMean}" x2="${W - R}" y2="${yMean}" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.65"/>
      <text x="${W - R - 6}" y="${yMean - 6}" fill="var(--muted)" font-size="10" font-family="var(--font)" text-anchor="end">Mean: ${refMean} Mm³</text>
    `;
  }

  let xTicksSvg = "";
  const step = Math.max(1, Math.floor(n / 6));
  for (let i = 0; i < n; i += step) {
    const xPos = x(i);
    const d = new Date(pts[i][0] * 1000);
    const label = ntsActiveRange === "24h"
      ? d.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
    xTicksSvg += `<text x="${xPos}" y="${H - 8}" fill="var(--muted)" font-size="10.5" font-family="var(--font)" text-anchor="middle">${label}</text>`;
  }

  let linePath = "";
  pts.forEach((p, i) => {
    linePath += (i === 0 ? "M" : "L") + `${x(i).toFixed(1)} ${y(p[1]).toFixed(1)} `;
  });
  const areaPath = linePath + `L ${x(n - 1).toFixed(1)} ${H - B} L ${x(0).toFixed(1)} ${H - B} Z`;

  const lastX = x(n - 1).toFixed(1);
  const lastY = y(pts[n - 1][1]).toFixed(1);

  svg.innerHTML = `
    <defs>
      <linearGradient id="nts-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--tso-nts, #f59e0b)" stop-opacity="0.25"/>
        <stop offset="100%" stop-color="var(--tso-nts, #f59e0b)" stop-opacity="0.01"/>
      </linearGradient>
    </defs>
    ${gridSvg}
    ${refSvg}
    ${xTicksSvg}
    <path d="${areaPath}" fill="url(#nts-grad)"/>
    <path d="${linePath}" fill="none" stroke="var(--tso-nts, #f59e0b)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
    <line id="chart-crosshair" x1="0" y1="${T}" x2="0" y2="${H - B}" stroke="var(--tso-nts, #f59e0b)" stroke-width="1.2" stroke-dasharray="3 3" opacity="0"/>
    <circle id="chart-hover-dot" r="4.5" fill="var(--tso-nts, #f59e0b)" stroke="#fff" stroke-width="1.5" opacity="0"/>
    <circle cx="${lastX}" cy="${lastY}" r="4.5" fill="var(--tso-nts, #f59e0b)" stroke="#fff" stroke-width="1.5"/>
  `;

  hookNtsTooltip(pts, x, y, W, H);
}

function hookNtsTooltip(pts, x, y, W, H) {
  const box = document.getElementById("nts-chart-box");
  const svg = document.getElementById("linepack-chart");
  const tip = document.getElementById("nts-chart-tooltip");
  const cross = svg.querySelector("#chart-crosshair");
  const dot = svg.querySelector("#chart-hover-dot");
  if (!box || !tip || !cross || !dot) return;

  const n = pts.length;

  function onMove(e) {
    const rect = svg.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const relX = clientX - rect.left;
    let frac = relX / rect.width;
    frac = Math.max(0, Math.min(1, frac));

    const idx = Math.min(n - 1, Math.max(0, Math.round(frac * (n - 1))));
    const p = pts[idx];
    const vx = x(idx);
    const vy = y(p[1]);

    cross.setAttribute("x1", vx);
    cross.setAttribute("x2", vx);
    cross.style.opacity = 0.9;

    dot.setAttribute("cx", vx);
    dot.setAttribute("cy", vy);
    dot.style.opacity = 1;

    const d = new Date(p[0] * 1000);
    const dtBrt = d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" }) +
      " " + d.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
    const rateSign = p[2] >= 0 ? "+" : "";

    tip.style.opacity = 1;
    tip.style.left = (vx / W) * 100 + "%";
    tip.style.top = (vy / H) * 100 + "%";
    tip.innerHTML = `
      <div><b>${fmtNumNts(p[1], 2)} Mm³</b></div>
      <div style="color:var(--muted);margin-top:2px;">Rate: ${rateSign}${fmtNumNts(p[2])} m³/h</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px;">${dtBrt} BRT</div>
    `;
  }

  function onLeave() {
    cross.style.opacity = 0;
    dot.style.opacity = 0;
    tip.style.opacity = 0;
  }

  box.onmousemove = onMove;
  box.onmouseleave = onLeave;
  box.ontouchstart = onMove;
  box.ontouchmove = onMove;
  box.ontouchend = onLeave;
}

function populateNtsTable() {
  const tbody = document.getElementById("telemetry-tbody");
  if (!tbody) return;
  const rows = (NTS_PAYLOAD.table || []);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);">No data available</td></tr>';
    return;
  }

  let htmlStr = "";
  rows.forEach(r => {
    const isPack = r.state === "packing";
    const arrow = isPack ? "▲" : "▼";
    const sign = isPack ? "+" : "";
    const badgeClass = isPack ? "packing" : "unpacking";
    const stateKey = isPack ? "ntsKpiPacking" : "ntsKpiUnpacking";
    const stateText = (typeof t === "function" ? t(stateKey) : null) || (isPack ? "Packing" : "Unpacking");

    htmlStr += `
      <tr>
        <td class="mono">${r.ts_utc}</td>
        <td class="mono">${r.ts_brt}</td>
        <td class="num"><b>${fmtNumNts(r.val_mm3, 3)}</b></td>
        <td class="num">${fmtNumNts(r.val_m3)}</td>
        <td class="num">${sign}${fmtNumNts(r.rate)}</td>
        <td>
          <span class="badge-pack ${badgeClass}">
            ${arrow} <span>${stateText}</span>
          </span>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = htmlStr;
}

function exportNtsTableCsv() {
  const rows = (NTS_PAYLOAD.table || []);
  if (!rows.length) return;
  let csv = "observed_utc,observed_brt,volume_mm3,volume_m3,rate_m3_h,status\n";
  rows.forEach(r => {
    csv += `${r.ts_utc},${r.ts_brt},${r.val_mm3},${r.val_m3},${r.rate},${r.state}\n`;
  });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nts_linepack_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/* ==================== TAG MAGO LOGIC ==================== */
let DATA = null;
let LP = {}, LP_HIST = {}, LP_ROWS = [], ZONE_SERIES = {}, GROUP_SERIES = {};
let selectedZones = new Set();
let selectedGroups = new Set();
let zoneMode = "line";
let zoneGran = "state";
let histFilter = "all";
let hmFilter = "all";
let selectedDay = null;

function fmtMm3(v) {
  if (v == null || !isFinite(v)) return "—";
  return (v / 1e6).toFixed(2) + " Mm³";
}

function setMagoKpis() {
  if (!DATA) return;
  const lpEl = document.getElementById("kpi-lp");
  if (lpEl) {
    lpEl.textContent = DATA.kpiLinepackMm3 != null
      ? DATA.kpiLinepackMm3.toFixed(2) + " Mm³" : fmtMm3(DATA.kpiLinepackM3);
  }
  const lpM3El = document.getElementById("kpi-lp-m3");
  if (lpM3El) {
    const m3Val = DATA.kpiLinepackM3 != null ? DATA.kpiLinepackM3 : (DATA.kpiLinepackMm3 != null ? DATA.kpiLinepackMm3 * 1e6 : null);
    lpM3El.textContent = m3Val != null ? Math.round(m3Val).toLocaleString("pt-BR") + " m³" : "—";
  }
  const snapEl = document.getElementById("kpi-snap");
  if (snapEl) snapEl.textContent = DATA.snapshotAt || "—";
  const z = DATA.kpiZone;
  const kpiZoneEl = document.getElementById("kpi-zone");
  const pillEl = document.getElementById("linepack-zone-pill");
  if (z) {
    const lang = document.documentElement.getAttribute("data-lang") || "en";
    const label = lang === "pt" ? (z.namePt || z.name) : z.name;
    if (kpiZoneEl) {
      kpiZoneEl.innerHTML = `<span class="zone-pill ${escapeHtml(z.badgeClass || '')}">${escapeHtml(label)}</span>`;
    }
    if (pillEl) {
      pillEl.className = "zone-pill " + (z.badgeClass || "");
      pillEl.textContent = label;
    }
  }
}

function updateTelemetryHealth() {
  const now = Date.now();
  // TAG telemetry health
  if (DATA) {
    const snapStr = DATA.snapshotIso || DATA.snapshotAt;
    if (snapStr) {
      const snapTs = new Date(snapStr.length > 10 && !snapStr.endsWith("Z") && !snapStr.includes("+") ? snapStr + "Z" : snapStr).getTime();
      const diffMin = Math.round((now - snapTs) / 60000);
      const el = document.getElementById("health-tag-time");
      const dot = document.getElementById("health-tag-dot");
      const pill = document.getElementById("health-tag-pill");
      if (el && dot) {
        if (isNaN(diffMin) || diffMin < 0) {
          el.textContent = "Live";
        } else if (diffMin < 60) {
          el.textContent = diffMin + "m ago";
        } else {
          el.textContent = Math.floor(diffMin / 60) + "h ago";
        }
        dot.className = "pulse-dot" + (diffMin > 360 ? " stale" : (diffMin > 180 ? " amber" : ""));
        if (pill) pill.title = "TAG Mago: " + (DATA.snapshotAt || snapStr);
      }
    }
  }
  // NTS telemetry health
  const ntsKpis = (NTS_PAYLOAD && NTS_PAYLOAD.kpis) || {};
  const ntsSnapStr = NTS_PAYLOAD.last_updated_iso || NTS_PAYLOAD.last_updated_utc || ntsKpis.last_updated_iso || ntsKpis.last_updated_utc;
  if (ntsSnapStr) {
    const snapTs = new Date(ntsSnapStr.length > 10 && !ntsSnapStr.endsWith("Z") && !ntsSnapStr.includes("+") ? ntsSnapStr + "Z" : ntsSnapStr).getTime();
    const diffMin = Math.round((now - snapTs) / 60000);
    const el = document.getElementById("health-nts-time");
    const dot = document.getElementById("health-nts-dot");
    const pill = document.getElementById("health-nts-pill");
    if (el && dot) {
      if (isNaN(diffMin) || diffMin < 0) {
        el.textContent = "Live";
      } else if (diffMin < 60) {
        el.textContent = diffMin + "m ago";
      } else {
        el.textContent = Math.floor(diffMin / 60) + "h ago";
      }
      dot.className = "pulse-dot" + (diffMin > 360 ? " stale" : (diffMin > 180 ? " amber" : ""));
      if (pill) pill.title = "NTS OnTime: " + (NTS_PAYLOAD.last_updated_utc || ntsSnapStr);
    }
  }
}

function updateNationalGridKpis() {
  let tagLpMm3 = null;
  if (DATA) {
    if (DATA.kpiLinepackMm3 != null) tagLpMm3 = DATA.kpiLinepackMm3;
    else if (DATA.kpiLinepackM3 != null) tagLpMm3 = DATA.kpiLinepackM3 / 1e6;
  }
  let ntsLpMm3 = null;
  if (NTS_PAYLOAD) {
    if (NTS_PAYLOAD.current_mm3 != null) ntsLpMm3 = NTS_PAYLOAD.current_mm3;
    else if (NTS_PAYLOAD.kpis && NTS_PAYLOAD.kpis.current_mm3 != null) ntsLpMm3 = NTS_PAYLOAD.kpis.current_mm3;
    else if (NTS_PAYLOAD.series && NTS_PAYLOAD.series.length) {
      ntsLpMm3 = NTS_PAYLOAD.series[NTS_PAYLOAD.series.length - 1][1];
    }
  }

  // Combined Linepack
  if (tagLpMm3 != null && ntsLpMm3 != null) {
    const totalMm3 = tagLpMm3 + ntsLpMm3;
    const tagPct = Math.round((tagLpMm3 / totalMm3) * 100);
    const ntsPct = 100 - tagPct;
    ["tag-nat-lp-num", "nts-nat-lp-num"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = totalMm3.toFixed(2);
    });
    ["tag-nat-lp-sub", "nts-nat-lp-sub"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = `TAG ${tagPct}% · NTS ${ntsPct}%`;
    });
  }

  // Combined Packing Rate
  let ntsRate = 0;
  if (NTS_PAYLOAD) {
    if (NTS_PAYLOAD.rate_m3_h != null) ntsRate = NTS_PAYLOAD.rate_m3_h;
    else if (NTS_PAYLOAD.kpis && NTS_PAYLOAD.kpis.rate_m3_h != null) ntsRate = NTS_PAYLOAD.kpis.rate_m3_h;
  }
  let tagRate = 0;
  if (DATA && DATA.linepack && DATA.linepack.actual && DATA.linepack.actual.values && DATA.linepack.actual.values.length >= 2) {
    const vals = DATA.linepack.actual.values;
    tagRate = vals[vals.length - 1] - vals[vals.length - 2];
  }
  const combRate = Math.round(tagRate + ntsRate);
  const combDaily = ((combRate * 24) / 1e6).toFixed(2);
  const isPack = combRate > 2000;
  const isDraft = combRate < -2000;
  const packClass = isPack ? "packing" : (isDraft ? "unpacking" : "packing");
  const arrow = isPack ? "▲" : (isDraft ? "▼" : "◆");
  const stateKey = isPack ? "gridStatusPacking" : (isDraft ? "gridStatusDrafting" : "gridStatusBalanced");
  const lang = document.documentElement.getAttribute("data-lang") || "en";
  const dict = (typeof GB_I18N !== "undefined" && GB_I18N[lang]) || {};
  const stateLabel = dict[stateKey] || (isPack ? "Grid Packing" : (isDraft ? "Grid Drafting" : "In-Balance"));
  const sign = combRate >= 0 ? "+" : "";
  const rateFmt = sign + Math.round(combRate).toLocaleString("pt-BR");
  const dailyFmt = sign + combDaily;
  const subText = `${rateFmt} m³/h · ${dailyFmt} Mm³/d eq.`;

  ["tag-nat-pack-badge", "nts-nat-pack-badge"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.className = "badge-pack " + packClass;
      el.innerHTML = `${arrow} <span data-i18n="${stateKey}">${escapeHtml(stateLabel)}</span>`;
    }
  });
  ["tag-nat-bal-sub", "nts-nat-bal-sub"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = subText;
  });
}

function chartSvg(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs || {}).forEach(([k,v]) => el.setAttribute(k, v));
  return el;
}

function tsMs(iso) {
  const d = new Date(iso.length > 10 ? iso : iso + "T00:00:00Z");
  return d.getTime();
}

const TAG_SERIES_PALETTE = [
  "#2563eb",
  "#f97316",
  "#10b981",
  "#a855f7",
  "#ef4444",
  "#06b6d4",
  "#eab308",
  "#ec4899",
  "#14b8a6",
  "#6366f1",
  "#84cc16",
  "#d97706",
];

function getOrCreateChartTooltip() {
  let tt = document.getElementById("chart-tt");
  if (!tt) {
    tt = document.createElement("div");
    tt.id = "chart-tt";
    tt.className = "tt";
    document.body.appendChild(tt);
  }
  return tt;
}

function consumptionStateKeys() {
  return (DATA.groups || []).filter(g => g !== "total");
}

function formatDayLabel(ms) {
  const d = new Date(ms);
  return (d.getUTCMonth() + 1) + "/" + d.getUTCDate();
}

function updateSelectionHint() {
  const el = document.getElementById("selection-hint");
  if (!el) return;
  if (zoneMode === "stack") {
    el.textContent = "Stacked view shows all states + total dot.";
    return;
  }
  const n = zoneGran === "state" ? selectedGroups.size : selectedZones.size;
  el.textContent = n ? (n + " selected") : "Nothing selected";
}

function drawConsumptionStackedDaily(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return;
  host.innerHTML = "";
  const totalBag = GROUP_SERIES.total;
  const stateKeys = consumptionStateKeys();
  if (!totalBag || !totalBag.times || totalBag.times.length < 1 || !stateKeys.length) {
    host.innerHTML = '<div class="chart-empty" style="padding:48px 16px;text-align:center;color:var(--muted)">No daily forecast in this snapshot.</div>';
    return;
  }
  const palette = TAG_SERIES_PALETTE;
  const n = totalBag.times.length;
  const days = totalBag.times.map((t, i) => ({
    x: tsMs(t),
    dateStr: t,
    total: totalBag.values[i],
    states: stateKeys.map((g, si) => {
      const bag = GROUP_SERIES[g];
      const v = bag && bag.values ? bag.values[i] : null;
      return {
        g,
        v: v != null && isFinite(v) ? v : 0,
        color: palette[si % palette.length],
        label: (DATA.groupLabels && DATA.groupLabels[g]) ? DATA.groupLabels[g] : g,
      };
    }),
  }));
  const maxTot = Math.max(...days.map(d => (d.total != null && isFinite(d.total) ? d.total : 0)), 1);
  const W = Math.max(640, host.clientWidth || 640), H = 260, ML = 52, MR = 12, MT = 12, MB = 36;
  const plotW = W - ML - MR;
  const gap = Math.max(8, (plotW / Math.max(n, 1)) * 0.08);
  const barW = Math.max(18, (plotW - gap * (n + 1)) / n);
  const y = v => MT + (H - MT - MB) * (1 - v / maxTot);
  const svg = chartSvg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  for (let i = 0; i <= 4; i++) {
    const t = maxTot * (i / 4);
    const yy = y(t);
    svg.appendChild(chartSvg("line", { x1: ML, x2: W - MR, y1: yy, y2: yy, stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvg("text", { x: ML - 6, y: yy + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11, "font-family": "var(--font)" });
    lb.textContent = t.toFixed(0); svg.appendChild(lb);
  }

  days.forEach((day, i) => {
    const x0 = ML + gap + i * (barW + gap);
    const cx = x0 + barW / 2;
    let yTop = MT + (H - MT - MB);
    day.states.forEach(st => {
      if (!st.v) return;
      const h = (st.v / maxTot) * (H - MT - MB);
      yTop -= h;
      svg.appendChild(chartSvg("rect", {
        x: x0.toFixed(1), y: yTop.toFixed(1), width: barW.toFixed(1), height: h.toFixed(1),
        fill: st.color, stroke: "none", "data-state": st.g,
      }));
    });
    if (day.total != null && isFinite(day.total)) {
      const cy = y(day.total);
      svg.appendChild(chartSvg("circle", {
        cx: cx.toFixed(1), cy: cy.toFixed(1), r: 4.5, fill: "var(--text)", stroke: "var(--panel)", "stroke-width": 1.5,
      }));
    }
    const lbl = chartSvg("text", {
      x: cx.toFixed(1), y: (H - 10).toFixed(1),
      "text-anchor": "middle", fill: "var(--muted)", "font-size": 10, "font-family": "var(--font)",
    });
    lbl.textContent = formatDayLabel(day.x);
    svg.appendChild(lbl);

    const colHit = chartSvg("rect", {
      x: (x0 - gap / 2).toFixed(1), y: MT, width: (barW + gap).toFixed(1), height: H - MT - MB,
      fill: "transparent", style: "cursor:pointer;",
    });
    colHit.addEventListener("pointermove", ev => {
      const tt = getOrCreateChartTooltip();
      const lang = document.documentElement.getAttribute("data-lang") || "en";
      const isPt = lang === "pt";
      const dt = new Date(day.x);
      const dayHeader = dt.toLocaleDateString(isPt ? "pt-BR" : "en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
      let rows = "";
      day.states.forEach(st => {
        if (st.v > 0) {
          rows += `<tr><td><span class="sw" style="background:${st.color}"></span> ${escapeHtml(st.label)}</td><td class="v">${st.v.toFixed(2)} Mm³/d</td></tr>`;
        }
      });
      if (day.total != null) {
        rows += `<tr><td style="font-weight:600"><span class="sw" style="background:var(--text)"></span> Total</td><td class="v" style="font-weight:600">${day.total.toFixed(2)} Mm³/d</td></tr>`;
      }
      tt.innerHTML = `<div class="d">${escapeHtml(dayHeader)}</div><table>${rows}</table>`;
      placeChartTooltip(tt, ev.clientX, ev.clientY);
    });
    colHit.addEventListener("pointerleave", () => {
      const tt = document.getElementById("chart-tt");
      if (tt) tt.style.display = "none";
    });
    svg.appendChild(colHit);
  });

  const legHost = document.createElement("div");
  legHost.className = "legend";
  stateKeys.forEach((g, si) => {
    const span = document.createElement("span");
    span.style.color = palette[si % palette.length];
    span.innerHTML = `<span class="sw" style="background:${palette[si % palette.length]}"></span> ` +
      escapeHtml((DATA.groupLabels && DATA.groupLabels[g]) ? DATA.groupLabels[g] : g);
    legHost.appendChild(span);
  });
  const totSpan = document.createElement("span");
  totSpan.style.color = "var(--text)";
  totSpan.innerHTML = '<span class="sw" style="background:var(--text)"></span> ' +
    escapeHtml((DATA.groupLabels && DATA.groupLabels.total) ? DATA.groupLabels.total : "Total");
  legHost.appendChild(totSpan);

  host.appendChild(svg);
  host.appendChild(legHost);
}

function drawLines(hostId, seriesList, yFmt, bands) {
  const host = document.getElementById(hostId);
  if (!host) return;
  host.innerHTML = "";
  const usable = seriesList.filter(s => (s.points || []).length >= 2);
  if (!usable.length) {
    host.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted)">No series in this view.</div>';
    return;
  }
  const allPts = usable.flatMap(s => s.points);
  const xs = allPts.map(p => p.x);
  const ys = allPts.map(p => p.y).filter(v => v != null && isFinite(v));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (bands) {
    const bVals = Object.values(bands).filter(v => v != null && isFinite(v));
    if (bVals.length) {
      lo = Math.min(lo, ...bVals);
      hi = Math.max(hi, ...bVals);
    }
  }
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = hostId === "chart-zones" ? 230 : (hostId === "chart-lp" ? 260 : 210);
  const ML = 52, MR = bands ? 84 : 10, MT = 12, MB = 26;
  const plotLeft = ML, plotWidth = W - ML - MR, plotTop = MT, plotBottom = H - MB;
  const x = v => ML + plotWidth * ((v - minX) / (maxX - minX || 1));
  const y = v => MT + (plotBottom - plotTop) * (1 - (v - lo) / (hi - lo || 1));
  const svg = chartSvg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  if (bands) {
    const sevSup = bands.severo_superior;
    const bSup = bands.baixo_superior;
    const mSup = bands.marginal_superior;
    const mInf = bands.marginal_inferior;
    const bInf = bands.baixo_inferior;
    const sevInf = bands.severo_inferior;

    const zoneRects = [
      { topVal: hi, botVal: sevSup, color: "rgba(239, 68, 68, 0.08)" },
      { topVal: sevSup, botVal: bSup, color: "rgba(245, 158, 11, 0.07)" },
      { topVal: bSup, botVal: mSup, color: "rgba(16, 185, 129, 0.05)" },
      { topVal: mSup, botVal: mInf, color: "rgba(16, 185, 129, 0.11)" },
      { topVal: mInf, botVal: bInf, color: "rgba(16, 185, 129, 0.05)" },
      { topVal: bInf, botVal: sevInf, color: "rgba(245, 158, 11, 0.07)" },
      { topVal: sevInf, botVal: lo, color: "rgba(239, 68, 68, 0.08)" },
    ];

    zoneRects.forEach(zr => {
      if (zr.topVal == null || zr.botVal == null) return;
      const y1 = Math.max(plotTop, Math.min(plotBottom, y(zr.topVal)));
      const y2 = Math.max(plotTop, Math.min(plotBottom, y(zr.botVal)));
      const rH = y2 - y1;
      if (rH > 0) {
        svg.appendChild(chartSvg("rect", {
          x: plotLeft,
          y: y1,
          width: plotWidth,
          height: rH,
          fill: zr.color,
          stroke: "none",
        }));
      }
    });
  }

  for (let i = 0; i <= 4; i++) {
    const t = lo + (hi - lo) * (i / 4);
    const yy = y(t);
    svg.appendChild(chartSvg("line", { x1: ML, x2: W - MR, y1: yy, y2: yy, stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvg("text", { x: ML - 6, y: yy + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 10.5, "font-family": "var(--font)" });
    lb.textContent = yFmt(t); svg.appendChild(lb);
  }

  if (bands) {
    const axisX = plotLeft + plotWidth;
    svg.appendChild(chartSvg("line", {
      x1: axisX, x2: axisX, y1: plotTop, y2: plotBottom,
      stroke: "var(--border)", "stroke-width": 1,
    }));

    const guides = [
      { key: "sev_sup", val: bands.severo_superior, color: "#ef4444", labelEn: "Critical High Threshold", labelPt: "Limite Severo Superior" },
      { key: "alt_sup", val: bands.baixo_superior, color: "#f59e0b", labelEn: "High Alert Threshold", labelPt: "Limite Alerta Alto" },
      { key: "marg_sup", val: bands.marginal_superior, color: "#10b981", labelEn: "Target Upper Limit", labelPt: "Limite Marginal Superior" },
      { key: "marg_inf", val: bands.marginal_inferior, color: "#10b981", labelEn: "Target Lower Limit", labelPt: "Limite Marginal Inferior" },
      { key: "alt_inf", val: bands.baixo_inferior, color: "#f59e0b", labelEn: "Low Alert Threshold", labelPt: "Limite Alerta Baixo" },
      { key: "sev_inf", val: bands.severo_inferior, color: "#ef4444", labelEn: "Critical Low Threshold", labelPt: "Limite Severo Inferior" },
    ];
    guides.forEach(g => {
      if (g.val == null || !isFinite(g.val)) return;
      const gy = y(g.val);
      if (gy < plotTop - 2 || gy > plotBottom + 2) return;
      const line = chartSvg("line", {
        x1: plotLeft, x2: axisX, y1: gy, y2: gy,
        stroke: g.color, "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0.65,
      });
      svg.appendChild(line);

      const rLabel = chartSvg("text", {
        x: axisX + 5, y: gy + 3, fill: g.color,
        "font-size": 9, "font-weight": 600, "font-family": "var(--font)",
      });
      rLabel.textContent = `${(g.val / 1e6).toFixed(1)}M`;
      svg.appendChild(rLabel);
    });
  }

  const numTicks = 4;
  for (let i = 0; i <= numTicks; i++) {
    const tMs = minX + (maxX - minX) * (i / numTicks);
    const tx = x(tMs);
    const d = new Date(tMs);
    const timeStr = (d.getUTCMonth() + 1) + "/" + d.getUTCDate() + " " + String(d.getUTCHours()).padStart(2, "0") + "h";
    const tLabel = chartSvg("text", {
      x: tx, y: H - 8,
      "text-anchor": i === 0 ? "start" : (i === numTicks ? "end" : "middle"),
      fill: "var(--muted)", "font-size": 10, "font-family": "var(--font)"
    });
    tLabel.textContent = timeStr;
    svg.appendChild(tLabel);
  }

  usable.forEach(s => {
    let d = "";
    let started = false;
    s.points.forEach(p => {
      if (p.y == null || !isFinite(p.y)) return;
      d += (started ? "L" : "M") + x(p.x).toFixed(1) + " " + y(p.y).toFixed(1) + " ";
      started = true;
    });
    if (!d) return;
    const path = chartSvg("path", {
      d: d.trim(), fill: "none", stroke: s.color || "var(--accent)", "stroke-width": 2,
    });
    if (s.dash) path.setAttribute("stroke-dasharray", s.dash);
    svg.appendChild(path);
  });

  // Crosshair line and hover dots
  const cross = chartSvg("line", {
    x1: 0, x2: 0, y1: plotTop, y2: plotBottom,
    stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "3 3",
    style: "display:none; pointer-events:none;",
  });
  svg.appendChild(cross);

  const dots = usable.map(s => {
    const dot = chartSvg("circle", {
      r: 4, fill: s.color || "var(--accent)", stroke: "var(--panel)", "stroke-width": 1.5,
      style: "display:none; pointer-events:none;",
    });
    svg.appendChild(dot);
    return dot;
  });

  const hit = chartSvg("rect", {
    x: plotLeft, y: plotTop, width: plotWidth, height: plotBottom - plotTop,
    fill: "transparent", style: "cursor:crosshair;",
  });
  svg.appendChild(hit);

  function hideTips() {
    const tt = document.getElementById("chart-tt");
    if (tt) tt.style.display = "none";
    cross.style.display = "none";
    dots.forEach(d => { d.style.display = "none"; });
  }

  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    if (px < plotLeft || px > plotLeft + plotWidth) {
      hideTips();
      return;
    }
    const curX = minX + ((px - plotLeft) / plotWidth) * (maxX - minX);

    let bestT = null;
    let bestDist = Infinity;
    usable.forEach(s => {
      s.points.forEach(p => {
        const dist = Math.abs(p.x - curX);
        if (dist < bestDist) {
          bestDist = dist;
          bestT = p.x;
        }
      });
    });
    if (bestT == null) {
      hideTips();
      return;
    }

    const crossX = x(bestT);
    cross.setAttribute("x1", crossX.toFixed(1));
    cross.setAttribute("x2", crossX.toFixed(1));
    cross.style.display = "";

    const d = new Date(bestT);
    const datePart = (d.getUTCMonth() + 1) + "/" + d.getUTCDate();
    const timePart = String(d.getUTCHours()).padStart(2, "0") + ":00 UTC";
    const headerStr = `${datePart} ${timePart}`;

    let rows = "";
    usable.forEach((s, idx) => {
      const pt = s.points.find(p => Math.abs(p.x - bestT) < 3600000);
      const dot = dots[idx];
      if (pt && pt.y != null && isFinite(pt.y)) {
        const cy = y(pt.y);
        dot.setAttribute("cx", crossX.toFixed(1));
        dot.setAttribute("cy", cy.toFixed(1));
        dot.style.display = "";

        let valStr = "";
        if (hostId === "chart-lp" || hostId === "chart-lp-hist") {
          valStr = (pt.y / 1e6).toFixed(2) + " Mm³";
        } else {
          valStr = pt.y.toFixed(2) + " Mm³/d";
        }
        rows += `<tr><td><span class="sw" style="background:${s.color}"></span> ${escapeHtml(s.name || "")}</td><td class="v">${valStr}</td></tr>`;
      } else {
        dot.style.display = "none";
      }
    });

    if (!rows) {
      hideTips();
      return;
    }

    const tt = getOrCreateChartTooltip();
    tt.innerHTML = `<div class="d">${escapeHtml(headerStr)}</div><table>${rows}</table>`;
    placeChartTooltip(tt, ev.clientX, ev.clientY);
  });

  hit.addEventListener("pointerleave", hideTips);

  host.appendChild(svg);
}

function packLinepack() {
  if (!DATA) return;
  const actualPts = (LP.actual?.times || []).map((t, i) => ({ x: tsMs(t), y: LP.actual.values[i] }));
  const forePts = (LP.forecast?.times || []).map((t, i) => ({ x: tsMs(t), y: LP.forecast.values[i] }));
  const series = [
    { name: "Actual", color: "var(--tso-tag, #0066cc)", points: actualPts },
    { name: "Forecast", color: "#888", dash: "4 3", points: forePts },
  ];
  drawLines("chart-lp", series, v => (v / 1e6).toFixed(1), DATA.toleranceBands);
}

function packLinepackHistory() {
  if (!DATA) return;
  let rows = LP_ROWS;
  if (selectedDay) rows = rows.filter(r => (r.observedAt || "").startsWith(selectedDay));
  if (histFilter === "alerts") rows = rows.filter(r => r.isAlert);
  const pts = rows.map(r => ({ x: tsMs(r.observedAt), y: r.valueM3 }));
  pts.sort((a,b) => a.x - b.x);
  const series = [{ name: "Line pack", color: "var(--tso-tag, #0066cc)", points: pts }];
  drawLines("chart-lp-hist", series, v => (v / 1e6).toFixed(1), DATA.toleranceBands);
}

function packZones() {
  if (!DATA) return;
  if (zoneMode === "stack") {
    drawConsumptionStackedDaily("chart-zones");
    updateSelectionHint();
    return;
  }
  const isState = zoneGran === "state";
  const source = isState ? GROUP_SERIES : ZONE_SERIES;
  const selected = isState ? selectedGroups : selectedZones;
  const keys = [...selected];
  const host = document.getElementById("chart-zones");
  if (!keys.length) {
    if (host) host.innerHTML = '<div class="chart-empty" style="padding:48px 16px;text-align:center;color:var(--muted)">Select states or zones below, or click <strong>Select all</strong>.</div>';
    updateSelectionHint();
    return;
  }
  const series = keys.map((k, idx) => {
    const s = source[k] || { times: [], values: [] };
    const pts = (s.times || []).map((t, i) => ({ x: tsMs(t), y: s.values[i] }));
    const isTotal = k.toLowerCase() === "total";
    const label = (DATA.groupLabels && DATA.groupLabels[k]) ? DATA.groupLabels[k] : k;
    const color = isTotal ? "var(--text)" : TAG_SERIES_PALETTE[idx % TAG_SERIES_PALETTE.length];
    const dash = isTotal ? "4 3" : undefined;
    return { name: label, color, points: pts, dash };
  });
  drawLines("chart-zones", series, v => v.toFixed(1));
  updateSelectionHint();
}

function renderFaixasTable() {
  if (!DATA) return;
  const host = document.getElementById("faixas-grid");
  if (!host) return;
  const list = DATA.toleranceBandsList || [];
  const lang = document.documentElement.getAttribute("data-lang") || "en";
  const isPt = lang === "pt";
  let h = '<table class="faixas-table"><thead><tr>' +
    '<th>Tier</th><th>Threshold</th><th>Description</th></tr></thead><tbody>';
  list.forEach(item => {
    const name = isPt ? (item.namePt || item.name) : (item.nameEn || item.name);
    const desc = isPt ? (item.descPt || item.descEn) : item.descEn;
    h += `<tr><td><span class="zone-pill ${item.badgeClass}">${escapeHtml(name)}</span></td>` +
      `<td><strong>${escapeHtml(item.range)}</strong></td><td style="color:var(--muted)">${escapeHtml(desc)}</td></tr>`;
  });
  h += '</tbody></table>';
  host.innerHTML = h;
}

function renderHeatmap() {
  if (!DATA) return;
  const sumHost = document.getElementById("hm-summary-grid");
  const calHost = document.getElementById("hm-calendar-grid");
  const sum = DATA.linepackHeatmapSummary || {};
  const days = DATA.linepackHeatmap || [];
  if (sumHost) {
    sumHost.innerHTML = `
      <div class="hm-stat-card"><div class="hm-stat-label">Compliance</div><div class="hm-stat-val" style="color:#10b981">${sum.compliancePct ?? 100}%</div></div>
      <div class="hm-stat-card"><div class="hm-stat-label">Alert Hours</div><div class="hm-stat-val" style="color:#f59e0b">${sum.alertHoursCount ?? 0}</div></div>
      <div class="hm-stat-card"><div class="hm-stat-label">Critical Hours</div><div class="hm-stat-val" style="color:#ef4444">${sum.criticalHoursCount ?? 0}</div></div>
      <div class="hm-stat-card"><div class="hm-stat-label">Days Monitored</div><div class="hm-stat-val">${sum.totalDays ?? days.length}</div></div>
    `;
  }
  if (calHost) {
    let filtered = days;
    if (hmFilter === "alerts") filtered = days.filter(d => d.hasAlert);
    else if (hmFilter === "critical") filtered = days.filter(d => d.hasCritical);
    calHost.innerHTML = filtered.map(d => {
      const col = d.peakBadge === "badge-danger" ? "#ef4444" : d.peakBadge === "badge-warning" ? "#f59e0b" : "#10b981";
      return `<div class="hm-day-cell" style="background:${col}1a;color:${col}" title="${d.date}: ${d.peakZone} (${(d.minMm3||0).toFixed(1)}–${(d.maxMm3||0).toFixed(1)} Mm³)" onclick="selectHmDay('${d.date}')"><div class="num">${d.date.slice(8,10)}</div><div class="tag">${d.peakZone.slice(0,3)}</div></div>`;
    }).join("");
  }
}

function selectHmDay(day) {
  selectedDay = day;
  const bar = document.getElementById("hm-selected-day-indicator");
  const txt = document.getElementById("hm-filter-day-text");
  if (bar && txt) {
    bar.style.display = "flex";
    txt.textContent = "Filtered by day: " + day;
  }
  packLinepackHistory();
  renderLpTable();
}

function renderLpTable() {
  const tbody = document.getElementById("lp-tbody");
  if (!tbody) return;
  let rows = LP_ROWS;
  if (selectedDay) rows = rows.filter(r => (r.observedAt || "").startsWith(selectedDay));
  if (histFilter === "alerts") rows = rows.filter(r => r.isAlert);
  tbody.innerHTML = rows.slice(0, 100).map(r => `
    <tr>
      <td>${r.observedAt}</td>
      <td class="num"><strong>${r.valueMm3 != null ? r.valueMm3.toFixed(2) : "—"}</strong></td>
      <td class="num">${r.valueM3 != null ? r.valueM3.toLocaleString() : "—"}</td>
      <td><span class="zone-pill ${r.badgeClass || ''}">${escapeHtml(r.zoneLabel || r.zone || '')}</span></td>
      <td style="color:var(--muted)">${r.snapshotAt || '—'}</td>
    </tr>
  `).join("");
}

function renderFilters() {
  if (!DATA) return;
  const sHost = document.getElementById("filter-state");
  const zHost = document.getElementById("filter-zone");
  if (!sHost || !zHost) return;
  const groups = DATA.groups || [];
  const zones = DATA.zones || [];
  sHost.innerHTML = groups.map(g => `<button type="button" class="filter-chip ${selectedGroups.has(g) ? 'active' : ''}" data-k="${g}">${g}</button>`).join("");
  zHost.innerHTML = zones.map(z => `<button type="button" class="filter-chip ${selectedZones.has(z) ? 'active' : ''}" data-k="${z}">${z}</button>`).join("");

  sHost.querySelectorAll("button").forEach(b => {
    b.addEventListener("click", () => {
      const k = b.dataset.k;
      if (selectedGroups.has(k)) selectedGroups.delete(k); else selectedGroups.add(k);
      b.classList.toggle("active", selectedGroups.has(k));
      packZones();
    });
  });
  zHost.querySelectorAll("button").forEach(b => {
    b.addEventListener("click", () => {
      const k = b.dataset.k;
      if (selectedZones.has(k)) selectedZones.delete(k); else selectedZones.add(k);
      b.classList.toggle("active", selectedZones.has(k));
      packZones();
    });
  });
}

function exportLpCsv() {
  if (!LP_ROWS.length) return;
  let csv = "observed_at_utc,value_mm3,value_m3,operating_zone,snapshot_at_utc\n";
  LP_ROWS.forEach(r => {
    csv += `${r.observedAt},${r.valueMm3},${r.valueM3},${r.zone},${r.snapshotAt}\n`;
  });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tag_mago_linepack_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function paintAsof() {
  if (!DATA) return;
  const refEl = document.getElementById("asof-refreshed");
  const thrEl = document.getElementById("asof-through");
  if (refEl) refEl.textContent = formatRefreshedLocal(DATA.generatedIso, DATA.generated);
  if (thrEl) thrEl.textContent = DATA.snapshotAt || "—";
}

async function fetchMagoPayloadJson() {
  const urls = [PAYLOAD_URL, MAGO_PAYLOAD_R2];
  let lastErr;
  for (const u of urls) {
    if (!u) continue;
    try {
      return await inflateGzipUrl(u);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("Mago payload unavailable");
}

/* ==================== GLOBAL INIT ==================== */
async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  buildMonitorTabs();

  // Tab restoration from query param or localStorage
  const qp = gbQueryParams().get("tab");
  const validTab = gbValidEnum(qp, ["tag", "nts"]);
  if (validTab) {
    monitorTab = validTab;
  } else {
    try {
      const saved = localStorage.getItem("monitor-tab");
      if (saved === "tag" || saved === "nts") monitorTab = saved;
    } catch (e) {}
  }
  setMonitorTab(monitorTab);

  initThemeToggle("theme-toggle", () => {
    if (monitorTab === "nts") renderNtsChart();
    else { packLinepack(); packLinepackHistory(); packZones(); }
  });
  initLangToggle("lang-toggle", () => {
    applyI18n();
    if (monitorTab === "nts") { renderNtsChart(); populateNtsTable(); }
    else { setMagoKpis(); renderFaixasTable(); renderHeatmap(); renderLpTable(); packLinepack(); packZones(); }
  });
  initCrossLinks();
  gbCopyLink("btn-share");
  applyI18n();

  // Wire NTS static elements
  renderNtsChart();
  populateNtsTable();

  // Wire Mago buttons
  const btnCsv = document.getElementById("btn-lp-csv");
  if (btnCsv) btnCsv.addEventListener("click", exportLpCsv);
  const btnClearDay = document.getElementById("btn-clear-day-filter");
  if (btnClearDay) btnClearDay.addEventListener("click", () => {
    selectedDay = null;
    document.getElementById("hm-selected-day-indicator").style.display = "none";
    packLinepackHistory();
    renderLpTable();
  });
  const btnHmAll = document.getElementById("btn-hm-all");
  const btnHmAlerts = document.getElementById("btn-hm-alerts");
  const btnHmCrit = document.getElementById("btn-hm-critical");
  if (btnHmAll) btnHmAll.addEventListener("click", () => { hmFilter = "all"; btnHmAll.classList.add("active"); btnHmAlerts.classList.remove("active"); btnHmCrit.classList.remove("active"); renderHeatmap(); });
  if (btnHmAlerts) btnHmAlerts.addEventListener("click", () => { hmFilter = "alerts"; btnHmAlerts.classList.add("active"); btnHmAll.classList.remove("active"); btnHmCrit.classList.remove("active"); renderHeatmap(); });
  if (btnHmCrit) btnHmCrit.addEventListener("click", () => { hmFilter = "critical"; btnHmCrit.classList.add("active"); btnHmAll.classList.remove("active"); btnHmAlerts.classList.remove("active"); renderHeatmap(); });

  const btnHAll = document.getElementById("btn-hist-all");
  const btnHAlerts = document.getElementById("btn-hist-alerts");
  if (btnHAll) btnHAll.addEventListener("click", () => { histFilter = "all"; btnHAll.classList.add("active"); btnHAlerts.classList.remove("active"); packLinepackHistory(); renderLpTable(); });
  if (btnHAlerts) btnHAlerts.addEventListener("click", () => { histFilter = "alerts"; btnHAlerts.classList.add("active"); btnHAll.classList.remove("active"); packLinepackHistory(); renderLpTable(); });

  const segGran = document.querySelectorAll(".seg button[data-gran]");
  segGran.forEach(b => b.addEventListener("click", () => {
    segGran.forEach(x => x.classList.toggle("on", x === b));
    zoneGran = b.dataset.gran;
    if (zoneGran === "zone" && zoneMode === "stack") {
      zoneMode = "line";
      document.querySelectorAll(".seg button[data-mode]").forEach(m => m.classList.toggle("on", m.dataset.mode === "line"));
    }
    document.getElementById("filter-state").classList.toggle("is-hidden", zoneGran !== "state");
    document.getElementById("filter-zone").classList.toggle("is-hidden", zoneGran !== "zone");
    packZones();
  }));
  const segMode = document.querySelectorAll(".seg button[data-mode]");
  segMode.forEach(b => b.addEventListener("click", () => {
    segMode.forEach(x => x.classList.toggle("on", x === b));
    zoneMode = b.dataset.mode;
    if (zoneMode === "stack" && zoneGran !== "state") {
      zoneGran = "state";
      segGran.forEach(g => g.classList.toggle("on", g.dataset.gran === "state"));
      document.getElementById("filter-state").classList.remove("is-hidden");
      document.getElementById("filter-zone").classList.add("is-hidden");
    }
    packZones();
  }));

  const btnSelAll = document.getElementById("btn-select-zones");
  if (btnSelAll) {
    btnSelAll.addEventListener("click", () => {
      if (zoneGran === "state") {
        selectedGroups = new Set(DATA ? (DATA.groups || []) : []);
      } else {
        selectedZones = new Set(DATA ? (DATA.zones || []) : []);
      }
      renderFilters();
      packZones();
    });
  }
  const btnClrSel = document.getElementById("btn-clear-zones");
  if (btnClrSel) {
    btnClrSel.addEventListener("click", () => {
      if (zoneGran === "state") {
        selectedGroups.clear();
      } else {
        selectedZones.clear();
      }
      renderFilters();
      packZones();
    });
  }

  // Initialize telemetry health pulse and periodic update
  updateTelemetryHealth();
  setInterval(updateTelemetryHealth, 60000);
  const langToggle = document.getElementById("lang-toggle");
  if (langToggle) langToggle.addEventListener("click", () => setTimeout(updateNationalGridKpis, 60));

  // Fetch TAG Mago JSON in background
  try {
    const json = await fetchMagoPayloadJson();
    const raw = parseDashboardJson(json);
    DATA = (raw && raw.tag) ? raw.tag : raw;
    if (raw && raw.nts && raw.nts.payload) {
      NTS_PAYLOAD = raw.nts.payload;
      if (monitorTab === "nts") {
        renderNtsChart();
        populateNtsTable();
      }
    }
    LP = DATA.linepack || {};
    LP_HIST = DATA.linepackHistory || {};
    LP_ROWS = DATA.linepackHistoryRows || [];
    ZONE_SERIES = DATA.zoneSeries || {};
    GROUP_SERIES = DATA.groupSeries || {};
    selectedGroups = new Set(DATA.groups || []);
    selectedZones = new Set((DATA.zones || []).slice(0, 6));

    setMagoKpis();
    renderFaixasTable();
    renderHeatmap();
    renderLpTable();
    renderFilters();
    packLinepack();
    packLinepackHistory();
    packZones();
    paintAsof();
    updateTelemetryHealth();
    updateNationalGridKpis();
  } catch (err) {
    console.error("TAG Mago payload could not be loaded:", err);
  }

  window.addEventListener("resize", () => {
    if (monitorTab === "nts") renderNtsChart();
    else { packLinepack(); packLinepackHistory(); packZones(); }
  });
}

init();
</script>
</body>
</html>
"""


def load_tag_data():
    mago_dash = _load_module("mago_dash", ROOT / "mago" / "dashboard.py")
    try:
        return mago_dash.load_payload()
    except Exception as exc:
        print(f"Local TAG Mago parquet not found or failed ({exc}); continuing with fallback.")
        return None


def load_nts_data():
    nts_dash = _load_module("nts_dash", ROOT / "nts" / "dashboard.py")
    df = nts_dash._load_data()
    kpis, payload = nts_dash._build_payload(df)
    return kpis, payload


def build_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    out_path = Path(out_path)
    tag_payload = load_tag_data()
    nts_kpis, nts_payload = load_nts_data()

    now = dt.datetime.now(dt.UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")

    kpi_tag_lp = ""
    if tag_payload and tag_payload.get("kpiLinepackMm3") is not None:
        kpi_tag_lp = f"{tag_payload['kpiLinepackMm3']:.2f}"

    cur_mm3 = f"{nts_kpis['current_mm3']:.2f}"
    cur_m3 = f"{int(round(nts_kpis['current_m3'])):,}".replace(",", ".")
    is_pack = nts_kpis["is_packing"]
    pack_class = "packing" if is_pack else "unpacking"
    pack_arrow = "▲" if is_pack else "▼"
    pack_state = "Packing" if is_pack else "Unpacking"
    pack_state_i18n = "ntsKpiPacking" if is_pack else "ntsKpiUnpacking"

    rate_sign = "+" if is_pack else ""
    rate_val = f"{rate_sign}{int(round(nts_kpis['rate_m3_h'])):,}".replace(",", ".")
    rate_daily = f"{rate_sign}{nts_kpis['rate_mm3_d']:.2f}"

    delta_sign = "+" if nts_kpis["delta_24h_m3"] >= 0 else ""
    delta_24h_val = f"{delta_sign}{int(round(nts_kpis['delta_24h_m3'])):,}".replace(",", ".")
    delta_24h_pct = f"{delta_sign}{nts_kpis['delta_24h_pct']:.2f}%"

    min_24h = f"{nts_kpis['min_24h']:.2f}"
    max_24h = f"{nts_kpis['max_24h']:.2f}"
    avg_24h = f"{nts_kpis['avg_24h']:.2f}"

    # National Grid Pack metrics
    tag_lp_float = tag_payload.get("kpiLinepackMm3") if tag_payload else None
    nts_lp_float = nts_kpis.get("current_mm3") if nts_kpis else None
    if tag_lp_float is not None and nts_lp_float is not None:
        nat_lp_total = tag_lp_float + nts_lp_float
        nat_lp_val = f"{nat_lp_total:.2f}"
        tag_pct = round((tag_lp_float / nat_lp_total) * 100)
        nts_pct = 100 - tag_pct
        nat_lp_sub = f"TAG {tag_pct}% · NTS {nts_pct}%"
    elif nts_lp_float is not None:
        nat_lp_val = f"{nts_lp_float:.2f}"
        nat_lp_sub = "NTS 100%"
    else:
        nat_lp_val = "—"
        nat_lp_sub = "—"

    # National Packing Rate & System Balance
    tag_rate_m3_h = 0.0
    if tag_payload:
        lp_actual_vals = tag_payload.get("linepack", {}).get("actual", {}).get("values", [])
        if len(lp_actual_vals) >= 2 and lp_actual_vals[-1] is not None and lp_actual_vals[-2] is not None:
            tag_rate_m3_h = float(lp_actual_vals[-1] - lp_actual_vals[-2])
    nts_rate_m3_h = float(nts_kpis.get("rate_m3_h", 0.0))
    comb_rate_m3_h = round(tag_rate_m3_h + nts_rate_m3_h)
    comb_rate_mm3_d = (comb_rate_m3_h * 24.0) / 1_000_000.0
    is_nat_pack = comb_rate_m3_h > 2000
    is_nat_draft = comb_rate_m3_h < -2000
    nat_pack_class = "packing" if is_nat_pack else ("unpacking" if is_nat_draft else "packing")
    nat_pack_arrow = "▲" if is_nat_pack else ("▼" if is_nat_draft else "◆")
    nat_pack_state = "Grid Packing" if is_nat_pack else ("Grid Drafting" if is_nat_draft else "In-Balance")
    nat_pack_i18n = "gridStatusPacking" if is_nat_pack else ("gridStatusDrafting" if is_nat_draft else "gridStatusBalanced")

    comb_sign = "+" if comb_rate_m3_h >= 0 else ""
    comb_rate_fmt = f"{comb_sign}{int(round(comb_rate_m3_h)):,}".replace(",", ".")
    comb_daily_fmt = f"{comb_sign}{comb_rate_mm3_d:.2f}"
    nat_bal_sub = f"{comb_rate_fmt} m³/h · {comb_daily_fmt} Mm³/d eq."

    # Telemetry Health & Freshness Timestamps
    tag_snap_str = tag_payload.get("snapshotIso") or tag_payload.get("snapshotAt") if tag_payload else None
    tag_health_time = "Live"
    tag_dot_class = "pulse-dot"
    if tag_snap_str:
        dt_tag = _parse_ts(tag_snap_str)
        if dt_tag:
            diff_m = int((now - dt_tag).total_seconds() / 60)
            if diff_m < 0:
                tag_health_time = "Live"
            elif diff_m < 60:
                tag_health_time = f"{diff_m}m ago"
            else:
                tag_health_time = f"{diff_m // 60}h ago"
            tag_dot_class = "pulse-dot" + (" stale" if diff_m > 360 else (" amber" if diff_m > 180 else ""))

    nts_snap_str = nts_kpis.get("last_updated_iso") or nts_kpis.get("last_updated_utc") if nts_kpis else None
    nts_health_time = "Live"
    nts_dot_class = "pulse-dot"
    if nts_snap_str:
        dt_nts = _parse_ts(nts_snap_str)
        if dt_nts:
            diff_m = int((now - dt_nts).total_seconds() / 60)
            if diff_m < 0:
                nts_health_time = "Live"
            elif diff_m < 60:
                nts_health_time = f"{diff_m}m ago"
            else:
                nts_health_time = f"{diff_m // 60}h ago"
            nts_dot_class = "pulse-dot" + (" stale" if diff_m > 360 else (" amber" if diff_m > 180 else ""))

    combined_payload = {
        "generated": now_str,
        "generatedIso": now.isoformat(),
        "tag": tag_payload,
        "nts": {
            "kpis": nts_kpis,
            "payload": nts_payload,
        },
    }

    _p_path, payload_href = dk.write_and_publish_artifact("monitor", combined_payload, HERE)
    if payload_href == "payload.json.gz":
        payload_href = "https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev/monitor/payload.json.gz"

    head_html = kit.seo_head(
        title="Pipeline Monitor — TAG Mago & NTS OnTime | GasBrazil",
        description="Integrated natural gas pipeline transmission monitor: TAG Mago operational line pack and 7-day zone forecasts, combined with NTS OnTime real-time SCADA telemetry.",
        path="/monitor/",
    )

    rendered = kit.render(
        TEMPLATE,
        HEAD=head_html,
        GENERATED=now_str,
        KPI_TAG_LP=kpi_tag_lp,
        KPI_NTS_LP=cur_mm3,
        KPI_NTS_RATE=rate_val,
        PAYLOAD_URL=payload_href,
        TAG_HEALTH_TIME=tag_health_time,
        TAG_DOT_CLASS=tag_dot_class,
        NTS_HEALTH_TIME=nts_health_time,
        NTS_DOT_CLASS=nts_dot_class,
        NAT_LP_VAL=nat_lp_val,
        NAT_LP_SUB=nat_lp_sub,
        NAT_PACK_CLASS=nat_pack_class,
        NAT_PACK_ARROW=nat_pack_arrow,
        NAT_PACK_STATE=nat_pack_state,
        NAT_PACK_I18N=nat_pack_i18n,
        NAT_BAL_SUB=nat_bal_sub,
        CUR_MM3=cur_mm3,
        CUR_M3=cur_m3,
        PACK_CLASS=pack_class,
        PACK_ARROW=pack_arrow,
        PACK_STATE=pack_state,
        PACK_STATE_I18N=pack_state_i18n,
        RATE_VAL=rate_val,
        RATE_DAILY=rate_daily,
        DELTA_24H_VAL=delta_24h_val,
        DELTA_24H_PCT=delta_24h_pct,
        MIN_24H=min_24h,
        MAX_24H=max_24h,
        AVG_24H=avg_24h,
        NTS_PAYLOAD_JSON=json.dumps(nts_payload),
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_TYPO_WEIGHT_CSS=kit.typo_weight_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_CSV=kit.JS_CSV_HELPERS,
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("monitor"),
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_ASOF=kit.refreshed_local_js(),
        SHARED_JS_QUERY_STATE=kit.JS_QUERY_STATE,
        SHARED_MASTHEAD=kit.masthead_html("monitor"),
        SHARED_METHODOLOGY=kit.methodology_html("monitor"),
        SHARED_SHARE_BUTTON=kit.share_link_button_html(),
        SHARED_CLEAR_SELECTION=kit.clear_selection_button_html("btn-clear-zones"),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Rendered Pipeline Monitor dashboard: {out_path} ({len(rendered):,} bytes)")
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    build_dashboard(out)
