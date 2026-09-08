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
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-links { display: flex; gap: 8px; flex-wrap: wrap; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
.lede { font-size: 13px; color: var(--muted2); font-weight: 300; max-width: 48em; line-height: 1.45; margin: 0 0 var(--gap); }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin-bottom: var(--gap); }
.kpi-cell { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; }
.kpi-cell .lbl { font-size: 11px; font-weight: 400; color: var(--muted2); }
.kpi-cell .val { font-size: 18px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 2px; }
.kpi-cell .unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; }
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
th { position: sticky; top: 0; background: var(--panel); color: var(--muted2); font-weight: 400; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
.tt { position: fixed; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 8px 10px; font-size: 12px; z-index: 50; display: none; min-width: 160px; }
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
<div class="asof-strip" id="asof-strip">
  <span class="asof-label" data-i18n="kpiRefresh">Last refreshed</span>
  <span class="asof-val" id="asof-refreshed">&mdash;</span>
  <span class="asof-label" data-i18n="dataThrough">Data through</span>
  <span class="asof-val" id="asof-through">&mdash;</span>
</div>
<div class="flagbar" aria-hidden="true"></div>
<div class="sources">
  <span class="sources-label" data-i18n="sources">Sources</span>
  <a class="pill" href="https://www.gov.br/anp/pt-br/assuntos/movimentacao-estocagem-e-comercializacao-de-gas-natural/acompanhamento-do-mercado-de-gas-natural/publicidade-dos-precos-de-gas-natural" target="_blank" rel="noopener" data-i18n="sourcePrecos">ANP — publicidade dos preços<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
<p class="lede" data-i18n="precosLede">Official monthly ANP disclosures under Resolution 52/2011 — aggregated trading prices (tax-inclusive R$/MMBtu), not assessed spot benchmarks. Gaps are suppressions, not missing downloads.</p>
<div class="kpi-row" id="kpi-row"></div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosProdTitle">Producer sales by basin</p>
  <p class="panel-note" data-i18n="precosProdNote">Wellhead sales between producers. Santos has been the cheapest and most stable; Other basins remain highest.</p>
  <div id="chart-producers"></div>
  <div class="legend" id="leg-producers"></div>
</div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosDistTitle">Sales to distributors &amp; free consumers</p>
  <p class="panel-note" data-i18n="precosDistNote">Thermal contracts run far below non-thermal. Blank stretches are ANP suppressions (too few counterparties).</p>
  <div id="chart-distributors"></div>
  <div class="legend" id="leg-distributors"></div>
</div>
<div class="chart-card">
  <p class="panel-title" data-i18n="precosMktTitle">Sales to marketers</p>
  <p class="panel-note" data-i18n="precosMktNote">Brazil-wide. Watch volume and price spikes in recent months — still short history.</p>
  <div id="chart-marketers"></div>
  <div class="legend" id="leg-marketers"></div>
</div>
<ul class="notes">
  <li data-i18n="precosCaveat1">Prices include ICMS, PIS and Cofins. Volumes in thousand m³/day at reference conditions.</li>
  <li data-i18n="precosCaveat2">Published with roughly a two-month lag. Chart gaps are intentional — do not interpolate.</li>
</ul>
<div class="toolbar">
  <button type="button" id="btn-csv" data-i18n="precosCsv">Download CSV</button>
  <button type="button" id="btn-xlsx" data-i18n="precosXlsx">Export Excel</button>
  <span class="count" id="row-count"></span>
</div>
<div class="table-wrap">
  <table id="data-table"><thead><tr id="thead-row"></tr></thead><tbody id="tbody"></tbody></table>
</div>
<footer>
  &copy; <span id="year"></span> GasBrazil.com &middot;
  <span data-i18n="precosFooter">Data: ANP publicidade dos preços de gás natural. Not an official ANP product.</span>
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

GB_I18N.en.precosLede = "Official monthly ANP disclosures under Resolution 52/2011 — aggregated trading prices (tax-inclusive R$/MMBtu), not assessed spot benchmarks. Gaps are suppressions, not missing downloads.";
GB_I18N.en.precosProdTitle = "Producer sales by basin";
GB_I18N.en.precosProdNote = "Wellhead sales between producers. Santos has been the cheapest and most stable; Other basins remain highest.";
GB_I18N.en.precosDistTitle = "Sales to distributors & free consumers";
GB_I18N.en.precosDistNote = "Thermal contracts run far below non-thermal. Blank stretches are ANP suppressions (too few counterparties).";
GB_I18N.en.precosMktTitle = "Sales to marketers";
GB_I18N.en.precosMktNote = "Brazil-wide. Watch volume and price spikes in recent months — still short history.";
GB_I18N.en.precosCaveat1 = "Prices include ICMS, PIS and Cofins. Volumes in thousand m³/day at reference conditions.";
GB_I18N.en.precosCaveat2 = "Published with roughly a two-month lag. Chart gaps are intentional — do not interpolate.";
GB_I18N.en.precosCsv = "Download CSV";
GB_I18N.en.precosXlsx = "Export Excel";
GB_I18N.en.precosFooter = "Data: ANP publicidade dos preços de gás natural. Not an official ANP product.";
GB_I18N.pt.precosLede = "Divulgações mensais oficiais da ANP (Resolução 52/2011) — preços agregados com impostos (R$/MMBtu), não benchmarks de spot. Lacunas são omissões da ANP, não falhas de download.";
GB_I18N.pt.precosProdTitle = "Vendas entre produtores por bacia";
GB_I18N.pt.precosProdNote = "Vendas na boca do poço. Santos tem sido a mais barata e estável; Demais Bacias, a mais cara.";
GB_I18N.pt.precosDistTitle = "Vendas a distribuidoras e consumidores livres";
GB_I18N.pt.precosDistNote = "Contratos térmicos ficam bem abaixo dos não térmicos. Trechos em branco são omissões da ANP.";
GB_I18N.pt.precosMktTitle = "Vendas a comercializadores";
GB_I18N.pt.precosMktNote = "Nacional. Acompanhe volume e preços recentes — histórico ainda curto.";
GB_I18N.pt.precosCaveat1 = "Preços incluem ICMS, PIS e Cofins. Volumes em mil m³/dia nas condições de referência.";
GB_I18N.pt.precosCaveat2 = "Publicação com cerca de dois meses de defasagem. Lacunas no gráfico são intencionais — sem interpolar.";
GB_I18N.pt.precosCsv = "Baixar CSV";
GB_I18N.pt.precosXlsx = "Exportar Excel";
GB_I18N.pt.precosFooter = "Dados: ANP publicidade dos preços de gás natural. Não é um produto oficial da ANP.";

let DATA = null;
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
function lineChart(host, legend, series, months) {
  host.innerHTML = ""; legend.innerHTML = "";
  const plot = series.filter(s => s.pts.some(p => p.v != null));
  if (!plot.length) { host.innerHTML = '<div class="chart-empty">No data</div>'; return; }
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
    const t = el("text", { x: ML-8, y: y(tk)+4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
    t.textContent = fmt(tk, 0); svg.appendChild(t);
  });
  const nT = Math.min(8, months.length);
  for (let i = 0; i < nT; i++) {
    const mi = months[Math.round(i*(months.length-1)/Math.max(1,nT-1))];
    const t = el("text", { x: x(mi), y: H-8, fill: "var(--muted)", "font-size": 11, "text-anchor": i===0?"start":(i===nT-1?"end":"middle") });
    t.textContent = mi; svg.appendChild(t);
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
  host.appendChild(svg);
}
function renderKpis() {
  const host = document.getElementById("kpi-row");
  const last = DATA.dataThrough || "";
  const santos = DATA.kpiSantos;
  host.innerHTML = `
    <div class="kpi-cell"><div class="lbl">Santos</div><div class="val">${fmt(santos)}</div><div class="unit">R$/MMBtu · ${last}</div></div>
    <div class="kpi-cell"><div class="lbl">Months</div><div class="val">${DATA.nMonths||"—"}</div><div class="unit">in series</div></div>`;
}
function renderAll() {
  const months = DATA.months;
  const pal = chartPalette();
  const prod = Object.keys(DATA.producers||{}).map((k,i) => ({
    label: k, color: pal[i%pal.length],
    pts: months.map((m,j) => ({ month: m, v: DATA.producers[k][j] }))
  }));
  lineChart(document.getElementById("chart-producers"), document.getElementById("leg-producers"), prod, months);
  const distLabels = {
    "non_thermal|Norte-Nordeste": "Non-thermal N-NE",
    "non_thermal|Sudeste": "Non-thermal SE",
    "non_thermal|Sul-Centro-Oeste": "Non-thermal S-CO",
    "thermal|Norte-Nordeste": "Thermal N-NE",
    "thermal|Sudeste-Sul-Centro-Oeste": "Thermal SE-S-CO"
  };
  const dist = Object.keys(DATA.distributors||{}).map((k,i) => ({
    label: distLabels[k] || k, color: pal[i%pal.length],
    pts: months.map((m,j) => ({ month: m, v: DATA.distributors[k][j] }))
  }));
  lineChart(document.getElementById("chart-distributors"), document.getElementById("leg-distributors"), dist, months);
  const mkt = [
    { label: "Price", color: pal[0], pts: months.map((m,j) => ({ month: m, v: DATA.marketersPrice[j] })) },
  ];
  lineChart(document.getElementById("chart-marketers"), document.getElementById("leg-marketers"), mkt, months);

  const thead = document.getElementById("thead-row");
  thead.innerHTML = "<th>Month</th><th>Santos</th><th>Campos</th><th>Other</th><th>Marketers</th><th>Mkt vol</th>";
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  for (let i = months.length - 1; i >= 0; i--) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${months[i]}</td>
      <td class="num">${fmt(DATA.producers.Santos[i])}</td>
      <td class="num">${fmt(DATA.producers.Campos[i])}</td>
      <td class="num">${fmt(DATA.producers["Other basins"][i])}</td>
      <td class="num">${fmt(DATA.marketersPrice[i])}</td>
      <td class="num">${fmt(DATA.marketersVolume[i], 0)}</td>`;
    tb.appendChild(tr);
  }
  document.getElementById("row-count").textContent = months.length + " months";
}
function tableRows() {
  const rows = [["month","santos","campos","other_basins","marketers_price","marketers_volume"]];
  DATA.months.forEach((m,i) => rows.push([
    m, DATA.producers.Santos[i], DATA.producers.Campos[i], DATA.producers["Other basins"][i],
    DATA.marketersPrice[i], DATA.marketersVolume[i]
  ]));
  return rows;
}
async function init() {
  const json = await inflateGzipUrl(PAYLOAD_URL);
  DATA = JSON.parse(json);
  document.getElementById("asof-refreshed").textContent = DATA.generated || "—";
  document.getElementById("asof-through").textContent = DATA.dataThrough || "—";
  document.getElementById("year").textContent = new Date().getFullYear();
  renderKpis();
  renderAll();
  document.getElementById("btn-csv").addEventListener("click", () => downloadCsv("anp-prices.csv", tableRows()));
  document.getElementById("btn-xlsx").addEventListener("click", () => downloadXlsx("anp-prices.xlsx", [{ name: "prices", rows: tableRows() }]));
  initThemeToggle("theme-toggle", () => renderAll());
  initLangToggle("lang-toggle");
  initCrossLinks();
  window.addEventListener("resize", () => { clearTimeout(window.__pr); window.__pr = setTimeout(renderAll, 120); });
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
