"""
Builds the single-file POC Contratos (gas transport contracts) dashboard from
data/contratos.parquet.

Usage: python dashboard.py [output_path]  (default: docs/index.html)
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402  (must follow sys.path.insert)

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "contratos.parquet"
DEFAULT_OUT = HERE / "docs" / "index.html"

COLUMNS = [
    "Transporter (TSO)", "Contract Number", "Contract Category", "Status", "Shipper",
    "Product Type", "Point/Zone", "Flow", "Quality", "Start Date", "End Date",
    "Contracted Capacity (000 m3/d)", "Allocated Tariff (R$/MMBtu)", "Tariff Multiplier",
    "Transporter Ownership %", "Amendment",
]

# Internal column key -> display label shown in the table header / CSV export.
# Keys not listed here are displayed as-is (most of them already are the
# display label, since contratos_pipeline.py writes English column names).
DISPLAY_NAMES = {
    "Transporter (TSO)": "Pipeline",
}

DATE_COLS = {"Start Date", "End Date"}


def load_payload():
    df = pd.read_parquet(PARQUET_PATH)

    # Concluded transport contracts are expired/closed -- Eric asked to drop
    # them from the shipped dashboard to keep the client-side payload smaller,
    # since the full history (including concluded rows) stays available in the
    # checked-in data/contratos.parquet for anyone who needs it. Matched
    # case-insensitively since the API's own casing isn't something we control.
    total_rows = len(df)
    is_concluded = df["Status"].astype(str).str.casefold() == "concluded".casefold()
    excluded_concluded = int(is_concluded.sum())
    df = df[~is_concluded]

    df = df[COLUMNS].copy()
    for c in DATE_COLS:
        df[c] = df[c].dt.strftime("%Y-%m-%d").where(df[c].notna(), None)
    # Normalize every remaining missing value (NaN/NaT/pd.NA) to None so json.dumps
    # never has to serialize a bare NaN (invalid JSON) for numeric or string columns.
    df = df.astype(object).where(pd.notna(df), None)
    records = df.to_dict(orient="records")

    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"Excluded {excluded_concluded} concluded contract(s) of {total_rows} total; shipping {len(records)} rows.")

    return {
        "generated": generated,
        "columns": COLUMNS,
        "displayNames": DISPLAY_NAMES,
        "rows": records,
        "excludedConcluded": excluded_concluded,
    }


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>POC Contracts Dashboard</title>
<meta name="description" content="Active transport and master transport contracts across TBG, TAG, and NTS from Brazil's Portal de Oferta de Capacidade.">
<link rel="canonical" href="https://gasbrazil.com/contratos/">
<link rel="icon" href="{{FAVICON_DATA_URI}}">
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
/* Everything below is this dashboard's own layout/components -- the palette
   (neutral tokens + the shared Brazilian-flag accent) now lives entirely in
   shared/theme.css (see ADR-001, Decision 2 Option C). Token names are
   unchanged (this file already used the shared kit's canonical names), so
   only the *values* behind --accent/--accent-soft/--pos changed, uniformly,
   via that one shared file. */
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
header { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; justify-content: space-between; margin-bottom: var(--gap); }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.subtitle { color: var(--muted2); font-size: 13px; }
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-links { display: flex; gap: 8px; flex-wrap: wrap; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 999px; padding: 3px 10px; white-space: nowrap; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.navlink { font-size: 11.5px; color: var(--accent); text-decoration: none; font-weight: 600; border: 1px solid var(--accent); border-radius: 999px; padding: 3px 10px; white-space: nowrap; }
.navlink:hover { background: var(--accent); color: #fff; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }
.tso-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: var(--gap); }
.tso-chip { background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; box-shadow: var(--shadow); white-space: nowrap; cursor: pointer; color: var(--text); font-family: var(--font); }
.tso-chip:hover { background: var(--accent-soft); }
.tso-chip.selected { background: var(--accent); color: #fff; border-color: var(--accent); }
.tso-chip.selected .muted { color: rgba(255,255,255,.72); }
.tso-chip.empty { cursor: default; }
.tso-chip.empty:hover { background: var(--panel); }
.tso-chip.empty { color: var(--muted); }
.tso-chip b { font-weight: 700; }
.tso-chip .muted { color: var(--muted); }
.quick-filters { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.qf-sep { width: 1px; align-self: stretch; background: var(--border-strong); margin: 0 4px; }
.qf-btn.qf-validity { border-style: dashed; }
.drill-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin-bottom: var(--gap); }
.drill-card table { border-collapse: collapse; width: 100%; font-size: 12.5px; white-space: nowrap; }
.drill-card th, .drill-card td { padding: 4px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.drill-card th { color: var(--muted2); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; cursor: default; position: static; }
.drill-card thead tr:first-child th { border-bottom: none; padding-bottom: 0; }
.drill-card th.grp { text-align: center; color: var(--text); letter-spacing: .04em; }
.drill-card th.grp.on { color: var(--accent); }
.drill-card .sep { border-left: 1px solid var(--border); }
.drill-card td.zero { color: var(--muted); }
.drill-card td.num, .drill-card th.num { text-align: right; font-variant-numeric: tabular-nums; }
.drill-card tbody tr { cursor: pointer; }
.drill-card tbody tr:hover { background: var(--accent-soft); }
.drill-card tbody tr.picked { background: var(--accent-soft); font-weight: 600; }
.drill-card .rank { color: var(--muted); width: 22px; }
.drill-more { background: none; border: none; color: var(--accent); font-size: 12px; cursor: pointer; padding: 8px 0 0; font-family: var(--font); }
.qf-btn { background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); }
.qf-btn:hover { background: var(--accent-soft); }
.qf-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.toolbar select, .toolbar input { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 10px; color: var(--text); font-size: 12.5px; font-family: var(--font); }
.toolbar select:hover { background: var(--accent-soft); }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); }
.toolbar button:hover { background: var(--accent-soft); }
.toolbar button.secondary { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; }
.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: auto; box-shadow: var(--shadow); max-height: 65vh; }
table { border-collapse: collapse; width: auto; min-width: 100%; font-size: 12.5px; white-space: nowrap; table-layout: auto; }
th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); }
th { position: sticky; top: 0; background: var(--panel); cursor: pointer; user-select: none; color: var(--muted2); font-weight: 600; z-index: 2; position: relative; }
th:hover { background: var(--accent-soft); }
th.dragging { opacity: .4; }
th.drag-over { box-shadow: inset 2px 0 0 var(--accent); }
th .head-inner { display: inline-flex; align-items: center; gap: 3px; }
th .arrow { opacity: .4; }
th .filter-icon { opacity: .45; font-size: 10px; padding: 0 2px; }
th .filter-icon:hover, th .filter-icon.active { opacity: 1; color: var(--accent); }
th .resizer { position: absolute; right: 0; top: 0; width: 6px; height: 100%; cursor: col-resize; z-index: 3; }
th .resizer:hover, th .resizer.active { background: var(--accent); opacity: .5; }
.truncate { overflow: hidden; text-overflow: ellipsis; }
tbody tr:hover { background: var(--accent-soft); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; }
footer a { color: var(--accent); }
.filter-menu { position: fixed; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.16); padding: 8px; z-index: 50; min-width: 190px; max-width: 260px; font-weight: 400; color: var(--text); font-size: 12.5px; }
.filter-menu .fm-list { max-height: 220px; overflow: auto; margin: 4px 0; }
.filter-menu .fm-item { display: flex; align-items: center; gap: 6px; padding: 3px 2px; cursor: pointer; }
.filter-menu .fm-item input { margin: 0; }
.filter-menu .fm-row { display: flex; justify-content: space-between; gap: 6px; }
.filter-menu .fm-row.actions { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.filter-menu button { font-size: 11.5px; padding: 4px 10px; border-radius: 6px; cursor: pointer; }
.filter-menu button.link { background: none; border: none; color: var(--accent); padding: 2px 0; }
.filter-menu button.primary { background: var(--accent); color: #fff; border: none; }
.filter-menu button.secondary { background: var(--panel); color: var(--text); border: 1px solid var(--border); }
.filter-menu label.fm-date { display: block; font-size: 11px; color: var(--muted); margin: 6px 0 3px; }
.filter-menu input[type="date"] { width: 100%; }
.filter-menu input[type="text"].fm-search { width: 100%; box-sizing: border-box; padding: 4px 6px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 12px; margin-bottom: 6px; }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin: 12px 0 var(--gap); }
.panel-title { font-size: 13px; font-weight: 600; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; }
.chart-picker { display: flex; flex-wrap: wrap; gap: 14px 18px; margin-bottom: 12px; }
.pick-group { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.pick-group-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; margin-right: 2px; }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); font-weight: 600; }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
#chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
.tt { position: fixed; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 6px 20px rgba(0,0,0,.16); z-index: 50; display: none; min-width: 200px; }
.tt .d { font-weight: 600; margin-bottom: 5px; }
.tt table { border-collapse: collapse; width: 100%; }
.tt td { padding: 1px 0; }
.tt td.v { text-align: right; padding-left: 14px; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
</head>
<body>
<a class="skip-link" href="#data-table" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header>
  <div>
    <h1 data-i18n="navContratos">POC Contracts Dashboard</h1>
    <div class="subtitle" id="subtitle">Last refreshed &mdash;</div>
  </div>
  <div class="header-right">
    <div class="header-links">
      <a class="navlink" id="link-home" href="https://gasbrazil.com/">&larr; GasBrazil.com</a>
      <a class="navlink" id="link-poc" href="https://gasbrazil.com/poc/">POC Results Dashboard &rarr;</a>
      <a class="navlink" id="link-ons" href="https://gasbrazil.com/ons/">ONS Balances Dashboard &rarr;</a>
      <a class="navlink" href="../about/" data-i18n="navAbout">About</a>
    </div>
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label">Data source</span>
  <a class="pill" href="https://ofertadecapacidade.com.br/home/contratos" target="_blank" rel="noopener">Portal de Oferta de Capacidade &mdash; Contracts</a>
</div>
<div class="tso-row" id="tso-row"></div>
<div class="drill-card" id="drill-card"></div>
<div class="quick-filters" id="quick-filters"></div>
<div class="toolbar">
  <select id="f-category"><option value="">All contract categories</option></select>
  <input id="f-search" type="search" placeholder="Search contract # / shipper / point&hellip;">
  <button class="secondary" id="btn-reset">Reset filters</button>
  <button class="secondary" id="btn-refresh" title="Reload the latest published build. Data itself refreshes automatically; this does not trigger a new pull.">&#8635; Reload latest</button>
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
<div class="chart-card">
  <p class="panel-title">Allocated Tariff Trend</p>
  <p class="panel-note">Capacity-weighted avg allocated tariff, R$/MMBtu, by contract start date.</p>
  <div class="chart-picker" id="chart-picker"></div>
  <div id="chart-host"></div>
</div>
<footer>
  &copy; <span id="year"></span> GasBrazil.com &middot; Data: Portal de Oferta de Capacidade (public API) &middot; Contact: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
  <br><span id="coverage-note">Active Transport &amp; Master contracts</span><button class="infodot" type="button" aria-label="About contract coverage" data-info="Covers the &quot;Transport Contract&quot; and &quot;Master Contract&quot; contract types. &quot;Legacy Transport Contract&quot; and &quot;Access Connection&quot; are small, separately-sourced categories on the source site and are not yet included. Concluded contracts are excluded from the view.">i</button>
</footer>
</div>
<div class="tt" id="chart-tt"></div>
<script>
const PAYLOAD_B64 = "__PAYLOAD__";

__SHARED_JS_DECODE__
__SHARED_JS_CSV__
__SHARED_JS_XLSX__

const NUMERIC_COLS = new Set(["Contracted Capacity (000 m3/d)", "Allocated Tariff (R$/MMBtu)", "Tariff Multiplier", "Transporter Ownership %"]);
const DEFAULT_COL_WIDTH = { "Shipper": 260, "Contract Number": 190 };
// Columns hidden by default so the table fits most screens without horizontal
// scrolling. Users can re-enable any of these (or hide more) from the Columns
// menu; the choice is remembered in localStorage.
const DEFAULT_HIDDEN_COLS = ["Amendment", "Tariff Multiplier", "Transporter Ownership %", "Quality"];
const COL_PREFS_KEY = "pocContratosDashboard.columnPrefs.v1";
// Every column gets an Excel-style header filter menu: a date-range picker for
// the date columns, a searchable checkbox list for everything else.
const DATE_FILTER_COLS = new Set(["Start Date", "End Date"]);

// Quick-filter chips above the toolbar. "set" writes columnFilters[col] to a
// Set of allowed values (same shape the header checkbox menu uses); "days"
// writes a {from, to} range ending today (same shape the date-range menu
// uses). Clicking an already-active chip clears that column's filter.
const QUICK_FILTERS = [
  { key: "active", label: "Active", col: "Status", type: "set", values: ["Active", "Master Contract Enabled"] },
  { key: "master", label: "Master Contract", col: "Contract Category", type: "set", values: ["Master Contract"] },
  { key: "last30", label: "Started Last 30 Days", col: "Start Date", type: "days", days: 30 },
];
// Pipeline selection lives on the clickable summary chips above (which also
// open the top-shippers drill-down), so it is deliberately not duplicated as a
// quick-filter chip here.

// A contract row is only shown by default when today falls inside its
// [Start Date, End Date] window. The source feed keeps rows at status
// "Active" / "Master Contract Enabled" well past their own end date, so
// status alone is not a reliable currency test. Both exclusions are
// reversible from their own chips rather than silently dropped at build time,
// and "today" is evaluated in the browser so the published file stays correct
// as it ages between rebuilds.
const ACTIVE_STATUSES = new Set(["Active", "Master Contract Enabled"]);
let showExpired = false;
let showFuture = false;
function todayIso() {
  const n = new Date();
  const p = v => String(v).padStart(2, "0");
  return n.getFullYear() + "-" + p(n.getMonth() + 1) + "-" + p(n.getDate());
}
const TODAY_ISO = todayIso();
const isExpired = r => !!r["End Date"] && r["End Date"] < TODAY_ISO;
const isNotYetStarted = r => !!r["Start Date"] && r["Start Date"] > TODAY_ISO;
const isCurrentlyValid = r => !isExpired(r) && !isNotYetStarted(r);

/* ---------- tariff chart -----------------------------------------------------
   A single combined SVG line chart: pick any Pipeline + Contract Category
   combination as a toggle chip below, each becomes its own colored line,
   plotting the capacity-weighted average Allocated Tariff (R$/MMBtu) against
   the contract Start Date. Master contracts carry no tariff/capacity of
   their own, so in practice only "Transport Contract" (and the rare
   "...(Auction)") categories produce a line -- picking a Master combo simply
   shows no points, same empty-state handling as any other combo with zero
   priced rows. The chart plots against the table's `filtered` rows, so the
   existing toolbar / quick-filter / column filters narrow the chart exactly
   like they narrow the table.
------------------------------------------------------------------------- */
const CHART_PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
const CHART_PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const CATEGORY_ORDER = ["Transport Contract", "Transport Contract (Auction)", "Master Contract"];
const TSO_ORDER = ["TBG", "TAG", "NTS"];

const comboKey = (tso, cat) => tso + "||" + cat;
const comboLabel = (tso, cat) => tso + " · " + cat;

let chartPicked = new Set();
let chartResizeTimer = null;
const chartSlots = new Map();
function chartClaimSlot(key) {
  if (chartSlots.has(key)) return chartSlots.get(key);
  const slot = chartSlots.size % CHART_PALETTE_LIGHT.length;
  chartSlots.set(key, slot);
  return slot;
}
function chartColorOf(key) {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  return (dark ? CHART_PALETTE_DARK : CHART_PALETTE_LIGHT)[chartClaimSlot(key)];
}

// Every (TSO, category) pair with at least one tariffed row, anywhere in the
// dataset -- the picker's chip list, independent of the table's current
// filters so a chip never disappears just because a filter happens to be
// narrowing the table right now.
function availableCombos() {
  const seen = new Set();
  for (const r of DATA.rows) {
    if (r["Allocated Tariff (R$/MMBtu)"] === null || r["Allocated Tariff (R$/MMBtu)"] === undefined) continue;
    const tso = r["Transporter (TSO)"], cat = r["Contract Category"];
    if (!tso || !cat) continue;
    seen.add(comboKey(tso, cat));
  }
  const tsos = [...new Set([...seen].map(k => k.split("||")[0]))].sort((a, b) => {
    const ai = TSO_ORDER.indexOf(a), bi = TSO_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
  });
  return tsos.map(tso => {
    const cats = [...seen].filter(k => k.split("||")[0] === tso).map(k => k.split("||")[1]).sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a), bi = CATEGORY_ORDER.indexOf(b);
      return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
    });
    return { tso, cats };
  });
}

function buildChartPicker() {
  const host = document.getElementById("chart-picker");
  host.innerHTML = "";
  for (const group of availableCombos()) {
    const g = document.createElement("div");
    g.className = "pick-group";
    const gl = document.createElement("span");
    gl.className = "pick-group-label";
    gl.textContent = group.tso;
    g.appendChild(gl);
    for (const cat of group.cats) {
      const key = comboKey(group.tso, cat);
      const btn = document.createElement("button");
      btn.className = "series-btn";
      btn.type = "button";
      btn.dataset.key = key;
      btn.innerHTML = '<span class="sw"></span>' + escapeHtml(cat);
      btn.addEventListener("click", () => toggleChartCombo(key));
      g.appendChild(btn);
    }
    host.appendChild(g);
  }
  updateChartPickerButtons();
}

function toggleChartCombo(key) {
  if (chartPicked.has(key)) { chartPicked.delete(key); chartSlots.delete(key); }
  else { chartPicked.add(key); chartClaimSlot(key); }
  updateChartPickerButtons();
  renderChart();
}

function updateChartPickerButtons() {
  document.querySelectorAll(".series-btn").forEach(btn => {
    const key = btn.dataset.key, active = chartPicked.has(key);
    btn.classList.toggle("active", active);
    btn.querySelector(".sw").style.background = active ? chartColorOf(key) : "";
  });
}

// Capacity-weighted average Allocated Tariff for one (TSO, category) combo,
// one point per Start Date it actually appears on. Falls back to a plain
// mean if every contract on a date has zero/blank capacity.
function computeSeries(rows, tso, cat) {
  const byDate = new Map();
  for (const r of rows) {
    if (r["Transporter (TSO)"] !== tso || r["Contract Category"] !== cat) continue;
    const tariff = r["Allocated Tariff (R$/MMBtu)"];
    if (tariff === null || tariff === undefined || !r["Start Date"]) continue;
    const d = r["Start Date"];
    if (!byDate.has(d)) byDate.set(d, []);
    byDate.get(d).push({ tariff, cap: Number(r["Contracted Capacity (000 m3/d)"]) || 0 });
  }
  const pts = [];
  for (const [date, bids] of byDate) {
    const totalCap = bids.reduce((a, b) => a + b.cap, 0);
    const tariff = totalCap > 0 ? bids.reduce((a, b) => a + b.tariff * b.cap, 0) / totalCap : mean(bids.map(b => b.tariff));
    pts.push({ date, tariff, contracts: bids.length });
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
const CHART_DAY_MS = 86400000;
// Date-axis ticks are placed on calendar boundaries across the plotted time
// range, NOT at evenly spaced positions in the list of dates that happen to
// carry a point. Sampling the date list by index is what produced the
// overlapping "Aug '26 / Sep '26" collisions: a cluster of start dates a few
// days apart yielded two ticks that rounded to the same month label and to
// nearly the same pixel, and the final tick was force-anchored "end" on top of
// its neighbour. Month-start (or day-step) ticks plus the minimum-gap check in
// renderChart make the spacing a function of elapsed time instead.
function chartAxisTicks(minD, maxD, spanDays) {
  if (maxD <= minD) return [minD];
  const out = [];
  if (spanDays > 200) {
    const months = Math.max(1, Math.round(spanDays / 30.44));
    const step = Math.max(1, Math.ceil(months / 8));
    const d0 = new Date(minD);
    let cur = Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), 1);
    while (cur < minD) { const c = new Date(cur); cur = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1); }
    while (cur <= maxD) {
      out.push(cur);
      const c = new Date(cur);
      cur = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + step, 1);
    }
  } else {
    const step = Math.max(1, Math.ceil(spanDays / 8));
    for (let t = minD; t <= maxD; t += step * CHART_DAY_MS) out.push(t);
  }
  // A range shorter than one step (or one month) can leave nothing to label.
  if (!out.length) out.push(minD, maxD);
  return out;
}
function chartAxisLabelMs(ms, spanDays) {
  const d = new Date(ms);
  return spanDays > 200
    ? CHART_MON[d.getUTCMonth()] + " '" + String(d.getUTCFullYear()).slice(2)
    : d.getUTCDate() + " " + CHART_MON[d.getUTCMonth()];
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
    host.innerHTML = '<div class="chart-empty">Pick one or more pipeline / contract-category combinations above to see the tariff trend.</div>';
    return;
  }
  const seriesList = [...chartPicked].map(key => {
    const [tso, cat] = key.split("||");
    return { key, tso, cat, pts: computeSeries(filtered, tso, cat) };
  }).filter(s => s.pts.length);
  if (!seriesList.length) {
    host.innerHTML = '<div class="chart-empty">No tariffed contracts match the current table filters for the selected series.</div>';
    return;
  }

  const allDates = [...new Set(seriesList.flatMap(s => s.pts.map(p => p.date)))].sort();
  const dNum = iso => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const minD = dNum(allDates[0]), maxD = dNum(allDates[allDates.length - 1]);
  const spanDays = Math.max(1, (maxD - minD) / 86400000);

  let lo = Infinity, hi = -Infinity;
  seriesList.forEach(s => s.pts.forEach(p => { lo = Math.min(lo, p.tariff); hi = Math.max(hi, p.tariff); }));
  if (lo > 0 && lo / hi <= 0.55) lo = 0;
  const pad = (hi - lo) * 0.08 || 1; hi += pad; if (lo < 0) lo -= pad;

  const W = Math.max(680, host.clientWidth || 680), H = 360, ML = 66, MR = 24, MT = 26, MB = 32;
  const xMs = ms => ML + (W - ML - MR) * (maxD === minD ? 0.5 : (ms - minD) / (maxD - minD));
  const x = iso => xMs(dNum(iso));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo));

  const svg = chartSvgEl("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Allocated tariff trend by pipeline and contract category" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  chartNiceTicks(lo, hi, 5).forEach(t => {
    svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(t), y2: y(t), stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvgEl("text", { x: ML - 9, y: y(t) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11.5 });
    lb.textContent = fmtAxisNum(t, 2); lb.style.fontVariantNumeric = "tabular-nums"; svg.appendChild(lb);
  });
  if (lo < 0 && hi > 0) svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1.5 }));

  const lTitle = chartSvgEl("text", { x: ML, y: 14, fill: "var(--muted2)", "font-size": 11, "font-weight": 600 });
  lTitle.textContent = "R$/MMBtu"; svg.appendChild(lTitle);

  // Draw ticks left to right, skipping any that would sit within MIN_TICK_GAP
  // pixels of the previous label. Labels near either edge switch anchor so a
  // long label can never be clipped by, or bleed past, the plot area.
  const MIN_TICK_GAP = 62;
  let lastTickX = -Infinity;
  for (const ms of chartAxisTicks(minD, maxD, spanDays)) {
    const px = xMs(ms);
    if (px < ML - 1 || px > W - MR + 1) continue;
    if (px - lastTickX < MIN_TICK_GAP) continue;
    lastTickX = px;
    const anchor = px < ML + 18 ? "start" : (px > W - MR - 18 ? "end" : "middle");
    const t = chartSvgEl("text", { x: px, y: H - 9, fill: "var(--muted)", "font-size": 11.5, "text-anchor": anchor });
    t.textContent = chartAxisLabelMs(ms, spanDays); svg.appendChild(t);
  }

  seriesList.forEach(s => {
    let d = "";
    s.pts.forEach((p, i) => { d += (i === 0 ? "M" : "L") + x(p.date).toFixed(1) + " " + y(p.tariff).toFixed(1) + " "; });
    svg.appendChild(chartSvgEl("path", { d, fill: "none", stroke: chartColorOf(s.key), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    s.pts.forEach(p => {
      svg.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.tariff), r: 3, fill: chartColorOf(s.key), stroke: "var(--panel)", "stroke-width": 1.5 }));
    });
  });

  const cross = chartSvgEl("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--border-strong)", "stroke-width": 1, opacity: 0 });
  svg.appendChild(cross);
  const dots = chartSvgEl("g", { opacity: 0 });
  svg.appendChild(dots);
  const hit = chartSvgEl("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(hit);

  const tt = document.getElementById("chart-tt");
  // Click-to-reveal hover model (matches ons-dashboard and poc-dashboard):
  // hovering blank chart space shows nothing. Hovering directly on a line
  // (within HOVER_PX vertical pixels of it, at the nearest plotted date)
  // shows just that line's value, live, tracking the cursor. Clicking a
  // spot that ISN'T on a line pins the full breakdown for that date (every
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
      const dy = Math.abs(y(p.tariff) - py);
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
      dots.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.tariff), r: 4, fill: chartColorOf(s.key), stroke: "var(--panel)", "stroke-width": 2 }));
      rows += '<tr><td><span class="sw" style="display:inline-block;background:' + chartColorOf(s.key) + '"></span> ' + escapeHtml(comboLabel(s.tso, s.cat)) +
        '</td><td class="v">' + fmtAxisNum(p.tariff, 2) + ' R$/MMBtu</td></tr>';
    });
    tt.innerHTML = '<div class="d">' + date + '</div><table>' + rows + '</table>';
    tt.style.display = "block";
    const tw = tt.offsetWidth, th = tt.offsetHeight;
    tt.style.left = Math.min(window.innerWidth - tw - 12, clientX + 16) + "px";
    tt.style.top = Math.min(window.innerHeight - th - 12, Math.max(8, clientY - th / 2)) + "px";
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
    span.innerHTML = '<span class="sw" style="background:' + chartColorOf(s.key) + '"></span>' + escapeHtml(comboLabel(s.tso, s.cat)) +
      ' <span style="color:var(--muted)">(' + s.pts.length + ' start date' + (s.pts.length === 1 ? "" : "s") + ')</span>';
    lg.appendChild(span);
  });
  host.appendChild(lg);
}

function initChartDefaults() {
  for (const group of availableCombos()) {
    if (group.cats.includes("Transport Contract")) {
      const key = comboKey(group.tso, "Transport Contract");
      chartPicked.add(key);
      chartClaimSlot(key);
    }
  }
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
let sortCol = "Start Date";
let sortDir = -1; // 1 = ascending, -1 = descending, 0 = unsorted (third click on a header)
let filtered = [];
// Same row set as `filtered` but with any Shipper filter left off -- see rowPasses().
let filteredForDrill = [];
let columnWidths = Object.assign({}, DEFAULT_COL_WIDTH);
let columnOrder = [];
let hiddenCols = new Set(DEFAULT_HIDDEN_COLS);
// columnFilters["Start Date"] = {from, to}; columnFilters[otherCol] = Set of allowed values.
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
function makeResizable() {
  const ths = document.querySelectorAll("#thead-row th");
  const visCols = visibleColumnList();
  ths.forEach((th, idx) => {
    const col = visCols[idx];
    const resizer = document.createElement("div");
    resizer.className = "resizer";
    th.appendChild(resizer);
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
      // Three-state cycle per column: ascending -> descending -> unsorted.
      // Clicking a different column always starts it at ascending.
      if (sortCol === col) {
        if (sortDir === 1) sortDir = -1;
        else if (sortDir === -1) { sortDir = 0; sortCol = null; }
        else { sortCol = col; sortDir = 1; }
      } else {
        sortCol = col; sortDir = 1;
      }
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

// `skipCol` lets a caller evaluate every filter EXCEPT one column's. The
// drill-down uses it to ignore the Shipper filter, so clicking a shipper in
// the ranking narrows the table without collapsing the ranking that produced
// the click to a single row.
function rowPasses(r, category, search, skipCol) {
  if (!showExpired && isExpired(r)) return false;
  if (!showFuture && isNotYetStarted(r)) return false;
  if (category && r["Contract Category"] !== category) return false;
  for (const col of DATA.columns) {
    if (col === skipCol) continue;
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
    const hay = ((r["Contract Number"] || "") + " " + (r["Shipper"] || "") + " " + (r["Point/Zone"] || "")).toLowerCase();
    if (!hay.includes(search)) return false;
  }
  return true;
}

function applyFilters() {
  const category = document.getElementById("f-category").value;
  const search = document.getElementById("f-search").value.trim().toLowerCase();
  filtered = DATA.rows.filter(r => rowPasses(r, category, search, null));
  filteredForDrill = columnFilters["Shipper"]
    ? DATA.rows.filter(r => rowPasses(r, category, search, "Shipper"))
    : filtered;
}

function sortRows() {
  if (!sortCol || sortDir === 0) return; // third click on a header clears sorting
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

function mean(nums) {
  const valid = nums.filter(n => n !== null && n !== undefined && !isNaN(n));
  if (!valid.length) return null;
  return valid.reduce((a, b) => a + b, 0) / valid.length;
}

// Rows that count toward a pipeline's headline position and toward the
// top-shippers panel: status Active / Master Contract Enabled AND currently inside
// their own contract term. Status alone overstates it -- the feed leaves
// plenty of "Active" rows sitting past their end date.
const isActiveRow = r => ACTIVE_STATUSES.has(r["Status"]) && isCurrentlyValid(r);

function orderedTsos() {
  return [...new Set(DATA.rows.map(r => r["Transporter (TSO)"]).filter(Boolean))].sort((a, b) => {
    const ai = TSO_ORDER.indexOf(a), bi = TSO_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
  });
}

// Snapshot summary, not a rolling time window (contracts are a stock, not a
// stream of trades) -- for each known TSO: how many contracts are active and
// currently in term, and how much contracted capacity that represents (Master
// rows carry no capacity of their own, so they add to the count but not the
// capacity total). Each chip is a button: clicking it filters the table to
// that pipeline and opens the top-shippers drill-down below.
function renderTsoRow() {
  const el = document.getElementById("tso-row");
  el.innerHTML = "";
  for (const tso of orderedTsos()) {
    const rows = DATA.rows.filter(r => r["Transporter (TSO)"] === tso && isActiveRow(r));
    const capacity = rows.reduce((a, r) => a + (Number(r["Contracted Capacity (000 m3/d)"]) || 0), 0);
    const chip = document.createElement("button");
    chip.type = "button";
    chip.dataset.tso = tso;
    if (rows.length) {
      chip.className = "tso-chip";
      chip.title = "Isolate " + tso + " in the top-shippers table and the contract table";
      chip.innerHTML = `<b>${escapeHtml(tso)}</b> &middot; ${rows.length.toLocaleString("en-US")} active contract${rows.length === 1 ? "" : "s"} &middot; ${fmtNum(capacity, 0)} 000 m&sup3;/d contracted`;
      chip.addEventListener("click", () => toggleDrillTso(tso));
    } else {
      chip.className = "tso-chip empty";
      chip.disabled = true;
      chip.innerHTML = `<b>${escapeHtml(tso)}</b> &middot; no active contracts`;
    }
    el.appendChild(chip);
  }
  updateTsoChips();
}

function updateTsoChips() {
  document.querySelectorAll("#tso-row .tso-chip").forEach(c => {
    c.classList.toggle("selected", c.dataset.tso === drillTso);
  });
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

/* ---------- top shippers panel ---------------------------------------------
   The headline panel: who actually holds capacity right now, ranked. It
   defaults to all pipelines with one Entry/Exit column pair per pipeline --
   the same shipper commonly holds both sides, and holdings on TBG vs NTS are
   not interchangeable, so neither dimension is summed away. Clicking a
   pipeline chip narrows it to that pipeline (writing the same
   columnFilters["Transporter (TSO)"] Set the header menu and quick filters
   use, so the table, chart and CSV export narrow with it). A shipper row is
   itself a filter -- clicking one drills the table to that shipper, clicking
   it again releases it.
------------------------------------------------------------------------- */
let drillTso = null;
let drillShowAll = false;
const DRILL_TOP_N = 10;

function toggleDrillTso(tso) {
  if (drillTso === tso) {
    drillTso = null;
    delete columnFilters["Transporter (TSO)"];
  } else {
    drillTso = tso;
    columnFilters["Transporter (TSO)"] = new Set([tso]);
  }
  drillShowAll = false;
  delete columnFilters["Shipper"];
  updateFilterIcons();
  render();
}

// One entry per shipper, carrying entry/exit capacity per pipeline. Built from
// filteredForDrill (every filter in effect except Shipper), restricted to
// contracts that are active AND currently within their own term.
function drillShipperRows(tsos) {
  const by = new Map();
  for (const r of filteredForDrill) {
    const tso = r["Transporter (TSO)"];
    if (!tsos.includes(tso) || !isActiveRow(r)) continue;
    const name = r["Shipper"] || "(unnamed)";
    if (!by.has(name)) by.set(name, { name, cap: {}, contracts: new Set() });
    const e = by.get(name);
    if (!e.cap[tso]) e.cap[tso] = { entry: 0, exit: 0 };
    const c = Number(r["Contracted Capacity (000 m3/d)"]) || 0;
    if (r["Flow"] === "Entry") e.cap[tso].entry += c;
    else if (r["Flow"] === "Exit") e.cap[tso].exit += c;
    if (r["Contract Number"]) e.contracts.add(r["Contract Number"]);
  }
  const out = [...by.values()].map(e => {
    let total = 0;
    for (const t of tsos) total += (e.cap[t] ? e.cap[t].entry + e.cap[t].exit : 0);
    return { ...e, total, nContracts: e.contracts.size };
  });
  out.sort((a, b) => b.total - a.total || b.nContracts - a.nContracts || a.name.localeCompare(b.name));
  return out;
}

function renderDrill() {
  const card = document.getElementById("drill-card");
  // Which pipelines get a column pair: the selected one, or every pipeline
  // that still carries capacity under the filters in effect.
  const candidates = drillTso ? [drillTso] : orderedTsos();
  const all = drillShipperRows(candidates);
  const tsos = candidates.filter(t => all.some(e => e.cap[t] && (e.cap[t].entry || e.cap[t].exit)));
  const cols = tsos.length ? tsos : candidates;

  const scope = drillTso ? escapeHtml(drillTso) : "All Pipelines";
  if (!all.length) {
    card.innerHTML = `<p class="panel-title">Top Shippers by Held Capacity &mdash; ${scope}</p>
      <p class="panel-note">No active, currently-valid contracts match the filters in effect.</p>`;
    return;
  }

  const pickedShipper = columnFilters["Shipper"] && columnFilters["Shipper"].size === 1
    ? [...columnFilters["Shipper"]][0] : null;
  const shown = drillShowAll ? all : all.slice(0, DRILL_TOP_N);
  const grand = all.reduce((a, e) => a + e.total, 0);
  const totalsByTso = {};
  for (const t of cols) totalsByTso[t] = all.reduce((a, e) => a + (e.cap[t] ? e.cap[t].entry + e.cap[t].exit : 0), 0);

  const cell = v => v ? fmtNum(v, 0) : '<span class="zero">&ndash;</span>';
  const head1 = cols.map(t => `<th class="grp sep ${t === drillTso ? "on" : ""}" colspan="2">${escapeHtml(t)}</th>`).join("");
  const head2 = cols.map(() => '<th class="num sep">Entry</th><th class="num">Exit</th>').join("");
  const body = shown.map((e, i) => {
    const cells = cols.map(t => {
      const c = e.cap[t] || { entry: 0, exit: 0 };
      return `<td class="num sep">${cell(c.entry)}</td><td class="num">${cell(c.exit)}</td>`;
    }).join("");
    return `<tr data-shipper="${escapeHtml(e.name)}" class="${pickedShipper === e.name ? "picked" : ""}">
      <td class="rank">${i + 1}</td>
      <td>${escapeHtml(e.name)}</td>
      <td class="num">${e.nContracts.toLocaleString("en-US")}</td>
      ${cells}
      <td class="num sep">${fmtNum(e.total, 0)}</td>
      <td class="num">${grand > 0 ? fmtNum(100 * e.total / grand, 1) + "%" : "&ndash;"}</td>
    </tr>`;
  }).join("");

  const mix = cols.map(t => `${escapeHtml(t)} ${fmtNum(totalsByTso[t], 0)}`).join(" &middot; ");
  card.innerHTML = `
    <p class="panel-title">Top Shippers by Held Capacity &mdash; ${scope}</p>
    <p class="panel-note">Capacity in 000 m&sup3;/d on active contracts currently within their term &middot;
      ${all.length.toLocaleString("en-US")} shipper${all.length === 1 ? "" : "s"} &middot; ${mix} &middot; total ${fmtNum(grand, 0)}</p>
    <table>
      <thead>
        <tr><th></th><th></th><th></th>${head1}<th class="sep"></th><th></th></tr>
        <tr><th></th><th>Shipper</th><th class="num">Contracts</th>${head2}<th class="num sep">Total</th><th class="num">Share</th></tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
    ${all.length > DRILL_TOP_N ? `<button class="drill-more">${drillShowAll ? "Show top " + DRILL_TOP_N + " only" : "Show all " + all.length.toLocaleString("en-US") + " shippers"}</button>` : ""}`;

  card.querySelectorAll("tbody tr").forEach(tr => {
    tr.addEventListener("click", () => {
      const name = tr.dataset.shipper;
      if (pickedShipper === name) delete columnFilters["Shipper"];
      else columnFilters["Shipper"] = new Set([name]);
      updateFilterIcons();
      render();
    });
  });
  const more = card.querySelector(".drill-more");
  if (more) more.addEventListener("click", () => { drillShowAll = !drillShowAll; renderDrill(); });
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
  const sep = document.createElement("span");
  sep.className = "qf-sep";
  el.appendChild(sep);
  // The two currency toggles are separated from the filter chips above because
  // they widen the row set rather than narrowing it.
  const nExpired = DATA.rows.filter(isExpired).length;
  const nFuture = DATA.rows.filter(isNotYetStarted).length;
  const mkToggle = (key, text, count, get, set) => {
    const btn = document.createElement("button");
    btn.className = "qf-btn qf-validity";
    btn.dataset.validity = key;
    btn.textContent = text + " (" + count.toLocaleString("en-US") + ")";
    btn.title = "Hidden by default -- these contracts are not currently in term.";
    btn.addEventListener("click", () => { set(!get()); render(); });
    el.appendChild(btn);
  };
  mkToggle("expired", "Show expired", nExpired, () => showExpired, v => { showExpired = v; });
  mkToggle("future", "Show not yet started", nFuture, () => showFuture, v => { showFuture = v; });
}

function updateQuickFilterButtons() {
  document.querySelectorAll(".qf-btn[data-qf]").forEach(btn => {
    const qf = QUICK_FILTERS.find(q => q.key === btn.dataset.qf);
    btn.classList.toggle("active", quickFilterActive(qf));
  });
  const ex = document.querySelector('.qf-btn[data-validity="expired"]');
  if (ex) ex.classList.toggle("active", showExpired);
  const fu = document.querySelector('.qf-btn[data-validity="future"]');
  if (fu) fu.classList.toggle("active", showFuture);
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
      }
      if (columnWidths[col]) applyColWidth(td, columnWidths[col]);
      tr.appendChild(td);
    }
    frag.appendChild(tr);
  }
  tbody.innerHTML = "";
  tbody.appendChild(frag);
  const inScope = DATA.rows.filter(r => (showExpired || !isExpired(r)) && (showFuture || !isNotYetStarted(r))).length;
  const hidden = DATA.rows.length - inScope;
  document.getElementById("row-count").textContent =
    `${filtered.length.toLocaleString("en-US")} of ${inScope.toLocaleString("en-US")} rows` +
    (hidden ? ` (${hidden.toLocaleString("en-US")} not currently valid, hidden)` : "");
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

// Shareable view state in the URL. Toolbar + quick chips + TSO/shipper drill
// + the expired/future validity toggles. Header-menu column Sets stay local.
// `refreshed` is a cache-bust token and is stripped from shared links.
function applyQueryFilters() {
  const sp = new URLSearchParams(location.search);
  const category = sp.get("category");
  if (category) {
    const sel = document.getElementById("f-category");
    if ([...sel.options].some(o => o.value === category)) sel.value = category;
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
  const tso = sp.get("tso");
  if (tso && orderedTsos().includes(tso)) {
    drillTso = tso;
    columnFilters["Transporter (TSO)"] = new Set([tso]);
  }
  const shipper = sp.get("shipper");
  if (shipper) columnFilters["Shipper"] = new Set([shipper]);
  if (sp.get("expired") === "1") showExpired = true;
  if (sp.get("future") === "1") showFuture = true;
}

function writeQueryFilters() {
  const u = new URL(location.href);
  const sp = u.searchParams;
  sp.delete("refreshed");
  const category = document.getElementById("f-category").value;
  if (category) sp.set("category", category); else sp.delete("category");
  const q = document.getElementById("f-search").value.trim();
  if (q) sp.set("q", q); else sp.delete("q");
  const activeQf = QUICK_FILTERS.filter(quickFilterActive).map(qf => qf.key);
  if (activeQf.length) sp.set("qf", activeQf.join(",")); else sp.delete("qf");
  if (drillTso) sp.set("tso", drillTso); else sp.delete("tso");
  const shipper = columnFilters["Shipper"] && columnFilters["Shipper"].size === 1
    ? [...columnFilters["Shipper"]][0] : null;
  if (shipper) sp.set("shipper", shipper); else sp.delete("shipper");
  if (showExpired) sp.set("expired", "1"); else sp.delete("expired");
  if (showFuture) sp.set("future", "1"); else sp.delete("future");
  const qs = sp.toString();
  const next = u.pathname + (qs ? "?" + qs : "") + u.hash;
  if (next !== location.pathname + location.search + location.hash)
    history.replaceState(null, "", next);
}

function render() {
  applyFilters();
  sortRows();
  renderTable();
  renderDrill();
  renderChart();
  updateArrows();
  updateQuickFilterButtons();
  updateTsoChips();
  writeQueryFilters();
}

function downloadCsv() {
  const lines = [columnOrder.map(c => csvEscape(label(c))).join(",")];
  for (const row of filtered) {
    lines.push(columnOrder.map(c => csvEscape(row[c])).join(","));
  }
  downloadTextFile(lines.join("\\n"), "text/csv;charset=utf-8;", "poc_contracts.csv");
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
  btn.disabled = true; btn.textContent = "Building\u2026";
  try {
    await new Promise(r => setTimeout(r, 10));
    const rows = [DATA.columns.map(label)]
      .concat(DATA.rows.map(row => DATA.columns.map(c => row[c])));
    const blob = await buildWorkbookXlsxBlob([{ name: "POC Contracts", rows }]);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "poc_contracts_all_data.xlsx";
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

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const text = await inflateGzipB64(PAYLOAD_B64);
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
  document.getElementById("subtitle").textContent = "Last refreshed " + DATA.generated;
  if (DATA.excludedConcluded) {
    document.getElementById("coverage-note").textContent =
      `Active Transport & Master contracts \u00b7 ${DATA.excludedConcluded.toLocaleString("en-US")} concluded excluded`;
  }
  populateSelect(document.getElementById("f-category"), DATA.rows.map(r => r["Contract Category"]));
  buildHeader();
  renderTsoRow();
  buildQuickFilters();
  initChartDefaults();
  buildChartPicker();
  applyQueryFilters();
  updateFilterIcons();
  render();
  document.getElementById("f-category").addEventListener("change", render);
  document.getElementById("f-search").addEventListener("input", render);
  document.getElementById("btn-reset").addEventListener("click", () => {
    document.getElementById("f-category").value = "";
    document.getElementById("f-search").value = "";
    columnFilters = {};
    drillTso = null;
    drillShowAll = false;
    showExpired = false;
    showFuture = false;
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
  // is. It does NOT trigger a new pull from the source API: that can only
  // happen server-side (scheduled/manual GitHub Actions run). Preserve other
  // query params so an open filter view survives the reload.
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
    b64 = kit.encode_payload_b64(payload)
    html = kit.render(
        TEMPLATE,
        PAYLOAD=b64,
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_CSV=kit.JS_CSV_HELPERS,
        SHARED_JS_XLSX=kit.JS_XLSX_ENGINE,
        SHARED_SITE_LINKS_JS=kit.site_links_js("contratos"),
        FAVICON_DATA_URI=kit.embed_favicon(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote dashboard ({len(html):,} bytes, {len(payload['rows'])} rows) to {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
