"""
Builds the single-file CCEE PLD dashboard from data/pld_daily.parquet
and, when present, data/pld_hourly.parquet.

Usage: python dashboard.py [output_path]  (default: index.html)

Embeds the last ~24 months of daily PLD by submarket (N / NE / SE / S),
the last ~31 days of hourly PLD, and daily peak / off-peak averages
derived from hourly (ANEEL-style ponta: hours 18–20 on weekdays).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402
import transforms as xf  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "pld_daily.parquet"
HOURLY_PARQUET_PATH = HERE / "data" / "pld_hourly.parquet"
DEFAULT_OUT = HERE / "index.html"

# Display order matches ONS subsystem convention (SE, S, NE, N).
SUBMARKET_ORDER = ["SE", "S", "NE", "N"]
SUBMARKET_LABELS = {
    "SE": "Southeast",
    "S": "South",
    "NE": "Northeast",
    "N": "North",
}
SUBMARKET_LABELS_PT = {
    "SE": "Sudeste",
    "S": "Sul",
    "NE": "Nordeste",
    "N": "Norte",
}

# Keep the embedded payload lean: last N months of daily points,
# plus a short hourly window (hourly charts are unreadable at 24 months).
EMBED_MONTHS = 24
EMBED_HOURLY_DAYS = 31


def _num_or_none(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(v), 2)


def _align_series(part: pd.Series, index: pd.Index) -> list:
    part = part[~part.index.duplicated(keep="last")]
    aligned = part.reindex(index)
    return [_num_or_none(v) for v in aligned.tolist()]


def _load_hourly_frame() -> pd.DataFrame | None:
    if not HOURLY_PARQUET_PATH.exists():
        return None
    hdf = pd.read_parquet(HOURLY_PARQUET_PATH)
    hdf["date"] = pd.to_datetime(hdf["date"], errors="coerce")
    hdf["hour"] = pd.to_numeric(hdf["hour"], errors="coerce")
    hdf = hdf.dropna(subset=["date", "hour", "submarket", "pld"])
    hdf["submarket"] = hdf["submarket"].astype(str).str.upper()
    hdf = hdf[hdf["submarket"].isin(SUBMARKET_ORDER)]
    hdf["hour"] = hdf["hour"].astype(int)
    hdf = hdf[(hdf["hour"] >= 0) & (hdf["hour"] <= 23)]
    return hdf if not hdf.empty else None


def _pack_hourly(hdf: pd.DataFrame) -> dict | None:
    last = hdf["date"].max()
    cutoff = last - pd.Timedelta(days=EMBED_HOURLY_DAYS - 1)
    embed = hdf[hdf["date"] >= cutoff].copy()
    if embed.empty:
        return None
    embed["ts"] = embed["date"] + pd.to_timedelta(embed["hour"], unit="h")
    times = sorted(embed["ts"].unique())
    time_index = pd.DatetimeIndex(times)
    time_labels = [ts.strftime("%Y-%m-%dT%H") for ts in time_index]
    series: dict[str, list] = {}
    latest: dict[str, float | None] = {}
    latest_time = time_labels[-1] if time_labels else None
    last_ts = time_index[-1]
    for sm in SUBMARKET_ORDER:
        part = embed[embed["submarket"] == sm].set_index("ts")["pld"]
        series[sm] = _align_series(part, time_index)
        on_last = embed[(embed["submarket"] == sm) & (embed["ts"] == last_ts)]
        if len(on_last):
            latest[sm] = _num_or_none(on_last["pld"].iloc[-1])
        elif not part.empty:
            latest[sm] = _num_or_none(part.iloc[-1])
        else:
            latest[sm] = None
    return {
        "times": time_labels,
        "series": series,
        "latest": latest,
        "latestTime": latest_time,
    }


def _pack_peak_offpeak(hdf: pd.DataFrame, daily_dates: list[str]) -> dict | None:
    last = hdf["date"].max()
    cutoff = last - pd.DateOffset(months=EMBED_MONTHS)
    embed = hdf[hdf["date"] >= cutoff].copy()
    if embed.empty:
        return None
    mask = xf.pld_peak_mask(embed["date"], embed["hour"])
    peak = (
        embed[mask]
        .groupby(["date", "submarket"], as_index=False)["pld"]
        .mean()
    )
    off = (
        embed[~mask]
        .groupby(["date", "submarket"], as_index=False)["pld"]
        .mean()
    )
    # Prefer the daily embed's dates when they overlap so the two views
    # share an axis; otherwise use whatever hourly coverage we have.
    peak_dates = sorted(embed["date"].dt.strftime("%Y-%m-%d").unique())
    if daily_dates:
        overlap = [d for d in daily_dates if d in set(peak_dates)]
        dates = overlap or peak_dates
    else:
        dates = peak_dates
    date_index = pd.DatetimeIndex(pd.to_datetime(dates))
    peak_series: dict[str, list] = {}
    off_series: dict[str, list] = {}
    latest_peak: dict[str, float | None] = {}
    latest_off: dict[str, float | None] = {}
    for sm in SUBMARKET_ORDER:
        p = peak[peak["submarket"] == sm].set_index("date")["pld"]
        o = off[off["submarket"] == sm].set_index("date")["pld"]
        peak_series[sm] = _align_series(p, date_index)
        off_series[sm] = _align_series(o, date_index)
        latest_peak[sm] = next((v for v in reversed(peak_series[sm]) if v is not None), None)
        latest_off[sm] = next((v for v in reversed(off_series[sm]) if v is not None), None)
    return {
        "dates": dates,
        "peak": peak_series,
        "offPeak": off_series,
        "latestPeak": latest_peak,
        "latestOffPeak": latest_off,
        "peakHours": list(xf.PLD_PEAK_HOURS),
        "peakWeekdays": list(xf.PLD_PEAK_WEEKDAYS),
        "touVersion": xf.PLD_TOU["version"],
    }


def load_payload() -> dict:
    if not PARQUET_PATH.exists():
        raise RuntimeError(
            f"Missing {PARQUET_PATH} — run make_mock.py or pld_pipeline.py build first"
        )
    df = pd.read_parquet(PARQUET_PATH)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "submarket", "pld"])
    df["submarket"] = df["submarket"].astype(str).str.upper()
    df = df[df["submarket"].isin(SUBMARKET_ORDER)]
    if df.empty:
        raise RuntimeError("pld_daily.parquet has no usable rows")

    last = df["date"].max()
    cutoff = last - pd.DateOffset(months=EMBED_MONTHS)
    embed = df[df["date"] >= cutoff].copy()
    embed = embed.sort_values(["date", "submarket"])

    dates = sorted(embed["date"].dt.strftime("%Y-%m-%d").unique())
    date_index = pd.DatetimeIndex(pd.to_datetime(dates))

    series: dict[str, list] = {}
    for sm in SUBMARKET_ORDER:
        part = embed[embed["submarket"] == sm].set_index("date")["pld"]
        part = part[~part.index.duplicated(keep="last")]
        aligned = part.reindex(date_index)
        series[sm] = [
            None if (v is None or (isinstance(v, float) and pd.isna(v))) else round(float(v), 2)
            for v in aligned.tolist()
        ]

    # Latest non-null PLD per submarket (for KPI tiles + home teaser).
    latest: dict[str, float | None] = {}
    latest_date = last.strftime("%Y-%m-%d")
    for sm in SUBMARKET_ORDER:
        sm_df = df[df["submarket"] == sm].sort_values("date")
        if sm_df.empty:
            latest[sm] = None
            continue
        # Prefer the shared last date; else fall back to that submarket's own last.
        on_last = sm_df[sm_df["date"] == last]
        val = float(on_last["pld"].iloc[-1]) if len(on_last) else float(sm_df["pld"].iloc[-1])
        latest[sm] = round(val, 2)

    se_latest = latest.get("SE")
    _now_utc = dt.datetime.now(dt.timezone.utc)

    # Optional PLD × CMO × CVU join when ONS daily parquet is available.
    compare: dict | None = None
    ons_candidates = [
        HERE.parent / "ons" / "data" / "daily.parquet",
        HERE.parent / "lake" / "power" / "ons_daily.parquet",
    ]
    for ons_path in ons_candidates:
        if not ons_path.exists():
            continue
        try:
            sys.path.insert(0, str(HERE.parent / "shared"))
            import joins  # noqa: E402

            ons = pd.read_parquet(ons_path)
            joined = joins.join_pld_cmo_cvu(
                df[df["date"] >= cutoff],
                ons,
                date_from=cutoff,
                how="left",
            )
            # Keep only dates in the embed window; series keyed by submarket.
            joined = joined[joined["date"].isin(date_index)]
            by_sm: dict[str, dict[str, list]] = {}
            for sm in SUBMARKET_ORDER:
                part = joined[joined["submarket"] == sm].set_index("date")
                part = part[~part.index.duplicated(keep="last")].reindex(date_index)

                def _col(name: str) -> list:
                    if name not in part.columns:
                        return [None] * len(dates)
                    return [
                        None if (v is None or (isinstance(v, float) and pd.isna(v))) else round(float(v), 2)
                        for v in part[name].tolist()
                    ]

                by_sm[sm] = {
                    "pld": _col("pld"),
                    "cmo": _col("cmo"),
                    "cvu_gas_med": _col("cvu_gas_med"),
                }
            # Only expose if we got any CMO points.
            has_cmo = any(
                any(v is not None for v in by_sm[sm]["cmo"]) for sm in SUBMARKET_ORDER
            )
            if has_cmo:
                compare = {"dates": dates, "bySubmarket": by_sm}
            break
        except Exception as e:
            print(f"  note: PLD/CMO/CVU join skipped ({ons_path.name}): {e}")

    hourly_pack = None
    peak_pack = None
    hdf = _load_hourly_frame()
    if hdf is not None:
        try:
            hourly_pack = _pack_hourly(hdf)
            peak_pack = _pack_peak_offpeak(hdf, dates)
        except Exception as e:
            print(f"  note: hourly PLD pack skipped: {e}")

    return {
        "generated": _now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": _now_utc.isoformat(),
        "dates": dates,
        "submarkets": SUBMARKET_ORDER,
        "labels": SUBMARKET_LABELS,
        "labelsPt": SUBMARKET_LABELS_PT,
        "series": series,
        "latest": latest,
        "latestDate": latest_date,
        "kpiSe": se_latest,
        "compare": compare,
        "hourly": hourly_pack,
        "peakOffPeak": peak_pack,
        "source": "CCEE — PLD média diária / PLD horário",
        "note": "PLD is CCEE's settlement price (R$/MWh). It is not ONS CMO.",
    }


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PLD Prices — GasBrazil.com</title>
<meta name="description" content="CCEE daily-average and hourly PLD (Preço de Liquidação das Diferenças) by Brazilian electricity submarket — Southeast, South, Northeast, and North.">
<link rel="canonical" href="https://gasbrazil.com/pld/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py:
     generated: __GENERATED__
     kpi_se: __KPI_SE__
     latest_date: __LATEST_DATE__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; font-weight: 300; }
/* Single-row header: wordmark-menu · title … Wiki/About · PT · theme */
header.dash-head { display: flex; flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; width: auto; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; font-weight: 300; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }
.note-strip { font-size: 12.5px; color: var(--muted2); font-weight: 300; margin: 0 0 var(--gap); line-height: 1.45; max-width: 52em; }
.note-strip a { color: var(--accent); }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: var(--gap); }
@media (max-width: 720px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi-tile { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; }
.kpi-tile .k-label { font-size: 11px; font-weight: 400; color: var(--muted2); }
.kpi-tile .k-val { font-size: 20px; font-weight: 400; font-variant-numeric: tabular-nums; margin-top: 2px; letter-spacing: -.01em; }
.kpi-tile .k-unit { font-size: 11px; color: var(--muted); font-weight: 200; }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 0 0 12px; font-weight: 200; }
.chart-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.chart-controls label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; }
.chart-controls select { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; color: var(--text); font-size: 12.5px; font-family: var(--font); font-weight: 300; }
.sm-toggles { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.sm-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 4px 10px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 300; }
.sm-btn:hover { background: var(--accent-soft); }
.sm-btn.active { border-color: var(--border-strong); font-weight: 400; }
.sm-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.view-toggle { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
.view-btn { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; padding: 5px 12px; font-size: 12.5px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 300; }
.view-btn:hover { background: var(--accent-soft); }
.view-btn.active { border-color: var(--border-strong); font-weight: 400; background: var(--accent-soft); }
#chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; font-weight: 300; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); font-weight: 300; }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
/* Chart tooltip (.tt) styles live in shared/theme.css */
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 5px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); font-weight: 400; }
.toolbar button:hover { background: var(--accent-soft); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; font-weight: 200; }
.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 5px; overflow: auto; max-height: 55vh; margin-bottom: var(--gap); }
table.data { border-collapse: collapse; width: 100%; font-size: var(--table-font-size); font-weight: 300; table-layout: fixed; }
table.data th, table.data td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
table.data th { position: sticky; top: 0; background: var(--panel); color: var(--muted2); font-weight: 400; z-index: 2; }
table.data .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.data tbody tr:hover { background: var(--accent-soft); }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; font-weight: 200; }
footer a { color: var(--accent); }
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
  <a href="https://dadosabertos.ccee.org.br/dataset/pld_media_diaria" target="_blank" rel="noopener">CCEE daily<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  <a href="https://dadosabertos.ccee.org.br/dataset/pld_horario" target="_blank" rel="noopener">CCEE hourly<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>
<div class="kpi-row" id="kpi-row"></div>
<div class="chart-card">
  <div class="view-toggle" id="view-toggle" role="tablist" aria-label="PLD series"></div>
  <p class="panel-title" id="chart-title" data-i18n="pldChartTitle">Daily PLD by submarket</p>
  <p class="panel-note" id="chart-note"></p>
  <div class="chart-controls">
    <label for="f-preset" data-i18n="pldWindow">Window</label>
    <select id="f-preset">
      <option value="3m">3 months</option>
      <option value="6m">6 months</option>
      <option value="12m" selected>12 months</option>
      <option value="24m">24 months</option>
      <option value="all">All embedded</option>
    </select>
  </div>
  <div class="sm-toggles" id="sm-toggles"></div>
  <div id="chart-host"></div>
</div>
<div class="chart-card" id="compare-card" hidden>
  <p class="panel-title" data-i18n="pldCompareTitle">PLD vs CMO vs gas CVU</p>
  <div class="chart-controls">
    <label for="f-compare-sm">Submarket</label>
    <select id="f-compare-sm">
      <option value="SE" selected>SE</option>
      <option value="S">S</option>
      <option value="NE">NE</option>
      <option value="N">N</option>
    </select>
  </div>
  <div id="compare-host"></div>
  <div class="legend" id="compare-legend"></div>
</div>
<div class="toolbar">
  <button id="btn-csv" data-i18n="pldCsv">Download CSV</button>
  <button id="btn-xlsx" data-i18n="pldXlsx">Export all data (Excel)</button>
  __SHARED_SHARE_BUTTON__
  <span class="count" id="row-count"></span>
</div>
<div class="table-wrap">
  <table class="data" id="data-table">
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
  __SHARED_METHODOLOGY__
  &copy; <span id="year"></span> GasBrazil.com &middot;
  <span data-i18n="pldFooter">Data: CCEE (daily-average and hourly PLD). Not an official CCEE product.</span>
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

let DATA = null;
let visibleSm = new Set(["SE", "S", "NE", "N"]);
let viewMode = "daily"; // daily | hourly | peak
let datePreset = "12m";
let hourlyPreset = "7d";
let chartResizeTimer = null;
const DEFAULT_SORT = { col: "date", dir: -1 };
let tableSort = { ...DEFAULT_SORT };
let tableFilters = {};

function hasHourly() { return !!(DATA && DATA.hourly && (DATA.hourly.times || []).length); }
function hasPeak() { return !!(DATA && DATA.peakOffPeak && (DATA.peakOffPeak.dates || []).length); }

function smLabel(sm) {
  const pack = currentLang() === "pt" ? (DATA.labelsPt || {}) : (DATA.labels || {});
  return pack[sm] || sm;
}
function fmtNum(v, d) {
  if (v === null || v === undefined || !isFinite(v)) return "–";
  return v.toLocaleString(currentLang() === "pt" ? "pt-BR" : "en-US", {
    minimumFractionDigits: d, maximumFractionDigits: d
  });
}
function formatHourlyLabel(ts) {
  if (!ts) return "";
  if (ts.length >= 13 && ts.charAt(10) === "T") return ts.slice(0, 10) + " " + ts.slice(11, 13) + ":00";
  return ts;
}
function colorOf(sm) {
  const pal = chartPalette();
  const idx = (DATA.submarkets || []).indexOf(sm);
  return pal[idx >= 0 ? idx % pal.length : 0] || "var(--accent)";
}

function renderKpis() {
  const host = document.getElementById("kpi-row");
  host.innerHTML = "";
  (DATA.submarkets || []).forEach(sm => {
    const tile = document.createElement("div");
    tile.className = "kpi-tile";
    let v = DATA.latest ? DATA.latest[sm] : null;
    let unit = "R$/MWh · " + escapeHtml(DATA.latestDate || "");
    if (viewMode === "hourly" && hasHourly()) {
      v = DATA.hourly.latest ? DATA.hourly.latest[sm] : null;
      const ts = DATA.hourly.latestTime || "";
      unit = "R$/MWh · " + escapeHtml(formatHourlyLabel(ts));
    } else if (viewMode === "peak" && hasPeak()) {
      v = DATA.peakOffPeak.latestPeak ? DATA.peakOffPeak.latestPeak[sm] : null;
      const off = DATA.peakOffPeak.latestOffPeak ? DATA.peakOffPeak.latestOffPeak[sm] : null;
      unit = (currentLang() === "pt" ? "ponta" : "peak") + " · " +
        (currentLang() === "pt" ? "fora ponta " : "off-peak ") +
        (off == null ? "–" : fmtNum(off, 2));
    }
    tile.innerHTML =
      '<div class="k-label">' + escapeHtml(smLabel(sm)) + " (" + sm + ")</div>" +
      '<div class="k-val">' + (v == null ? "–" : fmtNum(v, 2)) + "</div>" +
      '<div class="k-unit">' + unit + "</div>";
    host.appendChild(tile);
  });
}

function buildViewToggle() {
  const host = document.getElementById("view-toggle");
  if (!host) return;
  const defs = [
    { id: "daily", key: "pldViewDaily", label: "Daily average" },
    { id: "hourly", key: "pldViewHourly", label: "Hourly", need: hasHourly() },
    { id: "peak", key: "pldViewPeak", label: "Peak / off-peak", need: hasPeak() },
  ];
  host.innerHTML = "";
  defs.forEach(d => {
    if (d.need === false) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "view-btn" + (viewMode === d.id ? " active" : "");
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", viewMode === d.id ? "true" : "false");
    btn.setAttribute("data-i18n", d.key);
    btn.textContent = t(d.key) || d.label;
    btn.addEventListener("click", () => {
      if (viewMode === d.id) return;
      viewMode = d.id;
      tableSort = { col: d.id === "hourly" ? "datetime" : "date", dir: -1 };
      tableFilters = {};
      paintChrome();
    });
    host.appendChild(btn);
  });
}

function dailyWindowOptions() {
  const pt = currentLang() === "pt";
  return [
    ["3m", pt ? "3 meses" : "3 months"],
    ["6m", pt ? "6 meses" : "6 months"],
    ["12m", pt ? "12 meses" : "12 months"],
    ["24m", pt ? "24 meses" : "24 months"],
    ["all", pt ? "Tudo embutido" : "All embedded"],
  ];
}
function hourlyWindowOptions() {
  const pt = currentLang() === "pt";
  return [
    ["1d", pt ? "1 dia" : "1 day"],
    ["3d", pt ? "3 dias" : "3 days"],
    ["7d", pt ? "7 dias" : "7 days"],
    ["14d", pt ? "14 dias" : "14 days"],
    ["30d", pt ? "30 dias" : "30 days"],
  ];
}
function syncWindowSelect() {
  const sel = document.getElementById("f-preset");
  if (!sel) return;
  const opts = viewMode === "hourly" ? hourlyWindowOptions() : dailyWindowOptions();
  const cur = viewMode === "hourly" ? hourlyPreset : datePreset;
  sel.innerHTML = opts.map(([v, l]) => '<option value="' + v + '">' + l + "</option>").join("");
  if (opts.some(o => o[0] === cur)) sel.value = cur;
  else sel.value = viewMode === "hourly" ? "7d" : "12m";
}
function syncChartChrome() {
  const title = document.getElementById("chart-title");
  const note = document.getElementById("chart-note");
  const titleKey = viewMode === "hourly" ? "pldChartTitleHourly"
    : viewMode === "peak" ? "pldChartTitlePeak" : "pldChartTitle";
  if (title) {
    title.setAttribute("data-i18n", titleKey);
    title.textContent = t(titleKey);
  }
  if (note) {
    if (viewMode === "peak" && hasPeak()) {
      note.hidden = false;
      note.setAttribute("data-i18n", "pldPeakNote");
      note.textContent = t("pldPeakNote");
    } else if (viewMode === "hourly") {
      note.hidden = false;
      note.setAttribute("data-i18n", "pldHourlyNote");
      note.textContent = t("pldHourlyNote");
    } else {
      note.hidden = true;
      note.textContent = "";
    }
  }
}

function buildSmToggles() {
  const host = document.getElementById("sm-toggles");
  host.innerHTML = "";
  (DATA.submarkets || []).forEach(sm => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sm-btn" + (visibleSm.has(sm) ? " active" : "");
    btn.innerHTML = '<span class="sw" style="background:' + colorOf(sm) + '"></span>' +
      escapeHtml(smLabel(sm));
    btn.addEventListener("click", () => {
      if (visibleSm.has(sm)) {
        if (visibleSm.size > 1) visibleSm.delete(sm);
      } else visibleSm.add(sm);
      buildSmToggles();
      renderChart();
      writePldQuery();
    });
    host.appendChild(btn);
  });
}

function windowStartIso() {
  const dates = DATA.dates || [];
  if (!dates.length) return null;
  if (datePreset === "all") return dates[0];
  const last = dates[dates.length - 1];
  const months = { "3m": 3, "6m": 6, "12m": 12, "24m": 24 }[datePreset] || 12;
  const end = new Date(last + "T00:00:00Z");
  end.setUTCMonth(end.getUTCMonth() - months);
  const iso = end.toISOString().slice(0, 10);
  return iso < dates[0] ? dates[0] : iso;
}
function peakDates() {
  return (DATA.peakOffPeak && DATA.peakOffPeak.dates) || DATA.dates || [];
}
function peakWindowStartIso() {
  const dates = peakDates();
  if (!dates.length) return null;
  if (datePreset === "all") return dates[0];
  const last = dates[dates.length - 1];
  const months = { "3m": 3, "6m": 6, "12m": 12, "24m": 24 }[datePreset] || 12;
  const end = new Date(last + "T00:00:00Z");
  end.setUTCMonth(end.getUTCMonth() - months);
  const iso = end.toISOString().slice(0, 10);
  return iso < dates[0] ? dates[0] : iso;
}
function hourlyWindowStartTs() {
  const times = (DATA.hourly && DATA.hourly.times) || [];
  if (!times.length) return null;
  const days = { "1d": 1, "3d": 3, "7d": 7, "14d": 14, "30d": 30 }[hourlyPreset] || 7;
  const n = days * 24;
  if (times.length <= n) return times[0];
  return times[times.length - n];
}

function chartNiceTicks(lo, hi, n) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const norm = raw / mag, step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(v);
  return out;
}
const CHART_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const CHART_MON_PT = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
function chartAxisLabel(iso, spanDays) {
  const p = iso.split("-");
  const mon = (currentLang() === "pt" ? CHART_MON_PT : CHART_MON)[+p[1] - 1];
  return spanDays > 200 ? mon + " '" + p[0].slice(2) : p[2] + " " + mon;
}
function chartAxisLabelHourly(ts, spanDays) {
  if (!ts || ts.length < 13) return ts || "";
  if (spanDays <= 2) return ts.slice(11, 13) + ":00";
  return chartAxisLabel(ts.slice(0, 10), spanDays);
}
function tsToUtcMs(ts) {
  if (!ts || ts.length < 13) return NaN;
  return Date.UTC(+ts.slice(0, 4), +ts.slice(5, 7) - 1, +ts.slice(8, 10), +ts.slice(11, 13));
}

function collectChartSeries() {
  const sms = (DATA.submarkets || []).filter(sm => visibleSm.has(sm));
  if (viewMode === "hourly" && hasHourly()) {
    const times = DATA.hourly.times || [];
    const start = hourlyWindowStartTs();
    const win = start ? times.filter(t => t >= start) : times.slice();
    const seriesList = [];
    sms.forEach(sm => {
      const arr = (DATA.hourly.series && DATA.hourly.series[sm]) || [];
      const pts = [];
      win.forEach(t => {
        const i = times.indexOf(t);
        const v = i >= 0 ? arr[i] : null;
        if (v !== null && v !== undefined && isFinite(v)) pts.push({ date: t, v });
      });
      if (pts.length) seriesList.push({ sm, label: smLabel(sm), pts, dashed: false });
    });
    return { winKeys: win, seriesList, hourly: true };
  }
  if (viewMode === "peak" && hasPeak()) {
    const dates = peakDates();
    const start = peakWindowStartIso();
    const win = start ? dates.filter(d => d >= start) : dates.slice();
    const peakLab = currentLang() === "pt" ? " ponta" : " peak";
    const offLab = currentLang() === "pt" ? " fora ponta" : " off-peak";
    const seriesList = [];
    sms.forEach(sm => {
      const pArr = (DATA.peakOffPeak.peak && DATA.peakOffPeak.peak[sm]) || [];
      const oArr = (DATA.peakOffPeak.offPeak && DATA.peakOffPeak.offPeak[sm]) || [];
      const pPts = [], oPts = [];
      win.forEach(d => {
        const i = dates.indexOf(d);
        const pv = i >= 0 ? pArr[i] : null;
        const ov = i >= 0 ? oArr[i] : null;
        if (pv !== null && pv !== undefined && isFinite(pv)) pPts.push({ date: d, v: pv });
        if (ov !== null && ov !== undefined && isFinite(ov)) oPts.push({ date: d, v: ov });
      });
      if (pPts.length) seriesList.push({ sm, label: smLabel(sm) + peakLab, pts: pPts, dashed: false });
      if (oPts.length) seriesList.push({ sm, label: smLabel(sm) + offLab, pts: oPts, dashed: true });
    });
    return { winKeys: win, seriesList, hourly: false };
  }
  const dates = DATA.dates || [];
  const start = windowStartIso();
  const win = start ? dates.filter(d => d >= start) : dates.slice();
  const seriesList = sms.map(sm => {
    const arr = DATA.series[sm] || [];
    const pts = [];
    win.forEach(d => {
      const i = dates.indexOf(d);
      const v = i >= 0 ? arr[i] : null;
      if (v !== null && v !== undefined && isFinite(v)) pts.push({ date: d, v });
    });
    return { sm, label: smLabel(sm), pts, dashed: false };
  }).filter(s => s.pts.length);
  return { winKeys: win, seriesList, hourly: false };
}

function renderChart() {
  const host = document.getElementById("chart-host");
  host.innerHTML = "";
  const packed = collectChartSeries();
  const winDates = packed.winKeys;
  const seriesList = packed.seriesList;
  if (!winDates.length || !seriesList.length) {
    host.innerHTML = '<div class="chart-empty">No data in this window.</div>';
    return;
  }
  const dNum = packed.hourly
    ? ts => tsToUtcMs(ts)
    : iso => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const minD = dNum(winDates[0]), maxD = dNum(winDates[winDates.length - 1]);
  const spanDays = Math.max(1, (maxD - minD) / 86400000);

  let lo = Infinity, hi = -Infinity;
  seriesList.forEach(s => s.pts.forEach(p => { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); }));
  if (lo > 0 && lo / hi <= 0.55) lo = 0;
  const pad = (hi - lo) * 0.08 || 1; hi += pad; if (lo > 0) lo = Math.max(0, lo - pad);

  const W = Math.max(640, host.clientWidth || 640), H = 340, ML = 56, MR = 16, MT = 18, MB = 32;
  const x = iso => ML + (W - ML - MR) * (maxD === minD ? 0.5 : (dNum(iso) - minD) / (maxD - minD));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo || 1));

  const aria = viewMode === "hourly" ? "Hourly PLD by submarket"
    : viewMode === "peak" ? "Peak and off-peak PLD by submarket"
    : "Daily PLD by submarket";
  const svg = chartSvgEl("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img",
    "aria-label": aria });
  svg.style.width = "100%"; svg.style.height = H + "px";

  chartNiceTicks(lo, hi, 5).forEach(t => {
    svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(t), y2: y(t), stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvgEl("text", { x: ML - 8, y: y(t) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
    lb.textContent = fmtNum(t, 0); lb.style.fontVariantNumeric = "tabular-nums"; svg.appendChild(lb);
  });

  const nT = Math.min(8, winDates.length);
  for (let i = 0; i < nT; i++) {
    const di = winDates[Math.round(i * (winDates.length - 1) / Math.max(1, nT - 1))];
    const t = chartSvgEl("text", { x: x(di), y: H - 9, fill: "var(--muted)", "font-size": 11,
      "text-anchor": i === 0 ? "start" : (i === nT - 1 ? "end" : "middle") });
    t.textContent = packed.hourly ? chartAxisLabelHourly(di, spanDays) : chartAxisLabel(di, spanDays);
    svg.appendChild(t);
  }

  seriesList.forEach(s => {
    let d = "";
    s.pts.forEach((p, i) => { d += (i === 0 ? "M" : "L") + x(p.date).toFixed(1) + " " + y(p.v).toFixed(1) + " "; });
    const attrs = { d, fill: "none", stroke: colorOf(s.sm), "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" };
    if (s.dashed) attrs["stroke-dasharray"] = "5 4";
    svg.appendChild(chartSvgEl("path", attrs));
  });

  const cross = chartSvgEl("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--border-strong)", "stroke-width": 1, opacity: 0 });
  svg.appendChild(cross);
  const dots = chartSvgEl("g", { opacity: 0 });
  svg.appendChild(dots);
  const hit = chartSvgEl("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(hit);

  const tt = document.getElementById("chart-tt");
  function nearestDateAt(px) {
    let nearest = winDates[0], best = Infinity;
    for (const d of winDates) {
      const dist = Math.abs(x(d) - px);
      if (dist < best) { best = dist; nearest = d; }
    }
    return nearest;
  }
  function showTooltip(date, clientX, clientY) {
    cross.setAttribute("x1", x(date)); cross.setAttribute("x2", x(date)); cross.setAttribute("opacity", 1);
    dots.innerHTML = ""; dots.setAttribute("opacity", 1);
    let rows = "";
    seriesList.forEach(s => {
      const p = s.pts.find(pt => pt.date === date);
      if (!p) return;
      dots.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.v), r: 4, fill: colorOf(s.sm),
        stroke: "var(--panel)", "stroke-width": 2 }));
      rows += '<tr><td><span class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' +
        colorOf(s.sm) + '"></span> ' + escapeHtml(s.label) +
        '</td><td class="v">' + fmtNum(p.v, 2) + '</td></tr>';
    });
    const head = packed.hourly ? formatHourlyLabel(date) : date;
    tt.innerHTML = '<div class="d">' + escapeHtml(head) + '</div><table>' + rows + '</table>';
    placeChartTooltip(tt, clientX, clientY);
  }
  function hideTooltip() {
    tt.style.display = "none"; cross.setAttribute("opacity", 0); dots.setAttribute("opacity", 0);
  }
  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width * W;
    showTooltip(nearestDateAt(px), ev.clientX, ev.clientY);
  });
  hit.addEventListener("pointerleave", hideTooltip);

  host.appendChild(svg);
  const lg = document.createElement("div");
  lg.className = "legend";
  seriesList.forEach(s => {
    const span = document.createElement("span");
    const swStyle = "background:" + colorOf(s.sm) + (s.dashed ? ";outline:1px dashed " + colorOf(s.sm) + ";outline-offset:1px" : "");
    span.innerHTML = '<span class="sw" style="' + swStyle + '"></span>' + escapeHtml(s.label);
    lg.appendChild(span);
  });
  host.appendChild(lg);
}

function tableRows() {
  if (viewMode === "hourly" && hasHourly()) {
    const times = DATA.hourly.times || [];
    const start = hourlyWindowStartTs();
    const rows = [];
    times.forEach((t, i) => {
      if (start && t < start) return;
      const row = { datetime: formatHourlyLabel(t), date: t.slice(0, 10), hour: t.slice(11, 13) };
      let any = false;
      (DATA.submarkets || []).forEach(sm => {
        const v = (DATA.hourly.series[sm] || [])[i];
        row[sm] = v;
        if (v !== null && v !== undefined) any = true;
      });
      if (any) rows.push(row);
    });
    return rows;
  }
  if (viewMode === "peak" && hasPeak()) {
    const dates = peakDates();
    const start = peakWindowStartIso();
    const rows = [];
    dates.forEach((d, i) => {
      if (start && d < start) return;
      const row = { date: d };
      let any = false;
      (DATA.submarkets || []).forEach(sm => {
        const pv = (DATA.peakOffPeak.peak[sm] || [])[i];
        const ov = (DATA.peakOffPeak.offPeak[sm] || [])[i];
        row[sm + "_peak"] = pv;
        row[sm + "_off"] = ov;
        if (pv != null || ov != null) any = true;
      });
      if (any) rows.push(row);
    });
    return rows;
  }
  const dates = DATA.dates || [];
  const start = windowStartIso();
  const rows = [];
  dates.forEach((d, i) => {
    if (start && d < start) return;
    const row = { date: d };
    let any = false;
    (DATA.submarkets || []).forEach(sm => {
      const v = (DATA.series[sm] || [])[i];
      row[sm] = v;
      if (v !== null && v !== undefined) any = true;
    });
    if (any) rows.push(row);
  });
  return rows;
}

function tableColumns() {
  const pt = currentLang() === "pt";
  if (viewMode === "hourly" && hasHourly()) {
    return [
      { key: "datetime", label: pt ? "Data e hora" : "Datetime" },
      ...DATA.submarkets.map(sm => ({ key: sm, label: smLabel(sm) + " (R$/MWh)" })),
    ];
  }
  if (viewMode === "peak" && hasPeak()) {
    const peak = pt ? " ponta" : " peak";
    const off = pt ? " fora ponta" : " off-peak";
    return [
      { key: "date", label: pt ? "Data" : "Date" },
      ...DATA.submarkets.flatMap(sm => ([
        { key: sm + "_peak", label: smLabel(sm) + peak },
        { key: sm + "_off", label: smLabel(sm) + off },
      ])),
    ];
  }
  return [
    { key: "date", label: pt ? "Data" : "Date" },
    ...DATA.submarkets.map(sm => ({ key: sm, label: smLabel(sm) + " (R$/MWh)" })),
  ];
}
const CHART_NS = "http://www.w3.org/2000/svg";
function chartSvgEl(n, a) {
  const e = document.createElementNS(CHART_NS, n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}

function renderTable(sortState, filters) {
  const defaultSort = { col: viewMode === "hourly" ? "datetime" : "date", dir: -1 };
  tableSort = sortState || tableSort;
  if (!tableColumns().some(c => c.key === tableSort.col)) tableSort = { ...defaultSort };
  tableFilters = filters || tableFilters;
  const hostHead = document.getElementById("thead-row");
  const hostBody = document.getElementById("tbody");
  const cols = tableColumns();
  withFocusPreserved(hostHead.parentElement, () => {
    hostHead.innerHTML = "";
    cols.forEach(col => {
      const isText = col.key === "date" || col.key === "datetime";
      hostHead.appendChild(buildSortFilterTh(col, tableSort, defaultSort, tableFilters, renderTable,
        isText ? "" : "num"));
    });
  });

  let rows = tableRows();
  rows = rows.filter(r => {
    return cols.every(col => {
      const q = tableFilters[col.key];
      if (!q) return true;
      const v = r[col.key];
      return String(v == null ? "" : v).toLowerCase().includes(q);
    });
  });
  rows.sort((a, b) => {
    const ca = a[tableSort.col], cb = b[tableSort.col];
    if (ca == null && cb == null) return 0;
    if (ca == null) return 1;
    if (cb == null) return -1;
    if (typeof ca === "number" && typeof cb === "number") return (ca - cb) * tableSort.dir;
    return String(ca).localeCompare(String(cb)) * tableSort.dir;
  });

  hostBody.innerHTML = "";
  const frag = document.createDocumentFragment();
  rows.forEach(r => {
    const tr = document.createElement("tr");
    let html = "";
    cols.forEach(col => {
      const v = r[col.key];
      const isText = col.key === "date" || col.key === "datetime";
      html += isText
        ? "<td>" + escapeHtml(v == null ? "" : String(v)) + "</td>"
        : '<td class="num">' + (v == null ? "" : fmtNum(v, 2)) + "</td>";
    });
    tr.innerHTML = html;
    frag.appendChild(tr);
  });
  hostBody.appendChild(frag);
  const pt = currentLang() === "pt";
  const unit = viewMode === "hourly" ? (pt ? " horas" : " hours") : (pt ? " dias" : " days");
  document.getElementById("row-count").textContent = rows.length.toLocaleString() + unit;
}

function exportColumns() {
  if (viewMode === "hourly" && hasHourly()) {
    return {
      keys: ["datetime", ...DATA.submarkets],
      header: ["datetime", ...DATA.submarkets.map(sm => "pld_" + sm.toLowerCase() + "_rs_mwh")],
      filename: "pld_hourly",
      sheet: "PLD hourly",
    };
  }
  if (viewMode === "peak" && hasPeak()) {
    const keys = ["date", ...DATA.submarkets.flatMap(sm => [sm + "_peak", sm + "_off"])];
    const header = ["date", ...DATA.submarkets.flatMap(sm => [
      "pld_" + sm.toLowerCase() + "_peak_rs_mwh",
      "pld_" + sm.toLowerCase() + "_offpeak_rs_mwh",
    ])];
    return { keys, header, filename: "pld_peak_offpeak", sheet: "PLD peak off-peak" };
  }
  return {
    keys: ["date", ...DATA.submarkets],
    header: ["date", ...DATA.submarkets.map(sm => "pld_" + sm.toLowerCase() + "_rs_mwh")],
    filename: "pld_daily",
    sheet: "PLD daily",
  };
}

function downloadCsv() {
  const spec = exportColumns();
  const lines = [spec.header.map(csvEscape).join(",")];
  tableRows().forEach(r => {
    lines.push(spec.keys.map(c => csvEscape(r[c] == null ? "" : r[c])).join(","));
  });
  downloadTextFile(lines.join("\\n"), "text/csv;charset=utf-8", spec.filename + ".csv");
}

async function downloadXlsx() {
  const spec = exportColumns();
  const rows = [spec.header];
  tableRows().forEach(r => {
    rows.push(spec.keys.map(c => r[c] == null ? "" : r[c]));
  });
  const blob = await buildWorkbookXlsxBlob([{ name: spec.sheet, rows }]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = spec.filename + ".xlsx";
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function paintChrome() {
  buildViewToggle();
  syncWindowSelect();
  syncChartChrome();
  renderKpis();
  buildSmToggles();
  renderChart();
  renderCompare();
  renderTable(tableSort, tableFilters);
  writePldQuery();
}

// Shareable view state: visible submarkets, date window, compare submarket, series view.
function applyPldQuery() {
  const sp = gbQueryParams();
  const sms = gbValidList(sp.get("sm"), DATA.submarkets || []);
  if (sms && sms.length) visibleSm = new Set(sms);
  const allowedViews = ["daily"];
  if (hasHourly()) allowedViews.push("hourly");
  if (hasPeak()) allowedViews.push("peak");
  viewMode = gbValidEnum(sp.get("view"), allowedViews) || viewMode;
  if (viewMode === "hourly") {
    hourlyPreset = gbValidEnum(sp.get("window"), ["1d", "3d", "7d", "14d", "30d"]) || hourlyPreset;
  } else {
    datePreset = gbValidEnum(sp.get("window"), ["3m", "6m", "12m", "24m", "all"]) || datePreset;
  }
  const csm = gbValidEnum(sp.get("csm"), DATA.submarkets || []);
  if (csm) {
    const sel = document.getElementById("f-compare-sm");
    if (sel) sel.value = csm;
  }
}
function writePldQuery() {
  if (!DATA) return;
  const cmpSm = (document.getElementById("f-compare-sm") || {}).value || null;
  gbWriteQuery({
    sm: [...visibleSm],
    window: viewMode === "hourly" ? hourlyPreset : datePreset,
    view: viewMode,
    csm: cmpSm,
  });
}

function renderCompare() {
  const card = document.getElementById("compare-card");
  const host = document.getElementById("compare-host");
  const legend = document.getElementById("compare-legend");
  if (!card || !host) return;
  const cmp = DATA && DATA.compare;
  if (!cmp || !cmp.bySubmarket) { card.hidden = true; return; }
  card.hidden = false;
  const sm = (document.getElementById("f-compare-sm") || {}).value || "SE";
  const block = cmp.bySubmarket[sm] || {};
  const dates = cmp.dates || [];
  const pal = chartPalette();
  const series = [
    { key: "pld", label: "PLD", color: pal[0] || "#002776", pts: dates.map((d,i) => ({ d, v: (block.pld||[])[i] })) },
    { key: "cmo", label: "CMO", color: pal[1] || "#4a5568", pts: dates.map((d,i) => ({ d, v: (block.cmo||[])[i] })) },
    { key: "cvu", label: "CVU gas med", color: pal[2] || "#2f6fed", pts: dates.map((d,i) => ({ d, v: (block.cvu_gas_med||[])[i] })) },
  ].filter(s => s.pts.some(p => p.v != null));
  host.innerHTML = ""; legend.innerHTML = "";
  if (!series.length) { host.innerHTML = '<div class="chart-empty">No CMO/CVU overlap for this window.</div>'; return; }
  let lo = Infinity, hi = -Infinity;
  series.forEach(s => s.pts.forEach(p => { if (p.v != null) { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); } }));
  if (lo > 0 && lo / hi <= 0.35) lo = 0;
  const pad = (hi - lo) * 0.08 || 1; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = 300, ML = 52, MR = 12, MT = 18, MB = 28;
  const NS = "http://www.w3.org/2000/svg";
  function el(n,a){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}
  const dNum = d => Date.parse(d + "T00:00:00Z");
  const minD = dNum(dates[0]), maxD = dNum(dates[dates.length-1]);
  const x = d => ML + (W-ML-MR) * (maxD===minD ? 0.5 : (dNum(d)-minD)/(maxD-minD));
  const y = v => MT + (H-MT-MB) * (1 - (v-lo)/(hi-lo));
  const svg = el("svg", { viewBox: "0 0 "+W+" "+H, width: W, height: H });
  series.forEach(s => {
    let path = "", started = false;
    s.pts.forEach(p => {
      if (p.v == null) { started = false; return; }
      path += (started ? "L" : "M") + x(p.d).toFixed(1) + " " + y(p.v).toFixed(1) + " ";
      started = true;
    });
    if (path) svg.appendChild(el("path", { d: path.trim(), fill: "none", stroke: s.color, "stroke-width": 2 }));
    const span = document.createElement("span");
    span.innerHTML = '<span class="sw" style="background:'+s.color+'"></span>' + s.label;
    legend.appendChild(span);
  });
  host.appendChild(svg);
}

__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__
__SHARED_JS_QUERY_STATE__

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const text = await inflateGzipUrl(PAYLOAD_URL);
  DATA = JSON.parse(text);

  document.getElementById("asof-through").textContent = DATA.latestDate || "—";
  initStalenessBadgeFor("pld", DATA.latestDate);
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated);

  applyPldQuery();
  syncWindowSelect();

  document.getElementById("f-preset").addEventListener("change", e => {
    if (viewMode === "hourly") hourlyPreset = e.target.value;
    else datePreset = e.target.value;
    paintChrome();
  });
  const cmpSm = document.getElementById("f-compare-sm");
  if (cmpSm) cmpSm.addEventListener("change", () => { renderCompare(); writePldQuery(); });
  document.getElementById("btn-csv").addEventListener("click", downloadCsv);
  document.getElementById("btn-xlsx").addEventListener("click", downloadXlsx);
  window.addEventListener("resize", () => {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(() => { renderChart(); renderCompare(); }, 140);
  });
  initThemeToggle("theme-toggle", () => { renderChart(); renderCompare(); });
  initLangToggle("lang-toggle", () => { paintChrome(); });
  initCrossLinks();
  gbCopyLink("btn-share");
  paintChrome();
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
    payload_path, payload_href = dk.write_and_publish_artifact("pld", payload, here)
    kpi_se = payload["kpiSe"]
    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_SE="" if kpi_se is None else f"{kpi_se:.2f}",
        LATEST_DATE=payload["latestDate"] or "",
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
        SHARED_SITE_LINKS_JS=kit.site_links_js("pld"),
        SHARED_MASTHEAD=kit.masthead_html("pld"),
        SHARED_METHODOLOGY=kit.methodology_html("pld"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    n_dates = len(payload["dates"])
    n_hourly = len((payload.get("hourly") or {}).get("times") or [])
    print(
        f"Wrote dashboard shell ({len(html):,} bytes) + {payload_path.name} "
        f"({payload_path.stat().st_size:,} bytes, {n_dates} days × "
        f"{len(payload['submarkets'])} submarkets"
        + (f", {n_hourly} hourly stamps" if n_hourly else "")
        + f") → {payload_href}"
    )
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
