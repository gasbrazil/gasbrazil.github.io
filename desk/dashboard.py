"""
Builds the Market Desk dashboard (cross-product snapshot + spark calculator).

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
<title>Market Desk — GasBrazil.com</title>
<meta name="description" content="Cross-product market desk for Brazil natural gas and power: gas generation, PLD–CMO–CVU, ANP and POC prices, pipeline utilization, and a thermal spark-spread calculator.">
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
header.dash-head { display: flex; flex-direction: column; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-links { display: flex; gap: 8px; flex-wrap: wrap; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }
.lede { font-size: 13px; color: var(--muted2); font-weight: 300; margin: 0 0 var(--gap); line-height: 1.45; max-width: 54em; }
.gap-note { font-size: 12px; color: var(--muted); margin: 0 0 var(--gap); font-weight: 200; }
.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: var(--gap); }
@media (max-width: 960px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 520px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi-cell { padding: 2px 0 6px; border-bottom: 1px solid var(--border); }
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
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
.tt { position: fixed; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 6px 20px rgba(0,0,0,.16); z-index: 50; display: none; min-width: 180px; }
.tt .d { font-weight: 400; margin-bottom: 5px; }
.tt table { border-collapse: collapse; width: 100%; }
.tt td { padding: 1px 0; }
.tt td.v { text-align: right; padding-left: 14px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.spark-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; margin-bottom: 14px; }
@media (max-width: 520px) { .spark-form { grid-template-columns: 1fr; } }
.spark-form label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--muted2); font-weight: 400; }
.spark-form input, .spark-form select { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 6px 10px; color: var(--text); font-size: 13px; font-family: var(--font); font-weight: 300; font-variant-numeric: tabular-nums; }
.spark-out { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
@media (max-width: 520px) { .spark-out { grid-template-columns: 1fr; } }
.spark-metric .lbl { font-size: 11px; color: var(--muted2); }
.spark-metric .val { font-size: 20px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 2px; letter-spacing: -.01em; }
.spark-metric .unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.spark-metric.pos .val { color: var(--accent); }
.spark-metric.neg .val { color: var(--muted2); }
.table-wrap { overflow: auto; max-height: 40vh; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
table.util { border-collapse: collapse; width: 100%; font-size: var(--table-font-size); }
table.util th, table.util td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); font-weight: 300; }
table.util th { color: var(--muted2); font-weight: 400; position: sticky; top: 0; background: var(--panel); z-index: 2; }
th .th-label { cursor: pointer; }
table.util .num { text-align: right; font-variant-numeric: tabular-nums; }
table.util tbody tr:hover { background: var(--accent-soft); }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
@media (max-width: 720px) {
  .sources, .series-picker { flex-direction: column; align-items: stretch; }
}
</style>
</head>
<body>
<a class="skip-link" href="#main-chart" data-i18n="skip">Skip to content</a>
<div class="wrap">
<header class="dash-head">
  <div>
    <h1 data-i18n="navDesk">Market Desk</h1>
  </div>
  <div class="header-right">
    <div class="header-links">
      __SHARED_NAV_LINKS__
    </div>
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
</header>
<div class="asof-strip" id="asof-strip">
  <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
  <span class="asof-val" id="asof-refreshed">&mdash;</span>
  <span class="asof-label" data-i18n="dataThrough">Data through</span>
  <span class="asof-val" id="asof-through">&mdash;</span>
</div>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a class="pill" href="../ons/" data-i18n="sourceOns">ONS open data</a>
  <a class="pill" href="../pld/" data-i18n="sourcePld">CCEE open data — PLD média diária</a>
  <a class="pill" href="../precos/" data-i18n="sourcePrecos">ANP — publicidade dos preços de gás natural</a>
  <a class="pill" href="../poc/" data-i18n="sourcePoc">Portal de Oferta de Capacidade</a>
  <a class="pill" href="../flows/" data-i18n="sourceFlows">ANP open data — pipeline movement</a>
</div>
<p class="lede" data-i18n="deskLede">One screen across gas and power: latest SIN gas generation, SE PLD and CMO, disclosed ANP and POC prices, pipeline utilization, and a client-side thermal spark calculator. Product pages keep filters and full history.</p>
<p class="gap-note" id="data-notes" hidden></p>
<div class="kpi-row" id="kpi-row"></div>

<div class="desk-grid">
  <section class="panel" aria-labelledby="compare-title">
    <p class="panel-title" id="compare-title" data-i18n="deskCompareTitle">PLD vs CMO vs gas CVU — SE</p>
    <p class="panel-note" data-i18n="deskCompareNote">Last ~90 days, Southeast. CMO and median gas-plant CVU from ONS (R$/MWh). CVU is a planning cost, not a market price.</p>
    <div class="series-picker" id="picker-compare"></div>
    <div class="chart-host" id="main-chart"></div>
  </section>
  <section class="panel" aria-labelledby="spark-title">
    <p class="panel-title" id="spark-title">
      <span data-i18n="deskSparkTitle">Thermal spark / implied CVU</span>
      <span class="infodot" id="spark-info" title="" aria-label="Formula">i</span>
    </p>
    <p class="panel-note" data-i18n="deskSparkNote">Implied generation cost from gas price and heat rate, compared with current PLD SE and CMO SE. Optional CVU override replaces the calculated cost.</p>
    <div class="spark-form">
      <label><span data-i18n="deskGasPrice">Gas price</span> (R$/MMBtu)
        <input type="number" id="spark-gas" step="0.1" min="0" inputmode="decimal">
      </label>
      <label><span data-i18n="deskHeatRate">Heat rate</span> (kcal/kWh)
        <select id="spark-hr-preset">
          <option value="ccgt" data-i18n="deskHrCcgt">CCGT 1800</option>
          <option value="ocgt" data-i18n="deskHrOcgt">OCGT 2500</option>
          <option value="custom" data-i18n="deskHrCustom">Custom</option>
        </select>
      </label>
      <label><span data-i18n="deskHrCustom">Custom heat rate</span>
        <input type="number" id="spark-hr" step="50" min="500" inputmode="decimal">
      </label>
      <label><span data-i18n="deskCvuOverride">CVU override</span> (R$/MWh)
        <input type="number" id="spark-cvu" step="1" min="0" placeholder="—" inputmode="decimal">
      </label>
    </div>
    <div class="spark-out">
      <div class="spark-metric"><div class="lbl" data-i18n="deskImpliedCvu">Implied CVU</div><div class="val" id="spark-implied">—</div><div class="unit">R$/MWh</div></div>
      <div class="spark-metric" id="spark-vs-pld-wrap"><div class="lbl" data-i18n="deskVsPld">vs PLD SE</div><div class="val" id="spark-vs-pld">—</div><div class="unit">R$/MWh</div></div>
      <div class="spark-metric" id="spark-vs-cmo-wrap"><div class="lbl" data-i18n="deskVsCmo">vs CMO SE</div><div class="val" id="spark-vs-cmo">—</div><div class="unit">R$/MWh</div></div>
    </div>
  </section>
</div>

<section class="panel" aria-labelledby="poc-anp-title">
  <p class="panel-title" id="poc-anp-title" data-i18n="deskPocAnpTitle">POC vs ANP — monthly</p>
  <p class="panel-note" data-i18n="deskPocAnpNote">Mean POC auction price vs ANP Santos producers and non-thermal Sudeste distributors (R$/MMBtu).</p>
  <div class="series-picker" id="picker-poc-anp"></div>
  <div class="chart-host" id="poc-anp-chart"></div>
</section>

<section class="panel" aria-labelledby="util-title">
  <p class="panel-title" id="util-title" data-i18n="deskUtilTitle">Contracted capacity vs realized flows</p>
  <p class="panel-note" data-i18n="deskUtilNote">Active contracted capacity (thousand m³/d) vs average realized volume over the last 30 days of flow data, by TSO.</p>
  <div class="table-wrap">
    <table class="util" id="util-table">
      <thead><tr id="util-thead"></tr></thead>
      <tbody id="util-body"></tbody>
    </table>
  </div>
</section>

<footer>
  &copy; <span id="year"></span> GasBrazil.com &middot;
  <span data-i18n="deskFooter">Cross-product snapshot from sibling dashboards. Not an official ONS, ANP, CCEE, or transportadora product.</span>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
  &middot; <a href="../about/" data-i18n="footerAbout">About & methodology</a>
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
__SHARED_SITE_LINKS_JS__

GB_I18N.en.deskLede = "One screen across gas and power: latest SIN gas generation, SE PLD and CMO, disclosed ANP and POC prices, pipeline utilization, and a client-side thermal spark calculator. Product pages keep filters and full history.";
GB_I18N.en.deskCompareTitle = "PLD vs CMO vs gas CVU — SE";
GB_I18N.en.deskCompareNote = "Last ~90 days, Southeast. CMO and median gas-plant CVU from ONS (R$/MWh). CVU is a planning cost, not a market price.";
GB_I18N.en.deskSparkTitle = "Thermal spark / implied CVU";
GB_I18N.en.deskSparkNote = "Implied generation cost from gas price and heat rate, compared with current PLD SE and CMO SE. Optional CVU override replaces the calculated cost.";
GB_I18N.en.deskGasPrice = "Gas price";
GB_I18N.en.deskHeatRate = "Heat rate";
GB_I18N.en.deskHrCustom = "Custom";
GB_I18N.en.deskHrCcgt = "CCGT 1800";
GB_I18N.en.deskHrOcgt = "OCGT 2500";
GB_I18N.en.deskCvuOverride = "CVU override";
GB_I18N.en.deskImpliedCvu = "Implied CVU";
GB_I18N.en.deskVsPld = "vs PLD SE";
GB_I18N.en.deskVsCmo = "vs CMO SE";
GB_I18N.en.deskPocAnpTitle = "POC vs ANP — monthly";
GB_I18N.en.deskPocAnpNote = "Mean POC auction price vs ANP Santos producers and non-thermal Sudeste distributors (R$/MMBtu).";
GB_I18N.en.deskUtilTitle = "Contracted capacity vs realized flows";
GB_I18N.en.deskUtilNote = "Active contracted capacity (thousand m³/d) vs average realized volume over the last 30 days of flow data, by TSO.";
GB_I18N.en.deskUtilTso = "TSO";
GB_I18N.en.deskUtilCap = "Contracted";
GB_I18N.en.deskUtilReal = "Realized avg";
GB_I18N.en.deskUtilPct = "Utilization";
GB_I18N.en.deskFooter = "Cross-product snapshot from sibling dashboards. Not an official ONS, ANP, CCEE, or transportadora product.";
GB_I18N.en.deskEmptyChart = "No series available — sibling parquet missing at build time.";
GB_I18N.en.deskEmpty = "No series available — sibling parquet missing at build time.";
GB_I18N.en.deskPickSeries = "Select one or more series.";
GB_I18N.en.deskSeriesPld = "PLD SE";
GB_I18N.en.deskSeriesCmo = "CMO SE";
GB_I18N.en.deskSeriesCvu = "CVU gas med";
GB_I18N.en.deskSeriesPoc = "POC avg";
GB_I18N.en.deskSeriesAnpSantos = "ANP Santos";
GB_I18N.en.deskSeriesAnpNtSe = "ANP non-thermal SE";
GB_I18N.en.deskKpiGen = "Gas gen SIN";
GB_I18N.en.deskKpiPld = "PLD SE";
GB_I18N.en.deskKpiCmo = "CMO SE";
GB_I18N.en.deskKpiSantos = "ANP Santos";
GB_I18N.en.deskKpiPoc = "POC 7d";
GB_I18N.en.deskKpiFlows = "Flows 7d";

GB_I18N.pt.deskLede = "Uma tela cruzando gás e energia: geração a gás no SIN, PLD e CMO SE, preços ANP e POC, utilização de gasodutos e calculadora térmica de spark. Os painéis de produto guardam filtros e o histórico completo.";
GB_I18N.pt.deskCompareTitle = "PLD vs CMO vs CVU a gás — SE";
GB_I18N.pt.deskCompareNote = "Últimos ~90 dias, Sudeste. CMO e CVU mediano de usinas a gás da ONS (R$/MWh). CVU é custo de planejamento, não preço de mercado.";
GB_I18N.pt.deskSparkTitle = "Spark térmico / CVU implícito";
GB_I18N.pt.deskSparkNote = "Custo implícito de geração a partir do preço do gás e do heat rate, comparado ao PLD SE e ao CMO SE atuais. O override de CVU substitui o custo calculado.";
GB_I18N.pt.deskGasPrice = "Preço do gás";
GB_I18N.pt.deskHeatRate = "Heat rate";
GB_I18N.pt.deskHrCustom = "Personalizado";
GB_I18N.pt.deskHrCcgt = "CCGT 1800";
GB_I18N.pt.deskHrOcgt = "OCGT 2500";
GB_I18N.pt.deskCvuOverride = "Override de CVU";
GB_I18N.pt.deskImpliedCvu = "CVU implícito";
GB_I18N.pt.deskVsPld = "vs PLD SE";
GB_I18N.pt.deskVsCmo = "vs CMO SE";
GB_I18N.pt.deskPocAnpTitle = "POC vs ANP — mensal";
GB_I18N.pt.deskPocAnpNote = "Preço médio de leilão POC vs produtores Santos e distribuidoras não térmicas Sudeste (R$/MMBtu).";
GB_I18N.pt.deskUtilTitle = "Capacidade contratada vs fluxos realizados";
GB_I18N.pt.deskUtilNote = "Capacidade contratada ativa (mil m³/d) vs volume realizado médio nos últimos 30 dias de dados de fluxo, por TSO.";
GB_I18N.pt.deskUtilTso = "TSO";
GB_I18N.pt.deskUtilCap = "Contratada";
GB_I18N.pt.deskUtilReal = "Realizado méd.";
GB_I18N.pt.deskUtilPct = "Utilização";
GB_I18N.pt.deskFooter = "Retrato cruzado a partir dos painéis irmãos. Não é um produto oficial da ONS, ANP, CCEE ou transportadoras.";
GB_I18N.pt.deskEmptyChart = "Sem séries — parquet irmão ausente no build.";
GB_I18N.pt.deskEmpty = "Sem séries — parquet irmão ausente no build.";
GB_I18N.pt.deskPickSeries = "Selecione uma ou mais séries.";
GB_I18N.pt.deskSeriesPld = "PLD SE";
GB_I18N.pt.deskSeriesCmo = "CMO SE";
GB_I18N.pt.deskSeriesCvu = "CVU gás méd.";
GB_I18N.pt.deskSeriesPoc = "POC méd.";
GB_I18N.pt.deskSeriesAnpSantos = "ANP Santos";
GB_I18N.pt.deskSeriesAnpNtSe = "ANP não térmico SE";
GB_I18N.pt.deskKpiGen = "Geração a gás SIN";
GB_I18N.pt.deskKpiPld = "PLD SE";
GB_I18N.pt.deskKpiCmo = "CMO SE";
GB_I18N.pt.deskKpiSantos = "ANP Santos";
GB_I18N.pt.deskKpiPoc = "POC 7d";
GB_I18N.pt.deskKpiFlows = "Fluxos 7d";

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

let DATA = null;
let chartResizeTimer = null;
let pickedCompare = new Set();
let pickedPocAnp = new Set();
let compareSlots = new Map();
let pocAnpSlots = new Map();
let utilSortState = { col: "tso", dir: 1 };
const utilDefaultSort = { col: "tso", dir: 1 };
let utilFilters = {};

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

function refreshCompare() {
  buildPicker("picker-compare", COMPARE_META, pickedCompare, compareSlots, refreshCompare);
  renderCompareChart();
}
function refreshPocAnp() {
  buildPicker("picker-poc-anp", POC_ANP_META, pickedPocAnp, pocAnpSlots, refreshPocAnp);
  renderPocAnpChart();
}
function buildPickers() {
  buildPicker("picker-compare", COMPARE_META, pickedCompare, compareSlots, refreshCompare);
  buildPicker("picker-poc-anp", POC_ANP_META, pickedPocAnp, pocAnpSlots, refreshPocAnp);
}

function paintAsof() {
  let refreshedText = DATA.generated || "—";
  try {
    const d = new Date(DATA.generatedIso);
    if (!isNaN(d)) {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const loc = currentLang() === "pt" ? "pt-BR" : undefined;
      refreshedText = d.toLocaleDateString(loc, { year: "numeric", month: "2-digit", day: "2-digit" })
        + " " + d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" })
        + " " + tz;
    }
  } catch (e) {}
  document.getElementById("asof-refreshed").textContent = refreshedText;
  document.getElementById("asof-through").textContent = DATA.dataThrough || "—";
}

function renderNotes() {
  const el = document.getElementById("data-notes");
  const notes = (DATA.notes || []).filter(Boolean);
  if (!notes.length) { el.hidden = true; el.textContent = ""; return; }
  el.hidden = false;
  el.textContent = notes.join(" · ");
}

function renderKpis() {
  const k = DATA.kpi || {};
  const cells = [
    { lbl: t("deskKpiGen"), val: fmtNum(k.genGasSin, 0), unit: "MWmed" + (k.genGasWhen ? " · " + k.genGasWhen : "") },
    { lbl: t("deskKpiPld"), val: fmtNum(k.pldSe, 2), unit: "R$/MWh" + (k.pldWhen ? " · " + k.pldWhen : "") },
    { lbl: t("deskKpiCmo"), val: fmtNum(k.cmoSe, 2), unit: "R$/MWh" + (k.cmoWhen ? " · " + k.cmoWhen : "") },
    { lbl: t("deskKpiSantos"), val: fmtNum(k.anpSantos, 1), unit: "R$/MMBtu" + (k.anpSantosMonth ? " · " + k.anpSantosMonth : "") },
    { lbl: t("deskKpiPoc"), val: fmtNum(k.pocAvg7d, 2), unit: "R$/MMBtu" + (k.pocTrades7d != null ? " · " + k.pocTrades7d : "") },
    { lbl: t("deskKpiFlows"), val: fmtNum(k.flowsTotal7d, 0), unit: "mil m³" + (k.flowsWhen ? " · " + k.flowsWhen : "") },
  ];
  const host = document.getElementById("kpi-row");
  host.innerHTML = cells.map(c =>
    '<div class="kpi-cell"><div class="lbl">' + escapeHtml(c.lbl) + '</div>' +
    '<div class="val">' + escapeHtml(c.val) + '</div>' +
    '<div class="unit">' + escapeHtml(c.unit) + '</div></div>'
  ).join("");
}

function impliedCvu(gas, hr, natgas, mmbtuPer1000) {
  if (gas == null || hr == null || !(natgas > 0) || !(mmbtuPer1000 > 0)) return null;
  return gas * hr * 1000 / (natgas * mmbtuPer1000);
}

function renderSpark() {
  if (!DATA) return;
  const s = DATA.spark || {};
  const gasEl = document.getElementById("spark-gas");
  const hrEl = document.getElementById("spark-hr");
  const preset = document.getElementById("spark-hr-preset");
  const ovEl = document.getElementById("spark-cvu");
  const gas = parseFloat(gasEl.value);
  let hr = parseFloat(hrEl.value);
  if (preset.value === "ccgt") hr = s.heatRateCcgt;
  else if (preset.value === "ocgt") hr = s.heatRateOcgt;
  if (preset.value !== "custom") hrEl.value = hr;
  const override = ovEl.value === "" ? null : parseFloat(ovEl.value);
  const calc = impliedCvu(gas, hr, s.natgasKcalPerM3, s.mmbtuPer1000M3);
  const cost = (override != null && !isNaN(override)) ? override : calc;
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
}

function initSparkForm() {
  const s = DATA.spark || {};
  const gasEl = document.getElementById("spark-gas");
  const hrEl = document.getElementById("spark-hr");
  const preset = document.getElementById("spark-hr-preset");
  if (s.defaultGasPrice != null) gasEl.value = s.defaultGasPrice;
  hrEl.value = s.heatRateCcgt || 1800;
  preset.value = "ccgt";
  ["spark-gas", "spark-hr", "spark-cvu"].forEach(id => {
    document.getElementById(id).addEventListener("input", renderSpark);
  });
  preset.addEventListener("change", () => {
    const s2 = DATA.spark || {};
    if (preset.value === "ccgt") hrEl.value = s2.heatRateCcgt;
    else if (preset.value === "ocgt") hrEl.value = s2.heatRateOcgt;
    renderSpark();
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
  const H = 260;
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
    tt.style.display = "block";
    const tw = tt.offsetWidth, th = tt.offsetHeight;
    tt.style.left = Math.min(window.innerWidth - tw - 12, ev.clientX + 16) + "px";
    tt.style.top = Math.min(window.innerHeight - th - 12, Math.max(8, ev.clientY - th / 2)) + "px";
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

function renderCompareChart() {
  if (!DATA) return;
  const c = DATA.compareSe || {};
  if (!pickedCompare.size) {
    drawLineChart("main-chart", [], [], t("deskPickSeries"));
    return;
  }
  const series = COMPARE_META.filter(m => pickedCompare.has(m.key)).map(m => ({
    label: t(m.labelKey),
    values: c[m.field] || [],
    color: colorOf(compareSlots, m.key),
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
    color: colorOf(pocAnpSlots, m.key),
  }));
  drawLineChart("poc-anp-chart", c.months || [], series, c.note || t("deskEmptyChart"));
}

function utilRawRows() {
  const u = DATA.utilization || {};
  return (u.rows || []).map(r => ({
    tso: r.tso,
    contracted: r.contracted,
    realized: r.realized,
    utilization: r.utilization == null ? null : r.utilization * 100,
  }));
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

function renderUtil() {
  if (!DATA) return;
  const u = DATA.utilization || {};
  const thead = document.getElementById("util-thead");
  const body = document.getElementById("util-body");
  const cols = [
    { key: "tso", label: t("deskUtilTso") },
    { key: "contracted", label: t("deskUtilCap"), num: true },
    { key: "realized", label: t("deskUtilReal"), num: true },
    { key: "utilization", label: t("deskUtilPct"), num: true },
  ];
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
      tr.innerHTML = '<td colspan="4" style="color:var(--muted)">' + escapeHtml(u.note || t("deskEmptyChart")) + "</td>";
      body.appendChild(tr);
      return;
    }
    rows.forEach(r => {
      const tr = document.createElement("tr");
      const util = r.utilization == null ? "—" : fmtNum(r.utilization, 0) + "%";
      tr.innerHTML =
        "<td>" + escapeHtml(r.tso) + "</td>" +
        '<td class="num">' + escapeHtml(fmtNum(r.contracted, 1)) + "</td>" +
        '<td class="num">' + escapeHtml(fmtNum(r.realized, 1)) + "</td>" +
        '<td class="num">' + escapeHtml(util) + "</td>";
      body.appendChild(tr);
    });
  });
}

function renderAll() {
  paintAsof();
  renderNotes();
  renderKpis();
  buildPickers();
  renderCompareChart();
  renderPocAnpChart();
  renderUtil();
  renderSpark();
  applyI18n();
}

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  initThemeToggle("theme-toggle", () => {
    if (DATA) {
      buildPickers();
      renderCompareChart();
      renderPocAnpChart();
    }
  });
  initLangToggle("lang-toggle", () => {
    if (DATA) renderAll();
    else applyI18n();
  });
  initCrossLinks();
  applyI18n();
  try {
    const json = await inflateGzipUrl(PAYLOAD_URL);
    DATA = JSON.parse(json);
    COMPARE_META.forEach(m => { pickedCompare.add(m.key); colorOf(compareSlots, m.key); });
    POC_ANP_META.forEach(m => { pickedPocAnp.add(m.key); colorOf(pocAnpSlots, m.key); });
    initSparkForm();
    renderAll();
    window.addEventListener("resize", () => {
      clearTimeout(chartResizeTimer);
      chartResizeTimer = setTimeout(() => {
        renderCompareChart();
        renderPocAnpChart();
      }, 140);
    });
  } catch (err) {
    console.error(err);
    const el = document.getElementById("data-notes");
    el.hidden = false;
    el.textContent = String(err && err.message || err);
  }
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    payload = build_payload()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
    import data_kit as dk  # noqa: E402

    here = Path(__file__).resolve().parent
    payload_path, payload_href = dk.write_and_publish_artifact("desk", payload, here)
    kpi = payload.get("kpi") or {}
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_PLD_SE="" if kpi.get("pldSe") is None else str(kpi["pldSe"]),
        KPI_GEN_GAS="" if kpi.get("genGasSin") is None else str(kpi["genGasSin"]),
        DATA_THROUGH=payload.get("dataThrough") or "",
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_TABLE_SORT=kit.JS_TABLE_SORT,
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("desk"),
        SHARED_NAV_LINKS=kit.nav_links_html("desk"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(
        f"Wrote dashboard shell ({len(html):,} bytes) + {payload_path.name} "
        f"({payload_path.stat().st_size:,} bytes) -> {payload_href}"
    )
    if payload.get("notes"):
        print("  notes:", "; ".join(payload["notes"]).encode("ascii", "replace").decode("ascii"))
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
