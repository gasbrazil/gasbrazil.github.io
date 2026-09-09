"""
Builds the ANP gas-prices dashboard from data/anp_prices.parquet.

Usage: python dashboard.py [output_path]
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "anp_prices.parquet"
DEFAULT_OUT = HERE / "index.html"

PRODUCER_CATS = ("Santos", "Campos", "Other basins")
DIST_KEYS = (
    ("non_thermal", "Norte-Nordeste"),
    ("non_thermal", "Sudeste"),
    ("non_thermal", "Sul-Centro-Oeste"),
    ("thermal", "Norte-Nordeste"),
    ("thermal", "Sudeste-Sul-Centro-Oeste"),
)


def _series_for(df: pd.DataFrame, months: list[str], mask, col: str = "price_brl_mmbtu") -> list:
    part = df.loc[mask].set_index("month")[col] if mask.any() else pd.Series(dtype=float)
    out = []
    for m in months:
        if m in part.index:
            v = part.loc[m]
            if isinstance(v, pd.Series):
                v = v.dropna()
                v = v.iloc[-1] if len(v) else None
            out.append(None if v is None or (isinstance(v, float) and pd.isna(v)) else round(float(v), 3))
        else:
            out.append(None)
    return out


def load_payload() -> dict:
    if not PARQUET_PATH.exists():
        raise RuntimeError(f"Missing {PARQUET_PATH} — run make_mock.py + precos_pipeline.py build")
    df = pd.read_parquet(PARQUET_PATH)
    if df.empty:
        raise RuntimeError("anp_prices.parquet is empty")

    months = sorted(df["month"].dropna().astype(str).unique().tolist())
    producers = {
        cat: _series_for(df, months, (df["segment"] == "producers") & (df["category"] == cat))
        for cat in PRODUCER_CATS
    }
    distributors = {}
    for market, region in DIST_KEYS:
        key = f"{market}|{region}"
        distributors[key] = _series_for(
            df,
            months,
            (df["segment"] == "distributors")
            & (df["category"] == market)
            & (df["region"].astype(str) == region),
        )
    marketers_price = _series_for(df, months, df["segment"] == "marketers")
    marketers_vol = _series_for(
        df, months, df["segment"] == "marketers", col="volume_thousand_m3_day"
    )

    # Latest Santos price for hub teaser
    santos = None
    data_through = months[-1] if months else None
    for i in range(len(months) - 1, -1, -1):
        v = producers["Santos"][i]
        if v is not None:
            santos = v
            data_through = months[i]
            break

    _now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated": _now.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": _now.isoformat(),
        "months": months,
        "producers": producers,
        "distributors": distributors,
        "marketersPrice": marketers_price,
        "marketersVolume": marketers_vol,
        "dataThrough": data_through,
        "kpiSantos": santos,
        "nMonths": len(months),
        "source": "ANP — Publicidade dos preços de gás natural (Res. 52/2011)",
    }


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ANP Prices — GasBrazil.com</title>
<meta name="description" content="ANP Resolution 52/2011 monthly natural gas trading price disclosures — producers by basin, distributors, and marketers. Tax-inclusive R$/MMBtu.">
<link rel="canonical" href="https://gasbrazil.com/precos/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_santos: __KPI_SANTOS__
     data_through: __DATA_THROUGH__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; font-weight: 300; }
header.dash-head { display: flex; flex-direction: column; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; width: 100%; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
.lede { font-size: 13px; color: var(--muted2); font-weight: 300; max-width: 48em; line-height: 1.45; margin: 0 0 var(--gap); }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 8px; margin-bottom: var(--gap); }
.kpi-cell { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; text-align: left; cursor: pointer; font-family: var(--font); color: var(--text); width: 100%; }
.kpi-cell:hover { background: var(--accent-soft); }
.kpi-cell.active { border-color: var(--accent); border-width: 2px; padding: 9px 11px; }
.kpi-cell .lbl { font-size: 11px; font-weight: 400; color: var(--muted2); }
.kpi-cell .val { font-size: 18px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 2px; }
.kpi-cell .unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.kpi-cell .delta { font-size: 11px; font-weight: 400; margin-top: 2px; font-variant-numeric: tabular-nums; }
.kpi-cell .delta.up { color: var(--neg); }
.kpi-cell .delta.down { color: var(--ok-ink); }
.kpi-cell .delta.flat { color: var(--muted); }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; }
.series-picker { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.caption { font-size: 12px; color: var(--muted2); margin: 8px 0 0; font-weight: 300; line-height: 1.4; max-width: 52em; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
#chart-producers svg, #chart-distributors svg, #chart-marketers svg { display: block; width: 100%; height: 320px; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.notes { font-size: 12px; color: var(--muted2); line-height: 1.55; max-width: 52em; margin: 0 0 var(--gap); }
.notes li { margin: 4px 0; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); font-weight: 400; }
.toolbar button:hover { background: var(--accent-soft); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; font-weight: 200; }
.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; overflow: auto; max-height: 50vh; }
table { border-collapse: collapse; width: 100%; font-size: var(--table-font-size); font-weight: 300; }
th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { position: sticky; top: 0; z-index: 2; background: var(--panel); color: var(--muted2); font-weight: 400; }
th .th-label { cursor: pointer; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:hover { background: var(--accent-soft); }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
/* Chart tooltip (.tt) styles live in shared/theme.css */
@media (max-width: 720px) {
  .toolbar, .sources, .series-picker { flex-direction: column; align-items: stretch; }
  .toolbar button { width: 100%; }
  .count { margin-left: 0; }
}
</style>
</head>
<body>
<a class="skip-link" href="#chart-producers" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  <div><h1 data-i18n="navPrecos">ANP Prices</h1></div>
  <div class="header-right">
    <div class="header-links">__SHARED_NAV_LINKS__</div>
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a href="https://www.gov.br/anp/pt-br/assuntos/movimentacao-estocagem-e-comercializacao-de-gas-natural/acompanhamento-do-mercado-de-gas-natural/publicidade-dos-precos-de-gas-natural" target="_blank" rel="noopener">ANP<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
<div class="kpi-row" id="kpi-row"></div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosProdTitle">Producer sales by basin</p>
  <div class="series-picker" id="picker-producers"></div>
  <div id="chart-producers"></div>
  <div class="legend" id="leg-producers"></div>
</div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosDistTitle">Sales to distributors &amp; free consumers</p>
  <div class="series-picker" id="picker-distributors"></div>
  <div id="chart-distributors"></div>
  <div class="legend" id="leg-distributors"></div>
</div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosMktTitle">Sales to marketers</p>
  <div id="chart-marketers"></div>
  <div class="legend" id="leg-marketers"></div>
</div>
<div class="toolbar">
  <button type="button" id="btn-csv" data-i18n="precosCsv">Download CSV</button>
  <button type="button" id="btn-xlsx" data-i18n="precosXlsx">Export Excel</button>
  <span class="count" id="row-count"></span>
</div>
<div class="table-wrap">
  <table id="data-table"><thead><tr id="thead-row"></tr></thead><tbody id="tbody"></tbody></table>
</div>
<footer>
  <div class="asof-strip asof-footer" id="asof-strip">
    <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
    <span class="asof-val" id="asof-refreshed">&mdash;</span>
    <span class="asof-label" data-i18n="dataThrough">Data through</span>
    <span class="asof-val" id="asof-through">&mdash;</span>
  </div>
  &copy; <span id="year"></span> GasBrazil.com &middot;
  <span data-i18n="precosFooter">Data: ANP publicidade dos preços de gás natural. Not an official ANP product.</span>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
  &middot; <a href="../about/" data-i18n="footerAbout">About</a>
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

GB_I18N.en.precosProdTitle = "Producer sales by basin";
GB_I18N.en.precosDistTitle = "Sales to distributors & free consumers";
GB_I18N.en.precosMktTitle = "Sales to marketers";
GB_I18N.en.precosCsv = "Download CSV";
GB_I18N.en.precosXlsx = "Export Excel";
GB_I18N.en.precosFooter = "Data: ANP publicidade dos preços de gás natural. Not an official ANP product.";
GB_I18N.en.precosKpiSantos = "Santos wellhead";
GB_I18N.en.precosKpiCampos = "Campos wellhead";
GB_I18N.en.precosKpiDistSE = "Dist. SE non-thermal";
GB_I18N.en.precosKpiMarketers = "Marketers price";
GB_I18N.en.precosKpiMktVol = "Marketers volume";
GB_I18N.en.precosKpiMom = "vs prior month";
GB_I18N.en.precosKpiVolUnit = "thousand m³/d";
GB_I18N.en.precosKpiHint = "Click to show/hide on the chart";
GB_I18N.en.precosThMonth = "Month";
GB_I18N.en.precosThSantos = "Santos";
GB_I18N.en.precosThCampos = "Campos";
GB_I18N.en.precosThOther = "Other basins";
GB_I18N.en.precosThMarketers = "Marketers";
GB_I18N.en.precosThMktVol = "Marketer volume";
GB_I18N.en.precosPrice = "Price";
GB_I18N.en.precosEmpty = "No data";
GB_I18N.en.precosPickSeries = "Select one or more series.";
GB_I18N.en.precosRowCount = "{n} months";
GB_I18N.en.precosBasinSantos = "Santos";
GB_I18N.en.precosBasinCampos = "Campos";
GB_I18N.en.precosBasinOther = "Other basins";
GB_I18N.en.precosDistNT_NNE = "Non-thermal N-NE";
GB_I18N.en.precosDistNT_SE = "Non-thermal SE";
GB_I18N.en.precosDistNT_SCO = "Non-thermal S-CO";
GB_I18N.en.precosDistT_NNE = "Thermal N-NE";
GB_I18N.en.precosDistT_SESCO = "Thermal SE-S-CO";

GB_I18N.pt.precosProdTitle = "Vendas entre produtores por bacia";
GB_I18N.pt.precosDistTitle = "Vendas a distribuidoras e consumidores livres";
GB_I18N.pt.precosMktTitle = "Vendas a comercializadores";
GB_I18N.pt.precosCsv = "Baixar CSV";
GB_I18N.pt.precosXlsx = "Exportar Excel";
GB_I18N.pt.precosFooter = "Dados: ANP publicidade dos preços de gás natural. Não é um produto oficial da ANP.";
GB_I18N.pt.precosKpiSantos = "Poço Santos";
GB_I18N.pt.precosKpiCampos = "Poço Campos";
GB_I18N.pt.precosKpiDistSE = "Dist. SE não térmico";
GB_I18N.pt.precosKpiMarketers = "Preço comercializadores";
GB_I18N.pt.precosKpiMktVol = "Volume comercializadores";
GB_I18N.pt.precosKpiMom = "vs mês anterior";
GB_I18N.pt.precosKpiVolUnit = "mil m³/d";
GB_I18N.pt.precosKpiHint = "Clique para mostrar/ocultar no gráfico";
GB_I18N.pt.precosThMonth = "Mês";
GB_I18N.pt.precosThSantos = "Santos";
GB_I18N.pt.precosThCampos = "Campos";
GB_I18N.pt.precosThOther = "Demais bacias";
GB_I18N.pt.precosThMarketers = "Comercializadores";
GB_I18N.pt.precosThMktVol = "Volume comercializadores";
GB_I18N.pt.precosPrice = "Preço";
GB_I18N.pt.precosEmpty = "Sem dados";
GB_I18N.pt.precosPickSeries = "Selecione uma ou mais séries.";
GB_I18N.pt.precosRowCount = "{n} meses";
GB_I18N.pt.precosBasinSantos = "Santos";
GB_I18N.pt.precosBasinCampos = "Campos";
GB_I18N.pt.precosBasinOther = "Demais bacias";
GB_I18N.pt.precosDistNT_NNE = "Não térmico N-NE";
GB_I18N.pt.precosDistNT_SE = "Não térmico SE";
GB_I18N.pt.precosDistNT_SCO = "Não térmico S-CO";
GB_I18N.pt.precosDistT_NNE = "Térmico N-NE";
GB_I18N.pt.precosDistT_SESCO = "Térmico SE-S-CO";

const PROD_META = [
  { key: "Santos", labelKey: "precosBasinSantos" },
  { key: "Campos", labelKey: "precosBasinCampos" },
  { key: "Other basins", labelKey: "precosBasinOther" },
];
const DIST_META = [
  { key: "non_thermal|Norte-Nordeste", labelKey: "precosDistNT_NNE" },
  { key: "non_thermal|Sudeste", labelKey: "precosDistNT_SE" },
  { key: "non_thermal|Sul-Centro-Oeste", labelKey: "precosDistNT_SCO" },
  { key: "thermal|Norte-Nordeste", labelKey: "precosDistT_NNE" },
  { key: "thermal|Sudeste-Sul-Centro-Oeste", labelKey: "precosDistT_SESCO" },
];

let DATA = null;
let pickedProd = new Set();
let pickedDist = new Set();
let prodSlots = new Map();
let distSlots = new Map();
let sortState = { col: "month", dir: -1 };
const defaultSort = { col: "month", dir: -1 };
let filters = {};
const NS = "http://www.w3.org/2000/svg";

function el(n, a) { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); return e; }
function fmt(v, d) {
  if (v == null) return "—";
  return Number(v).toLocaleString(currentLang() === "pt" ? "pt-BR" : "en-US", { maximumFractionDigits: d == null ? 1 : d });
}
function niceTicks(lo, hi, n) {
  if (!isFinite(lo) || !isFinite(hi) || lo === hi) return [lo || 0];
  const span = hi - lo, step0 = span / Math.max(1, n);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const r = step0 / mag, step = (r >= 5 ? 5 : r >= 2 ? 2 : 1) * mag;
  const start = Math.ceil(lo / step) * step, out = [];
  for (let v = start; v <= hi + step * 0.01; v += step) out.push(v);
  return out;
}
function colorOf(map, key) {
  const pal = chartPalette();
  if (!map.has(key)) map.set(key, map.size % Math.max(1, pal.length));
  return pal[map.get(key) % pal.length] || "var(--accent)";
}
function buildPicker(hostId, meta, picked, slots, onToggle) {
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  meta.forEach(m => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "series-btn" + (picked.has(m.key) ? " active" : "");
    btn.innerHTML = '<span class="sw"></span>' + escapeHtml(t(m.labelKey));
    btn.querySelector(".sw").style.background = picked.has(m.key) ? colorOf(slots, m.key) : "";
    btn.addEventListener("click", () => {
      if (picked.has(m.key)) { picked.delete(m.key); slots.delete(m.key); }
      else { picked.add(m.key); colorOf(slots, m.key); }
      onToggle();
    });
    host.appendChild(btn);
  });
}
function lineChart(host, legend, series, months) {
  host.innerHTML = ""; legend.innerHTML = "";
  const plot = series.filter(s => s.pts.some(p => p.v != null));
  if (!series.length) { host.innerHTML = '<div class="chart-empty">' + escapeHtml(t("precosPickSeries")) + "</div>"; return; }
  if (!plot.length) { host.innerHTML = '<div class="chart-empty">' + escapeHtml(t("precosEmpty")) + "</div>"; return; }
  let lo = Infinity, hi = -Infinity;
  plot.forEach(s => s.pts.forEach(p => { if (p.v != null) { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); } }));
  if (lo > 0 && lo / hi <= 0.4) lo = 0;
  const pad = (hi - lo) * 0.08 || 1; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = 300, ML = 52, MR = 12, MT = 18, MB = 28;
  const dNum = m => Date.UTC(+m.slice(0,4), +m.slice(5,7)-1, 1);
  const minD = dNum(months[0]), maxD = dNum(months[months.length-1]);
  const x = m => ML + (W-ML-MR) * (maxD===minD ? 0.5 : (dNum(m)-minD)/(maxD-minD));
  const y = v => MT + (H-MT-MB) * (1 - (v-lo)/(hi-lo));
  const svg = el("svg", { viewBox: "0 0 "+W+" "+H, width: W, height: H });
  niceTicks(lo, hi, 5).forEach(tk => {
    svg.appendChild(el("line", { x1: ML, x2: W-MR, y1: y(tk), y2: y(tk), stroke: "var(--border)", "stroke-width": 1 }));
    const tx = el("text", { x: ML-8, y: y(tk)+4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
    tx.textContent = fmt(tk, 0); svg.appendChild(tx);
  });
  const nT = Math.min(8, months.length);
  for (let i = 0; i < nT; i++) {
    const mi = months[Math.round(i*(months.length-1)/Math.max(1,nT-1))];
    const tx = el("text", { x: x(mi), y: H-8, fill: "var(--muted)", "font-size": 11, "text-anchor": i===0?"start":(i===nT-1?"end":"middle") });
    tx.textContent = mi; svg.appendChild(tx);
  }
  plot.forEach(s => {
    let d = "", started = false;
    s.pts.forEach(p => {
      if (p.v == null) { started = false; return; }
      d += (started ? "L" : "M") + x(p.month).toFixed(1) + " " + y(p.v).toFixed(1) + " ";
      started = true;
    });
    if (d) svg.appendChild(el("path", { d: d.trim(), fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const leg = document.createElement("span");
    leg.innerHTML = '<span class="sw" style="background:'+s.color+'"></span>' + escapeHtml(s.label);
    legend.appendChild(leg);
  });
  const cross = el("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "3 3", visibility: "hidden" });
  svg.appendChild(cross);
  const overlay = el("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(overlay);
  const tt = document.getElementById("chart-tt");
  const allM = months.slice();
  overlay.addEventListener("mousemove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
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
      if (!p || p.v == null) return;
      rows += '<tr><td><span class="sw" style="background:' + s.color + '"></span> ' +
        escapeHtml(s.label) + '</td><td class="v">' + fmt(p.v, 2) + "</td></tr>";
    });
    if (!rows) { tt.style.display = "none"; return; }
    tt.innerHTML = '<div class="d">' + escapeHtml(best) + "</div><table>" + rows + "</table>";
    placeChartTooltip(tt, ev.clientX, ev.clientY);
  });
  overlay.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden");
    tt.style.display = "none";
  });
  host.appendChild(svg);
}
function paintAsof() {
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated, currentLang() === "pt" ? "pt-BR" : undefined);
  document.getElementById("asof-through").textContent = DATA.dataThrough || "—";
}
function latestPoint(arr) {
  if (!arr) return null;
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] != null && !isNaN(arr[i])) return { v: arr[i], i, month: DATA.months[i] };
  }
  return null;
}
function momHtml(arr) {
  const cur = latestPoint(arr);
  if (!cur || cur.i <= 0) return "";
  let prev = null;
  for (let i = cur.i - 1; i >= 0; i--) {
    if (arr[i] != null && !isNaN(arr[i])) { prev = arr[i]; break; }
  }
  if (prev == null || prev === 0) return "";
  const d = cur.v - prev;
  const pct = 100 * d / prev;
  const cls = Math.abs(pct) < 0.05 ? "flat" : (d > 0 ? "up" : "down");
  const sign = d > 0 ? "+" : "";
  return `<div class="delta ${cls}">${sign}${pct.toFixed(1)}% <span class="muted">${escapeHtml(t("precosKpiMom"))}</span></div>`;
}
function renderKpis() {
  const host = document.getElementById("kpi-row");
  const cards = [
    {
      id: "santos", labelKey: "precosKpiSantos",
      arr: DATA.producers.Santos, digits: 1, unit: "R$/MMBtu",
      active: pickedProd.has("Santos"),
      onClick: () => toggleProd("Santos"),
      scrollId: "chart-producers",
    },
    {
      id: "campos", labelKey: "precosKpiCampos",
      arr: DATA.producers.Campos, digits: 1, unit: "R$/MMBtu",
      active: pickedProd.has("Campos"),
      onClick: () => toggleProd("Campos"),
      scrollId: "chart-producers",
    },
    {
      id: "dist-se", labelKey: "precosKpiDistSE",
      arr: DATA.distributors["non_thermal|Sudeste"], digits: 1, unit: "R$/MMBtu",
      active: pickedDist.has("non_thermal|Sudeste"),
      onClick: () => toggleDist("non_thermal|Sudeste"),
      scrollId: "chart-distributors",
    },
    {
      id: "mkt", labelKey: "precosKpiMarketers",
      arr: DATA.marketersPrice, digits: 1, unit: "R$/MMBtu",
      active: null,
      onClick: () => {},
      scrollId: "chart-marketers",
    },
    {
      id: "mkt-vol", labelKey: "precosKpiMktVol",
      arr: DATA.marketersVolume, digits: 0, unitKey: "precosKpiVolUnit",
      active: null,
      onClick: () => {},
      scrollId: "chart-marketers",
    },
  ];
  host.innerHTML = "";
  cards.forEach(c => {
    const pt = latestPoint(c.arr);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "kpi-cell" + (c.active ? " active" : "");
    btn.title = t("precosKpiHint");
    const unit = c.unitKey ? t(c.unitKey) : c.unit;
    const month = pt ? pt.month : (DATA.dataThrough || "");
    btn.innerHTML =
      `<div class="lbl" data-i18n="${c.labelKey}">${escapeHtml(t(c.labelKey))}</div>` +
      `<div class="val">${fmt(pt && pt.v, c.digits)}</div>` +
      `<div class="unit">${escapeHtml(unit)}${month ? " · " + escapeHtml(month) : ""}</div>` +
      momHtml(c.arr);
    btn.addEventListener("click", () => {
      c.onClick();
      refreshPickersAndCharts();
      renderKpis();
      const el = document.getElementById(c.scrollId);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    host.appendChild(btn);
  });
}
function toggleProd(key) {
  if (pickedProd.has(key)) { pickedProd.delete(key); prodSlots.delete(key); }
  else { pickedProd.add(key); colorOf(prodSlots, key); }
}
function toggleDist(key) {
  if (pickedDist.has(key)) { pickedDist.delete(key); distSlots.delete(key); }
  else { pickedDist.add(key); colorOf(distSlots, key); }
}
function renderCharts() {
  const months = DATA.months;
  const prod = PROD_META.filter(m => pickedProd.has(m.key)).map(m => ({
    label: t(m.labelKey), color: colorOf(prodSlots, m.key),
    pts: months.map((mo, j) => ({ month: mo, v: (DATA.producers[m.key] || [])[j] }))
  }));
  lineChart(document.getElementById("chart-producers"), document.getElementById("leg-producers"), prod, months);
  const dist = DIST_META.filter(m => pickedDist.has(m.key)).map(m => ({
    label: t(m.labelKey), color: colorOf(distSlots, m.key),
    pts: months.map((mo, j) => ({ month: mo, v: (DATA.distributors[m.key] || [])[j] }))
  }));
  lineChart(document.getElementById("chart-distributors"), document.getElementById("leg-distributors"), dist, months);
  const mkt = [{
    label: t("precosPrice"), color: chartPalette()[0],
    pts: months.map((mo, j) => ({ month: mo, v: DATA.marketersPrice[j] }))
  }];
  lineChart(document.getElementById("chart-marketers"), document.getElementById("leg-marketers"), mkt, months);
}
function tableRawRows() {
  return DATA.months.map((m, i) => ({
    month: m,
    santos: DATA.producers.Santos[i],
    campos: DATA.producers.Campos[i],
    other: DATA.producers["Other basins"][i],
    marketers: DATA.marketersPrice[i],
    mktVol: DATA.marketersVolume[i],
  }));
}
function tableRows() {
  return tableRawRows().filter(r => {
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
  const cols = [
    { key: "month", label: t("precosThMonth") },
    { key: "santos", label: t("precosThSantos"), num: true },
    { key: "campos", label: t("precosThCampos"), num: true },
    { key: "other", label: t("precosThOther"), num: true },
    { key: "marketers", label: t("precosThMarketers"), num: true },
    { key: "mktVol", label: t("precosThMktVol"), num: true },
  ];
  const host = document.getElementById("thead-row");
  const tbody = document.getElementById("tbody");
  withFocusPreserved(host.parentElement.parentElement, () => {
    host.innerHTML = "";
    cols.forEach(col => {
      host.appendChild(buildSortFilterTh(col, sortState, defaultSort, filters, (s, f) => {
        sortState = s; filters = f; renderTable();
      }, col.num ? "num" : ""));
    });
    const rows = tableRows();
    tbody.innerHTML = rows.map(r =>
      "<tr><td>" + escapeHtml(r.month) + "</td>" +
      '<td class="num">' + fmt(r.santos) + "</td>" +
      '<td class="num">' + fmt(r.campos) + "</td>" +
      '<td class="num">' + fmt(r.other) + "</td>" +
      '<td class="num">' + fmt(r.marketers) + "</td>" +
      '<td class="num">' + fmt(r.mktVol, 0) + "</td></tr>"
    ).join("");
    document.getElementById("row-count").textContent = t("precosRowCount").replace("{n}", String(rows.length));
  });
}
function downloadCsv() {
  const header = [t("precosThMonth"), t("precosThSantos"), t("precosThCampos"), t("precosThOther"), t("precosThMarketers"), t("precosThMktVol")];
  const keys = ["month", "santos", "campos", "other", "marketers", "mktVol"];
  const lines = [header.map(csvEscape).join(",")];
  tableRows().forEach(r => lines.push(keys.map(k => csvEscape(r[k] == null ? "" : r[k])).join(",")));
  downloadTextFile(lines.join("\n"), "text/csv;charset=utf-8", "gasbrazil-anp-prices.csv");
}
async function downloadXlsx() {
  const header = [t("precosThMonth"), t("precosThSantos"), t("precosThCampos"), t("precosThOther"), t("precosThMarketers"), t("precosThMktVol")];
  const keys = ["month", "santos", "campos", "other", "marketers", "mktVol"];
  const rows = [header];
  tableRows().forEach(r => rows.push(keys.map(k => r[k] == null ? "" : r[k])));
  const blob = await buildWorkbookXlsxBlob([{ name: "prices", rows }]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "gasbrazil-anp-prices.xlsx";
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
function refreshProd() { buildPicker("picker-producers", PROD_META, pickedProd, prodSlots, refreshProd); renderCharts(); }
function refreshDist() { buildPicker("picker-distributors", DIST_META, pickedDist, distSlots, refreshDist); renderCharts(); }
function refreshPickersAndCharts() {
  buildPicker("picker-producers", PROD_META, pickedProd, prodSlots, refreshProd);
  buildPicker("picker-distributors", DIST_META, pickedDist, distSlots, refreshDist);
  renderCharts();
}
async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  initThemeToggle("theme-toggle", () => { if (DATA) refreshPickersAndCharts(); });
  initLangToggle("lang-toggle", () => {
    if (!DATA) { applyI18n(); return; }
    paintAsof(); renderKpis(); refreshPickersAndCharts(); renderTable(); applyI18n();
  });
  initCrossLinks();
  applyI18n();
  try {
    const json = await inflateGzipUrl(PAYLOAD_URL);
    DATA = JSON.parse(json);
    PROD_META.forEach(m => { pickedProd.add(m.key); colorOf(prodSlots, m.key); });
    DIST_META.forEach(m => { pickedDist.add(m.key); colorOf(distSlots, m.key); });
    paintAsof();
    renderKpis();
    refreshPickersAndCharts();
    renderTable();
    document.getElementById("btn-csv").addEventListener("click", downloadCsv);
    document.getElementById("btn-xlsx").addEventListener("click", downloadXlsx);
    window.addEventListener("resize", () => { clearTimeout(window.__pr); window.__pr = setTimeout(renderCharts, 120); });
    applyI18n();
  } catch (err) {
    console.error(err);
    document.getElementById("kpi-row").innerHTML = '<div class="kpi-cell"><div class="lbl">Error</div><div class="val" style="font-size:13px">' + escapeHtml(String(err && err.message || err)) + "</div></div>";
  }
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path=DEFAULT_OUT):
    payload = load_payload()
    import data_kit as dk  # noqa: E402

    payload_path, payload_href = dk.write_and_publish_artifact("precos", payload, HERE)
    kpi = payload.get("kpiSantos")
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_SANTOS="" if kpi is None else str(kpi),
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
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("precos"),
        SHARED_NAV_LINKS=kit.nav_links_html("precos"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html):,} bytes) -> {payload_href}")


if __name__ == "__main__":
    write_dashboard(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
