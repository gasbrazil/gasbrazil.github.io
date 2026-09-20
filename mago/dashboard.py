"""
Build TAG Mago dashboard from data/tag_mago_series.parquet.

Embeds the latest snapshot's integrated line pack (actual + forecast) and
7-day hourly consumption forecasts for all TAG balancing zones, plus
deduplicated line-pack history across cached snapshots.
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

# State-level aggregation (TAG balancing zones grouped by federative unit).
STATE_GROUPS: dict[str, tuple[str, list[str]]] = {
    "total": ("Total (all zones)", ZONE_ORDER),
    "SE": ("Sergipe", ["SE"]),
    "RJ": ("Rio de Janeiro", ["RJ"]),
    "ES": ("Espírito Santo", ["ES1", "ES2", "ES3"]),
    "BA": ("Bahia", ["BA1", "BA2", "BA3", "BA4", "BA5"]),
    "AL": ("Alagoas", ["AL"]),
    "PE": ("Pernambuco", ["PE1", "PE2"]),
    "PB": ("Paraíba", ["PB"]),
    "RN": ("Rio Grande do Norte", ["RN1", "RN2", "RN3"]),
    "CE": ("Ceará", ["CE1", "CE2"]),
}

GROUP_ORDER = ["total", "SE", "RJ", "ES", "BA", "AL", "PE", "PB", "RN", "CE"]


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return round(float(v), 4)


def _series_pack(sub: pd.DataFrame) -> dict:
    sub = sub.sort_values("observed_at")
    times = [ts.strftime("%Y-%m-%dT%H:%M") for ts in sub["observed_at"]]
    values = [_num(v) for v in sub["value"].tolist()]
    return {"times": times, "values": values}


def _collapse_consumption_to_daily(series: dict) -> dict:
    """TAG zone forecasts are a 7-day daily horizon; snapshots often repeat hourly."""
    times = series.get("times") or []
    values = series.get("values") or []
    day_map: dict[str, tuple[str, float | None]] = {}
    for t, v in zip(times, values, strict=False):
        day = t[:10]
        is_midnight = len(t) >= 16 and t[11:16] == "00:00"
        if day not in day_map or is_midnight:
            day_map[day] = (f"{day}T00:00", v)
    days = sorted(day_map.keys())
    if not days:
        return {"times": [], "values": []}
    return {
        "times": [day_map[d][0] for d in days],
        "values": [day_map[d][1] for d in days],
    }


def _sum_zone_series(zone_series: dict[str, dict], zones: list[str]) -> dict:
    maps: dict[str, dict[str, float | None]] = {}
    for z in zones:
        bag = zone_series.get(z)
        if not bag or not bag.get("times"):
            continue
        maps[z] = dict(zip(bag["times"], bag["values"], strict=False))
    if not maps:
        return {"times": [], "values": []}
    all_times = sorted(set().union(*(m.keys() for m in maps.values())))
    values: list[float | None] = []
    for t in all_times:
        parts = [maps[z].get(t) for z in maps if t in maps[z]]
        nums = [p for p in parts if p is not None]
        values.append(round(sum(nums), 4) if nums else None)
    return {"times": all_times, "values": values}


def _linepack_history(df: pd.DataFrame) -> tuple[dict, list[dict]]:
    lp = df[(df["series"] == "linepack_actual") & (df["mesh"] == "integrated")].copy()
    if lp.empty:
        return {"times": [], "values": []}, []
    lp = lp.sort_values(["observed_at", "snapshot_at"])
    lp = lp.drop_duplicates(subset=["observed_at"], keep="last")
    series = _series_pack(lp)
    rows: list[dict] = []
    for _, row in lp.iterrows():
        val = _num(row["value"])
        rows.append(
            {
                "observedAt": pd.Timestamp(row["observed_at"]).strftime("%Y-%m-%dT%H:%M"),
                "snapshotAt": pd.Timestamp(row["snapshot_at"]).strftime("%Y-%m-%dT%H:%M"),
                "valueM3": val,
                "valueMm3": None if val is None else round(val / 1_000_000, 4),
            }
        )
    return series, rows


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
        zone_series[zone] = _collapse_consumption_to_daily(_series_pack(part))

    group_series: dict[str, dict] = {}
    group_zones: dict[str, list[str]] = {}
    groups_present: list[str] = []
    for key in GROUP_ORDER:
        label, member_zones = STATE_GROUPS[key]
        members = [z for z in member_zones if z in zones_present]
        if not members:
            continue
        groups_present.append(key)
        group_zones[key] = members
        group_series[key] = _sum_zone_series(zone_series, members)

    lp_hist_series, lp_hist_rows = _linepack_history(df)

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
        "groups": groups_present,
        "groupLabels": {k: STATE_GROUPS[k][0] for k in groups_present},
        "groupZones": group_zones,
        "groupSeries": group_series,
        "linepack": {
            "actual": _series_pack(lp_actual) if len(lp_actual) else {"times": [], "values": []},
            "forecast": _series_pack(lp_fore) if len(lp_fore) else {"times": [], "values": []},
        },
        "linepackHistory": lp_hist_series,
        "linepackHistoryRows": lp_hist_rows,
        "zoneSeries": zone_series,
        "kpiLinepackM3": latest_lp,
        "kpiLinepackMm3": None if latest_lp is None else round(latest_lp / 1_000_000, 3),
        "source": "TAG Mago — EMPACOTAMENTOS snapshots (api-mago-prod-lb.ntag.com.br)",
        "note": "Zone forecasts are TAG's 7-day daily consumption estimates (Mm³/d). "
        "Hourly PI samples in snapshots are collapsed to one point per UTC day. "
        "Line pack is integrated mesh inventory (m³). History merges hourly actuals "
        "across cached snapshots (newest snapshot wins at each timestamp).",
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
     kpi_linepack: __KPI_LINEPACK__
     kpi_snapshot: __KPI_SNAPSHOT__ -->
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
.panel { margin: 0 0 10px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.panel-tight { padding: 10px 12px; }
.panel h2 { margin: 0 0 .2rem; font-size: .98rem; font-weight: 500; }
.panel p.sub { margin: 0 0 .5rem; color: var(--muted); font-size: .8rem; font-weight: 200; line-height: 1.35; }
.panel p.sub.compact { margin-bottom: .35rem; }
.panel-head-row { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 6px; margin-bottom: 10px; }
.kpi { padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--panel); }
.kpi .label { color: var(--muted); font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; }
.kpi .val { font-size: 1.1rem; font-weight: 650; font-variant-numeric: tabular-nums; margin-top: 2px; }
.chart-box { min-height: 220px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); padding: 4px 2px 0; margin-bottom: 8px; }
.chart-box.chart-sm { min-height: 200px; }
#chart-lp, #chart-lp-hist, #chart-zones { min-height: 0; }
.chart-empty { color: var(--muted); padding: 1.25rem .75rem; text-align: center; font-size: .82rem; }
.legend { display: flex; flex-wrap: wrap; gap: .5rem .75rem; margin-top: .25rem; font-size: .75rem; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 3px; margin-right: .3rem; vertical-align: middle; background: currentColor; }
.legend .dash::before { background: repeating-linear-gradient(90deg, currentColor 0 4px, transparent 4px 7px); height: 0; border-top: 2px dashed currentColor; width: 12px; }
.filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 6px; }
.filter-bar .hint { font-size: .75rem; color: var(--muted); margin-left: auto; }
.filter-matrix { display: flex; flex-wrap: wrap; gap: 4px; max-height: 88px; overflow-y: auto; padding: 2px 0; }
.filter-matrix.zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(42px, 1fr)); gap: 4px; max-height: 120px; }
.filter-chip { border: 1px solid var(--border); background: var(--bg); color: inherit; border-radius: 4px; padding: 3px 7px; font-size: 11px; line-height: 1.2; cursor: pointer; font-family: var(--font); font-variant-numeric: tabular-nums; }
.filter-chip:hover { background: var(--accent-soft); }
.filter-chip.on { border-color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent); font-weight: 500; }
.is-hidden { display: none !important; }
.seg-row { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--border-strong); border-radius: 5px; overflow: hidden; }
.seg button { border: 0; background: var(--bg); color: var(--muted); font-size: 11px; padding: 4px 9px; cursor: pointer; font-family: var(--font); }
.seg button.on { background: var(--accent-soft); color: var(--text); font-weight: 500; }
.seg button + button { border-left: 1px solid var(--border); }
details.panel-fold { margin-bottom: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
details.panel-fold > summary { cursor: pointer; padding: 10px 12px; font-size: .92rem; font-weight: 500; list-style: none; }
details.panel-fold > summary::-webkit-details-marker { display: none; }
details.panel-fold > .fold-body { padding: 0 12px 12px; border-top: 1px solid var(--border); }
.data-table-wrap { overflow: auto; max-height: 220px; border: 1px solid var(--border); border-radius: var(--radius-sm); margin-top: .5rem; }
table.lp-table { width: 100%; border-collapse: collapse; font-size: .78rem; }
table.lp-table th, table.lp-table td { padding: 4px 8px; border-bottom: 1px solid var(--border); text-align: left; }
table.lp-table th { position: sticky; top: 0; background: var(--panel); cursor: pointer; font-weight: 500; }
table.lp-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.toolbar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; align-items: center; }
.toolbar button, .filter-bar .btn-clear { font-family: var(--font); cursor: pointer; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text); border-radius: 5px; padding: 4px 10px; font-size: .78rem; }
.toolbar button:hover, .filter-bar .btn-clear:hover { background: var(--accent-soft); }
footer { margin-top: 16px; color: var(--muted); font-size: 11px; line-height: 1.6; font-weight: 200; }
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

  <section class="panel panel-tight">
    <h2 data-i18n="magoLinepackTitle">Line pack — integrated mesh</h2>
    <p class="sub compact" data-i18n="magoLinepackSub">Hourly actual (solid) and short-horizon forecast (dashed) from the latest Mago snapshot.</p>
    <div class="chart-box chart-sm"><div id="chart-lp"></div></div>
    <div class="legend"><span style="color:var(--tso-tag,#0066cc)">Actual</span><span class="dash" style="color:#888">Forecast</span></div>
  </section>

  <details class="panel-fold">
    <summary data-i18n="magoLinepackHistTitle">Line pack history</summary>
    <div class="fold-body">
      <p class="sub compact" data-i18n="magoLinepackHistSub">Hourly integrated inventory from cached snapshots (newest wins on overlap).</p>
      <div class="chart-box chart-sm"><div id="chart-lp-hist"></div></div>
      <div class="toolbar">
        <button type="button" id="btn-lp-csv" data-i18n="magoLpCsv">Download line pack CSV</button>
      </div>
      <div class="data-table-wrap">
        <table class="lp-table" id="lp-table">
          <thead><tr>
            <th data-col="observedAt" data-i18n="magoColObserved">Observed (UTC)</th>
            <th data-col="valueMm3" class="num" data-i18n="magoColMm3">Mm³</th>
            <th data-col="valueM3" class="num" data-i18n="magoColM3">m³</th>
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
        <h2 data-i18n="magoZonesTitle">Consumption forecast</h2>
        <p class="sub compact" data-i18n="magoZonesSub">7-day daily TAG estimates (Mm³/d). Chart updates from the compact filters below.</p>
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
      <span id="selection-hint" class="hint"></span>
    </div>
    <div id="filter-state" class="filter-matrix"></div>
    <div id="filter-zone" class="filter-matrix zone-grid is-hidden"></div>
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
/** Public R2 artifact (same bucket as other GasBrazil dashboards). Used when the shell still points at a sibling payload.json.gz that is not on Pages. */
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

GB_I18N.en.magoFooter = "Data: TAG Mago EMPACOTAMENTOS snapshots. Not an official TAG product.";
GB_I18N.pt.magoFooter = "Dados: snapshots EMPACOTAMENTOS do TAG Mago. Não é um produto oficial da TAG.";
GB_I18N.en.magoLinepackHistTitle = "Line pack history";
GB_I18N.pt.magoLinepackHistTitle = "Histórico de empacotamento";
GB_I18N.en.magoLinepackHistSub = "Continuous hourly integrated inventory from all cached Mago snapshots (newest snapshot wins when hours overlap).";
GB_I18N.pt.magoLinepackHistSub = "Inventário integrado horário de todos os snapshots Mago em cache (snapshot mais recente prevalece quando horas coincidem).";
GB_I18N.en.magoByState = "States";
GB_I18N.pt.magoByState = "Estados";
GB_I18N.en.magoByZone = "Zones";
GB_I18N.pt.magoByZone = "Zonas";
GB_I18N.en.magoChartLine = "Lines";
GB_I18N.pt.magoChartLine = "Linhas";
GB_I18N.en.magoChartStack = "Stack";
GB_I18N.pt.magoChartStack = "Empilhado";
GB_I18N.en.magoSelectAll = "Select all";
GB_I18N.pt.magoSelectAll = "Selecionar tudo";
GB_I18N.en.magoZonesSub = "7-day daily TAG estimates (Mm³/d). Chart first; use compact filters below.";
GB_I18N.pt.magoZonesSub = "Estimativas diárias TAG (7 dias, Mm³/d). Gráfico acima; filtros compactos abaixo.";
GB_I18N.en.magoLpCsv = "Download line pack CSV";
GB_I18N.pt.magoLpCsv = "Baixar CSV de empacotamento";
GB_I18N.en.magoColObserved = "Observed (UTC)";
GB_I18N.pt.magoColObserved = "Observado (UTC)";
GB_I18N.en.magoColMm3 = "Mm³";
GB_I18N.pt.magoColMm3 = "Mm³";
GB_I18N.en.magoColM3 = "m³";
GB_I18N.pt.magoColM3 = "m³";
GB_I18N.en.magoColSnapshot = "Source snapshot";
GB_I18N.pt.magoColSnapshot = "Snapshot de origem";

let DATA = {};
let LP = {};
let LP_HIST = {};
let LP_ROWS = [];
let ZONE_SERIES = {};
let GROUP_SERIES = {};
let selectedGroups = new Set(["total"]);
let selectedZones = new Set();
let granularity = "state";
let chartMode = "line";
let lpSort = { col: "observedAt", dir: -1 };

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

function tsMs(iso) {
  const d = new Date(iso.length > 10 ? iso : iso + "T00:00:00Z");
  return d.getTime();
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
  const ys = allPts.map(p => p.y).filter(v => v != null && isFinite(v));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = hostId === "chart-zones" ? 240 : 220, ML = 52, MR = 10, MT = 12, MB = 26;
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
    let started = false;
    s.points.forEach(p => {
      if (p.y == null || !isFinite(p.y)) return;
      d += (started ? "L" : "M") + x(p.x).toFixed(1) + " " + y(p.y).toFixed(1) + " ";
      started = true;
    });
    if (!d) return;
    const attrs = { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" };
    if (s.dashed) attrs["stroke-dasharray"] = "6 4";
    svg.appendChild(chartSvg("path", attrs));
  });
  host.appendChild(svg);
}

function formatDayLabel(ms) {
  const d = new Date(ms);
  return (d.getUTCMonth() + 1) + "/" + d.getUTCDate() + "/" + d.getUTCFullYear();
}

function consumptionStateKeys() {
  return (DATA.groups || []).filter(g => g !== "total");
}

function drawConsumptionStackedDaily(hostId) {
  const host = document.getElementById(hostId);
  host.innerHTML = "";
  const totalBag = GROUP_SERIES.total;
  const stateKeys = consumptionStateKeys();
  if (!totalBag || !totalBag.times || totalBag.times.length < 1 || !stateKeys.length) {
    host.innerHTML = '<div class="chart-empty">No daily forecast in this snapshot.</div>';
    return;
  }
  const palette = (window.GB_CHART_PALETTE || ["#0066cc", "#e67e22", "#2ecc71", "#9b59b6", "#c0392b", "#16a085", "#8e44ad", "#d35400", "#2980b9"]);
  const n = totalBag.times.length;
  const days = totalBag.times.map((t, i) => ({
    x: tsMs(t),
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
  const gap = Math.max(8, plotW / Math.max(n, 1) * 0.08);
  const barW = Math.max(18, (plotW - gap * (n + 1)) / n);
  const y = v => MT + (H - MT - MB) * (1 - v / maxTot);
  const svg = chartSvg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  svg.style.width = "100%"; svg.style.height = H + "px";
  for (let i = 0; i <= 4; i++) {
    const t = maxTot * (i / 4);
    const yy = y(t);
    svg.appendChild(chartSvg("line", { x1: ML, x2: W - MR, y1: yy, y2: yy, stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvg("text", { x: ML - 6, y: yy + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
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
      "text-anchor": "middle", fill: "var(--muted)", "font-size": 10,
    });
    lbl.textContent = formatDayLabel(day.x);
    svg.appendChild(lbl);
  });
  const legHost = document.createElement("div");
  legHost.className = "legend";
  stateKeys.forEach((g, si) => {
    const span = document.createElement("span");
    span.style.color = palette[si % palette.length];
    span.textContent = (DATA.groupLabels && DATA.groupLabels[g]) ? DATA.groupLabels[g] : g;
    legHost.appendChild(span);
  });
  const totSpan = document.createElement("span");
  totSpan.style.color = "var(--text)";
  totSpan.textContent = "● " + ((DATA.groupLabels && DATA.groupLabels.total) ? DATA.groupLabels.total : "Total");
  legHost.appendChild(totSpan);
  host.appendChild(svg);
  host.appendChild(legHost);
}

function packLinepack() {
  const act = (LP.actual && LP.actual.times || []).map((t, i) => ({ x: tsMs(t), y: LP.actual.values[i] }));
  const fore = (LP.forecast && LP.forecast.times || []).map((t, i) => ({ x: tsMs(t), y: LP.forecast.values[i] }));
  drawLines("chart-lp", [
    { points: act, color: "var(--tso-tag,#0066cc)", dashed: false },
    { points: fore, color: "#888", dashed: true },
  ], v => (v / 1e6).toFixed(1));
}

function packLinepackHistory() {
  const pts = (LP_HIST.times || []).map((t, i) => ({ x: tsMs(t), y: LP_HIST.values[i] }));
  drawLines("chart-lp-hist", [
    { points: pts, color: "var(--tso-tag,#0066cc)", dashed: false },
  ], v => (v / 1e6).toFixed(2));
}

function activeZoneSeries() {
  const palette = (window.GB_CHART_PALETTE || ["#0066cc", "#e67e22", "#2ecc71", "#9b59b6", "#c0392b"]);
  let i = 0;
  const series = [];
  if (granularity === "state") {
    selectedGroups.forEach(g => {
      const bag = GROUP_SERIES[g];
      if (!bag || !bag.times) return;
      const pts = bag.times.map((t, j) => ({ x: tsMs(t), y: bag.values[j] }));
      const label = (DATA.groupLabels && DATA.groupLabels[g]) ? DATA.groupLabels[g] : g;
      series.push({ points: pts, color: palette[i++ % palette.length], label: label });
    });
  } else {
    selectedZones.forEach(z => {
      const bag = ZONE_SERIES[z];
      if (!bag || !bag.times) return;
      const pts = bag.times.map((t, j) => ({ x: tsMs(t), y: bag.values[j] }));
      series.push({ points: pts, color: palette[i++ % palette.length], label: z });
    });
  }
  return series;
}

function updateSelectionHint() {
  const el = document.getElementById("selection-hint");
  if (!el) return;
  if (chartMode === "stack") {
    el.textContent = "Stacked view shows all states + total dot.";
    return;
  }
  const n = granularity === "state" ? selectedGroups.size : selectedZones.size;
  el.textContent = n ? (n + " selected") : "Nothing selected";
}

function packZones() {
  if (chartMode === "stack") {
    drawConsumptionStackedDaily("chart-zones");
    updateSelectionHint();
    return;
  }
  const series = activeZoneSeries();
  const host = document.getElementById("chart-zones");
  if (!series.length) {
    host.innerHTML = '<div class="chart-empty">Select states or zones below, or click <strong>Select all</strong>.</div>';
    updateSelectionHint();
    return;
  }
  drawLines("chart-zones", series, v => v.toFixed(1));
  updateSelectionHint();
}

function selectAllMago() {
  if (granularity === "state") {
    selectedGroups = new Set(DATA.groups || []);
  } else {
    selectedZones = new Set(DATA.zones || []);
  }
  renderFilters();
  packZones();
  writeMagoQuery();
}

function clearMagoSelections() {
  selectedGroups.clear();
  selectedZones.clear();
  renderFilters();
  packZones();
  writeMagoQuery();
}

function renderFilters() {
  const stateHost = document.getElementById("filter-state");
  const zoneHost = document.getElementById("filter-zone");
  if (!stateHost || !zoneHost) return;
  stateHost.innerHTML = "";
  zoneHost.innerHTML = "";
  const isState = granularity === "state";
  stateHost.classList.toggle("is-hidden", !isState);
  zoneHost.classList.toggle("is-hidden", isState);
  if (isState) {
    (DATA.groups || []).forEach(g => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "filter-chip" + (selectedGroups.has(g) ? " on" : "");
      const label = (DATA.groupLabels && DATA.groupLabels[g]) ? DATA.groupLabels[g] : g;
      b.textContent = g === "total" ? "Total" : g;
      b.title = label;
      b.addEventListener("click", () => {
        if (selectedGroups.has(g)) selectedGroups.delete(g); else selectedGroups.add(g);
        renderFilters(); packZones(); writeMagoQuery();
      });
      stateHost.appendChild(b);
    });
  } else {
    (DATA.zones || []).forEach(z => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "filter-chip" + (selectedZones.has(z) ? " on" : "");
      b.textContent = z;
      b.title = (DATA.zoneLabels && DATA.zoneLabels[z]) ? DATA.zoneLabels[z] : z;
      b.addEventListener("click", () => {
        if (selectedZones.has(z)) selectedZones.delete(z); else selectedZones.add(z);
        renderFilters(); packZones(); writeMagoQuery();
      });
      zoneHost.appendChild(b);
    });
  }
}

function syncGranularityUi() {
  document.querySelectorAll("[data-gran]").forEach(btn => {
    btn.classList.toggle("on", btn.getAttribute("data-gran") === granularity);
  });
  document.querySelectorAll("[data-mode]").forEach(btn => {
    btn.classList.toggle("on", btn.getAttribute("data-mode") === chartMode);
  });
  renderFilters();
}

function sortedLpRows() {
  const rows = LP_ROWS.slice();
  const col = lpSort.col;
  rows.sort((a, b) => {
    const av = a[col], bv = b[col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * lpSort.dir;
    return String(av).localeCompare(String(bv)) * lpSort.dir;
  });
  return rows;
}

function renderLpTable() {
  const tbody = document.getElementById("lp-tbody");
  tbody.innerHTML = sortedLpRows().map(r => `
    <tr>
      <td>${escapeHtml(r.observedAt)}</td>
      <td class="num">${r.valueMm3 != null ? r.valueMm3.toFixed(4) : "—"}</td>
      <td class="num">${r.valueM3 != null ? r.valueM3.toFixed(2) : "—"}</td>
      <td>${escapeHtml(r.snapshotAt)}</td>
    </tr>`).join("");
}

function downloadLpCsv() {
  const header = ["observed_utc", "mm3", "m3", "source_snapshot_utc"];
  const lines = [header.map(csvEscape).join(",")];
  sortedLpRows().forEach(r => {
    lines.push([
      r.observedAt,
      r.valueMm3 != null ? r.valueMm3 : "",
      r.valueM3 != null ? r.valueM3 : "",
      r.snapshotAt,
    ].map(csvEscape).join(","));
  });
  downloadTextFile(lines.join("\n"), "text/csv;charset=utf-8", "gasbrazil-mago-linepack.csv");
}

function magoGroupKeys() { return DATA.groups || []; }
function magoZoneKeys() { return DATA.zones || []; }

function applyMagoQuery() {
  const q = gbQueryParams();
  const g = gbValidList(q.get("groups"), magoGroupKeys());
  if (g) selectedGroups = new Set(g);
  const z = gbValidList(q.get("zones"), magoZoneKeys());
  if (z) selectedZones = new Set(z);
  const gran = gbValidEnum(q.get("gran"), ["state", "zone"]);
  if (gran) granularity = gran;
  const mode = gbValidEnum(q.get("mode"), ["line", "stack"]);
  if (mode) chartMode = mode;
}

function writeMagoQuery() {
  gbWriteQuery({
    groups: granularity === "state" ? [...selectedGroups] : null,
    zones: granularity === "zone" ? [...selectedZones] : null,
    gran: granularity,
    mode: chartMode,
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
  syncGranularityUi();
  packLinepack();
  packLinepackHistory();
  packZones();
  renderLpTable();
  paintAsof();
}

function showPayloadError() {
  const banner = document.createElement("div");
  banner.className = "panel";
  banner.setAttribute("role", "alert");
  banner.innerHTML = '<p class="sub" style="color:var(--text);margin:0">Could not load TAG Mago data. The dashboard payload may not be published yet — it refreshes automatically every few hours. If this persists, check that the Mago CI workflow completed on <code>main</code>.</p>';
  const wrap = document.querySelector(".wrap");
  if (wrap && wrap.firstChild) wrap.insertBefore(banner, wrap.children[1] || wrap.firstChild);
}

async function fetchMagoPayloadJson() {
  const urls = [PAYLOAD_URL];
  if (!/^https?:/i.test(String(PAYLOAD_URL || ""))) urls.push(MAGO_PAYLOAD_R2);
  let lastErr;
  for (const u of urls) {
    try {
      return await inflateGzipUrl(u);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("payload unavailable");
}

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  let json;
  try {
    json = await fetchMagoPayloadJson();
  } catch (e) {
    console.error(e);
    showPayloadError();
    applyI18n();
    initThemeToggle("theme-toggle", () => {});
    initLangToggle("lang-toggle", () => applyI18n());
    initCrossLinks();
    gbCopyLink("btn-share");
    return;
  }
  DATA = parseDashboardJson(json);
  LP = DATA.linepack || {};
  LP_HIST = DATA.linepackHistory || {};
  LP_ROWS = DATA.linepackHistoryRows || [];
  ZONE_SERIES = DATA.zoneSeries || {};
  GROUP_SERIES = DATA.groupSeries || {};
  applyMagoQuery();
  if (granularity === "state" && !selectedGroups.size) selectedGroups = new Set(["total"]);
  if (granularity === "zone" && !selectedZones.size) {
    selectedZones = new Set((DATA.zones || []).slice(0, 5));
  }
  paintPage();
  writeMagoQuery();

  document.getElementById("btn-select-zones").addEventListener("click", selectAllMago);
  document.getElementById("btn-clear-zones").addEventListener("click", clearMagoSelections);
  document.querySelectorAll("[data-gran]").forEach(btn => {
    btn.addEventListener("click", () => {
      granularity = btn.getAttribute("data-gran") || "state";
      syncGranularityUi();
      packZones();
      writeMagoQuery();
    });
  });
  document.querySelectorAll("[data-mode]").forEach(btn => {
    btn.addEventListener("click", () => {
      chartMode = btn.getAttribute("data-mode") || "line";
      syncGranularityUi();
      packZones();
      writeMagoQuery();
    });
  });
  document.getElementById("btn-lp-csv").addEventListener("click", downloadLpCsv);
  document.querySelectorAll("#lp-table th[data-col]").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.getAttribute("data-col");
      if (lpSort.col === col) lpSort.dir *= -1;
      else { lpSort.col = col; lpSort.dir = col === "observedAt" ? -1 : 1; }
      renderLpTable();
    });
  });

  initThemeToggle("theme-toggle", () => { packLinepack(); packLinepackHistory(); packZones(); });
  initLangToggle("lang-toggle", () => {
    renderFilters();
    setKpis();
    applyI18n();
  });
  initCrossLinks();
  gbCopyLink("btn-share");
  applyI18n();
  window.addEventListener("resize", () => { packLinepack(); packLinepackHistory(); packZones(); });
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path: Path | str = DEFAULT_OUT) -> Path:
    import data_kit as dk

    snap_param = None
    payload = load_payload(snapshot_at=snap_param)
    here = Path(__file__).resolve().parent
    _path, payload_href = dk.write_and_publish_artifact("mago", payload, here)
    if payload_href == "payload.json.gz":
        payload_href = "https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev/mago/payload.json.gz"
    kpi_lp = payload.get("kpiLinepackMm3")
    snap = payload.get("snapshotAt") or ""
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_LINEPACK="" if kpi_lp is None else f"{kpi_lp:.2f}",
        KPI_SNAPSHOT=snap,
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_TYPO_WEIGHT_CSS=kit.typo_weight_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_CSV=kit.JS_CSV_HELPERS,
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
        SHARED_CLEAR_SELECTION=kit.clear_selection_button_html("btn-clear-zones"),
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
