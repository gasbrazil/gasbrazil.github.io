"""
Builds the single-file POC (Oferta de Capacidade) results dashboard from
data/poc_results.parquet.

Usage: python dashboard.py [output_path]  (default: index.html)
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402  (must follow sys.path.insert)
import transforms as xf  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "poc_results.parquet"
DEFAULT_OUT = HERE / "index.html"

# Price in the source data is R$/MMBtu. PCR convention: MMBtu per 1000 m³.
MMBTU_PER_M3 = xf.MMBTU_PER_1000_M3

COLUMNS = [
    "Transporter (TSO)", "codigoProcesso", "Trade Date", "Flow Date Start", "Flow Date End",
    "Flow Days", "Trade Timing", "Transaction Type", "Delivery Point", "Service Type",
    "Price", "R$/m3", "Avg Process Price", "Volume Accepted", "Total Value",
    "Volume Offered", "Total Volume",
]

# Internal column key -> display label shown in the table header / CSV export.
# Keys not listed here are displayed as-is.
DISPLAY_NAMES = {
    "Transporter (TSO)": "Pipeline",
    "Price": "Price (R$/MMBtu)",
    "Avg Process Price": "Avg Process Price (R$/MMBtu)",
    "R$/m3": "R$/m³",
}

DATE_COLS = {"Trade Date", "Flow Date Start", "Flow Date End"}

# Short labels for the Transaction Type column / filters / chart chips.
# Covers both current pipeline output and older parquet values still on disk.
TRANSACTION_TYPE_DISPLAY = {
    "Aquisição de GUS": "GUS",
    "GUS Acquisition": "GUS",
    "Balanceamento Residual": "Res. Bal.",
    "Residual Balancing": "Res. Bal.",
    "Balanceamento Operacional": "Op. Bal.",
    "Operational Balancing": "Op. Bal.",
    "Congestionamento": "Congestion",
}


def load_payload():
    df = pd.read_parquet(PARQUET_PATH)
    df["R$/m3"] = (df["Price"] * MMBTU_PER_M3 / 1000).round(2)
    df = df[COLUMNS].copy()
    df["Transaction Type"] = df["Transaction Type"].replace(TRANSACTION_TYPE_DISPLAY)
    for c in DATE_COLS:
        df[c] = df[c].dt.strftime("%Y-%m-%d").where(df[c].notna(), None)
    # Normalize every remaining missing value (NaN/NaT/pd.NA) to None so json.dumps
    # never has to serialize a bare NaN (invalid JSON) for numeric or string columns.
    df = df.astype(object).where(pd.notna(df), None)
    records = df.to_dict(orient="records")

    _now_utc = dt.datetime.now(dt.timezone.utc)
    generated = _now_utc.strftime("%Y-%m-%d %H:%M UTC")
    generatedIso = _now_utc.isoformat()

    # Hub teaser: volume-weighted? plain mean of last 7 trade days is fine.
    kpi_price = None
    kpi_n = 0
    kpi_when = None
    try:
        pdf = pd.read_parquet(PARQUET_PATH)
        if "Trade Date" in pdf.columns and "Price" in pdf.columns:
            pdf = pdf.dropna(subset=["Trade Date", "Price"]).copy()
            pdf["Trade Date"] = pd.to_datetime(pdf["Trade Date"], errors="coerce")
            pdf = pdf.dropna(subset=["Trade Date"])
            if len(pdf):
                latest = pdf["Trade Date"].max()
                week = pdf[pdf["Trade Date"] >= (latest - pd.Timedelta(days=7))]
                kpi_price = round(float(week["Price"].mean()), 2) if len(week) else None
                kpi_n = int(week["Price"].notna().sum()) if len(week) else 0
                kpi_when = latest.strftime("%Y-%m-%d")
    except Exception:
        pass

    return {
        "generated": generated,
        "generatedIso": generatedIso,
        "columns": COLUMNS,
        "displayNames": DISPLAY_NAMES,
        "rows": records,
        "kpiPrice7d": kpi_price,
        "kpiTrades7d": kpi_n,
        "kpiWhen": kpi_when,
    }


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>POC Results</title>
<meta name="description" content="Pipeline capacity offer results from Brazil's Portal de Oferta de Capacidade — balancing, GUS, and linepack trades.">
<link rel="canonical" href="https://gasbrazil.com/poc/">
<link rel="icon" href="{{FAVICON_DATA_URI}}">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_price_7d: __KPI_PRICE_7D__
     kpi_trades_7d: __KPI_TRADES_7D__
     kpi_when: __KPI_WHEN__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
/* Everything below is this dashboard's own layout/components -- the palette
   (neutral tokens + the shared Brazilian-flag accent) now lives entirely in
   shared/theme.css (see ADR-001, Decision 2 Option C). Token names are
   unchanged from before (poc-dashboard already used the shared kit's
   canonical names), so this file needed no var(--name) renames -- only the
   *values* behind --accent/--accent-soft/--pos changed, uniformly, via that
   one shared file. */
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
/* Same outer shell as ons-dashboard: the shared .wrap column with identical
   padding, in normal document flow -- that page scrolls normally too; only
   its own data tables cap their height and scroll internally (see the
   .table-wrap comment below). */
/* Title row, then the nav-links/controls row always on its own line below
   it -- deterministic, not dependent on flex-wrap kicking in at a given
   viewport width or pill count (see ADR-001: same layout on every
   GasBrazil.com dashboard, not just whichever happens to wrap). */
header.dash-head { display: flex; flex-direction: column; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; width: 100%; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
/* .navlink look owned by shared/theme.css (text underline nav, not pills). */
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }
.tso-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: var(--gap); }
.tso-chip { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 4px 12px; font-size: 12px; box-shadow: var(--shadow); white-space: nowrap; cursor: pointer; color: var(--text); font-family: var(--font); }
.tso-chip:hover { background: var(--accent-soft); }
.tso-chip.selected { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.tso-chip.selected .muted { color: var(--muted); }
.tso-chip.empty { color: var(--muted); }
.tso-chip.empty:hover { background: var(--accent-soft); }
.tso-chip.empty.selected { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.tso-chip.empty.selected:hover { background: var(--panel-grad-hover); }
.tso-chip.empty.selected .muted { color: var(--muted); }
.tso-chip b { font-weight: 400; }
.tso-chip .muted { color: var(--muted); }
.quick-filters { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: var(--gap); }
.qf-btn { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); }
.qf-btn:hover { background: var(--accent-soft); }
.qf-btn.active { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.toolbar select, .toolbar input { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; color: var(--text); font-size: 12.5px; font-family: var(--font); }
.toolbar select:hover { background: var(--accent-soft); }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); font-weight: 400; }
.toolbar button:hover { background: var(--accent-soft); }
.toolbar button.secondary { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; }
/* Capped-height, internally-scrolling table -- the same pattern ons-dashboard
   uses for its own data tables (.scroll / .entlist there: max-height +
   overflow, sticky header), just taller since here the table is the page's
   primary content rather than a small secondary widget. */
.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: auto; box-shadow: var(--shadow); max-height: 65vh; }
table { border-collapse: collapse; width: 100%; font-size: var(--table-font-size); table-layout: fixed; }
th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
th { position: sticky; top: 0; background: var(--panel); cursor: pointer; user-select: none; color: var(--muted2); font-weight: 400; z-index: 2; }
th:hover { background: var(--accent-soft); }
th.dragging { opacity: .4; }
th.drag-over { box-shadow: inset 2px 0 0 var(--accent); }
th .head-inner { display: inline-flex; align-items: center; gap: 3px; max-width: 100%; }
th .arrow { opacity: .4; }
th .filter-icon { opacity: .45; font-size: 10px; padding: 0 2px; }
th .filter-icon:hover, th .filter-icon.active { opacity: 1; color: var(--accent); }
th .resizer { position: absolute; right: 0; top: 0; width: 6px; height: 100%; cursor: col-resize; z-index: 3; }
th .resizer:hover, th .resizer.active { background: var(--accent); opacity: .5; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
tbody tr:hover { background: var(--accent-soft); }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; }
footer a { color: var(--accent); }
.filter-menu { position: fixed; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.16); padding: 8px; z-index: 50; min-width: 190px; max-width: 260px; font-weight: 400; color: var(--text); font-size: 12.5px; }
.filter-menu .fm-list { max-height: 220px; overflow: auto; margin: 4px 0; }
.filter-menu .fm-item { display: flex; align-items: center; gap: 6px; padding: 3px 2px; cursor: pointer; }
.filter-menu .fm-item input { margin: 0; }
.filter-menu .fm-row { display: flex; justify-content: space-between; gap: 6px; }
.filter-menu .fm-row.actions { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.filter-menu button { font-size: 11.5px; padding: 4px 10px; border-radius: 5px; cursor: pointer; font-weight: 400; }
.filter-menu button.link { background: none; border: none; color: var(--accent); padding: 2px 0; }
.filter-menu button.primary { background: var(--accent); color: #fff; border: none; }
.filter-menu button.secondary { background: var(--panel); color: var(--text); border: 1px solid var(--border); }
.filter-menu label.fm-date { display: block; font-size: 11px; color: var(--muted); margin: 6px 0 3px; }
.filter-menu input[type="date"] { width: 100%; }
.filter-menu input[type="text"].fm-search { width: 100%; box-sizing: border-box; padding: 4px 6px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 12px; margin-bottom: 6px; }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; }
.chart-picker { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; align-items: center; }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--accent); background: var(--accent-soft); font-weight: 400; }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.series-btn.active .sw { background: var(--accent); }
#chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
/* Chart tooltip (.tt) styles live in shared/theme.css */
@media (max-width: 720px) {
  .toolbar, .quick-filters, .sources, .tso-row, .chart-picker { flex-direction: column; align-items: stretch; }
  .toolbar select, .toolbar input, .toolbar button { width: 100%; }
  .count { margin-left: 0; }
}
</style>
</head>
<body>
<a class="skip-link" href="#data-table" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  <div>
    <h1 data-i18n="navPoc">POC Results</h1>
  </div>
  <div class="header-right">
    <div class="header-links">
      __SHARED_NAV_LINKS__
    </div>
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a href="https://www.ofertadecapacidade.com.br/PEG/resultado" target="_blank" rel="noopener">POC<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
<div class="tso-row" id="tso-row"></div>
<div class="chart-card">
  <p class="panel-title">Price Trend</p>
  <div class="chart-picker" id="chart-picker"></div>
  <div id="chart-host"></div>
</div>
<div class="quick-filters" id="quick-filters"></div>
<div class="toolbar">
  <select id="f-timing"><option value="">All trade timing</option></select>
  <input id="f-search" type="search" placeholder="Search process / delivery point&hellip;">
  <button class="secondary" id="btn-reset">Reset filters</button>
  <button class="secondary" id="btn-refresh" title="Reload the latest published build. Data itself refreshes automatically every 6 hours; this does not trigger a new pull.">&#8635; Reload latest</button>
  <button class="secondary" id="btn-columns" title="Show or hide columns">Columns</button>
  <button id="btn-csv">Download CSV</button>
  <button id="btn-xlsx">Export all data (Excel)</button>
  <span class="count" id="row-count"></span>
</div>
<div class="table-wrap">
  <table id="data-table">
    <thead><tr id="thead-row"></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>
<footer>
  <div class="asof-strip asof-footer" id="asof-strip">
    <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
    <span class="asof-val" id="asof-refreshed">&mdash;</span>
    <span class="asof-label" data-i18n="dataThrough">Data through</span>
    <span class="asof-val" id="asof-through">&mdash;</span>
  </div>
  &copy; <span id="year"></span> GasBrazil.com &middot; Data: Portal de Oferta de Capacidade (public API) &middot; Contact: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
</div>
<div class="tt" id="chart-tt"></div>
<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";

__SHARED_JS_DECODE__
__SHARED_JS_CSV__
__SHARED_JS_XLSX__
/* Shared cycleSort / buildSortFilterTh (flows/ONS pattern). Full header
   migration to buildSortFilterTh is deferred here: this table still needs
   Excel-style popup filters, column drag/reorder, resize, and hide prefs.
   cycleSort is adopted below for the 3-click header sort cycle. */
__SHARED_JS_TABLE_SORT__

const NUMERIC_COLS = new Set(["Flow Days", "Price", "R$/m3", "Avg Process Price", "Volume Accepted", "Total Value", "Volume Offered", "Total Volume"]);
const DEFAULT_COL_WIDTH = {
  "Transporter (TSO)": 56,
  "Trade Date": 96,
  "Flow Date Start": 96,
  "Flow Date End": 96,
  "Trade Timing": 88,
  "Transaction Type": 88,
  "Delivery Point": 140,
  "Price": 72,
  "R$/m3": 72,
  "Volume Accepted": 100,
  "Service Type": 160,
};
const FALLBACK_COL_WIDTH = 100;
// Columns hidden by default so the table fits most screens without horizontal
// scrolling. Users can re-enable any of these (or hide more) from the Columns
// menu; the choice is remembered in localStorage.
const DEFAULT_HIDDEN_COLS = ["codigoProcesso", "Flow Days", "Service Type", "Avg Process Price", "Total Value", "Volume Offered", "Total Volume"];
const COL_PREFS_KEY = "pocDashboard.columnPrefs.v1";
// Every column gets an Excel-style header filter menu: a date-range picker for
// the date columns, a searchable checkbox list for everything else.
const DATE_FILTER_COLS = new Set(["Trade Date", "Flow Date Start", "Flow Date End"]);

// Quick-filter chips above the toolbar. "set" writes columnFilters[col] to a
// Set of allowed values (same shape the header checkbox menu uses); "days"
// writes a {from, to} range ending today (same shape the date-range menu
// uses). Clicking an already-active chip clears that column's filter.
const QUICK_FILTERS = [
  { key: "last7", label: "Last 7 Days", col: "Trade Date", type: "days", days: 7 },
  { key: "last30", label: "Last 30 Days", col: "Trade Date", type: "days", days: 30 },
  { key: "gus-residual", label: "GUS + Res. Bal.", col: "Transaction Type", type: "set", values: ["GUS", "Res. Bal."] },
  { key: "tso-TAG", label: "TAG", col: "Transporter (TSO)", type: "set", values: ["TAG"] },
  { key: "tso-NTS", label: "NTS", col: "Transporter (TSO)", type: "set", values: ["NTS"] },
  { key: "tso-TBG", label: "TBG", col: "Transporter (TSO)", type: "set", values: ["TBG"] },
];

/* ---------- price chart -----------------------------------------------------
   A single combined SVG line chart: pick any Pipeline + Transaction Type
   combination as a toggle chip below, each becomes its own colored line.
   Left axis is R$/MMBtu (the source unit); the right axis mirrors the same
   gridlines rescaled to R$/m3 (R$/m3 = R$/MMBtu * MMBTU_PER_M3 / 1000, a
   fixed linear factor -- same constant used for the table's R$/m3 column), so
   both units read off one chart instead of duplicating panels. The chart
   plots against the table's `filtered` rows, so the existing toolbar /
   quick-filter / column filters (date range, pipeline, transaction type,
   search) narrow the chart exactly like they narrow the table -- there's
   no separate date range control for the chart itself. POC results are
   event-driven (irregular auction dates), not a daily-published series
   like ons-dashboard's, so points are plotted on a true elapsed-time axis
   and connected date-to-date rather than against a dense calendar grid.
------------------------------------------------------------------------- */
const MMBTU_PER_M3 = __MMBTU_PER_M3__;
__SHARED_JS_CHART_PALETTE__
// Fixed chip order within a pipeline group -- GUS/Residual first since
// those are the two Eric most often looks at together; anything not listed
// here (a new transaction type the API adds later) is appended
// alphabetically so it still shows up rather than silently disappearing.
const TRANSACTION_TYPE_ORDER = ["GUS", "Res. Bal.", "Op. Bal.", "Linepack", "Congestion"];
const PIPELINE_ORDER = ["NTS", "TAG", "TBG"];

const comboKey = (pipeline, type) => pipeline + "||" + type;
const comboLabel = (pipeline, type) => pipeline + " · " + type;

// Chart selection is pipeline chips × type chips (cartesian product of the
// two toggles), not one chip per (pipeline, type) pair. chartPicked is
// derived; colors are TSO-identity (NTS orange / TAG blue / TBG green) with
// shade by transaction type within that pipeline.
let chartPipelines = new Set();
let chartTypes = new Set();
let chartPicked = new Set();
let chartResizeTimer = null;
const chartSlots = new Map();
function chartClaimSlot(key) {
  if (chartSlots.has(key)) return chartSlots.get(key);
  const slot = chartSlots.size % 8;
  chartSlots.set(key, slot);
  return slot;
}
function chartColorOf(key) {
  const parts = String(key || "").split("||");
  const tso = parts[0] || "";
  const type = parts[1] || "";
  let shade = TRANSACTION_TYPE_ORDER.indexOf(type);
  if (shade < 0) shade = chartClaimSlot(key);
  return tsoColorOf(tso, shade);
}

function availableComboSet() {
  const seen = new Set();
  for (const r of DATA.rows) {
    if (r["Price"] === null || r["Price"] === undefined) continue;
    const pipeline = r["Transporter (TSO)"], type = r["Transaction Type"];
    if (!pipeline || !type) continue;
    seen.add(comboKey(pipeline, type));
  }
  return seen;
}

function availablePipelines() {
  const seen = availableComboSet();
  return [...new Set([...seen].map(k => k.split("||")[0]))].sort((a, b) => {
    const ai = PIPELINE_ORDER.indexOf(a), bi = PIPELINE_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
  });
}

function availableTypes() {
  const seen = availableComboSet();
  return [...new Set([...seen].map(k => k.split("||")[1]))].sort((a, b) => {
    const ai = TRANSACTION_TYPE_ORDER.indexOf(a), bi = TRANSACTION_TYPE_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
  });
}

function syncChartPicked() {
  const available = availableComboSet();
  const next = new Set();
  for (const pipeline of chartPipelines) {
    for (const type of chartTypes) {
      const key = comboKey(pipeline, type);
      if (available.has(key)) {
        next.add(key);
        chartClaimSlot(key);
      }
    }
  }
  for (const key of [...chartSlots.keys()]) {
    if (!next.has(key)) chartSlots.delete(key);
  }
  chartPicked = next;
}

function buildChartPicker() {
  const host = document.getElementById("chart-picker");
  host.innerHTML = "";
  for (const type of availableTypes()) {
    const btn = document.createElement("button");
    btn.className = "series-btn";
    btn.type = "button";
    btn.dataset.type = type;
    btn.innerHTML = '<span class="sw"></span>' + escapeHtml(type);
    btn.addEventListener("click", () => toggleChartType(type));
    host.appendChild(btn);
  }
  updateChartPickerButtons();
}

function toggleChartType(type) {
  if (chartTypes.has(type)) chartTypes.delete(type);
  else chartTypes.add(type);
  syncChartPicked();
  updateChartPickerButtons();
  updateTsoChips();
  renderChart();
}

function toggleChartPipeline(pipeline) {
  if (chartPipelines.has(pipeline)) chartPipelines.delete(pipeline);
  else chartPipelines.add(pipeline);
  syncChartPicked();
  updateChartPickerButtons();
  updateTsoChips();
  renderChart();
}

function updateChartPickerButtons() {
  document.querySelectorAll(".series-btn").forEach(btn => {
    btn.classList.toggle("active", chartTypes.has(btn.dataset.type));
  });
}

function updateTsoChips() {
  document.querySelectorAll("#tso-row .tso-chip").forEach(c => {
    c.classList.toggle("selected", chartPipelines.has(c.dataset.tso));
  });
}

// Volume-weighted average Price for one (pipeline, type) combo, one point
// per Trade Date it actually traded on. Falls back to a plain mean if
// every bid on a date has zero/blank accepted volume.
function computeSeries(rows, pipeline, type) {
  const byDate = new Map();
  for (const r of rows) {
    if (r["Transporter (TSO)"] !== pipeline || r["Transaction Type"] !== type) continue;
    if (r["Price"] === null || r["Price"] === undefined || !r["Trade Date"]) continue;
    const d = r["Trade Date"];
    if (!byDate.has(d)) byDate.set(d, []);
    byDate.get(d).push({ price: r["Price"], vol: Number(r["Volume Accepted"]) || 0 });
  }
  const pts = [];
  for (const [date, bids] of byDate) {
    const totalVol = bids.reduce((a, b) => a + b.vol, 0);
    const price = totalVol > 0 ? bids.reduce((a, b) => a + b.price * b.vol, 0) / totalVol : mean(bids.map(b => b.price));
    pts.push({ date, price, trades: bids.length });
  }
  pts.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
  return pts;
}

function chartNiceTicks(lo, hi, n) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag, step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(v);
  return out;
}
const CHART_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function chartAxisLabel(iso, spanDays) {
  const p = iso.split("-");
  return spanDays > 200 ? CHART_MON[+p[1] - 1] + " '" + p[0].slice(2) : p[2] + " " + CHART_MON[+p[1] - 1];
}
function fmtAxisNum(v, d) {
  if (v === null || v === undefined || !isFinite(v)) return "–";
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
const CHART_NS = "http://www.w3.org/2000/svg";
function chartSvgEl(n, a) {
  const e = document.createElementNS(CHART_NS, n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}

function renderChart() {
  const host = document.getElementById("chart-host");
  host.innerHTML = "";
  if (!chartPicked.size) {
    host.innerHTML = '<div class="chart-empty">Select one or more pipelines above and transaction types below to see the price trend.</div>';
    return;
  }
  const seriesList = [...chartPicked].map(key => {
    const [pipeline, type] = key.split("||");
    return { key, pipeline, type, pts: computeSeries(filtered, pipeline, type) };
  }).filter(s => s.pts.length);
  if (!seriesList.length) {
    host.innerHTML = '<div class="chart-empty">No priced trades match the current table filters for the selected series.</div>';
    return;
  }

  const allDates = [...new Set(seriesList.flatMap(s => s.pts.map(p => p.date)))].sort();
  const dNum = iso => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const minD = dNum(allDates[0]), maxD = dNum(allDates[allDates.length - 1]);
  const spanDays = Math.max(1, (maxD - minD) / 86400000);

  let lo = Infinity, hi = -Infinity;
  seriesList.forEach(s => s.pts.forEach(p => { lo = Math.min(lo, p.price); hi = Math.max(hi, p.price); }));
  if (lo > 0 && lo / hi <= 0.55) lo = 0;
  const pad = (hi - lo) * 0.08 || 1; hi += pad; if (lo < 0) lo -= pad;

  const W = Math.max(680, host.clientWidth || 680), H = 360, ML = 66, MR = 66, MT = 26, MB = 32;
  const x = iso => ML + (W - ML - MR) * (maxD === minD ? 0.5 : (dNum(iso) - minD) / (maxD - minD));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo));

  const svg = chartSvgEl("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Price trend by pipeline and transaction type" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  chartNiceTicks(lo, hi, 5).forEach(t => {
    svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(t), y2: y(t), stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvgEl("text", { x: ML - 9, y: y(t) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11.5 });
    lb.textContent = fmtAxisNum(t, 2); lb.style.fontVariantNumeric = "tabular-nums"; svg.appendChild(lb);
    const rb = chartSvgEl("text", { x: W - MR + 9, y: y(t) + 4, "text-anchor": "start", fill: "var(--muted)", "font-size": 11.5 });
    rb.textContent = fmtAxisNum(t * MMBTU_PER_M3 / 1000, 2); rb.style.fontVariantNumeric = "tabular-nums"; svg.appendChild(rb);
  });
  if (lo < 0 && hi > 0) svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1.5 }));

  const lTitle = chartSvgEl("text", { x: ML, y: 14, fill: "var(--muted2)", "font-size": 11, "font-weight": 600 });
  lTitle.textContent = "R$/MMBtu"; svg.appendChild(lTitle);
  const rTitle = chartSvgEl("text", { x: W - MR, y: 14, "text-anchor": "end", fill: "var(--muted2)", "font-size": 11, "font-weight": 600 });
  rTitle.textContent = "R$/m³"; svg.appendChild(rTitle);

  const nT = Math.min(8, allDates.length);
  for (let i = 0; i < nT; i++) {
    const di = allDates[Math.round(i * (allDates.length - 1) / Math.max(1, nT - 1))];
    const t = chartSvgEl("text", { x: x(di), y: H - 9, fill: "var(--muted)", "font-size": 11.5, "text-anchor": i === 0 ? "start" : (i === nT - 1 ? "end" : "middle") });
    t.textContent = chartAxisLabel(di, spanDays); svg.appendChild(t);
  }

  seriesList.forEach(s => {
    let d = "";
    s.pts.forEach((p, i) => { d += (i === 0 ? "M" : "L") + x(p.date).toFixed(1) + " " + y(p.price).toFixed(1) + " "; });
    svg.appendChild(chartSvgEl("path", { d, fill: "none", stroke: chartColorOf(s.key), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    s.pts.forEach(p => {
      svg.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.price), r: 3, fill: chartColorOf(s.key), stroke: "var(--panel)", "stroke-width": 1.5 }));
    });
  });

  const cross = chartSvgEl("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--border-strong)", "stroke-width": 1, opacity: 0 });
  svg.appendChild(cross);
  const dots = chartSvgEl("g", { opacity: 0 });
  svg.appendChild(dots);
  const hit = chartSvgEl("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(hit);

  const tt = document.getElementById("chart-tt");
  // Click-to-reveal hover model (matches ons-dashboard): hovering blank
  // chart space shows nothing. Hovering directly on a line (within
  // HOVER_PX vertical pixels of it, at the nearest plotted date) shows
  // just that line's value, live, tracking the cursor. Clicking a spot
  // that ISN'T on a line pins the full breakdown for that date (every
  // series with a point there); clicking the same pinned date again
  // unpins it, clicking a different spot re-pins there, and leaving the
  // chart clears the pin.
  const HOVER_PX = 14;
  let pinned = null; // pinned date string, or null

  function nearestDateAt(px) {
    let nearest = allDates[0], best = Infinity;
    for (const d of allDates) {
      const dist = Math.abs(x(d) - px);
      if (dist < best) { best = dist; nearest = d; }
    }
    return nearest;
  }
  function nearestLineAt(date, py) {
    let nearest = null, nearestDist = Infinity;
    seriesList.forEach(s => {
      const p = s.pts.find(pt => pt.date === date);
      if (!p) return;
      const dy = Math.abs(y(p.price) - py);
      if (dy < nearestDist) { nearestDist = dy; nearest = s; }
    });
    return (nearest && nearestDist <= HOVER_PX) ? nearest : null;
  }
  function showTooltip(date, focusSeries, clientX, clientY) {
    cross.setAttribute("x1", x(date)); cross.setAttribute("x2", x(date)); cross.setAttribute("opacity", 1);
    dots.innerHTML = ""; dots.setAttribute("opacity", 1);
    let rows = "";
    focusSeries.forEach(s => {
      const p = s.pts.find(pt => pt.date === date);
      if (!p) return;
      dots.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.price), r: 4, fill: chartColorOf(s.key), stroke: "var(--panel)", "stroke-width": 2 }));
      rows += '<tr><td><span class="sw" style="display:inline-block;background:' + chartColorOf(s.key) + '"></span> ' + escapeHtml(comboLabel(s.pipeline, s.type)) +
        '</td><td class="v">' + fmtAxisNum(p.price, 2) + ' MMBtu · ' + fmtAxisNum(p.price * MMBTU_PER_M3 / 1000, 2) + ' m³</td></tr>';
    });
    tt.innerHTML = '<div class="d">' + date + '</div><table>' + rows + '</table>';
    placeChartTooltip(tt, clientX, clientY);
  }
  function hideTooltip() {
    tt.style.display = "none"; cross.setAttribute("opacity", 0); dots.setAttribute("opacity", 0);
  }

  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const py = (ev.clientY - r.top) / r.height * H;
    const nearest = nearestDateAt(px);
    const line = nearestLineAt(nearest, py);
    if (line) showTooltip(nearest, [line], ev.clientX, ev.clientY);
    else if (pinned != null) showTooltip(pinned, seriesList, ev.clientX, ev.clientY);
    else hideTooltip();
  });
  hit.addEventListener("click", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    const py = (ev.clientY - r.top) / r.height * H;
    const nearest = nearestDateAt(px);
    if (nearestLineAt(nearest, py)) return; // clicking on a line: hover already shows it
    if (pinned === nearest) { pinned = null; hideTooltip(); }
    else { pinned = nearest; showTooltip(pinned, seriesList, ev.clientX, ev.clientY); }
  });
  hit.addEventListener("pointerleave", () => {
    pinned = null; hideTooltip();
  });

  host.appendChild(svg);

  const lg = document.createElement("div");
  lg.className = "legend";
  seriesList.forEach(s => {
    const span = document.createElement("span");
    span.innerHTML = '<span class="sw" style="background:' + chartColorOf(s.key) + '"></span>' + escapeHtml(comboLabel(s.pipeline, s.type)) +
      ' <span style="color:var(--muted)">(' + s.pts.length + ' trade date' + (s.pts.length === 1 ? "" : "s") + ')</span>';
    lg.appendChild(span);
  });
  host.appendChild(lg);
}

function initChartDefaults() {
  // Default: every pipeline that has priced data, with GUS on if available
  // (falls back to the first listed type so the chart isn't blank).
  for (const pipeline of availablePipelines()) chartPipelines.add(pipeline);
  const types = availableTypes();
  if (types.includes("GUS")) chartTypes.add("GUS");
  else if (types.length) chartTypes.add(types[0]);
  syncChartPicked();
}

function fmtNum(v, maxFrac) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("en-US", { maximumFractionDigits: maxFrac === undefined ? 2 : maxFrac });
}

function label(col) {
  return (DATA.displayNames && DATA.displayNames[col]) || col;
}

function visibleColumnList() {
  return columnOrder.filter(c => !hiddenCols.has(c));
}

function saveColumnPrefs() {
  try {
    localStorage.setItem(COL_PREFS_KEY, JSON.stringify({
      hidden: [...hiddenCols],
      order: columnOrder,
      widths: columnWidths,
    }));
  } catch (e) { /* storage unavailable (private browsing, etc.) -- ignore */ }
}

function loadColumnPrefs() {
  try {
    const raw = localStorage.getItem(COL_PREFS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

// Cross-dashboard nav links + escapeHtml are now shared (see
// shared/dashboard_kit.py) -- same runtime behavior as before, one canonical
// copy instead of three.
__SHARED_SITE_LINKS_JS__
__SHARED_JS_ESCAPE_HTML__

let DATA = null;
const DEFAULT_SORT = { col: "Trade Date", dir: -1 };
let sortState = { col: DEFAULT_SORT.col, dir: DEFAULT_SORT.dir };
let sortCol = sortState.col;
let sortDir = sortState.dir; // 1 = ascending, -1 = descending (kit cycleSort; no "unsorted")
let filtered = [];
let columnWidths = Object.assign({}, DEFAULT_COL_WIDTH);
let columnOrder = [];
let hiddenCols = new Set(DEFAULT_HIDDEN_COLS);
// columnFilters["Trade Date"] = {from, to}; columnFilters[otherCol] = Set of allowed values.
let columnFilters = {};
let draggedCol = null;

function populateSelect(sel, values) {
  const uniq = [...new Set(values.filter(v => v !== null && v !== undefined && v !== ""))].sort();
  for (const v of uniq) {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = v;
    sel.appendChild(opt);
  }
}

function applyColWidth(el, px) {
  el.style.width = px + "px";
  el.style.maxWidth = px + "px";
  el.classList.add("truncate");
}

// Column widths must survive renderTable() rebuilding tbody's innerHTML on every
// filter/sort/keystroke -- columnWidths is the persistent source of truth; both
// header cells (rebuilt on reorder) and body cells (rebuilt constantly) read from it.
function snapColWidth(col, th, idx) {
  const px = DEFAULT_COL_WIDTH[col] || FALLBACK_COL_WIDTH;
  columnWidths[col] = px;
  applyColWidth(th, px);
  document.querySelectorAll(`#tbody tr > td:nth-child(${idx + 1})`).forEach(td => applyColWidth(td, px));
  saveColumnPrefs();
}

function makeResizable() {
  const ths = document.querySelectorAll("#thead-row th");
  const visCols = visibleColumnList();
  ths.forEach((th, idx) => {
    const col = visCols[idx];
    const resizer = document.createElement("div");
    resizer.className = "resizer";
    th.appendChild(resizer);
    // Double-click the column border to restore that column's default width
    // (Excel-style snap; persists via saveColumnPrefs like a manual resize).
    resizer.addEventListener("dblclick", e => {
      e.preventDefault();
      e.stopPropagation();
      snapColWidth(col, th, idx);
    });
    resizer.addEventListener("mousedown", e => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.pageX;
      const startWidth = th.getBoundingClientRect().width;
      resizer.classList.add("active");
      function onMove(e2) {
        const newWidth = Math.max(44, startWidth + (e2.pageX - startX));
        columnWidths[col] = newWidth;
        applyColWidth(th, newWidth);
        document.querySelectorAll(`#tbody tr > td:nth-child(${idx + 1})`).forEach(td => applyColWidth(td, newWidth));
      }
      function onUp() {
        resizer.classList.remove("active");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        saveColumnPrefs();
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
}

function closeFilterMenus() {
  document.querySelectorAll(".filter-menu").forEach(m => m.remove());
}

function updateFilterIcons() {
  const visCols = visibleColumnList();
  document.querySelectorAll("#thead-row th").forEach((th, idx) => {
    const col = visCols[idx];
    const icon = th.querySelector(".filter-icon");
    if (icon) icon.classList.toggle("active", !!columnFilters[col]);
  });
}

function openFilterMenu(col, anchorEl) {
  const alreadyOpen = document.querySelector(".filter-menu");
  closeFilterMenus();
  if (alreadyOpen && alreadyOpen.dataset.col === col) return;

  const menu = document.createElement("div");
  menu.className = "filter-menu";
  menu.dataset.col = col;
  const rect = anchorEl.getBoundingClientRect();
  menu.style.left = Math.min(rect.left, window.innerWidth - 270) + "px";
  menu.style.top = (rect.bottom + 4) + "px";

  if (DATE_FILTER_COLS.has(col)) {
    const cur = columnFilters[col] || {};
    menu.innerHTML = `
      <label class="fm-date">From</label>
      <input type="date" class="fm-from" value="${cur.from || ""}">
      <label class="fm-date">To</label>
      <input type="date" class="fm-to" value="${cur.to || ""}">
      <div class="fm-row actions">
        <button class="secondary fm-clear">Clear</button>
        <button class="primary fm-apply">Apply</button>
      </div>`;
    menu.querySelector(".fm-apply").addEventListener("click", () => {
      const from = menu.querySelector(".fm-from").value;
      const to = menu.querySelector(".fm-to").value;
      if (from || to) columnFilters[col] = { from, to }; else delete columnFilters[col];
      closeFilterMenus();
      updateFilterIcons();
      render();
    });
    menu.querySelector(".fm-clear").addEventListener("click", () => {
      delete columnFilters[col];
      closeFilterMenus();
      updateFilterIcons();
      render();
    });
  } else {
    // Raw (untyped) unique values, sorted numerically for numeric columns and
    // lexicographically otherwise. Checkbox `value` attributes are always
    // strings, so filter Sets are stored/compared as strings via String(v) --
    // that's what lets a numeric column's active Set match r[col] (a number).
    const rawValues = [...new Set(DATA.rows.map(r => r[col]).filter(v => v !== null && v !== undefined && v !== ""))];
    if (NUMERIC_COLS.has(col)) rawValues.sort((a, b) => a - b); else rawValues.sort();
    const active = columnFilters[col];
    const itemsHtml = rawValues.map(v => {
      const vs = String(v);
      const checked = !active || active.has(vs) ? "checked" : "";
      const displayVal = NUMERIC_COLS.has(col) ? fmtNum(v) : escapeHtml(vs);
      return `<label class="fm-item"><input type="checkbox" value="${escapeHtml(vs)}" ${checked}> ${displayVal}</label>`;
    }).join("");
    menu.innerHTML = `
      <input type="text" class="fm-search" placeholder="Search&hellip;">
      <div class="fm-row">
        <button class="link fm-none">Clear</button>
        <button class="link fm-all">Select all</button>
      </div>
      <div class="fm-list">${itemsHtml}</div>
      <div class="fm-row actions">
        <span></span>
        <button class="primary fm-apply">Apply</button>
      </div>`;
    menu.querySelector(".fm-search").addEventListener("input", e => {
      const q = e.target.value.trim().toLowerCase();
      menu.querySelectorAll(".fm-item").forEach(item => {
        item.style.display = item.textContent.trim().toLowerCase().includes(q) ? "" : "none";
      });
    });
    // Select all / Clear act only on the currently visible (searched) rows.
    menu.querySelector(".fm-all").addEventListener("click", e => {
      e.preventDefault();
      menu.querySelectorAll(".fm-item").forEach(item => {
        if (item.style.display !== "none") item.querySelector("input").checked = true;
      });
    });
    menu.querySelector(".fm-none").addEventListener("click", e => {
      e.preventDefault();
      menu.querySelectorAll(".fm-item").forEach(item => {
        if (item.style.display !== "none") item.querySelector("input").checked = false;
      });
    });
    menu.querySelector(".fm-apply").addEventListener("click", () => {
      const checked = [...menu.querySelectorAll(".fm-list input:checked")].map(c => c.value);
      if (checked.length === 0 || checked.length === rawValues.length) delete columnFilters[col];
      else columnFilters[col] = new Set(checked);
      closeFilterMenus();
      updateFilterIcons();
      render();
    });
  }

  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener("mousedown", onOutsideClick), 0);
  function onOutsideClick(e) {
    if (!menu.contains(e.target) && e.target !== anchorEl) {
      closeFilterMenus();
      document.removeEventListener("mousedown", onOutsideClick);
    }
  }
}

function openColumnMenu(anchorEl) {
  const already = document.querySelector('.filter-menu[data-col-menu]');
  closeFilterMenus();
  if (already) return;

  const menu = document.createElement("div");
  menu.className = "filter-menu";
  menu.dataset.colMenu = "1";
  const rect = anchorEl.getBoundingClientRect();
  menu.style.left = Math.min(rect.left, window.innerWidth - 270) + "px";
  menu.style.top = (rect.bottom + 4) + "px";

  const itemsHtml = columnOrder.map(col => {
    const checked = hiddenCols.has(col) ? "" : "checked";
    return `<label class="fm-item"><input type="checkbox" data-col="${escapeHtml(col)}" ${checked}> ${escapeHtml(label(col))}</label>`;
  }).join("");

  menu.innerHTML = `
    <div class="fm-list">${itemsHtml}</div>
    <div class="fm-row actions">
      <button class="link fm-default">Reset to default</button>
      <button class="link fm-all">Show all</button>
    </div>`;

  menu.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener("change", () => {
      const col = cb.dataset.col;
      if (cb.checked) hiddenCols.delete(col); else hiddenCols.add(col);
      saveColumnPrefs();
      buildHeader();
      render();
    });
  });
  menu.querySelector(".fm-default").addEventListener("click", e => {
    e.preventDefault();
    hiddenCols = new Set(DEFAULT_HIDDEN_COLS);
    saveColumnPrefs();
    closeFilterMenus();
    buildHeader();
    render();
  });
  menu.querySelector(".fm-all").addEventListener("click", e => {
    e.preventDefault();
    hiddenCols = new Set();
    saveColumnPrefs();
    closeFilterMenus();
    buildHeader();
    render();
  });

  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener("mousedown", onColMenuOutsideClick), 0);
  function onColMenuOutsideClick(e) {
    if (!menu.contains(e.target) && e.target !== anchorEl) {
      closeFilterMenus();
      document.removeEventListener("mousedown", onColMenuOutsideClick);
    }
  }
}

function buildHeader() {
  const tr = document.getElementById("thead-row");
  tr.innerHTML = "";
  const visCols = visibleColumnList();
  visCols.forEach((col, idx) => {
    const th = document.createElement("th");
    th.draggable = true;
    th.dataset.col = col;

    const inner = document.createElement("span");
    inner.className = "head-inner";
    const span = document.createElement("span");
    span.textContent = label(col);
    inner.appendChild(span);
    const icon = document.createElement("span");
    icon.className = "filter-icon";
    icon.textContent = "▾";
    icon.addEventListener("click", e => {
      e.stopPropagation();
      openFilterMenu(col, icon);
    });
    inner.appendChild(icon);
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    inner.appendChild(arrow);
    th.appendChild(inner);

    th.addEventListener("click", e => {
      if (e.target.closest(".resizer") || e.target.closest(".filter-icon")) return;
      // Shared 3-click cycle (kit.JS_TABLE_SORT): natural dir -> reverse -> default.
      sortState = cycleSort(sortState, col, DEFAULT_SORT);
      sortCol = sortState.col;
      sortDir = sortState.dir;
      render();
    });

    th.addEventListener("dragstart", e => {
      draggedCol = col;
      th.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    th.addEventListener("dragend", () => {
      th.classList.remove("dragging");
      document.querySelectorAll("#thead-row th").forEach(x => x.classList.remove("drag-over"));
    });
    th.addEventListener("dragover", e => {
      e.preventDefault();
      if (col !== draggedCol) th.classList.add("drag-over");
    });
    th.addEventListener("dragleave", () => th.classList.remove("drag-over"));
    th.addEventListener("drop", e => {
      e.preventDefault();
      th.classList.remove("drag-over");
      if (!draggedCol || draggedCol === col) return;
      const fromIdx = columnOrder.indexOf(draggedCol);
      const toIdx = columnOrder.indexOf(col);
      columnOrder.splice(fromIdx, 1);
      columnOrder.splice(toIdx, 0, draggedCol);
      saveColumnPrefs();
      buildHeader();
      render();
    });

    tr.appendChild(th);
  });
  makeResizable();
  const ths = document.querySelectorAll("#thead-row th");
  visCols.forEach((col, idx) => {
    if (columnWidths[col]) applyColWidth(ths[idx], columnWidths[col]);
  });
  updateFilterIcons();
  updateArrows();
}

function applyFilters() {
  const timing = document.getElementById("f-timing").value;
  const search = document.getElementById("f-search").value.trim().toLowerCase();
  filtered = DATA.rows.filter(r => {
    if (timing && r["Trade Timing"] !== timing) return false;
    for (const col of DATA.columns) {
      const active = columnFilters[col];
      if (!active) continue;
      if (DATE_FILTER_COLS.has(col)) {
        if (active.from && (!r[col] || r[col] < active.from)) return false;
        if (active.to && (!r[col] || r[col] > active.to)) return false;
      } else if (!active.has(String(r[col]))) {
        return false;
      }
    }
    if (search) {
      const hay = ((r["codigoProcesso"] || "") + " " + (r["Delivery Point"] || "")).toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });
}

function sortRows() {
  filtered.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (av === null || av === undefined) av = "";
    if (bv === null || bv === undefined) bv = "";
    if (NUMERIC_COLS.has(sortCol)) { av = Number(av) || 0; bv = Number(bv) || 0; }
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  });
}

function last7dRows() {
  const now = new Date();
  const cutoff = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
  return DATA.rows.filter(r => {
    if (r["Price"] === null || r["Price"] === undefined || !r["Trade Date"]) return false;
    const d = new Date(r["Trade Date"]);
    return d >= cutoff && d <= now;
  });
}

function mean(nums) {
  const valid = nums.filter(n => n !== null && n !== undefined && !isNaN(n));
  if (!valid.length) return null;
  return valid.reduce((a, b) => a + b, 0) / valid.length;
}

// Shows every known pipeline, even ones with zero trades in the last 7 days --
// derived from the full dataset, not just the recent window, so a quiet pipeline
// doesn't just silently disappear from the row. Chips also toggle that pipeline
// on/off for the Price Trend chart (paired with the type chips below).
function renderTsoRow() {
  const allTsos = [...new Set(DATA.rows.map(r => r["Transporter (TSO)"]).filter(Boolean))].sort((a, b) => {
    const ai = PIPELINE_ORDER.indexOf(a), bi = PIPELINE_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
  });
  const recent = last7dRows();
  const byTso = {};
  for (const r of recent) {
    const tso = r["Transporter (TSO)"];
    if (!tso) continue;
    (byTso[tso] = byTso[tso] || []).push(r);
  }
  const el = document.getElementById("tso-row");
  el.innerHTML = "";
  for (const tso of allTsos) {
    const rows = byTso[tso] || [];
    const avg = mean(rows.map(r => r["R$/m3"]));
    const chip = document.createElement("button");
    chip.type = "button";
    chip.dataset.tso = tso;
    chip.title = "Toggle " + tso + " on the price chart";
    if (rows.length) {
      const vol = rows.reduce((a, r) => a + (Number(r["Volume Accepted"]) || 0), 0);
      const volLabel = vol >= 1e6
        ? (vol / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 }) + "M m³"
        : vol.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " m³";
      chip.className = "tso-chip";
      chip.innerHTML = `<b>${escapeHtml(tso)}</b> &middot; ${avg !== null ? avg.toFixed(2) : "—"} R$/m³ avg &middot; ${volLabel} &middot; ${rows.length} trade${rows.length === 1 ? "" : "s"} <span class="muted">(7d)</span>`;
    } else {
      chip.className = "tso-chip empty";
      chip.innerHTML = `<b>${escapeHtml(tso)}</b> &middot; no trades <span class="muted">(7d)</span>`;
    }
    chip.addEventListener("click", () => toggleChartPipeline(tso));
    el.appendChild(chip);
  }
  updateTsoChips();
}

function isoDate(d) { return d.toISOString().slice(0, 10); }

function daysAgoRange(n) {
  const now = new Date();
  const from = new Date(now.getTime() - n * 24 * 3600 * 1000);
  return { from: isoDate(from), to: isoDate(now) };
}

function setsEqual(a, b) {
  if (a.size !== b.size) return false;
  for (const v of a) if (!b.has(v)) return false;
  return true;
}

function quickFilterActive(qf) {
  const active = columnFilters[qf.col];
  if (!active) return false;
  if (qf.type === "set") return active instanceof Set && setsEqual(active, new Set(qf.values));
  const range = daysAgoRange(qf.days);
  return active.from === range.from && active.to === range.to;
}

function toggleQuickFilter(qf) {
  if (quickFilterActive(qf)) {
    delete columnFilters[qf.col];
  } else if (qf.type === "set") {
    columnFilters[qf.col] = new Set(qf.values);
  } else {
    columnFilters[qf.col] = daysAgoRange(qf.days);
  }
  updateFilterIcons();
  render();
}

function buildQuickFilters() {
  const el = document.getElementById("quick-filters");
  el.innerHTML = "";
  for (const qf of QUICK_FILTERS) {
    const btn = document.createElement("button");
    btn.className = "qf-btn";
    btn.dataset.qf = qf.key;
    btn.textContent = qf.label;
    btn.addEventListener("click", () => toggleQuickFilter(qf));
    el.appendChild(btn);
  }
}

function updateQuickFilterButtons() {
  document.querySelectorAll(".qf-btn").forEach(btn => {
    const qf = QUICK_FILTERS.find(q => q.key === btn.dataset.qf);
    btn.classList.toggle("active", quickFilterActive(qf));
  });
}

function renderTable() {
  const tbody = document.getElementById("tbody");
  const frag = document.createDocumentFragment();
  const visCols = visibleColumnList();
  for (const row of filtered) {
    const tr = document.createElement("tr");
    for (const col of visCols) {
      const td = document.createElement("td");
      let v = row[col];
      if (v === null || v === undefined) v = "";
      if (NUMERIC_COLS.has(col)) {
        td.classList.add("num");
        td.textContent = v === "" ? "" : fmtNum(v);
      } else {
        td.textContent = v;
        td.classList.add("truncate");
      }
      if (columnWidths[col]) applyColWidth(td, columnWidths[col]);
      if (v !== "" && v != null) td.title = String(v);
      tr.appendChild(td);
    }
    frag.appendChild(tr);
  }
  tbody.innerHTML = "";
  tbody.appendChild(frag);
  document.getElementById("row-count").textContent = `${filtered.length.toLocaleString("en-US")} of ${DATA.rows.length.toLocaleString("en-US")} rows`;
}

function updateArrows() {
  const ths = document.querySelectorAll("#thead-row th");
  const visCols = visibleColumnList();
  ths.forEach((th, idx) => {
    const arrow = th.querySelector(".arrow");
    if (!arrow) return;
    if (sortCol && visCols[idx] === sortCol) arrow.textContent = sortDir === 1 ? "↑" : "↓";
    else arrow.textContent = "";
  });
}

// Shareable view state in the URL. Covers the toolbar + quick-filter chips
// (the filters people actually want to send a colleague). Excel-style header
// menus are still local-only -- encoding arbitrary column Sets in the query
// string gets noisy fast. `refreshed` is a cache-bust token and is stripped
// so shared links stay clean.
function applyQueryFilters() {
  const sp = new URLSearchParams(location.search);
  const timing = sp.get("timing");
  if (timing) {
    const sel = document.getElementById("f-timing");
    if ([...sel.options].some(o => o.value === timing)) sel.value = timing;
  }
  const q = sp.get("q");
  if (q) document.getElementById("f-search").value = q;
  const qfRaw = sp.get("qf");
  if (qfRaw) {
    for (const key of qfRaw.split(",").map(s => s.trim()).filter(Boolean)) {
      const qf = QUICK_FILTERS.find(x => x.key === key);
      if (!qf) continue;
      if (qf.type === "set") columnFilters[qf.col] = new Set(qf.values);
      else columnFilters[qf.col] = daysAgoRange(qf.days);
    }
  }
}

function writeQueryFilters() {
  const u = new URL(location.href);
  const sp = u.searchParams;
  sp.delete("refreshed");
  const timing = document.getElementById("f-timing").value;
  if (timing) sp.set("timing", timing); else sp.delete("timing");
  const q = document.getElementById("f-search").value.trim();
  if (q) sp.set("q", q); else sp.delete("q");
  const activeQf = QUICK_FILTERS.filter(quickFilterActive).map(qf => qf.key);
  if (activeQf.length) sp.set("qf", activeQf.join(",")); else sp.delete("qf");
  const qs = sp.toString();
  const next = u.pathname + (qs ? "?" + qs : "") + u.hash;
  if (next !== location.pathname + location.search + location.hash)
    history.replaceState(null, "", next);
}

function render() {
  applyFilters();
  sortRows();
  renderTable();
  renderChart();
  updateArrows();
  updateQuickFilterButtons();
  writeQueryFilters();
}

function downloadCsv() {
  const lines = [columnOrder.map(c => csvEscape(label(c))).join(",")];
  for (const row of filtered) {
    lines.push(columnOrder.map(c => csvEscape(row[c])).join(","));
  }
  downloadTextFile(lines.join("\\n"), "text/csv;charset=utf-8;", "poc_results.csv");
}

// "Download CSV" exports only the filtered/visible rows. This is the
// complementary "give me everything" export -- every row, every column,
// straight from the embedded payload, as a single-sheet workbook. Uses the
// same dependency-free XLSX writer ons-dashboard already had (see
// shared/dashboard_kit.py JS_XLSX_ENGINE) -- backported per ADR-001's
// action items so all three dashboards have it.
async function downloadAllXLSX() {
  const btn = document.getElementById("btn-xlsx");
  const prevLabel = btn.textContent;
  btn.disabled = true; btn.textContent = "Building…";
  try {
    await new Promise(r => setTimeout(r, 10));
    const rows = [DATA.columns.map(label)]
      .concat(DATA.rows.map(row => DATA.columns.map(c => row[c])));
    const blob = await buildWorkbookXlsxBlob([{ name: "POC Results", rows }]);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "poc_results_all_data.xlsx";
    a.click(); URL.revokeObjectURL(a.href);
  } finally {
    btn.disabled = false; btn.textContent = prevLabel;
  }
}

// Theme-toggle icons + wiring now shared -- see shared/dashboard_kit.py
// JS_THEME_TOGGLE. initThemeToggle is called from init() below with this
// page's own post-toggle repaint (renderChart/updateChartPickerButtons).
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const text = await inflateGzipUrl(PAYLOAD_URL);
  DATA = JSON.parse(text);
  columnOrder = DATA.columns.slice();
  hiddenCols = new Set(DEFAULT_HIDDEN_COLS);
  const savedPrefs = loadColumnPrefs();
  if (savedPrefs) {
    const validCols = new Set(DATA.columns);
    if (Array.isArray(savedPrefs.order)) {
      const restoredOrder = savedPrefs.order.filter(c => validCols.has(c));
      for (const c of DATA.columns) if (!restoredOrder.includes(c)) restoredOrder.push(c);
      if (restoredOrder.length === DATA.columns.length) columnOrder = restoredOrder;
    }
    if (Array.isArray(savedPrefs.hidden)) hiddenCols = new Set(savedPrefs.hidden.filter(c => validCols.has(c)));
    if (savedPrefs.widths && typeof savedPrefs.widths === "object") columnWidths = Object.assign({}, DEFAULT_COL_WIDTH, savedPrefs.widths);
  }
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated);
  let through = "";
  for (const r of DATA.rows) {
    const d = r["Trade Date"];
    if (d && (!through || d > through)) through = d;
  }
  document.getElementById("asof-through").textContent = through || "—";
  populateSelect(document.getElementById("f-timing"), DATA.rows.map(r => r["Trade Timing"]));
  buildHeader();
  renderTsoRow();
  buildQuickFilters();
  initChartDefaults();
  buildChartPicker();
  applyQueryFilters();
  updateFilterIcons();
  render();
  document.getElementById("f-timing").addEventListener("change", render);
  document.getElementById("f-search").addEventListener("input", render);
  document.getElementById("btn-reset").addEventListener("click", () => {
    document.getElementById("f-timing").value = "";
    document.getElementById("f-search").value = "";
    columnFilters = {};
    updateFilterIcons();
    render();
  });
  document.getElementById("btn-columns").addEventListener("click", e => {
    e.stopPropagation();
    openColumnMenu(e.currentTarget);
  });
  document.getElementById("btn-csv").addEventListener("click", downloadCsv);
  document.getElementById("btn-xlsx").addEventListener("click", downloadAllXLSX);
  // Cache-busting reload -- fetches whatever the most recently published build
  // is (refreshed automatically every 6 hours by GitHub Actions). It does NOT
  // trigger a new pull from the source API: that can only happen server-side,
  // since the source has no CORS headers and a write-capable GitHub token
  // can't safely be embedded in a public static page. Preserve other query
  // params so an open filter view survives the reload.
  document.getElementById("btn-refresh").addEventListener("click", () => {
    const u = new URL(location.href);
    u.searchParams.set("refreshed", String(Date.now()));
    location.href = u.pathname + u.search + u.hash;
  });
  window.addEventListener("resize", () => {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(renderChart, 140);
  });
  initThemeToggle("theme-toggle", () => { renderChart(); updateChartPickerButtons(); });
  initLangToggle("lang-toggle");
  initCrossLinks();
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path=DEFAULT_OUT):
    payload = load_payload()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
    import data_kit as dk  # noqa: E402
    here = Path(__file__).resolve().parent
    payload_path, payload_href = dk.write_and_publish_artifact("poc", payload, here)
    kpi_p = payload.get("kpiPrice7d")
    kpi_n = payload.get("kpiTrades7d") or 0
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload.get("generated") or "",
        KPI_PRICE_7D="" if kpi_p is None else str(kpi_p),
        KPI_TRADES_7D=str(kpi_n),
        KPI_WHEN=payload.get("kpiWhen") or "",
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_ASOF=kit.refreshed_local_js(),
        SHARED_JS_CSV=kit.JS_CSV_HELPERS,
        SHARED_JS_XLSX=kit.JS_XLSX_ENGINE,
        SHARED_JS_TABLE_SORT=kit.JS_TABLE_SORT,
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("poc"),
        SHARED_NAV_LINKS=kit.nav_links_html("poc"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
        MMBTU_PER_M3=str(MMBTU_PER_M3),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(
        f"Wrote dashboard shell ({len(html):,} bytes) + {payload_path.name} "
        f"({payload_path.stat().st_size:,} bytes, {len(payload['rows'])} rows) → {payload_href}"
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
