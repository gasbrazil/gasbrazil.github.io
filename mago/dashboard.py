"""
Build TAG Mago dashboard from data/tag_mago_series.parquet.

Embeds the latest snapshot's integrated line pack (actual + forecast) and
7-day hourly consumption forecasts for all TAG balancing zones.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "tag_mago_series.parquet"
DEFAULT_OUT = HERE / "index.html"

ZONE_LABELS = {
    "AL": "Alagoas",
    "BA1": "Bahia 1",
    "BA2": "Bahia 2",
    "BA3": "Bahia 3",
    "BA4": "Bahia 4",
    "BA5": "Bahia 5",
    "CE1": "Ceará 1",
    "CE2": "Ceará 2",
    "ES1": "Espírito Santo 1",
    "ES2": "Espírito Santo 2",
    "ES3": "Espírito Santo 3",
    "PB": "Paraíba",
    "PE1": "Pernambuco 1",
    "PE2": "Pernambuco 2",
    "RJ": "Rio de Janeiro",
    "RN1": "Rio Grande do Norte 1",
    "RN2": "Rio Grande do Norte 2",
    "RN3": "Rio Grande do Norte 3",
    "SE": "Sergipe",
}

ZONE_ORDER = [
    "SE", "RJ", "ES1", "ES2", "ES3", "BA1", "BA2", "BA3", "BA4", "BA5",
    "AL", "PE1", "PE2", "PB", "RN1", "RN2", "RN3", "CE1", "CE2",
]


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return round(float(v), 4)


def _series_pack(sub: pd.DataFrame) -> dict:
    sub = sub.sort_values("observed_at")
    times = [ts.strftime("%Y-%m-%dT%H:%M") for ts in sub["observed_at"]]
    values = [_num(v) for v in sub["value"].tolist()]
    return {"times": times, "values": values}


def load_payload(*, snapshot_at: pd.Timestamp | None = None) -> dict:
    if not PARQUET_PATH.exists():
        raise RuntimeError(f"Missing {PARQUET_PATH} — run make_mock.py or mago_pipeline.py build")
    df = pd.read_parquet(PARQUET_PATH)
    df["snapshot_at"] = pd.to_datetime(df["snapshot_at"], utc=True)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)

    snapshots = sorted(df["snapshot_at"].unique())
    if not snapshots:
        raise RuntimeError("tag_mago_series.parquet is empty")
    snap = snapshot_at if snapshot_at is not None else snapshots[-1]
    if snap not in snapshots:
        snap = snapshots[-1]

    snap_df = df[df["snapshot_at"] == snap]
    lp_actual = snap_df[
        (snap_df["series"] == "linepack_actual") & (snap_df["mesh"] == "integrated")
    ]
    lp_fore = snap_df[
        (snap_df["series"] == "linepack_forecast") & (snap_df["mesh"] == "integrated")
    ]
    zones_df = snap_df[snap_df["series"] == "zone_consumption_forecast"]

    zone_series: dict[str, dict] = {}
    zones_present = [z for z in ZONE_ORDER if z in set(zones_df["zone"].dropna())]
    for zone in zones_present:
        part = zones_df[zones_df["zone"] == zone]
        zone_series[zone] = _series_pack(part)

    latest_lp = None
    if len(lp_actual):
        latest_lp = _num(lp_actual.sort_values("observed_at")["value"].iloc[-1])

    now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": now.isoformat(),
        "snapshotAt": pd.Timestamp(snap).strftime("%Y-%m-%d %H:%M UTC"),
        "snapshotIso": pd.Timestamp(snap).isoformat(),
        "snapshots": [pd.Timestamp(s).strftime("%Y-%m-%dT%H:%M") for s in snapshots[-40:]],
        "zones": zones_present,
        "zoneLabels": {z: ZONE_LABELS.get(z, z) for z in zones_present},
        "linepack": {
            "actual": _series_pack(lp_actual) if len(lp_actual) else {"times": [], "values": []},
            "forecast": _series_pack(lp_fore) if len(lp_fore) else {"times": [], "values": []},
        },
        "zoneSeries": zone_series,
        "kpiLinepackM3": latest_lp,
        "kpiLinepackMm3": None if latest_lp is None else round(latest_lp / 1_000_000, 3),
        "source": "TAG Mago — EMPACOTAMENTOS snapshots (api-mago-prod-lb.ntag.com.br)",
        "note": "Zone forecasts are TAG's 7-day hourly consumption estimates (Mm³/d). "
        "Line pack is integrated mesh inventory (m³).",
    }


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TAG Mago — GasBrazil.com</title>
<meta name="description" content="TAG Mago line pack and 7-day balancing-zone consumption forecasts from hourly operational snapshots.">
<link rel="canonical" href="https://gasbrazil.com/mago/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_linepack: __KPI_LINEPACK__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; font-weight: 300; }
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
.panel { margin: 0 0 var(--gap); padding: var(--card-pad); border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.panel h2 { margin: 0 0 .35rem; font-size: 1.05rem; }
.panel p.sub { margin: 0 0 .75rem; color: var(--muted); font-size: .92rem; font-weight: 200; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: var(--gap); }
.kpi { padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--panel); }
.kpi .label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
.kpi .val { font-size: 1.35rem; font-weight: 650; font-variant-numeric: tabular-nums; margin-top: 4px; }
.chips { display: flex; flex-wrap: wrap; gap: .35rem; margin: .5rem 0; }
.chip { border: 1px solid var(--border); background: var(--bg); color: inherit; border-radius: 999px; padding: .25rem .65rem; font-size: .82rem; cursor: pointer; font-family: var(--font); }
.chip.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
#chart-lp, #chart-zones { min-height: 320px; }
.chart-empty { color: var(--muted); padding: 2rem 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: .35rem; font-size: .85rem; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 12px; height: 3px; margin-right: .35rem; vertical-align: middle; background: currentColor; }
.legend .dash::before { background: repeating-linear-gradient(90deg, currentColor 0 5px, transparent 5px 9px); height: 0; border-top: 2px dashed currentColor; width: 14px; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
__SHARED_TYPO_WEIGHT_CSS__
</style>
</head>
<body>
<a class="skip-link" href="#chart-lp" data-i18n="skip">Skip to content</a>
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
  <a href="https://mago.ntag.com.br/empacotamento" target="_blank" rel="noopener">TAG Mago<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
  <div class="kpi-row">
    <div class="kpi"><div class="label" data-i18n="magoKpiLinepack">Integrated line pack</div><div class="val" id="kpi-lp">—</div></div>
    <div class="kpi"><div class="label" data-i18n="magoKpiSnapshot">Snapshot (UTC)</div><div class="val" id="kpi-snap">—</div></div>
  </div>

  <section class="panel">
    <h2 data-i18n="magoLinepackTitle">Line pack — integrated mesh</h2>
    <p class="sub" data-i18n="magoLinepackSub">Hourly actual (solid) and short-horizon forecast (dashed) from the latest Mago snapshot.</p>
    <div id="chart-lp"></div>
    <div class="legend"><span style="color:var(--tso-tag,#0066cc)">Actual</span><span class="dash" style="color:#888">Forecast</span></div>
  </section>

  <section class="panel">
    <h2 data-i18n="magoZonesTitle">Consumption forecast by zone</h2>
    <p class="sub" data-i18n="magoZonesSub">TAG 7-day hourly estimates (Mm³/d). Toggle zones to compare.</p>
    <div class="chips" id="zone-chips"></div>
    <div id="chart-zones"></div>
  </section>
<div class="toolbar" style="display:flex;gap:8px;margin-bottom:10px;">
  __SHARED_SHARE_BUTTON__
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
  <span data-i18n="magoFooter">Data: TAG Mago EMPACOTAMENTOS snapshots. Not an official TAG product.</span>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
</div>
<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";
__SHARED_JS_DECODE__
__SHARED_JS_ESCAPE_HTML__
__SHARED_JS_CHART_PALETTE__
__SHARED_SITE_LINKS_JS__
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__
__SHARED_JS_QUERY_STATE__

GB_I18N.en.magoFooter = "Data: TAG Mago EMPACOTAMENTOS snapshots. Not an official TAG product.";
GB_I18N.pt.magoFooter = "Dados: snapshots EMPACOTAMENTOS do TAG Mago. Não é um produto oficial da TAG.";

let DATA = {};
let LP = {};
let ZONE_SERIES = {};
let selectedZones = new Set();

function fmtMm3(v) {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  return (v / 1e6).toFixed(2) + " Mm³";
}

function setKpis() {
  document.getElementById("kpi-lp").textContent = DATA.kpiLinepackMm3 != null
    ? DATA.kpiLinepackMm3.toFixed(2) + " Mm³" : fmtMm3(DATA.kpiLinepackM3);
  document.getElementById("kpi-snap").textContent = DATA.snapshotAt || "—";
}

function chartSvg(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs || {}).forEach(([k,v]) => el.setAttribute(k, v));
  return el;
}

function drawLines(hostId, seriesList, yFmt) {
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  const usable = seriesList.filter(s => (s.points || []).length >= 2);
  if (!usable.length) {
    host.innerHTML = '<div class="chart-empty">No series in this view.</div>';
    return;
  }
  const allPts = usable.flatMap(s => s.points);
  const xs = allPts.map(p => p.x);
  const ys = allPts.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = 320, ML = 58, MR = 12, MT = 16, MB = 30;
  const x = v => ML + (W - ML - MR) * ((v - minX) / (maxX - minX || 1));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo || 1));
  const svg = chartSvg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  svg.style.width = "100%"; svg.style.height = H + "px";
  for (let i = 0; i <= 4; i++) {
    const t = lo + (hi - lo) * (i / 4);
    const yy = y(t);
    svg.appendChild(chartSvg("line", { x1: ML, x2: W - MR, y1: yy, y2: yy, stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvg("text", { x: ML - 6, y: yy + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
    lb.textContent = yFmt(t); svg.appendChild(lb);
  }
  usable.forEach(s => {
    let d = "";
    s.points.forEach((p, i) => { d += (i ? "L" : "M") + x(p.x).toFixed(1) + " " + y(p.y).toFixed(1) + " "; });
    const attrs = { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" };
    if (s.dashed) attrs["stroke-dasharray"] = "6 4";
    svg.appendChild(chartSvg("path", attrs));
  });
  host.appendChild(svg);
}

function tsMs(iso) {
  const d = new Date(iso.length > 10 ? iso : iso + "T00:00:00Z");
  return d.getTime();
}

function packLinepack() {
  const act = (LP.actual && LP.actual.times || []).map((t, i) => ({ x: tsMs(t), y: LP.actual.values[i] }));
  const fore = (LP.forecast && LP.forecast.times || []).map((t, i) => ({ x: tsMs(t), y: LP.forecast.values[i] }));
  drawLines("chart-lp", [
    { points: act, color: "var(--tso-tag,#0066cc)", dashed: false },
    { points: fore, color: "#888", dashed: true },
  ], v => (v / 1e6).toFixed(1));
}

function packZones() {
  const palette = (window.GB_CHART_PALETTE || ["#0066cc", "#e67e22", "#2ecc71", "#9b59b6", "#c0392b"]);
  let i = 0;
  const series = [];
  selectedZones.forEach(z => {
    const bag = ZONE_SERIES[z];
    if (!bag || !bag.times) return;
    const pts = bag.times.map((t, j) => ({ x: tsMs(t), y: bag.values[j] }));
    series.push({ points: pts, color: palette[i++ % palette.length], dashed: false, label: z });
  });
  drawLines("chart-zones", series, v => v.toFixed(1));
}

function renderZoneChips() {
  const host = document.getElementById("zone-chips");
  host.innerHTML = "";
  (DATA.zones || []).forEach(z => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip" + (selectedZones.has(z) ? " on" : "");
    b.textContent = (DATA.zoneLabels && DATA.zoneLabels[z]) ? DATA.zoneLabels[z] + " (" + z + ")" : z;
    b.addEventListener("click", () => {
      if (selectedZones.has(z)) selectedZones.delete(z); else selectedZones.add(z);
      renderZoneChips(); packZones();
    });
    host.appendChild(b);
  });
}

function paintAsof() {
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated);
  document.getElementById("asof-through").textContent = DATA.snapshotAt || "—";
  initStalenessBadgeFor("mago", DATA.snapshotAt);
}

function paintPage() {
  setKpis();
  renderZoneChips();
  packLinepack();
  packZones();
  paintAsof();
}

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const json = await inflateGzipUrl(PAYLOAD_URL);
  DATA = parseDashboardJson(json);
  LP = DATA.linepack || {};
  ZONE_SERIES = DATA.zoneSeries || {};
  selectedZones = new Set((DATA.zones || []).slice(0, 4));
  paintPage();
  initThemeToggle("theme-toggle", () => { packLinepack(); packZones(); });
  initLangToggle("lang-toggle", () => {
    renderZoneChips();
    setKpis();
    applyI18n();
  });
  initCrossLinks();
  gbCopyLink("btn-share");
  applyI18n();
  window.addEventListener("resize", () => { packLinepack(); packZones(); });
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    import data_kit as dk

    snap_param = None
    # Snapshot selection via query is applied at build time only when rebuilding
    # with env; runtime reload uses full payload for now.
    payload = load_payload(snapshot_at=snap_param)
    here = Path(__file__).resolve().parent
    _path, payload_href = dk.write_and_publish_artifact("mago", payload, here)
    kpi_lp = payload.get("kpiLinepackMm3")
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_LINEPACK="" if kpi_lp is None else f"{kpi_lp:.2f}",
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_TYPO_WEIGHT_CSS=kit.typo_weight_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_ASOF=kit.refreshed_local_js(),
        SHARED_JS_QUERY_STATE=kit.JS_QUERY_STATE,
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("mago"),
        SHARED_MASTHEAD=kit.masthead_html("mago"),
        SHARED_METHODOLOGY=kit.methodology_html("mago"),
        SHARED_SHARE_BUTTON=kit.share_link_button_html(),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html):,} bytes), payload → {payload_href}")
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
