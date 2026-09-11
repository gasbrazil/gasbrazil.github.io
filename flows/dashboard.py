"""
Builds the Pipeline Flows dashboard from data/flows_points.parquet and
data/flows_ledger.parquet.

Usage: python dashboard.py [output_path]  (default: index.html)

ADR-002 Track B: the large series payload is written to payload.json.gz
beside index.html; the HTML shell fetches and gunzips it at runtime
(hub teaser markers remain in the HTML comment).
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit  # noqa: E402  (must follow sys.path.insert)

HERE = Path(__file__).parent
POINTS_PARQUET = HERE / "data" / "flows_points.parquet"
LEDGER_PARQUET = HERE / "data" / "flows_ledger.parquet"
DEFAULT_OUT = HERE / "index.html"

# Display order + unit shown on the chart axis / table header. Keys must
# match flows_pipeline.py's *_VARIABLES_EN values exactly.
#
# Average Pressure is included for depth: the UI aggregates it with mean
# (like Allocation), matching the pipeline's median-across-shipper store.
POINT_VAR_ORDER = [
    ("Actual Volume (thousand m3)", "thousand m3/d"),
    ("Scheduled Volume (thousand m3)", "thousand m3/d"),
    ("Requested Volume (thousand m3)", "thousand m3/d"),
    ("Allocation (%)", "%"),
    ("Average Pressure (kgf/cm2)", "kgf/cm2"),
]
LEDGER_VAR_ORDER = [
    ("System Use Gas (thousand m3)", "thousand m3/d"),
    ("Unaccounted-for Gas (thousand m3)", "thousand m3/d"),
    ("Operational Losses (thousand m3)", "thousand m3/d"),
    ("Extraordinary Losses (thousand m3)", "thousand m3/d"),
    ("Daily Imbalance (thousand m3)", "thousand m3/d"),
    ("Accumulated Daily Imbalance (thousand m3)", "thousand m3"),
    ("Line Pack (thousand m3)", "thousand m3"),
]

# Primary transporters shown by default in the UI. TSB/GOM stay in the
# payload; the page exposes them behind an "Include TSB & GOM" toggle.
TSO_ORDER = ["NTS", "TAG", "TBG"]
MINOR_TSOS = ["TSB", "GOM"]

# Keep the dense daily grid lean: last N months (UI defaults to 12 months).
EMBED_MONTHS = 24


def _short_label(full_label: str) -> str:
    """'Actual Volume (thousand m3)' -> 'Actual Volume'."""
    return full_label.split(" (")[0]


def _pivot_series(df: pd.DataFrame, id_col: str, dates: list[str]) -> dict:
    """variable -> {id: [values aligned to `dates`, None where missing]}."""
    out = {}
    date_index = pd.DatetimeIndex(dates)
    mean_vars = {"Allocation (%)", "Average Pressure (kgf/cm2)"}
    for variable, group in df.groupby("variable", observed=True):
        agg = "mean" if variable in mean_vars else "sum"
        wide = group.pivot_table(index=id_col, columns="date", values="value", aggfunc=agg)
        wide = wide.reindex(columns=date_index)
        series = {}
        for row_id, row in wide.iterrows():
            vals = row.tolist()
            # Skip an id with literally nothing for this variable (shouldn't
            # happen given how the pipeline builds these tables, but cheap
            # to guard so a payload never carries an all-null array).
            if all(v is None or (isinstance(v, float) and pd.isna(v)) for v in vals):
                continue
            series[str(row_id)] = [None if (v is None or (isinstance(v, float) and pd.isna(v))) else round(float(v), 2) for v in vals]
        out[variable] = series
    return out


def load_payload() -> dict:
    points_df = pd.read_parquet(POINTS_PARQUET) if POINTS_PARQUET.exists() else pd.DataFrame()
    ledger_df = pd.read_parquet(LEDGER_PARQUET) if LEDGER_PARQUET.exists() else pd.DataFrame()

    # TSB and GOM stay in the payload; the UI defaults to NTS/TAG/TBG and
    # exposes an "Include TSB & GOM" toggle (see MINOR_TSOS / PRIMARY in JS).

    all_dates = pd.concat([
        points_df["date"] if len(points_df) else pd.Series(dtype="datetime64[ns]"),
        ledger_df["date"] if len(ledger_df) else pd.Series(dtype="datetime64[ns]"),
    ])
    if all_dates.empty:
        raise RuntimeError("No data in either parquet store -- run flows_pipeline.py first")
    cutoff = all_dates.max() - pd.DateOffset(months=EMBED_MONTHS)
    if len(points_df):
        points_df = points_df[points_df["date"] >= cutoff]
    if len(ledger_df):
        ledger_df = ledger_df[ledger_df["date"] >= cutoff]
    all_dates = pd.concat([
        points_df["date"] if len(points_df) else pd.Series(dtype="datetime64[ns]"),
        ledger_df["date"] if len(ledger_df) else pd.Series(dtype="datetime64[ns]"),
    ])
    if all_dates.empty:
        raise RuntimeError("No data in the embed window -- widen EMBED_MONTHS or rebuild stores")
    date_index = pd.date_range(all_dates.min(), all_dates.max(), freq="D")
    dates = [d.strftime("%Y-%m-%d") for d in date_index]

    points_meta = (
        points_df.drop_duplicates(subset=["point_code"], keep="last")
        [["point_code", "point_name", "point_type", "pipeline_code", "pipeline_name", "municipality", "uf", "tso"]]
        .rename(columns={"point_code": "id", "point_name": "name", "point_type": "type",
                          "pipeline_code": "pipelineCode", "pipeline_name": "pipeline",
                          "municipality": "muni"})
        .to_dict(orient="records")
    ) if len(points_df) else []

    pipelines_meta = (
        ledger_df.drop_duplicates(subset=["pipeline_code"], keep="last")
        [["pipeline_code", "pipeline_name", "tso"]]
        .rename(columns={"pipeline_code": "id", "pipeline_name": "name"})
        .to_dict(orient="records")
    ) if len(ledger_df) else []

    point_series = _pivot_series(points_df, "point_code", dates) if len(points_df) else {}
    ledger_series = _pivot_series(ledger_df, "pipeline_code", dates) if len(ledger_df) else {}

    # Headline KPI: total realized flow at every point, last 7 days we have
    # data for, grouped by TSO. Kept for the home-page teaser marker below
    # (../build_home.py scrapes it from the HTML comment); the dashboard's
    # own header now computes receipts/deliveries by month client-side from
    # pointSeries directly, so this is no longer rendered as its own chip
    # row on the page itself.
    kpi_by_tso = {}
    if len(points_df):
        realized = points_df[points_df["variable"] == "Actual Volume (thousand m3)"]
        if len(realized):
            last_date = realized["date"].max()
            cutoff = last_date - pd.Timedelta(days=6)
            recent = realized[(realized["date"] >= cutoff) & (realized["date"] <= last_date)]
            grp = recent.groupby("tso")["value"].sum()
            kpi_by_tso = {str(k): round(float(v), 1) for k, v in grp.items()}
            kpi_last_date = last_date.strftime("%Y-%m-%d")
        else:
            kpi_last_date = None
    else:
        kpi_last_date = None

    _now_utc = dt.datetime.now(dt.timezone.utc)
    sources_present = []
    if len(points_df) and "source" in points_df.columns:
        sources_present = sorted(points_df["source"].dropna().astype(str).unique().tolist())
    elif len(points_df):
        sources_present = ["anp"]
    return {
        "generated": _now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": _now_utc.isoformat(),
        "dates": dates,
        "points": points_meta,
        "pipelines": pipelines_meta,
        "pointVars": [v for v, _ in POINT_VAR_ORDER if v in point_series],
        "ledgerVars": [v for v, _ in LEDGER_VAR_ORDER if v in ledger_series],
        "pointUnits": dict(POINT_VAR_ORDER),
        "ledgerUnits": dict(LEDGER_VAR_ORDER),
        "pointSeries": point_series,
        "ledgerSeries": ledger_series,
        "kpiByTso": kpi_by_tso,
        "kpiLastDate": kpi_last_date,
        "kpiTotal7d": round(sum(kpi_by_tso.values()), 1) if kpi_by_tso else None,
        "nPoints": len(points_meta),
        "sources": sources_present,
    }


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pipeline Flows</title>
<meta name="description" content="Daily physical natural gas flow at every receipt and delivery point on Brazil's transport pipelines, plus system-use gas, losses, imbalance, and linepack -- from ANP open data and TAG/TBG/NTS Portaria 1/2003 publications.">
<link rel="canonical" href="https://gasbrazil.com/flows/">
<link rel="icon" href="__FAVICON_DATA_URI__">
__FONT_PRELOAD__
<!-- home-page teaser marker, read by ../build_home.py -- not otherwise used by this page:
     generated: __GENERATED__
     kpi_total_7d: __KPI_TOTAL_7D__
     n_points: __N_POINTS__ -->
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
/* Single-row header: brand · title … Wiki/About/☰ · PT · theme */
header.dash-head { display: flex; flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0; }
h1 { font-size: 25px; margin: 0; letter-spacing: -.01em; }
.header-right { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; width: auto; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 var(--gap); }
.sources-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.pill { font-size: 11.5px; color: var(--muted2); text-decoration: none; border: 1px solid var(--border); border-radius: 5px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
.pill:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
#theme-toggle { display: inline-flex; align-items: center; justify-content: center; background: var(--panel); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 9px; line-height: 0; cursor: pointer; color: var(--text); }
#theme-toggle:hover { background: var(--accent-soft); }
#theme-toggle svg { width: 16px; height: 16px; display: block; }

.kpi-card-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin-bottom: var(--gap); }
.kpi-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.kpi-title { font-size: 13px; font-weight: 400; }
.kpi-title .muted { color: var(--muted); font-weight: 400; }
.kpi-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 8px; }
.kpi-card { text-align: left; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 10px; padding: 10px 12px; cursor: pointer; font-family: var(--font); color: var(--text); }
.kpi-card:hover { background: var(--accent-soft); }
.kpi-card.active { border-color: var(--accent); border-width: 2px; padding: 9px 11px; box-shadow: var(--shadow); }
.kpi-card .tso-name { font-size: 13px; font-weight: 400; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; }
.kpi-card .tso-name .all-badge { font-size: 10px; font-weight: 200; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.kpi-stat-row { display: flex; justify-content: space-between; gap: 8px; font-size: 11.5px; padding: 2px 0; }
.kpi-stat-row .lbl { color: var(--muted); }
.kpi-stat-row .val { font-variant-numeric: tabular-nums; font-weight: 400; }
.kpi-stat-row.recv .val { color: var(--flow-recv, #1baf7a); }
.kpi-stat-row.del .val { color: var(--flow-del, #eb6834); }
.kpi-card.empty { color: var(--muted); font-style: italic; }
.kpi-balance-bar { height: 5px; border-radius: 3px; overflow: hidden; display: flex; margin: 7px 0 2px; background: var(--border); }
.kpi-balance-bar .recv-seg { background: var(--flow-recv, #1baf7a); }
.kpi-balance-bar .del-seg { background: var(--flow-del, #eb6834); }

.level-toggle, .view-toggle { display: flex; gap: 6px; margin-bottom: var(--gap); flex-wrap: wrap; }
.level-btn { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 8px; padding: 7px 16px; font-size: 13px; font-weight: 400; cursor: pointer; color: var(--text); font-family: var(--font); }
.level-btn:hover { background: var(--accent-soft); }
.level-btn.active { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.view-toggle .level-btn { padding: 6px 14px; font-size: 12.5px; }
:root { --flow-recv: #1baf7a; --flow-del: #eb6834; }
[data-theme="dark"] { --flow-recv: #199e70; --flow-del: #d95926; }
.filters-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin-bottom: var(--gap); }
.filters-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters-bar { justify-content: flex-start; }
.filters-bar .reset-btn { margin-left: auto; }
.filters-drawer-toggle {
  display: none; align-items: center;
  background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px;
  padding: 5px 12px; font-size: 12.5px; font-weight: 400; cursor: pointer;
  color: var(--text); font-family: var(--font);
}
.filters-drawer-toggle:hover { background: var(--accent-soft); }
.minor-tso-label { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text); cursor: pointer; }
.minor-tso-label input { cursor: pointer; }
.filters-row + .filters-row { margin-top: 8px; }
/* Page-wide, not just .filters-row -- the KPI month select and the
   variable/date-range/granularity selects above the chart live outside
   .filters-row and need the same treatment, or they fall back to the
   browser's native (unstyled) select/input look. */
select, input { background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 10px; color: var(--text); font-size: 12.5px; font-family: var(--font); cursor: pointer; }
input[type="search"] { cursor: text; }
select:hover, input:hover { background: var(--accent-soft); }
.tso-toggle-row { display: flex; gap: 6px; flex-wrap: wrap; }
.tso-toggle { background: var(--bg); border: 1px solid var(--border-strong); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.tso-toggle:hover { background: var(--accent-soft); }
.tso-toggle.active { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.kpi-card.active[data-tso="NTS"] { border-color: var(--tso-nts); }
.kpi-card.active[data-tso="TAG"] { border-color: var(--tso-tag); }
.kpi-card.active[data-tso="TBG"] { border-color: var(--tso-tbg); }
.flowtype-toggle { background: var(--bg); border: 1px solid var(--border-strong); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); font-weight: 400; }
.flowtype-toggle:hover { background: var(--accent-soft); }
.flowtype-toggle.active { background: var(--panel); color: var(--text); border-color: var(--border-strong); }
.filter-label { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 200; margin-right: 2px; }
.reset-btn { margin-left: auto; background: transparent; border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; color: var(--muted2); font-family: var(--font); }
.reset-btn:hover { background: var(--accent-soft); color: var(--text); }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: var(--card-pad); margin-bottom: var(--gap); }
.panel-title { font-size: 13px; font-weight: 400; margin: 0 0 2px; display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.panel-note { font-size: 11.5px; color: var(--muted); margin: 6px 0 10px; }
/* Collapse toggle for the meter picker (chip grid / table) -- picking is a
   one-time task before charting, and the picker (especially the meter
   table) takes up more room than the chart itself once you're done with it. */
.picker-head { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; }
.collapse-btn { background: var(--bg); border: 1px solid var(--border-strong); border-radius: 6px; width: 24px; height: 22px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text); font-size: 11px; padding: 0; flex: none; transition: transform .12s ease; }
.collapse-btn:hover { background: var(--accent-soft); }
.collapse-btn.collapsed { transform: rotate(-90deg); }
.picker-summary { font-size: 12px; color: var(--muted); }
.chip-scroll { display: flex; flex-wrap: wrap; gap: 6px; max-height: 168px; overflow: auto; padding: 2px; margin-bottom: 4px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); }
.meter-table-wrap { max-height: 320px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 4px; }
.meter-table-wrap table { width: 100%; border-collapse: collapse; font-size: var(--table-font-size); }
.meter-table-wrap th, #data-table th { position: sticky; top: 0; background: var(--panel); color: var(--muted2); font-weight: 400; text-align: left; padding: 6px 10px 7px; border-bottom: 1px solid var(--border); z-index: 1; cursor: auto; }
/* Sortable/filterable column header, shared by the meter table and the
   data table below the chart: a clickable label (3 clicks = asc, desc,
   back to the table's default order) plus a small inline filter box. */
.th-label { cursor: pointer; user-select: none; display: block; }
.th-label:hover { color: var(--text); }
.th-filter { display: block; width: 100%; margin-top: 4px; padding: 2px 6px; font-size: 11px; font-weight: 300; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 5px; color: var(--text); box-sizing: border-box; }
th.num .th-filter { text-align: right; }
.meter-table-wrap td { padding: 5px 10px; border-bottom: 1px solid var(--border); }
.meter-table-wrap tr.meter-row { cursor: pointer; }
.meter-table-wrap tr.meter-row:hover { background: var(--accent-soft); }
.meter-table-wrap tr.meter-row.picked { background: var(--accent-soft); font-weight: 400; }
.meter-table-wrap .sw-cell { width: 18px; }
.meter-table-wrap .type-badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 10.5px; font-weight: 400; text-transform: uppercase; letter-spacing: .03em; }
.meter-table-wrap .type-badge.recv { background: rgba(27,175,122,0.16); color: #1baf7a; }
.meter-table-wrap .type-badge.del { background: rgba(235,104,52,0.16); color: #eb6834; }
.series-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px 4px 8px; font-size: 12px; cursor: pointer; color: var(--text); font-family: var(--font); }
.series-btn:hover { background: var(--accent-soft); }
.series-btn.active { border-color: var(--border-strong); font-weight: 400; }
.series-btn .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--border-strong); }
.chip-truncate-note { font-size: 11px; color: var(--muted); margin: 4px 2px 8px; }
#chart-host svg { display: block; overflow: hidden; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 44px 0; text-align: center; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 12px; color: var(--muted2); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend .sw { width: 9px; height: 9px; border-radius: 2px; flex: none; }
/* Chart tooltip (.tt) styles live in shared/theme.css */
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: var(--gap); }
.toolbar button { background: var(--panel); color: var(--text); border: 1px solid var(--border-strong); border-radius: 6px; padding: 5px 10px; font-size: 12.5px; cursor: pointer; font-family: var(--font); }
.toolbar button:hover { background: var(--accent-soft); }
.count { color: var(--muted); font-size: 12px; margin-left: auto; }
.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: auto; box-shadow: var(--shadow); max-height: 50vh; }
table { border-collapse: collapse; width: 100%; font-size: var(--table-font-size); table-layout: fixed; }
th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
th { position: sticky; top: 0; background: var(--panel); color: var(--muted2); font-weight: 400; z-index: 2; cursor: pointer; user-select: none; }
th:hover { background: var(--accent-soft); }
th .arrow { opacity: .4; margin-left: 3px; }
tbody tr:hover { background: var(--accent-soft); }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
footer { margin-top: 22px; color: var(--muted); font-size: 11.5px; line-height: 1.7; }
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
  <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/dados-consolidados-movimentacao-de-gas-natural-em-gasodutos-de-transporte" target="_blank" rel="noopener">ANP<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  <a href="https://ntag.com.br/transparencia/" target="_blank" rel="noopener">TAG<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  <a href="https://www.tbg.com.br/informacoes-a-anp" target="_blank" rel="noopener">TBG<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
  <a href="https://www.ntsbrasil.com/transparencia/" target="_blank" rel="noopener">NTS<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
</div>

<div class="kpi-card-wrap">
  <div class="kpi-header">
    <span class="kpi-title">Receipts &amp; deliveries by transporter <span class="muted" id="kpi-month-label"></span></span>
    <span style="display:flex;gap:8px;align-items:center">
      <span class="filter-label">Month</span>
      <select id="f-kpi-month"></select>
    </span>
  </div>
  <div class="kpi-cards" id="kpi-cards"></div>
</div>

<div class="level-toggle" id="level-toggle"></div>
<div class="view-toggle" id="view-toggle"></div>

<div class="chart-card">
  <p class="panel-title">
    <span id="chart-title">Actual Volume</span>
    <span style="display:flex;gap:6px;flex-wrap:wrap">
      <select id="f-variable"></select>
      <select id="f-preset">
        <option value="90d">Last 90 days</option>
        <option value="12m" selected>Last 12 months</option>
        <option value="3y">Last 3 years</option>
        <option value="all">All history</option>
      </select>
      <select id="f-smooth">
        <option value="raw">Daily</option>
        <option value="7d">7-day avg</option>
        <option value="30d">30-day avg</option>
      </select>
    </span>
  </p>
  <p class="panel-note" id="chart-note">Totals summed across every matching receipt/delivery point.</p>
  <div class="picker-head" id="picker-head" hidden>
    <button type="button" class="collapse-btn" id="picker-collapse-btn" aria-expanded="true" aria-label="Collapse picker">&#9662;</button>
    <span class="picker-summary" id="picker-summary"></span>
  </div>
  <div id="picker-body">
    <div class="chip-scroll" id="chip-scroll" hidden></div>
    <div class="chip-truncate-note" id="chip-truncate-note" hidden></div>
    <div class="meter-table-wrap" id="meter-table-wrap" hidden></div>
  </div>
  <div id="chart-host"></div>
</div>

<div class="filters-card">
  <div class="filters-row filters-bar">
    <button type="button" class="filters-drawer-toggle" id="filters-drawer-toggle"
            aria-expanded="false" aria-controls="filters-drawer">Filters</button>
    <div id="tso-toggle-row" class="tso-toggle-row"></div>
    <button type="button" id="btn-reset-filters" class="reset-btn">Reset all filters</button>
  </div>
  <div id="filters-drawer" class="filters-collapsible is-collapsed">
    <div class="filters-row" id="flowtype-toggle-row"></div>
    <div class="filters-row">
      <span class="filter-label">Pipeline</span>
      <select id="f-pipeline"><option value="">All pipelines</option></select>
      <span class="filter-label" id="f-uf-label">State</span>
      <select id="f-uf"><option value="">All states</option></select>
      <input id="f-search" type="search" placeholder="Search pipeline / point&hellip;" style="min-width:200px">
      <label class="minor-tso-label"><input type="checkbox" id="f-include-minor-tsos"> Include TSB &amp; GOM</label>
    </div>
  </div>
</div>

<div class="toolbar">
  <button id="btn-clear-picks" hidden>Clear selection</button>
  <button id="btn-csv">Download CSV</button>
  <button id="btn-xlsx">Export table (Excel)</button>
  __SHARED_SHARE_BUTTON__
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
  __SHARED_METHODOLOGY__
  &copy; <span id="year"></span> GasBrazil.com &middot; Data: ANP open data + TAG/TBG/NTS Portaria 1/2003 (Actual/Scheduled prefer TSO when available) &middot; Shipper capacity is on <a href="../contratos/">POC Contracts</a>; this page shows physical flow totals only &middot; Contact: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
</div>
<div class="tt" id="chart-tt"></div>
<script>
const PAYLOAD_URL = "__PAYLOAD_URL__";

__SHARED_JS_DECODE__
__SHARED_JS_CSV__
__SHARED_JS_XLSX__
__SHARED_SITE_LINKS_JS__
__SHARED_JS_ESCAPE_HTML__
__SHARED_JS_QUERY_STATE__

__SHARED_JS_CHART_PALETTE__
const MAX_CHIPS_SHOWN = 60;
const DEFAULT_PICK_COUNT = 5;
const RECEIPT = "Receipt Point", DELIVERY = "Delivery Point";

let DATA = null;
let level = "points";        // "points" | "ledger"
let viewMode = "aggregate";  // "aggregate" (TSO totals) | "detail" (individual meters/pipelines)
let variable = null;         // current variable string
const PRIMARY_TSOS = ["NTS", "TAG", "TBG"];
const MINOR_TSOS = ["TSB", "GOM"];
let includeMinorTsos = false;
let tsoFilter = new Set();   // empty == all visible TSOs
let flowTypeFilter = "";     // "" | "Receipt Point" | "Delivery Point" -- points level only
let pipelineFilter = "";
let ufFilter = "";
let searchText = "";
let datePreset = "12m";
let smoothing = "raw";
let picked = new Set();      // detail-mode picks only
let chartSlots = new Map();
let pickerCollapsed = false;

// Shared 3-click sort cycle for every sortable table on this page: click 1
// sorts by the table's natural direction for that column (descending for
// whichever column is the table's own default, ascending otherwise), click
// 2 reverses it, click 3 clears back to the table's default order/column.
function naturalDir(col, defaultCol) { return col === defaultCol ? -1 : 1; }
function cycleSort(current, col, def) {
  const nd = naturalDir(col, def.col);
  if (current.col !== col) return { col, dir: nd };
  if (current.dir === nd) return { col, dir: -nd };
  return { col: def.col, dir: def.dir };
}

const METER_DEFAULT_SORT = { col: "volume", dir: -1 };
let meterSort = { col: "volume", dir: -1 };
let meterFilters = {};       // colKey -> lowercase substring filter

const DATA_DEFAULT_SORT = { col: "date", dir: -1 };
let dataSort = { col: "date", dir: -1 };
let dataFilters = {};        // "date" | entity id -> lowercase substring filter

let tableRows = []; // last rendered table rows, kept for CSV/XLSX export
let tableCols = [];
let chartResizeTimer = null;
let kpiMonth = null; // "YYYY-MM"

function chartClaimSlot(key) {
  if (chartSlots.has(key)) return chartSlots.get(key);
  const pal = chartPalette();
  const slot = chartSlots.size % Math.max(1, pal.length);
  chartSlots.set(key, slot);
  return slot;
}
function chartColorOf(key) {
  let tso = tsoFromChartKey(key);
  if (!tso) {
    const e = entityById(key);
    if (e && e.tso) tso = e.tso;
  }
  if (tso) return tsoColorOf(tso, chartClaimSlot(key));
  const pal = chartPalette();
  if (!pal.length) return "var(--accent)";
  return pal[chartClaimSlot(key) % pal.length];
}

function currentEntities() { return level === "points" ? DATA.points : DATA.pipelines; }
function currentVarList() { return level === "points" ? DATA.pointVars : DATA.ledgerVars; }
function currentUnits() { return level === "points" ? DATA.pointUnits : DATA.ledgerUnits; }
function currentSeriesMap() {
  const bag = level === "points" ? DATA.pointSeries : DATA.ledgerSeries;
  return bag[variable] || {};
}
function entityById(id) { return currentEntities().find(e => e.id === id); }
// ANP point names sometimes carry a trailing "(ORIGIN >> DEST)" segment
// spelling out the connecting sub-pipeline codes -- meaningful to ANP's own
// registry, but clutter on a page meant to be skimmed at a glance. Stripped
// from every on-page label; the full raw name is still available via the
// row's title attribute for anyone who needs the ANP-exact wording.
function shortPointName(name) {
  return name.replace(/\\s*\\([^()]*>>[^()]*\\)\\s*$/, "");
}

function entityLabel(e) {
  if (e.isAggregate) return e.name;
  if (level === "points") return e.pipeline + " · " + shortPointName(e.name) + " (" + (e.type === "Receipt Point" ? "Recv" : "Del") + ")";
  return e.name;
}

function isTsoVisible(tso) {
  if (!tso) return false;
  // Only TSB/GOM are gated; NTS/TAG/TBG and any other code stay visible.
  if (MINOR_TSOS.includes(tso)) return includeMinorTsos;
  return true;
}
function tsoUniverse(ents) {
  const all = [...new Set((ents || currentEntities()).map(e => e.tso).filter(Boolean))];
  const filtered = all.filter(isTsoVisible);
  return filtered.sort((a, b) => {
    const ia = PRIMARY_TSOS.indexOf(a), ib = PRIMARY_TSOS.indexOf(b);
    const ra = ia >= 0 ? ia : 100, rb = ib >= 0 ? ib : 100;
    return ra - rb || a.localeCompare(b);
  });
}
function matchesFilters(e) {
  if (tsoFilter.size) {
    if (!tsoFilter.has(e.tso)) return false;
  } else if (!isTsoVisible(e.tso)) {
    return false;
  }
  if (pipelineFilter && (level === "points" ? e.pipeline : e.name) !== pipelineFilter) return false;
  if (level === "points") {
    if (flowTypeFilter && e.type !== flowTypeFilter) return false;
    if (ufFilter && e.uf !== ufFilter) return false;
  }
  if (searchText) {
    const hay = (entityLabel(e) + " " + (e.muni || "")).toLowerCase();
    if (!hay.includes(searchText)) return false;
  }
  return true;
}

// Like matchesFilters, but for a specific (tso, pointType) aggregate group
// rather than the globally-selected tsoFilter/flowTypeFilter -- used when
// building the "totals" lines in aggregate mode, where each line has its
// own fixed TSO/flow-type regardless of how many TSOs are toggled on.
function matchesGroup(e, tso, pointType) {
  if (tso && e.tso !== tso) return false;
  if (!tso && !isTsoVisible(e.tso)) return false;
  if (level === "points" && pointType && e.type !== pointType) return false;
  if (pipelineFilter && (level === "points" ? e.pipeline : e.name) !== pipelineFilter) return false;
  if (level === "points" && ufFilter && e.uf !== ufFilter) return false;
  if (searchText) {
    const hay = (entityLabel(e) + " " + (e.muni || "")).toLowerCase();
    if (!hay.includes(searchText)) return false;
  }
  return true;
}

// Ranks entities by overall average magnitude in the currently selected
// variable's series -- used both to pick sensible chart defaults and to
// decide which chips survive the MAX_CHIPS_SHOWN cap when a filter/search
// still leaves a lot of matches.
function rankScore(id) {
  const arr = currentSeriesMap()[id];
  if (!arr) return 0;
  let sum = 0, n = 0;
  for (const v of arr) { if (v !== null) { sum += Math.abs(v); n++; } }
  return n ? sum / n : 0;
}

function availableEntities() {
  const seriesMap = currentSeriesMap();
  return currentEntities().filter(e => seriesMap[e.id] && matchesFilters(e));
}

function populateSelectPreserve(sel, values, placeholder) {
  const cur = sel.value;
  sel.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = ""; opt0.textContent = placeholder;
  sel.appendChild(opt0);
  const uniq = [...new Set(values.filter(Boolean))].sort();
  for (const v of uniq) {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = v;
    sel.appendChild(opt);
  }
  if (uniq.includes(cur)) sel.value = cur; else sel.value = "";
}

function buildLevelToggle() {
  const host = document.getElementById("level-toggle");
  host.innerHTML = "";
  const defs = [
    { id: "points", label: "Receipt & Delivery Points" },
    { id: "ledger", label: "Pipeline System (GUS, losses, imbalance, linepack)" },
  ];
  for (const d of defs) {
    const btn = document.createElement("button");
    btn.className = "level-btn" + (level === d.id ? " active" : "");
    btn.textContent = d.label;
    btn.addEventListener("click", () => {
      if (level === d.id) return;
      level = d.id;
      pipelineFilter = ""; flowTypeFilter = ""; ufFilter = "";
      document.getElementById("f-pipeline").value = "";
      document.getElementById("f-uf").value = "";
      variable = currentVarList()[0];
      picked = new Set();
      chartSlots = new Map();
      onLevelOrVariableChanged();
    });
    host.appendChild(btn);
  }
  const pointOnly = document.querySelectorAll("#f-uf-label, #f-uf, #flowtype-toggle-row");
  pointOnly.forEach(el => { el.style.display = level === "points" ? "" : "none"; });
}

function buildViewToggle() {
  const host = document.getElementById("view-toggle");
  host.innerHTML = "";
  const defs = [
    { id: "aggregate", label: "Totals by transporter" },
    { id: "detail", label: level === "points" ? "Individual meters" : "Individual pipelines" },
  ];
  for (const d of defs) {
    const btn = document.createElement("button");
    btn.className = "level-btn" + (viewMode === d.id ? " active" : "");
    btn.textContent = d.label;
    btn.addEventListener("click", () => {
      if (viewMode === d.id) return;
      viewMode = d.id;
      if (viewMode === "detail" && picked.size === 0) defaultPicks();
      onViewModeChanged();
    });
    host.appendChild(btn);
  }
}

function onViewModeChanged() {
  const isDetail = viewMode === "detail";
  const isPointsDetail = isDetail && level === "points";
  document.getElementById("picker-head").hidden = !isDetail;
  document.getElementById("chip-scroll").hidden = !isDetail || isPointsDetail;
  document.getElementById("meter-table-wrap").hidden = !isPointsDetail;
  document.getElementById("btn-clear-picks").hidden = !isDetail;
  document.getElementById("chart-note").textContent = isDetail
    ? "Pick one or more pipelines/points below to chart. Values summed across every shipper and contract active at that point/pipeline."
    : (level === "points"
        ? "Totals summed across every matching receipt/delivery point (use the filters above to narrow by pipeline or state)."
        : "Totals summed across every matching pipeline (use the filters above to narrow by pipeline)");
  applyPickerCollapse();
  render();
}

function applyPickerCollapse() {
  document.getElementById("picker-body").hidden = pickerCollapsed;
  const btn = document.getElementById("picker-collapse-btn");
  btn.classList.toggle("collapsed", pickerCollapsed);
  btn.setAttribute("aria-expanded", String(!pickerCollapsed));
  btn.setAttribute("aria-label", pickerCollapsed ? "Expand picker" : "Collapse picker");
}

// Single-select, not multi: picking TAG then clicking TBG should swap to
// TBG, not add to it -- there's no case where two specific transporters but
// not the third is a meaningful filter. An explicit "All" pill makes the
// no-filter state a real, clickable option instead of an implicit side
// effect of deselecting everything by hand.
function buildTsoToggles() {
  const host = document.getElementById("tso-toggle-row");
  host.innerHTML = '<span class="filter-label">Transporter</span>';
  const allTsos = tsoUniverse();
  // Drop a stuck selection if the minor-TSO toggle hid it.
  if (tsoFilter.size) {
    tsoFilter = new Set([...tsoFilter].filter(isTsoVisible));
  }

  const allBtn = document.createElement("button");
  allBtn.className = "tso-toggle" + (tsoFilter.size === 0 ? " active" : "");
  allBtn.textContent = "All";
  allBtn.addEventListener("click", () => {
    if (tsoFilter.size === 0) return;
    tsoFilter = new Set();
    render();
  });
  host.appendChild(allBtn);

  for (const tso of allTsos) {
    const btn = document.createElement("button");
    const isActive = tsoFilter.has(tso);
    btn.className = "tso-toggle" + (isActive ? " active" : "");
    btn.dataset.tso = tso;
    btn.textContent = tso;
    btn.addEventListener("click", () => {
      // Clicking the only active transporter again clears back to "All"
      // rather than leaving no way to toggle it off besides the All pill.
      tsoFilter = (isActive && tsoFilter.size === 1) ? new Set() : new Set([tso]);
      render();
    });
    host.appendChild(btn);
  }
}

function buildFlowTypeToggles() {
  const host = document.getElementById("flowtype-toggle-row");
  host.innerHTML = '<span class="filter-label">Flow type</span>';
  const defs = [{ v: "", label: "All" }, { v: RECEIPT, label: "Receipts" }, { v: DELIVERY, label: "Deliveries" }];
  for (const d of defs) {
    const btn = document.createElement("button");
    btn.className = "flowtype-toggle" + (flowTypeFilter === d.v ? " active" : "");
    btn.textContent = d.label;
    btn.addEventListener("click", () => { flowTypeFilter = d.v; render(); });
    host.appendChild(btn);
  }
}

function buildVariableSelect() {
  const sel = document.getElementById("f-variable");
  sel.innerHTML = "";
  for (const v of currentVarList()) {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = shortLabel(v) + " (" + currentUnits()[v] + ")";
    sel.appendChild(opt);
  }
  if (!currentVarList().includes(variable)) variable = currentVarList()[0];
  sel.value = variable;
}

function shortLabel(v) { return v.split(" (")[0]; }

function buildDependentSelects() {
  const ents = currentEntities().filter(e => {
    if (tsoFilter.size) return tsoFilter.has(e.tso);
    return isTsoVisible(e.tso);
  });
  if (level === "points") {
    populateSelectPreserve(document.getElementById("f-pipeline"), ents.map(e => e.pipeline), "All pipelines");
    populateSelectPreserve(document.getElementById("f-uf"), ents.map(e => e.uf), "All states");
  } else {
    populateSelectPreserve(document.getElementById("f-pipeline"), ents.map(e => e.name), "All pipelines");
  }
}

// Points level always uses the sortable/filterable meter table below --
// receipts/deliveries/both is already the Flow type filter above, and a
// real "Avg volume" column replaces a separate chip picker plus a hidden
// 60-item cap. The pipeline-system level still uses a small chip grid
// (there are only ever a handful of pipelines, TAG/NTS/TBG, so a table
// would be overkill there).
function buildChips() {
  const chipHost = document.getElementById("chip-scroll");
  chipHost.innerHTML = "";
  const note = document.getElementById("chip-truncate-note");
  if (viewMode !== "detail") { note.hidden = true; return; }

  let matches = availableEntities();

  if (level === "points") {
    note.hidden = true;
    renderMeterTable(matches);
    return;
  }

  matches.sort((a, b) => rankScore(b.id) - rankScore(a.id));
  if (matches.length > MAX_CHIPS_SHOWN) {
    note.hidden = false;
    note.textContent = `Showing the ${MAX_CHIPS_SHOWN} largest of ${matches.length} matches by average volume -- narrow the filters or search to see the rest.`;
    matches = matches.slice(0, MAX_CHIPS_SHOWN);
  } else {
    note.hidden = true;
  }
  matches.sort((a, b) => a.name.localeCompare(b.name));
  for (const e of matches) chipHost.appendChild(makeChip(e));
  if (!matches.length) {
    const empty = document.createElement("div");
    empty.style.cssText = "color:var(--muted);font-size:12.5px;padding:8px 4px";
    empty.textContent = "No pipelines/points match the current filters for this variable.";
    chipHost.appendChild(empty);
  }
  setPickerSummary(matches.length, matches.length);
}

function togglePick(id) {
  if (picked.has(id)) { picked.delete(id); chartSlots.delete(id); }
  else { picked.add(id); chartClaimSlot(id); }
  render();
}

function makeChip(e) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "series-btn" + (picked.has(e.id) ? " active" : "");
  btn.title = [e.pipeline, e.muni, e.uf].filter(Boolean).join(", ");
  btn.innerHTML = '<span class="sw"></span>' + escapeHtml(entityLabel(e));
  if (picked.has(e.id)) btn.querySelector(".sw").style.background = chartColorOf(e.id);
  btn.addEventListener("click", () => togglePick(e.id));
  return btn;
}

const METER_TABLE_COLS = [
  { key: "pipeline", label: "Pipeline" },
  { key: "name", label: "Meter" },
  { key: "type", label: "Type" },
  { key: "uf", label: "State" },
  { key: "volume", label: "Avg volume" },
];

function meterSortValue(e, col) {
  if (col === "volume") return rankScore(e.id);
  if (col === "name") return shortPointName(e.name);
  if (col === "type") return e.type;
  if (col === "uf") return e.uf || "";
  return e.pipeline;
}
function meterFilterValue(e, col) {
  if (col === "volume") return fmtAxisNum(rankScore(e.id), 1);
  if (col === "type") return e.type === RECEIPT ? "Receipt" : "Delivery";
  return String(meterSortValue(e, col));
}

// Rebuilding a table on every filter keystroke would normally steal focus
// out of the input the user is typing in. Both tables on this page share
// this fix: remember which .th-filter (by data-col) had focus and where
// the caret was, rebuild, then restore both.
function withFocusPreserved(host, rebuild) {
  const active = document.activeElement;
  const col = (active && active.classList && active.classList.contains("th-filter") && host.contains(active))
    ? active.dataset.col : null;
  const caret = col ? active.selectionStart : null;
  rebuild();
  if (col) {
    const input = host.querySelector('.th-filter[data-col="' + col + '"]');
    if (input) { input.focus(); if (caret != null) input.setSelectionRange(caret, caret); }
  }
}

// Shared header-cell builder for both sortable/filterable tables: a
// clickable label (see cycleSort) plus a small inline filter box.
function buildSortFilterTh(col, sortState, defaultSort, filters, onChange, extraClass) {
  const th = document.createElement("th");
  if (extraClass) th.className = extraClass;
  const labelSpan = document.createElement("span");
  labelSpan.className = "th-label";
  labelSpan.textContent = col.label;
  if (sortState.col === col.key) {
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = sortState.dir === 1 ? "↑" : "↓";
    labelSpan.appendChild(arrow);
  }
  labelSpan.addEventListener("click", () => onChange(cycleSort(sortState, col.key, defaultSort), filters));
  th.appendChild(labelSpan);
  const filterInput = document.createElement("input");
  filterInput.type = "search";
  filterInput.className = "th-filter";
  filterInput.dataset.col = col.key;
  filterInput.placeholder = "Filter…";
  filterInput.value = filters[col.key] || "";
  filterInput.addEventListener("input", () => {
    filters[col.key] = filterInput.value.toLowerCase();
    onChange(sortState, filters);
  });
  th.appendChild(filterInput);
  return th;
}

// The only points-level picker: every matching meter, sortable by any
// column (3-click cycle: asc, desc, back to volume-descending) and
// filterable in place per column -- never capped, unlike the old "chips"
// grid, which hid anything past the 60 largest until you switched to this
// same table anyway.
function renderMeterTable(matches) {
  const host = document.getElementById("meter-table-wrap");
  withFocusPreserved(host, () => {
    host.innerHTML = "";

    let rows = matches;
    for (const key in meterFilters) {
      const f = meterFilters[key];
      if (f) rows = rows.filter(e => meterFilterValue(e, key).toLowerCase().includes(f));
    }

    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const trh = document.createElement("tr");
    trh.appendChild(document.createElement("th")); // swatch column, unsortable/unfiltered
    for (const c of METER_TABLE_COLS) {
      trh.appendChild(buildSortFilterTh(c, meterSort, METER_DEFAULT_SORT, meterFilters, (next) => {
        meterSort = next;
        buildChips();
      }, c.key === "volume" ? "num" : ""));
    }
    thead.appendChild(trh);
    table.appendChild(thead);

    const sorted = rows.slice().sort((a, b) => {
      const av = meterSortValue(a, meterSort.col), bv = meterSortValue(b, meterSort.col);
      let cmp = (typeof av === "number") ? av - bv : String(av).localeCompare(String(bv));
      if (cmp === 0) cmp = a.pipeline.localeCompare(b.pipeline) || a.name.localeCompare(b.name);
      return cmp * meterSort.dir;
    });

    const tbody = document.createElement("tbody");
    const unit = currentUnits()[variable] || "";
    for (const e of sorted) {
      const tr = document.createElement("tr");
      tr.className = "meter-row" + (picked.has(e.id) ? " picked" : "");
      tr.title = e.name;
      const swColor = picked.has(e.id) ? chartColorOf(e.id) : "transparent";
      const isRecv = e.type === RECEIPT;
      tr.innerHTML =
        '<td class="sw-cell"><span class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + swColor + '"></span></td>' +
        "<td>" + escapeHtml(e.pipeline) + "</td>" +
        "<td>" + escapeHtml(shortPointName(e.name)) + "</td>" +
        '<td><span class="type-badge ' + (isRecv ? "recv" : "del") + '">' + (isRecv ? "Receipt" : "Delivery") + "</span></td>" +
        "<td>" + escapeHtml(e.uf || "") + "</td>" +
        '<td class="num">' + fmtAxisNum(rankScore(e.id), 1) + (unit ? " " + escapeHtml(unit) : "") + "</td>";
      tr.addEventListener("click", () => togglePick(e.id));
      tbody.appendChild(tr);
    }
    if (!sorted.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="6" style="color:var(--muted);padding:10px">No meters match the current filters.</td>';
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    host.appendChild(table);

    setPickerSummary(matches.length, sorted.length);
  });
}

function setPickerSummary(total, shown) {
  const el = document.getElementById("picker-summary");
  if (!el) return;
  const noun = level === "points" ? "meters" : "pipelines";
  el.textContent = (shown < total ? shown + " of " + total : total) + " " + noun
    + (picked.size ? " · " + picked.size + " selected" : "");
}

function defaultPicks() {
  const matches = availableEntities().sort((a, b) => rankScore(b.id) - rankScore(a.id));
  picked = new Set(matches.slice(0, DEFAULT_PICK_COUNT).map(e => e.id));
  chartSlots = new Map();
  picked.forEach(id => chartClaimSlot(id));
}

function onLevelOrVariableChanged() {
  buildLevelToggle();
  buildViewToggle();
  buildTsoToggles();
  buildFlowTypeToggles();
  buildDependentSelects();
  buildVariableSelect();
  if (viewMode === "detail" && picked.size === 0) defaultPicks();
  onViewModeChanged();
}

function dateRangeForPreset() {
  const allDates = DATA.dates;
  const maxD = allDates[allDates.length - 1];
  const maxIdx = allDates.length - 1;
  let fromIdx = 0;
  if (datePreset === "90d") fromIdx = Math.max(0, maxIdx - 89);
  else if (datePreset === "12m") fromIdx = Math.max(0, maxIdx - 364);
  else if (datePreset === "3y") fromIdx = Math.max(0, maxIdx - 1094);
  return { from: allDates[fromIdx], to: maxD, fromIdx, toIdx: maxIdx };
}

function smoothedValues(arr) {
  if (smoothing === "raw") return arr;
  const window = smoothing === "7d" ? 7 : 30;
  const out = new Array(arr.length).fill(null);
  for (let i = 0; i < arr.length; i++) {
    let sum = 0, n = 0;
    for (let j = Math.max(0, i - window + 1); j <= i; j++) {
      if (arr[j] !== null && arr[j] !== undefined) { sum += arr[j]; n++; }
    }
    out[i] = n ? sum / n : null;
  }
  return out;
}

// ---- Aggregate ("Totals by transporter") support -------------------------
//
// Every point/pipeline's full series is already in the payload, so an
// "aggregate" line is computed on the fly by summing (or, for a %
// variable, averaging) across whichever entities match a given
// (tso, pointType) group -- no server-side changes needed.

function aggregateGroups() {
  if (level === "points") {
    const tsos = tsoFilter.size ? [...tsoFilter] : [null];
    const types = flowTypeFilter ? [flowTypeFilter] : [RECEIPT, DELIVERY];
    const groups = [];
    for (const tso of tsos) {
      for (const t of types) {
        groups.push({
          key: (tso || "ALL") + ":" + t,
          tso, pointType: t,
          label: (tso ? tso + " " : "All Brazil — ") + (t === RECEIPT ? "Receipts" : "Deliveries"),
        });
      }
    }
    return groups;
  }
  // Ledger: no receipt/delivery split -- one aggregate line per TSO. With
  // nothing toggled on, show every TSO so "the system as a whole" is the
  // default comparison; narrowing to specific TSOs shows just those.
  const tsos = tsoFilter.size ? [...tsoFilter] : tsoUniverse(DATA.pipelines);
  return tsos.map(tso => ({ key: tso, tso, pointType: null, label: tso }));
}

function aggregateValuesForGroup(tso, pointType, fromIdx, toIdx) {
  const seriesMap = currentSeriesMap();
  const ids = currentEntities().filter(e => matchesGroup(e, tso, pointType)).map(e => e.id);
  const isMean = variable === "Allocation (%)" || variable.startsWith("Average Pressure");
  const out = [];
  for (let i = fromIdx; i <= toIdx; i++) {
    let sum = 0, n = 0, any = false;
    for (const id of ids) {
      const arr = seriesMap[id];
      if (!arr) continue;
      const v = arr[i];
      if (v !== null && v !== undefined) { sum += v; n++; any = true; }
    }
    out.push(any ? (isMean ? sum / n : sum) : null);
  }
  return out;
}

function aggregateSeriesList(range) {
  const dates = DATA.dates.slice(range.fromIdx, range.toIdx + 1);
  return aggregateGroups().map(g => {
    const raw = aggregateValuesForGroup(g.tso, g.pointType, range.fromIdx, range.toIdx);
    const vals = smoothedValues(raw);
    const pts = [];
    for (let i = 0; i < dates.length; i++) if (vals[i] !== null && vals[i] !== undefined) pts.push({ date: dates[i], v: vals[i] });
    const entity = { id: "AGG:" + g.key, name: g.label, tso: g.tso, pipeline: g.tso || "All Brazil", type: g.pointType, isAggregate: true };
    return { id: entity.id, entity, pts };
  }).filter(s => s.pts.length);
}

// ---- KPI cards: receipts vs. deliveries by transporter, for one month ----

function availableMonths() {
  const set = new Set(DATA.dates.map(d => d.slice(0, 7)));
  return [...set].sort().reverse();
}

function monthLabel(ym) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1, 1));
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
}

function monthIdxRange(ym) {
  const dates = DATA.dates;
  let startIdx = -1, endIdx = -1;
  for (let i = 0; i < dates.length; i++) {
    if (dates[i].slice(0, 7) === ym) { if (startIdx < 0) startIdx = i; endIdx = i; }
  }
  return { startIdx, endIdx };
}

function monthlyTotal(tso, pointType, startIdx, endIdx) {
  const seriesMap = DATA.pointSeries["Actual Volume (thousand m3)"] || {};
  let total = 0, any = false;
  for (const pt of DATA.points) {
    if (pt.type !== pointType) continue;
    if (tso && pt.tso !== tso) continue;
    if (!tso && !isTsoVisible(pt.tso)) continue;
    const arr = seriesMap[pt.id];
    if (!arr) continue;
    for (let i = startIdx; i <= endIdx; i++) {
      const v = arr[i];
      if (v !== null && v !== undefined) { total += v; any = true; }
    }
  }
  return any ? total : null;
}

function fmtVolume(v) {
  if (v === null || v === undefined) return "–";
  const abs = Math.abs(v);
  return abs >= 1000
    ? (v / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 }) + "M m³"
    : v.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " thousand m³";
}

function buildKpiMonthSelect() {
  const sel = document.getElementById("f-kpi-month");
  const months = availableMonths();
  if (!kpiMonth || !months.includes(kpiMonth)) kpiMonth = months[0];
  sel.innerHTML = "";
  for (const ym of months) {
    const opt = document.createElement("option");
    opt.value = ym; opt.textContent = monthLabel(ym);
    sel.appendChild(opt);
  }
  sel.value = kpiMonth;
}

function renderKpiCards() {
  const cardsHost = document.getElementById("kpi-cards");
  const labelHost = document.getElementById("kpi-month-label");
  cardsHost.innerHTML = "";
  if (!DATA.points.length) { document.querySelector(".kpi-card-wrap").hidden = true; return; }
  const { startIdx, endIdx } = monthIdxRange(kpiMonth);
  const lastOverallIdx = DATA.dates.length - 1;
  const isPartial = endIdx < lastOverallIdx ? false : (DATA.dates[endIdx].slice(8, 10) !== new Date(Date.UTC(+kpiMonth.slice(0, 4), +kpiMonth.slice(5, 7), 0)).getUTCDate().toString().padStart(2, "0"));
  labelHost.textContent = isPartial ? ("— partial, through " + DATA.dates[endIdx]) : "";

  const tsos = tsoUniverse(DATA.points);

  const makeCard = (tso, label, isAll) => {
    const recv = monthlyTotal(tso, RECEIPT, startIdx, endIdx);
    const del = monthlyTotal(tso, DELIVERY, startIdx, endIdx);
    const card = document.createElement("button");
    card.type = "button";
    if (!isAll) card.dataset.tso = tso;
    card.className = "kpi-card" + (isAll ? "" : (tsoFilter.has(tso) && tsoFilter.size === 1 ? " active" : "")) + (isAll && tsoFilter.size === 0 ? " active" : "");
    if (recv === null && del === null) card.classList.add("empty");
    let bar = "";
    if (recv !== null && del !== null && (recv + del) > 0) {
      const pct = (100 * recv / (recv + del)).toFixed(1);
      bar = `<div class="kpi-balance-bar"><div class="recv-seg" style="width:${pct}%"></div><div class="del-seg" style="width:${100 - pct}%"></div></div>`;
    }
    card.innerHTML = `
      <div class="tso-name">${label}${isAll ? '<span class="all-badge">nationwide</span>' : ""}</div>
      <div class="kpi-stat-row recv"><span class="lbl">Receipts</span><span class="val">${fmtVolume(recv)}</span></div>
      <div class="kpi-stat-row del"><span class="lbl">Deliveries</span><span class="val">${fmtVolume(del)}</span></div>
      ${bar}`;
    card.addEventListener("click", () => {
      if (isAll) { tsoFilter = new Set(); } else {
        tsoFilter = (tsoFilter.size === 1 && tsoFilter.has(tso)) ? new Set() : new Set([tso]);
      }
      level = "points"; viewMode = "aggregate"; flowTypeFilter = "";
      onLevelOrVariableChanged();
      document.querySelector(".chart-card").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return card;
  };

  cardsHost.appendChild(makeCard(null, "All Brazil", true));
  for (const tso of tsos) cardsHost.appendChild(makeCard(tso, tso, false));
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
  document.getElementById("chart-title").textContent = shortLabel(variable) + (viewMode === "aggregate" ? " — totals" : "");
  const range = dateRangeForPreset();
  const dates = DATA.dates.slice(range.fromIdx, range.toIdx + 1);
  const unit = currentUnits()[variable];

  let seriesList;
  if (viewMode === "aggregate") {
    seriesList = aggregateSeriesList(range);
  } else {
    const seriesMap = currentSeriesMap();
    seriesList = [...picked].map(id => {
      const raw = (seriesMap[id] || []).slice(range.fromIdx, range.toIdx + 1);
      const vals = smoothedValues(raw);
      const pts = [];
      for (let i = 0; i < dates.length; i++) if (vals[i] !== null && vals[i] !== undefined) pts.push({ date: dates[i], v: vals[i] });
      return { id, entity: entityById(id), pts };
    }).filter(s => s.entity && s.pts.length);
  }

  if (viewMode === "detail" && !picked.size) {
    host.innerHTML = '<div class="chart-empty">Pick one or more pipelines/points above to see the trend.</div>';
    renderTable([], dates);
    return;
  }
  if (!seriesList.length) {
    host.innerHTML = '<div class="chart-empty">No data for the selected series in this date range.</div>';
    renderTable([], dates);
    return;
  }

  const allDates = [...new Set(seriesList.flatMap(s => s.pts.map(p => p.date)))].sort();
  const dNum = iso => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const minD = dNum(allDates[0]), maxD = dNum(allDates[allDates.length - 1]);
  const spanDays = Math.max(1, (maxD - minD) / 86400000);

  let lo = Infinity, hi = -Infinity;
  seriesList.forEach(s => s.pts.forEach(p => { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); }));
  if (lo > 0 && lo / hi <= 0.55) lo = 0;
  if (lo >= 0 && hi <= 0) hi = 1;
  const pad = (hi - lo) * 0.08 || 1; hi += pad; if (lo < 0) lo -= pad;

  const W = Math.max(680, host.clientWidth || 680), H = 360, ML = 68, MR = 16, MT = 26, MB = 32;
  const x = iso => ML + (W - ML - MR) * (maxD === minD ? 0.5 : (dNum(iso) - minD) / (maxD - minD));
  const y = v => MT + (H - MT - MB) * (1 - (v - lo) / (hi - lo));

  const svg = chartSvgEl("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Trend chart" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  chartNiceTicks(lo, hi, 5).forEach(tk => {
    svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(tk), y2: y(tk), stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvgEl("text", { x: ML - 9, y: y(tk) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11.5 });
    lb.textContent = fmtAxisNum(tk, unit === "%" ? 1 : 0); lb.style.fontVariantNumeric = "tabular-nums"; svg.appendChild(lb);
  });
  if (lo < 0 && hi > 0) svg.appendChild(chartSvgEl("line", { x1: ML, x2: W - MR, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1.5 }));

  const lTitle = chartSvgEl("text", { x: ML, y: 14, fill: "var(--muted2)", "font-size": 11, "font-weight": 400 });
  lTitle.textContent = unit; svg.appendChild(lTitle);

  const nT = Math.min(8, allDates.length);
  for (let i = 0; i < nT; i++) {
    const di = allDates[Math.round(i * (allDates.length - 1) / Math.max(1, nT - 1))];
    const t = chartSvgEl("text", { x: x(di), y: H - 9, fill: "var(--muted)", "font-size": 11.5, "text-anchor": i === 0 ? "start" : (i === nT - 1 ? "end" : "middle") });
    t.textContent = chartAxisLabel(di, spanDays); svg.appendChild(t);
  }

  seriesList.forEach(s => {
    let d = "";
    s.pts.forEach((p, i) => { d += (i === 0 ? "M" : "L") + x(p.date).toFixed(1) + " " + y(p.v).toFixed(1) + " "; });
    svg.appendChild(chartSvgEl("path", { d, fill: "none", stroke: chartColorOf(s.id), "stroke-width": 1.8, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  });

  const cross = chartSvgEl("line", { x1: 0, x2: 0, y1: MT, y2: H - MB, stroke: "var(--border-strong)", "stroke-width": 1, opacity: 0 });
  svg.appendChild(cross);
  const dots = chartSvgEl("g", { opacity: 0 });
  svg.appendChild(dots);
  const hit = chartSvgEl("rect", { x: ML, y: MT, width: W - ML - MR, height: H - MT - MB, fill: "transparent" });
  svg.appendChild(hit);

  const tt = document.getElementById("chart-tt");
  const HOVER_PX = 14;
  let pinned = null;
  function nearestDateAt(px) {
    let nearest = allDates[0], best = Infinity;
    for (const d of allDates) { const dist = Math.abs(x(d) - px); if (dist < best) { best = dist; nearest = d; } }
    return nearest;
  }
  function nearestLineAt(date, py) {
    let nearest = null, nearestDist = Infinity;
    seriesList.forEach(s => {
      const p = s.pts.find(pt => pt.date === date);
      if (!p) return;
      const dy = Math.abs(y(p.v) - py);
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
      dots.appendChild(chartSvgEl("circle", { cx: x(p.date), cy: y(p.v), r: 4, fill: chartColorOf(s.id), stroke: "var(--panel)", "stroke-width": 2 }));
      rows += '<tr><td><span class="sw" style="display:inline-block;background:' + chartColorOf(s.id) + '"></span> ' + escapeHtml(entityLabel(s.entity)) +
        '</td><td class="v">' + fmtAxisNum(p.v, unit === "%" ? 1 : 1) + ' ' + unit + '</td></tr>';
    });
    tt.innerHTML = '<div class="d">' + date + '</div><table>' + rows + '</table>';
    placeChartTooltip(tt, clientX, clientY);
  }
  function hideTooltip() { tt.style.display = "none"; cross.setAttribute("opacity", 0); dots.setAttribute("opacity", 0); }

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
    if (nearestLineAt(nearest, py)) return;
    if (pinned === nearest) { pinned = null; hideTooltip(); }
    else { pinned = nearest; showTooltip(pinned, seriesList, ev.clientX, ev.clientY); }
  });
  hit.addEventListener("pointerleave", () => { pinned = null; hideTooltip(); });

  host.appendChild(svg);

  const lg = document.createElement("div");
  lg.className = "legend";
  seriesList.forEach(s => {
    const span = document.createElement("span");
    span.innerHTML = '<span class="sw" style="background:' + chartColorOf(s.id) + '"></span>' + escapeHtml(entityLabel(s.entity));
    lg.appendChild(span);
  });
  host.appendChild(lg);

  renderTable(seriesList, dates);
}

function renderTable(seriesList, dates) {
  tableCols = seriesList.map(s => s.entity);

  // Build a lookup so partial-history series (nulls at either end) still line up by date.
  const byId = {};
  seriesList.forEach(s => { const m = new Map(); s.pts.forEach(p => m.set(p.date, p.v)); byId[s.entity.id] = m; });
  const baseRows = dates.map(d => {
    const row = { date: d };
    seriesList.forEach(s => { row[s.entity.id] = byId[s.entity.id].has(d) ? byId[s.entity.id].get(d) : null; });
    return row;
  }).filter(row => seriesList.length === 0 || seriesList.some(s => row[s.entity.id] !== null));

  const dataCols = [{ key: "date", label: "Date" }, ...seriesList.map(s => ({ key: s.entity.id, label: entityLabel(s.entity) }))];

  function dataFilterValue(row, key) {
    if (key === "date") return row.date;
    const v = row[key];
    return v === null || v === undefined ? "" : String(v);
  }

  function rerender() {
    const host = document.getElementById("data-table");
    withFocusPreserved(host, () => {
      const theadRow = document.getElementById("thead-row");
      const tbody = document.getElementById("tbody");
      theadRow.innerHTML = "";
      for (const c of dataCols) {
        theadRow.appendChild(buildSortFilterTh(c, dataSort, DATA_DEFAULT_SORT, dataFilters, (next) => {
          dataSort = next;
          rerender();
        }, c.key === "date" ? "" : "num"));
      }

      let rows = baseRows;
      for (const key in dataFilters) {
        const f = dataFilters[key];
        if (f) rows = rows.filter(row => dataFilterValue(row, key).toLowerCase().includes(f));
      }
      const sorted = rows.slice().sort((a, b) => {
        const key = dataSort.col;
        const av = key === "date" ? a.date : a[key], bv = key === "date" ? b.date : b[key];
        // Numeric columns: rows with no value at this date always sort last,
        // regardless of direction, rather than clumping at whichever end
        // null happens to compare to.
        if (key !== "date") {
          if (av === null && bv === null) return 0;
          if (av === null) return 1;
          if (bv === null) return -1;
        }
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return cmp * dataSort.dir;
      });

      const frag = document.createDocumentFragment();
      for (const row of sorted) {
        const tr = document.createElement("tr");
        const td0 = document.createElement("td");
        td0.textContent = row.date;
        tr.appendChild(td0);
        seriesList.forEach(s => {
          const td = document.createElement("td");
          td.className = "num";
          const v = row[s.entity.id];
          td.textContent = v === null || v === undefined ? "" : v.toLocaleString("en-US", { maximumFractionDigits: 2 });
          tr.appendChild(td);
        });
        frag.appendChild(tr);
      }
      if (!sorted.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="' + (1 + seriesList.length) + '" style="color:var(--muted);padding:10px">No rows match the current filters.</td>';
        frag.appendChild(tr);
      }
      tbody.innerHTML = "";
      tbody.appendChild(frag);
      document.getElementById("row-count").textContent =
        (sorted.length < baseRows.length
          ? sorted.length.toLocaleString("en-US") + " of " + baseRows.length.toLocaleString("en-US")
          : sorted.length.toLocaleString("en-US")) + " rows";
      tableRows = sorted;
    });
  }

  rerender();
}

function downloadCsv() {
  const cols = ["Date", ...tableCols.map(entityLabel)];
  const lines = [cols.map(csvEscape).join(",")];
  for (const row of tableRows) {
    const vals = [row.date, ...tableCols.map(e => row[e.id])];
    lines.push(vals.map(csvEscape).join(","));
  }
  downloadTextFile(lines.join("\\n"), "text/csv;charset=utf-8;", "pipeline_flows.csv");
}

async function downloadXlsx() {
  const btn = document.getElementById("btn-xlsx");
  const prevLabel = btn.textContent;
  btn.disabled = true; btn.textContent = "Building…";
  try {
    await new Promise(r => setTimeout(r, 10));
    const header = ["Date", ...tableCols.map(entityLabel)];
    const rows = [header].concat(tableRows.map(row => [row.date, ...tableCols.map(e => row[e.id])]));
    const blob = await buildWorkbookXlsxBlob([{ name: "Pipeline Flows", rows }]);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pipeline_flows.xlsx";
    a.click(); URL.revokeObjectURL(a.href);
  } finally {
    btn.disabled = false; btn.textContent = prevLabel;
  }
}

function applyQueryState() {
  const sp = gbQueryParams();
  level = gbValidEnum(sp.get("level"), ["points", "ledger"]) || level;
  viewMode = gbValidEnum(sp.get("view"), ["aggregate", "detail"]) || viewMode;
  // TSO allow-list spans both levels plus the gated minors, so a link that
  // names TSB/GOM still resolves instead of silently dropping the filter.
  const allTsos = [...new Set(
    [...(DATA.points || []), ...(DATA.pipelines || [])].map(e => e.tso).filter(Boolean)
  ), ...MINOR_TSOS];
  const tsos = gbValidList(sp.get("tso"), allTsos);
  if (tsos) {
    tsoFilter = new Set(tsos);
    if (tsos.some(t => MINOR_TSOS.includes(t))) {
      includeMinorTsos = true;
      const minorCb = document.getElementById("f-include-minor-tsos");
      if (minorCb) minorCb.checked = true;
    }
  }
  const ft = sp.get("flow");
  if (ft === RECEIPT || ft === DELIVERY) flowTypeFilter = ft;
  const pl = sp.get("pipeline");
  if (pl) pipelineFilter = pl;
  datePreset = gbValidEnum(sp.get("preset"), ["90d", "12m", "3y", "all"]) || datePreset;
  smoothing = gbValidEnum(sp.get("smooth"), ["raw", "7d", "30d"]) || smoothing;
  const q = sp.get("q");
  if (q) searchText = q.toLowerCase();
  buildLevelToggle();
  buildViewToggle();
  buildTsoToggles();
  buildFlowTypeToggles();
  buildDependentSelects();
  // An unknown pipeline degrades to "all" rather than an empty page: only
  // keep the filter when it matches a known option.
  const pipeSel = document.getElementById("f-pipeline");
  if (pipelineFilter && ![...pipeSel.options].some(o => o.value === pipelineFilter)) pipelineFilter = "";
  if (pipelineFilter) pipeSel.value = pipelineFilter;
  document.getElementById("f-preset").value = datePreset;
  document.getElementById("f-smooth").value = smoothing;
  if (q) document.getElementById("f-search").value = q;
  buildVariableSelect();
  const v = sp.get("var");
  if (v && currentVarList().includes(v)) { variable = v; document.getElementById("f-variable").value = v; }
  const picks = gbValidList(sp.get("picks"), currentEntities().map(e => e.id));
  if (picks) picked = new Set(picks);
}

function writeQueryState() {
  gbWriteQuery({
    level,
    view: viewMode,
    var: variable,
    tso: tsoFilter.size ? [...tsoFilter] : null,
    flow: flowTypeFilter || null,
    pipeline: pipelineFilter || null,
    preset: datePreset,
    smooth: smoothing,
    q: searchText || null,
    picks: (viewMode === "detail" && picked.size) ? [...picked] : null,
  });
}

function render() {
  buildTsoToggles();
  buildFlowTypeToggles();
  buildDependentSelects();
  renderKpiCards();
  buildChips();
  renderChart();
  writeQueryState();
}

function resetAllFilters() {
  tsoFilter = new Set();
  includeMinorTsos = false;
  const minorCb = document.getElementById("f-include-minor-tsos");
  if (minorCb) minorCb.checked = false;
  flowTypeFilter = ""; pipelineFilter = ""; ufFilter = ""; searchText = "";
  document.getElementById("f-pipeline").value = "";
  document.getElementById("f-uf").value = "";
  document.getElementById("f-search").value = "";
  level = "points";
  viewMode = "aggregate";
  variable = DATA.pointVars[0];
  datePreset = "12m"; document.getElementById("f-preset").value = "12m";
  smoothing = "raw"; document.getElementById("f-smooth").value = "raw";
  picked = new Set(); chartSlots = new Map();
  meterSort = { ...METER_DEFAULT_SORT }; meterFilters = {};
  dataSort = { ...DATA_DEFAULT_SORT }; dataFilters = {};
  onLevelOrVariableChanged();
}

__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
__SHARED_JS_ASOF__

async function init() {
  document.getElementById("year").textContent = new Date().getFullYear();
  const text = await inflateGzipUrl(PAYLOAD_URL);
  DATA = JSON.parse(text);
  variable = DATA.pointVars[0];

  const through = DATA.dates.length ? DATA.dates[DATA.dates.length - 1] : "—";
  document.getElementById("asof-through").textContent = through;
  initStalenessBadgeFor("flows", through);
  document.getElementById("asof-refreshed").textContent =
    formatRefreshedLocal(DATA.generatedIso, DATA.generated);

  buildKpiMonthSelect();
  applyQueryState();
  onLevelOrVariableChanged();

  const drawer = document.getElementById("filters-drawer");
  const drawerToggle = document.getElementById("filters-drawer-toggle");
  drawerToggle.addEventListener("click", () => {
    const open = drawer.classList.toggle("is-collapsed") === false;
    drawerToggle.setAttribute("aria-expanded", String(open));
  });
  document.getElementById("f-include-minor-tsos").addEventListener("change", e => {
    includeMinorTsos = e.target.checked;
    render();
  });
  document.getElementById("f-kpi-month").addEventListener("change", e => { kpiMonth = e.target.value; renderKpiCards(); });
  document.getElementById("f-pipeline").addEventListener("change", e => { pipelineFilter = e.target.value; render(); });
  document.getElementById("f-uf").addEventListener("change", e => { ufFilter = e.target.value; render(); });
  document.getElementById("f-search").addEventListener("input", e => { searchText = e.target.value.trim().toLowerCase(); render(); });
  document.getElementById("f-variable").addEventListener("change", e => {
    variable = e.target.value; picked = new Set(); chartSlots = new Map();
    if (viewMode === "detail") defaultPicks();
    render();
  });
  document.getElementById("f-preset").addEventListener("change", e => { datePreset = e.target.value; renderChart(); writeQueryState(); });
  document.getElementById("f-smooth").addEventListener("change", e => { smoothing = e.target.value; renderChart(); writeQueryState(); });
  document.getElementById("btn-clear-picks").addEventListener("click", () => { picked = new Set(); chartSlots = new Map(); render(); });
  document.getElementById("btn-reset-filters").addEventListener("click", resetAllFilters);
  document.getElementById("picker-collapse-btn").addEventListener("click", () => {
    pickerCollapsed = !pickerCollapsed;
    applyPickerCollapse();
  });
  document.getElementById("btn-csv").addEventListener("click", downloadCsv);
  document.getElementById("btn-xlsx").addEventListener("click", downloadXlsx);
  window.addEventListener("resize", () => { clearTimeout(chartResizeTimer); chartResizeTimer = setTimeout(renderChart, 140); });
  initThemeToggle("theme-toggle", renderChart);
  initLangToggle("lang-toggle");
  initCrossLinks();
  gbCopyLink("btn-share");
}
init();
</script>
</body>
</html>
"""


def write_dashboard(out_path=DEFAULT_OUT):
    payload = load_payload()
    # ADR-002 Track B + R2: payload.json.gz locally (and on R2 when configured).
    # Hub teasers still read __GENERATED__ markers from the thin HTML shell.
    sys.path.insert(0, str(HERE.parent / "shared"))
    import data_kit as dk  # noqa: E402
    payload_path, payload_href = dk.write_and_publish_artifact("flows", payload, HERE)

    html = kit.render(
        TEMPLATE,
        PAYLOAD_URL=payload_href,
        GENERATED=payload["generated"],
        KPI_TOTAL_7D=str(payload["kpiTotal7d"]) if payload["kpiTotal7d"] is not None else "",
        N_POINTS=str(payload["nPoints"]),
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_DECODE=kit.JS_DECODE,
        SHARED_JS_ESCAPE_HTML=kit.JS_ESCAPE_HTML,
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_ASOF=kit.refreshed_local_js(),
        SHARED_JS_CSV=kit.JS_CSV_HELPERS,
        SHARED_JS_XLSX=kit.JS_XLSX_ENGINE,
        SHARED_JS_CHART_PALETTE=kit.chart_palette_js(),
        SHARED_JS_QUERY_STATE=kit.JS_QUERY_STATE,
        SHARED_SHARE_BUTTON=kit.share_link_button_html(),
        SHARED_SITE_LINKS_JS=kit.site_links_js("flows"),
        SHARED_MASTHEAD=kit.masthead_html("flows"),
        SHARED_METHODOLOGY=kit.methodology_html("flows"),
        FAVICON_DATA_URI=kit.embed_favicon(),
        FONT_PRELOAD=kit.font_preload_html(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(
        f"Wrote dashboard shell ({len(html):,} bytes) + {payload_path.name} "
        f"({payload_path.stat().st_size:,} bytes, {len(payload['points'])} points, "
        f"{len(payload['pipelines'])} pipelines) → {payload_href}"
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
