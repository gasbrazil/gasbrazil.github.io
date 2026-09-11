"""
Builds the single-file Gas Supply dashboard from data/supply_monthly.parquet.

Usage: python dashboard.py [output_path]  (default: index.html)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "supply_monthly.parquet"
DEFAULT_OUT = HERE / "index.html"

# Payload keys + chart labels. Units: thousand m³/month except LGN (m³).
METRICS = [
    ("production", "Production", "Produção", "thousand m³", "mil m³"),
    ("available", "Available", "Disponível", "thousand m³", "mil m³"),
    ("flare_loss", "Flare & loss", "Queima e perda", "thousand m³", "mil m³"),
    ("own_use", "Own use", "Consumo próprio", "thousand m³", "mil m³"),
    ("reinjection", "Reinjection", "Reinjeção", "thousand m³", "mil m³"),
    ("imports", "Imports", "Importações", "thousand m³", "mil m³"),
    ("lgn", "LGN (NGL)", "LGN", "m³", "m³"),
]

# Default on-chart series (LGN stays off — different unit scale).
DEFAULT_ON = {"production", "available", "flare_loss", "own_use"}


def load_payload() -> dict:
    if not PARQUET_PATH.exists():
        raise RuntimeError(f"Missing {PARQUET_PATH} — run supply_pipeline.py build (or make_mock.py + build)")
    df = pd.read_parquet(PARQUET_PATH)
    if df.empty:
        raise RuntimeError("supply_monthly.parquet is empty")

    months = [str(m) for m in df["month"].tolist()]
    series = {}
    for key, *_rest in METRICS:
        if key not in df.columns:
            series[key] = [None] * len(months)
            continue
        vals = []
        for v in df[key].tolist():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                vals.append(None)
            else:
                vals.append(round(float(v), 3))
        series[key] = vals

    # Latest month with production (or available) present
    last_idx = None
    for i in range(len(months) - 1, -1, -1):
        if series["production"][i] is not None or series["available"][i] is not None:
            last_idx = i
            break
    if last_idx is None:
        last_idx = len(months) - 1

    def _at(key: str):
        v = series.get(key, [None])[last_idx]
        return v

    _now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated": _now.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": _now.isoformat(),
        "months": months,
        "series": series,
        "metrics": [
            {
                "key": k,
                "labelEn": en,
                "labelPt": pt,
                "unitEn": uen,
                "unitPt": upt,
                "defaultOn": k in DEFAULT_ON,
            }
            for k, en, pt, uen, upt in METRICS
        ],
        "dataThrough": months[last_idx],
        "kpi": {
            "production": _at("production"),
            "available": _at("available"),
            "flare_loss": _at("flare_loss"),
            "own_use": _at("own_use"),
            "imports": _at("imports"),
        },
        "nMonths": len(months),
        "importGap": all(v is None for v in series.get("imports", [])),
    }


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gas Supply — GasBrazil.com</title>
<meta name="description" content="Brazil natural gas supply balance from ANP PPGN-EL: national monthly production, available gas, flare/loss, own use, reinjection, LGN, and imports.">
<link rel="canonical" href="https://gasbrazil.com/supply/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_production: __KPI_PRODUCTION__
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
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }

.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin-bottom: var(--gap); }
.kpi-cell { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; }
.kpi-cell .lbl { font-size: 11px; color: var(--muted2); font-weight: 400; }
.kpi-cell .val { font-size: 18px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 4px; }
.kpi-cell .unit { font-size: 11px; color: var(--muted); font-weight: 200; }

.chart-card, .table-card { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; }
.series-picker { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
#chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
/* Chart tooltip (.tt) styles live in shared/theme.css */

.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); font-weight: 400; }
.toolbar button:hover { background: var(--accent-soft); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; font-weight: 200; }
.table-wrap { overflow: auto; max-height: 55vh; border: 1px solid var(--border); border-radius: 5px; }
table { width: 100%; font-size: var(--table-font-size); table-layout: fixed; }
th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); font-weight: 300; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
th { background: var(--panel); color: var(--muted2); font-weight: 400; }
th .th-label { cursor: pointer; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tbody tr:hover { background: var(--accent-soft); }
.gap-note { font-size: 12px; color: var(--muted); margin: 0 0 var(--gap); font-weight: 200; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
@media (max-width: 720px) {
  .toolbar, .sources, .series-picker { flex-direction: column; align-items: stretch; }
  .toolbar button { width: 100%; }
  .count { margin-left: 0; }
}
</style>
</head>
<body>
<a class="skip-link" href="#chart-host" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  __SHARED_MASTHEAD__
  <div class="header-right">
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-estado-e-localizacao" target="_blank" rel="noopener" title="ANP PPGN-EL">ANP<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/importacoes-e-exportacoes" target="_blank" rel="noopener" title="ANP imports / exports">ANP<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
<p class="gap-note" id="import-gap" hidden data-i18n="supplyImportGap">Natural-gas import CSV was not available at build time; chart shows production / availability series only.</p>
<div class="kpi-row" id="kpi-row"></div>
<div class="chart-card">
  <p class="panel-title" data-i18n="supplyChartTitle">Monthly supply balance</p>
  <p class="panel-note" data-i18n="supplyChartNote">National totals (sum of UF × location). LGN is cubic metres; other series are thousand m³.</p>
  <div class="series-picker" id="series-picker"></div>
  <div id="chart-host"></div>
  <div class="legend" id="chart-legend"></div>
</div>
<div class="table-card">
  <p class="panel-title" data-i18n="supplyTableTitle">Monthly series</p>
  <div class="toolbar">
    <button type="button" id="btn-csv" data-i18n="supplyCsv">Download CSV</button>
    <button type="button" id="btn-xlsx" data-i18n="supplyXlsx">Export Excel</button>
    __SHARED_SHARE_BUTTON__
    <span class="count" id="row-count"></span>
  </div>
  <div class="table-wrap">
    <table id="data-table">
      <thead><tr id="thead-row"></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
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
  <span data-i18n="supplyFooter">Data: ANP PPGN-EL and importações de gás natural (open data). Not an official ANP product.</span>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
</div>
<div class="tt" id="chart-tt"></div>
<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";
__SHARED_JS_DECODE__
__SHARED_JS_ESCAPE_HTML__
__SHARED_JS_CSV__
__SHARED_JS_XLSX__
__SHARED_JS_TABLE_SORT__
__SHARED_JS_CHART_PALETTE__
__SHARED_SITE_LINKS_JS__
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__
__SHARED_JS_QUERY_STATE__

// Page-local i18n keys merged into the shared pack.
GB_I18N.en.navSupply = "Gas Supply";
GB_I18N.en.supplySubtitle = "ANP national monthly natural gas supply balance — production, available gas, flare, own use, and imports.";
GB_I18N.en.supplyChartTitle = "Monthly supply balance";
GB_I18N.en.supplyChartNote = "National totals (sum of UF × location). LGN is cubic metres; other series are thousand m³.";
GB_I18N.en.supplyTableTitle = "Monthly series";
GB_I18N.en.supplyCsv = "Download CSV";
GB_I18N.en.supplyXlsx = "Export Excel";
GB_I18N.en.supplyFooter = "Data: ANP PPGN-EL and importações de gás natural (open data). Not an official ANP product.";
GB_I18N.en.supplyImportGap = "Natural-gas import CSV was not available at build time; chart shows production / availability series only.";
GB_I18N.en.supplyKpiProd = "Production";
GB_I18N.en.supplyKpiAvail = "Available";
GB_I18N.en.supplyKpiFlare = "Flare & loss";
GB_I18N.en.supplyKpiOwn = "Own use";
GB_I18N.en.supplyKpiImp = "Imports";
GB_I18N.pt.navSupply = "Oferta de Gás";
GB_I18N.pt.supplySubtitle = "Balanço mensal nacional de gás natural da ANP (PPGN-EL) — produção, disponível, queima, consumo próprio e importações.";
GB_I18N.pt.supplyChartTitle = "Balanço mensal de oferta";
GB_I18N.pt.supplyChartNote = "Totais nacionais (soma UF × localização). LGN em m³; demais séries em mil m³.";
GB_I18N.pt.supplyTableTitle = "Série mensal";
GB_I18N.pt.supplyCsv = "Baixar CSV";
GB_I18N.pt.supplyXlsx = "Exportar Excel";
GB_I18N.pt.supplyFooter = "Dados: ANP PPGN-EL e importações de gás natural (dados abertos). Não é um produto oficial da ANP.";
GB_I18N.pt.supplyImportGap = "O CSV de importações de gás natural não estava disponível na compilação; o gráfico mostra só produção / disponibilidade.";
GB_I18N.pt.supplyKpiProd = "Produção";
GB_I18N.pt.supplyKpiAvail = "Disponível";
GB_I18N.pt.supplyKpiFlare = "Queima e perda";
GB_I18N.pt.supplyKpiOwn = "Consumo próprio";
GB_I18N.pt.supplyKpiImp = "Importações";

let DATA = null;
let picked = new Set();
let chartSlots = new Map();
let chartResizeTimer = null;
let sortState = { col: "month", dir: -1 };
const defaultSort = { col: "month", dir: -1 };
let filters = {};

function metricLabel(m) { return currentLang() === "pt" ? m.labelPt : m.labelEn; }
function metricUnit(m) { return currentLang() === "pt" ? m.unitPt : m.unitEn; }

function fmtNum(v, digits) {
  if (v === null || v === undefined) return "—";
  const d = digits == null ? (Math.abs(v) >= 1000 ? 0 : 1) : digits;
  return Number(v).toLocaleString(currentLang() === "pt" ? "pt-BR" : "en-US", {
    minimumFractionDigits: 0, maximumFractionDigits: d
  });
}

function colorOf(key) {
  const pal = chartPalette();
  if (!chartSlots.has(key)) chartSlots.set(key, chartSlots.size % Math.max(1, pal.length));
  return pal[chartSlots.get(key) % pal.length] || "var(--accent)";
}

function buildPicker() {
  const host = document.getElementById("series-picker");
  host.innerHTML = "";
  DATA.metrics.forEach(m => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "series-btn" + (picked.has(m.key) ? " active" : "");
    btn.dataset.key = m.key;
    btn.innerHTML = '<span class="sw"></span>' + escapeHtml(metricLabel(m));
    btn.querySelector(".sw").style.background = picked.has(m.key) ? colorOf(m.key) : "";
    btn.addEventListener("click", () => {
      if (picked.has(m.key)) { picked.delete(m.key); chartSlots.delete(m.key); }
      else { picked.add(m.key); colorOf(m.key); }
      buildPicker();
      renderChart();
      writeSupplyQuery();
    });
    host.appendChild(btn);
  });
}

// Shareable view state: the selected series set. Unknown keys degrade to
// the builder defaults via the shared gb* query helpers
// (see shared/dashboard_kit.py JS_QUERY_STATE).
function supplySeriesKeys() { return (DATA.metrics || []).map(m => m.key); }
function applySupplyQuery() {
  const keys = gbValidList(gbQueryParams().get("series"), supplySeriesKeys());
  if (keys) {
    picked = new Set(keys);
    chartSlots = new Map();
    keys.forEach(k => colorOf(k));
  }
}
function writeSupplyQuery() {
  gbWriteQuery({ series: [...picked] });
}

function renderKpis() {
  const host = document.getElementById("kpi-row");
  const kpi = DATA.kpi || {};
  const cells = [
    { key: "supplyKpiProd", val: kpi.production, unit: "thousand m³" },
    { key: "supplyKpiAvail", val: kpi.available, unit: "thousand m³" },
    { key: "supplyKpiFlare", val: kpi.flare_loss, unit: "thousand m³" },
    { key: "supplyKpiOwn", val: kpi.own_use, unit: "thousand m³" },
    { key: "supplyKpiImp", val: kpi.imports, unit: "thousand m³" },
  ];
  host.innerHTML = cells.map(c => `
    <div class="kpi-cell">
      <div class="lbl" data-i18n="${c.key}">${t(c.key)}</div>
      <div class="val">${fmtNum(c.val)}</div>
      <div class="unit">${c.unit} · ${DATA.dataThrough || ""}</div>
    </div>`).join("");
}

const CHART_NS = "http://www.w3.org/2000/svg";
function el(n, a) {
  const e = document.createElementNS(CHART_NS, n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}
function niceTicks(lo, hi, n) {
  if (!isFinite(lo) || !isFinite(hi) || lo === hi) return [lo || 0];
  const span = hi - lo;
  const step0 = span / Math.max(1, n);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const residual = step0 / mag;
  const step = (residual >= 5 ? 5 : residual >= 2 ? 2 : 1) * mag;
  const start = Math.ceil(lo / step) * step;
  const out = [];
  for (let v = start; v <= hi + step * 0.01; v += step) out.push(v);
  return out;
}

function renderChart() {
  const host = document.getElementById("chart-host");
  const legend = document.getElementById("chart-legend");
  host.innerHTML = "";
  legend.innerHTML = "";
  const keys = [...picked];
  if (!keys.length) {
    host.innerHTML = '<div class="chart-empty">Select one or more series.</div>';
    return;
  }
  const months = DATA.months;
  const seriesList = keys.map(k => {
    const m = DATA.metrics.find(x => x.key === k);
    const pts = [];
    const arr = DATA.series[k] || [];
    for (let i = 0; i < months.length; i++) {
      if (arr[i] !== null && arr[i] !== undefined) pts.push({ month: months[i], v: arr[i] });
    }
    return { key: k, meta: m, pts, color: colorOf(k) };
  }).filter(s => s.pts.length);

  if (!seriesList.length) {
    host.innerHTML = '<div class="chart-empty">No data for the selected series.</div>';
    return;
  }

  // LGN uses a different unit — if mixed with 1000m3 series, chart only non-LGN
  // unless LGN is the sole pick.
  const hasLgn = seriesList.some(s => s.key === "lgn");
  const hasOther = seriesList.some(s => s.key !== "lgn");
  let plot = seriesList;
  if (hasLgn && hasOther) plot = seriesList.filter(s => s.key !== "lgn");

  let lo = Infinity, hi = -Infinity;
  plot.forEach(s => s.pts.forEach(p => { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); }));
  if (lo > 0 && lo / hi <= 0.55) lo = 0;
  const pad = (hi - lo) * 0.08 || 1;
  hi += pad;
  if (lo < 0) lo -= pad;

  const allM = [...new Set(plot.flatMap(s => s.pts.map(p => p.month)))].sort();
  const dNum = m => Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, 1);
  const minD = dNum(allM[0]), maxD = dNum(allM[allM.length - 1]);

  const W = Math.max(680, host.clientWidth || 680), H = 360, ML = 72, MR = 16, MT = 26, MB = 32;
  const x = m => ML + (W - ML - MR) * (maxD === minD ? 0.5 : (dNum(m) - minD) / (maxD - minD));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo));

  const svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Supply chart" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  niceTicks(lo, hi, 5).forEach(tk => {
    svg.appendChild(el("line", { x1: ML, x2: W - MR, y1: y(tk), y2: y(tk), stroke: "var(--border)", "stroke-width": 1 }));
    const lb = el("text", { x: ML - 9, y: y(tk) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11.5 });
    lb.textContent = fmtNum(tk, Math.abs(tk) >= 1000 ? 0 : 1);
    lb.style.fontVariantNumeric = "tabular-nums";
    svg.appendChild(lb);
  });

  const unitTitle = el("text", { x: ML, y: 14, fill: "var(--muted2)", "font-size": 11, "font-weight": 400 });
  unitTitle.textContent = plot[0] ? metricUnit(plot[0].meta) : "";
  svg.appendChild(unitTitle);

  const nT = Math.min(8, allM.length);
  for (let i = 0; i < nT; i++) {
    const mi = allM[Math.round(i * (allM.length - 1) / Math.max(1, nT - 1))];
    const tEl = el("text", {
      x: x(mi), y: H - 9, fill: "var(--muted)", "font-size": 11.5,
      "text-anchor": i === 0 ? "start" : (i === nT - 1 ? "end" : "middle")
    });
    tEl.textContent = mi;
    svg.appendChild(tEl);
  }

  plot.forEach(s => {
    let d = "";
    s.pts.forEach((p, i) => { d += (i === 0 ? "M" : "L") + x(p.month).toFixed(1) + " " + y(p.v).toFixed(1) + " "; });
    svg.appendChild(el("path", { d: d.trim(), fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  });

  // hover capture
  const overlay = el("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(overlay);
  const cross = el("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--border-strong)", "stroke-width": 1, "stroke-dasharray": "3 3", visibility: "hidden" });
  svg.appendChild(cross);
  const tt = document.getElementById("chart-tt");
  overlay.addEventListener("mousemove", ev => {
    const rect = svg.getBoundingClientRect();
    const px = (ev.clientX - rect.left) * (W / rect.width);
    let best = allM[0], bestDist = Infinity;
    allM.forEach(m => {
      const dist = Math.abs(x(m) - px);
      if (dist < bestDist) { bestDist = dist; best = m; }
    });
    cross.setAttribute("x1", x(best)); cross.setAttribute("x2", x(best));
    cross.setAttribute("visibility", "visible");
    let rows = "";
    plot.forEach(s => {
      const p = s.pts.find(pt => pt.month === best);
      if (!p) return;
      rows += "<tr><td>" + escapeHtml(metricLabel(s.meta)) + '</td><td class="v">' + fmtNum(p.v) + "</td></tr>";
    });
    tt.innerHTML = '<div class="d">' + best + "</div><table>" + rows + "</table>";
    placeChartTooltip(tt, ev.clientX, ev.clientY);
  });
  overlay.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden");
    tt.style.display = "none";
  });

  host.appendChild(svg);
  legend.innerHTML = plot.map(s =>
    '<span><span class="sw" style="background:' + s.color + '"></span>' + escapeHtml(metricLabel(s.meta)) + "</span>"
  ).join("");
  if (hasLgn && hasOther) {
    legend.innerHTML += '<span style="color:var(--muted)">(LGN hidden while mixed with thousand-m³ series — toggle others off to view)</span>';
  }
}

function tableRows() {
  const rows = DATA.months.map((m, i) => {
    const r = { month: m };
    DATA.metrics.forEach(met => { r[met.key] = (DATA.series[met.key] || [])[i]; });
    return r;
  });
  return rows.filter(r => {
    for (const [col, q] of Object.entries(filters)) {
      if (!q) continue;
      const v = r[col];
      if (String(v == null ? "" : v).toLowerCase().indexOf(q) < 0) return false;
    }
    return true;
  }).sort((a, b) => {
    const av = a[sortState.col], bv = b[sortState.col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortState.dir;
    return String(av).localeCompare(String(bv)) * sortState.dir;
  });
}

function renderTable() {
  const cols = [{ key: "month", label: "Month" }].concat(
    DATA.metrics.map(m => ({ key: m.key, label: metricLabel(m) + " (" + metricUnit(m) + ")" }))
  );
  const host = document.getElementById("thead-row");
  const tbody = document.getElementById("tbody");
  withFocusPreserved(host.parentElement.parentElement, () => {
    host.innerHTML = "";
    cols.forEach(col => {
      host.appendChild(buildSortFilterTh(col, sortState, defaultSort, filters, (s, f) => {
        sortState = s; filters = f; renderTable();
      }));
    });
    const rows = tableRows();
    tbody.innerHTML = rows.map(r => {
      let cells = '<td>' + escapeHtml(r.month) + "</td>";
      DATA.metrics.forEach(m => {
        cells += '<td class="num">' + fmtNum(r[m.key]) + "</td>";
      });
      return "<tr>" + cells + "</tr>";
    }).join("");
    document.getElementById("row-count").textContent = rows.length + " months";
  });
}

function downloadCsv() {
  const cols = ["month"].concat(DATA.metrics.map(m => m.key));
  const header = ["month"].concat(DATA.metrics.map(m => metricLabel(m) + " (" + metricUnit(m) + ")"));
  const lines = [header.map(csvEscape).join(",")];
  tableRows().forEach(r => {
    lines.push(cols.map(c => csvEscape(r[c] == null ? "" : r[c])).join(","));
  });
  downloadTextFile(lines.join("\n"), "text/csv;charset=utf-8", "gasbrazil-supply.csv");
}

async function downloadXlsx() {
  const header = ["month"].concat(DATA.metrics.map(m => metricLabel(m) + " (" + metricUnit(m) + ")"));
  const keys = ["month"].concat(DATA.metrics.map(m => m.key));
  const rows = [header];
  tableRows().forEach(r => rows.push(keys.map(k => r[k] == null ? "" : r[k])));
  const blob = await buildWorkbookXlsxBlob([{ name: "supply", rows }]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "gasbrazil-supply.xlsx";
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function paintAsof() {
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated);
  document.getElementById("asof-through").textContent = DATA.dataThrough || "—";
  initStalenessBadgeFor("supply", DATA.dataThrough);
}

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const json = await inflateGzipUrl(PAYLOAD_URL);
  DATA = JSON.parse(json);
  document.getElementById("import-gap").hidden = !DATA.importGap;
  DATA.metrics.forEach(m => { if (m.defaultOn) { picked.add(m.key); colorOf(m.key); } });
  applySupplyQuery();
  paintAsof();
  renderKpis();
  buildPicker();
  renderChart();
  renderTable();
  writeSupplyQuery();
  document.getElementById("btn-csv").addEventListener("click", downloadCsv);
  document.getElementById("btn-xlsx").addEventListener("click", downloadXlsx);
  window.addEventListener("resize", () => {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(renderChart, 140);
  });
  initThemeToggle("theme-toggle", () => { buildPicker(); renderChart(); });
  initLangToggle("lang-toggle", () => {
    renderKpis(); buildPicker(); renderChart(); renderTable(); applyI18n();
  });
  initCrossLinks();
  gbCopyLink("btn-share");
  applyI18n();
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    payload = load_payload()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
    import data_kit as dk  # noqa: E402
    here = Path(__file__).resolve().parent
    payload_path, payload_href = dk.write_and_publish_artifact("supply", payload, here)
    kpi_prod = payload["kpi"].get("production")
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_PRODUCTION="" if kpi_prod is None else str(kpi_prod),
        DATA_THROUGH=payload.get("dataThrough") or "",
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
        SHARED_JS_QUERY_STATE=kit.JS_QUERY_STATE,
        SHARED_SHARE_BUTTON=kit.share_link_button_html(),
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("supply"),
        SHARED_MASTHEAD=kit.masthead_html("supply"),
        SHARED_METHODOLOGY=kit.methodology_html("supply"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(
        f"Wrote dashboard shell ({len(html):,} bytes) + {payload_path.name} "
        f"({payload_path.stat().st_size:,} bytes, {payload['nMonths']} months) → {payload_href}"
    )
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
