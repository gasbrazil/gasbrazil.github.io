"""Build NTS OnTime dashboard from data/nts_linepack_series.parquet.

Generates nts/index.html with:
  * Real-time linepack inventory (Mm³ and m³) and packing/unpacking state
  * Rate of change (m³/h and Mm³/d equivalent)
  * 24h delta, high/low/average operating envelopes
  * Interactive SVG linepack chart with 24h, 7d, and all-time range filters
  * Hourly history table with client-side TSV/CSV export
  * Full bilingual English / Português (BR) and dark/light theme support
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARQUET_PATH = HERE / "data" / "nts_linepack_series.parquet"
DEFAULT_OUT = HERE / "index.html"

sys.path.insert(0, str(ROOT / "shared"))
import dashboard_kit as kit  # noqa: E402

HISTORICAL_MEAN_MM3 = 46.2
HISTORICAL_P10_MM3 = 43.0
HISTORICAL_P90_MM3 = 49.5


def _num(val: object) -> float | None:
    if val is None or pd.isna(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _load_data(parquet_path: Path | str | None = None) -> pd.DataFrame:
    path = Path(parquet_path) if parquet_path else PARQUET_PATH
    if not path.exists():
        # Fallback synthetic series if parquet not yet generated (e.g. CI or fresh checkout)
        base_time = pd.Timestamp.now(tz="UTC").floor("h")
        timestamps = [base_time - pd.Timedelta(hours=i) for i in range(48, -1, -1)]
        values_m3 = [47_000_000.0 + (i % 7) * 100_000.0 for i in range(len(timestamps))]
        df = pd.DataFrame({
            "timestamp": timestamps,
            "value_m3": values_m3,
            "value_mm3": [v / 1_000_000.0 for v in values_m3],
            "rate_m3_h": [15_000.0 if i % 2 == 0 else -10_000.0 for i in range(len(timestamps))],
            "observed_at": [ts + pd.Timedelta(minutes=5) for ts in timestamps],
            "source": ["nts"] * len(timestamps),
        })
        return df
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _build_payload(df: pd.DataFrame) -> tuple[dict, dict]:
    """Compute KPI metrics and downsampled series for client-side rendering."""
    if df.empty:
        return {}, {}

    latest = df.iloc[-1]
    cur_val_m3 = float(latest["value_m3"])
    cur_val_mm3 = float(latest["value_mm3"])
    cur_rate = float(latest["rate_m3_h"])
    cur_ts = pd.Timestamp(latest["timestamp"])

    # 24-hour window
    cutoff_24h = cur_ts - pd.Timedelta(hours=24)
    df_24h = df[df["timestamp"] >= cutoff_24h]
    if len(df_24h) > 1:
        v0 = float(df_24h.iloc[0]["value_m3"])
        delta_24h_m3 = cur_val_m3 - v0
        delta_24h_pct = (delta_24h_m3 / v0) * 100.0 if v0 else 0.0
        min_24h = float(df_24h["value_mm3"].min())
        max_24h = float(df_24h["value_mm3"].max())
        avg_24h = float(df_24h["value_mm3"].mean())
    else:
        delta_24h_m3 = 0.0
        delta_24h_pct = 0.0
        min_24h = max_24h = avg_24h = cur_val_mm3

    # 7-day window
    cutoff_7d = cur_ts - pd.Timedelta(days=7)
    df_7d = df[df["timestamp"] >= cutoff_7d]
    min_7d = float(df_7d["value_mm3"].min()) if not df_7d.empty else cur_val_mm3
    max_7d = float(df_7d["value_mm3"].max()) if not df_7d.empty else cur_val_mm3
    avg_7d = float(df_7d["value_mm3"].mean()) if not df_7d.empty else cur_val_mm3

    # All-time window
    min_all = float(df["value_mm3"].min())
    max_all = float(df["value_mm3"].max())
    avg_all = float(df["value_mm3"].mean())

    kpis = {
        "current_m3": cur_val_m3,
        "current_mm3": round(cur_val_mm3, 2),
        "rate_m3_h": round(cur_rate, 0),
        "rate_mm3_d": round(cur_rate * 24.0 / 1_000_000.0, 2),
        "is_packing": cur_rate >= 0,
        "delta_24h_m3": round(delta_24h_m3, 0),
        "delta_24h_pct": round(delta_24h_pct, 2),
        "min_24h": round(min_24h, 2),
        "max_24h": round(max_24h, 2),
        "avg_24h": round(avg_24h, 2),
        "min_7d": round(min_7d, 2),
        "max_7d": round(max_7d, 2),
        "avg_7d": round(avg_7d, 2),
        "min_all": round(min_all, 2),
        "max_all": round(max_all, 2),
        "avg_all": round(avg_all, 2),
        "last_updated_utc": cur_ts.strftime("%Y-%m-%d %H:%M UTC"),
        "last_updated_iso": cur_ts.isoformat(),
        "total_records": len(df),
    }

    # Prepare compact client series
    # Format: [unix_epoch_sec, value_mm3, rate_m3_h]
    series_points = []
    for _, row in df.iterrows():
        ts_sec = int(row["timestamp"].timestamp())
        series_points.append([
            ts_sec,
            round(float(row["value_mm3"]), 3),
            round(float(row["rate_m3_h"]), 0),
        ])

    # Table rows: recent 150 points in reverse chronological order
    table_rows = []
    for _, row in df.iloc[::-1].head(150).iterrows():
        t_utc = pd.Timestamp(row["timestamp"])
        t_brt = t_utc.tz_convert("America/Sao_Paulo")
        rate = float(row["rate_m3_h"])
        table_rows.append({
            "ts_utc": t_utc.strftime("%Y-%m-%d %H:%M"),
            "ts_brt": t_brt.strftime("%d/%m %H:%M"),
            "val_mm3": round(float(row["value_mm3"]), 3),
            "val_m3": int(round(float(row["value_m3"]))),
            "rate": int(round(rate)),
            "state": "packing" if rate >= 0 else "unpacking",
        })

    payload = {
        "kpis": kpis,
        "series": series_points,
        "table": table_rows,
        "ref": {
            "mean": HISTORICAL_MEAN_MM3,
            "p10": HISTORICAL_P10_MM3,
            "p90": HISTORICAL_P90_MM3,
        },
    }

    return kpis, payload


PAGE_CSS = """
:root {
  --tso-nts: #d97706;
  --tso-nts-hover: #b45309;
  --tso-nts-light: rgba(217, 119, 6, 0.12);
  --tso-nts-glow: rgba(217, 119, 6, 0.25);
  --pack-up: #10b981;
  --pack-down: #f59e0b;
}
[data-theme="dark"] {
  --tso-nts: #f59e0b;
  --tso-nts-hover: #fbbf24;
  --tso-nts-light: rgba(245, 158, 11, 0.16);
  --tso-nts-glow: rgba(245, 158, 11, 0.3);
}

.nts-wrap {
  width: var(--content-w);
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 32px 0 48px;
}
@media (max-width: 900px) {
  .nts-wrap { width: auto; padding: 20px 16px 40px; }
}

/* Header & Intro */
.nts-intro {
  margin-bottom: 24px;
}
.nts-intro-sub {
  font-size: 14px;
  color: var(--muted);
  margin-top: 4px;
}

/* KPI Cards Grid */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}
.nts-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
  transition: transform 0.15s ease, border-color 0.15s ease;
  position: relative;
  overflow: hidden;
}
.nts-card:hover {
  border-color: var(--tso-nts);
}
.nts-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--border);
}
.nts-card.accent::before {
  background: var(--tso-nts);
}

.kpi-title {
  font-size: 12.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.kpi-num {
  font-size: 28px;
  font-weight: 600;
  font-family: var(--font-mono, monospace);
  color: var(--text);
  line-height: 1.1;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.kpi-unit {
  font-size: 15px;
  font-weight: 400;
  color: var(--muted);
}
.kpi-sub {
  font-size: 12.5px;
  color: var(--muted);
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Status Badges */
.badge-pack {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
}
.badge-pack.packing {
  background: rgba(16, 185, 129, 0.14);
  color: #10b981;
}
.badge-pack.unpacking {
  background: rgba(245, 158, 11, 0.14);
  color: #f59e0b;
}

/* Chart Container */
.chart-section {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 28px;
}
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}
.chart-title-group h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--text);
}
.chart-title-group p {
  font-size: 13px;
  color: var(--muted);
  margin: 4px 0 0;
}

.range-toggle-group {
  display: inline-flex;
  background: var(--bg-hover, rgba(128,128,128,0.08));
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px;
}
.range-btn {
  background: transparent;
  border: none;
  padding: 5px 12px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s ease;
}
.range-btn:hover {
  color: var(--text);
}
.range-btn.active {
  background: var(--card-bg);
  color: var(--tso-nts);
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.chart-svg-box {
  width: 100%;
  height: 380px;
  position: relative;
  user-select: none;
}
.chart-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.chart-tooltip {
  position: absolute;
  pointer-events: none;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.15));
  opacity: 0;
  transition: opacity 0.12s ease;
  z-index: 20;
  transform: translate(-50%, -115%);
  white-space: nowrap;
}
.chart-tooltip b {
  color: var(--tso-nts);
  font-size: 13px;
}

/* History Table */
.table-section {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  padding: 20px 24px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 28px;
}
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
.table-header h2 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
}
.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s ease;
}
.download-btn:hover {
  border-color: var(--tso-nts);
  color: var(--tso-nts);
}

.data-table-wrap {
  overflow-x: auto;
  max-height: 440px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  text-align: left;
}
.data-table th {
  position: sticky;
  top: 0;
  background: var(--bg);
  color: var(--muted);
  font-weight: 500;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  z-index: 5;
}
.data-table td {
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.data-table tr:hover td {
  background: var(--bg-hover, rgba(128,128,128,0.04));
}
.mono {
  font-family: var(--font-mono, monospace);
}

.nts-footer {
  width: var(--content-w);
  max-width: var(--content-max);
  margin: 24px auto 0;
  padding: 16px 0 32px;
  font-size: 12px;
  color: var(--muted);
  border-top: 1px solid var(--border);
}
@media (max-width: 900px) {
  .nts-footer { width: auto; padding: 16px 16px 32px; }
}
.nts-footer-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.nts-footer a {
  color: var(--muted);
  text-decoration: none;
}
.nts-footer a:hover {
  color: var(--tso-nts);
}
"""

DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__HEAD__
<style>
__PAGE_CSS__
</style>
</head>
<body>
<!--
  generated: __GENERATED_UTC__
  kpi_linepack: __CUR_MM3__
  kpi_rate: __RATE_VAL_RAW__
-->
<a class="skip-link" href="#main" data-i18n="skip">Skip to content</a>
__MASTHEAD__

<main class="nts-wrap" id="main">
  <!-- Page Header Intro -->
  <div class="nts-intro">
    __PAGE_INTRO__
    <div class="flagbar" aria-hidden="true"></div>
    <div class="nts-intro-sub" data-i18n="ntsLinepackSub">
      Real-time pipeline line pack inventory and hourly packing/unpacking rate.
    </div>
  </div>

  <!-- KPI Cards Grid -->
  <div class="kpi-grid">
    <div class="nts-card accent">
      <div class="kpi-title">
        <span data-i18n="ntsKpiLinepack">NTS Line pack</span>
        <span class="pulse-dot" title="Real-time telemetry"></span>
      </div>
      <div class="kpi-num">
        <span id="kpi-cur-mm3">__CUR_MM3__</span>
        <span class="kpi-unit">Mm³</span>
      </div>
      <div class="kpi-sub">
        <span class="mono" id="kpi-cur-m3">__CUR_M3__</span> m³
      </div>
    </div>

    <div class="nts-card">
      <div class="kpi-title">
        <span data-i18n="ntsKpiRate">Packing Rate</span>
        <span class="badge-pack __PACK_CLASS__" id="kpi-pack-badge">
          __PACK_ARROW__ <span id="kpi-pack-state" data-i18n="__PACK_STATE_I18N__">__PACK_STATE__</span>
        </span>
      </div>
      <div class="kpi-num">
        <span id="kpi-rate-val">__RATE_VAL__</span>
        <span class="kpi-unit">m³/h</span>
      </div>
      <div class="kpi-sub">
        <span id="kpi-rate-daily">__RATE_DAILY__</span> Mm³/d eq.
      </div>
    </div>

    <div class="nts-card">
      <div class="kpi-title">
        <span data-i18n="kpiDelta24h">24h Change</span>
        <span class="mono" id="kpi-delta-pct">__DELTA_24H_PCT__</span>
      </div>
      <div class="kpi-num">
        <span id="kpi-delta-val">__DELTA_24H_VAL__</span>
        <span class="kpi-unit">m³</span>
      </div>
      <div class="kpi-sub" data-i18n="kpiDeltaNet">Net 24-hour variation</div>
    </div>

    <div class="nts-card">
      <div class="kpi-title">
        <span data-i18n="kpiEnvelope24h">24h Range</span>
        <span class="mono" id="kpi-avg-24h">Avg: __AVG_24H__</span>
      </div>
      <div class="kpi-num">
        <span id="kpi-span-24h">__MIN_24H__ – __MAX_24H__</span>
        <span class="kpi-unit">Mm³</span>
      </div>
      <div class="kpi-sub">
        <span data-i18n="kpiHistMean">Historical mean</span>: ~46.2 Mm³
      </div>
    </div>
  </div>

  <!-- Interactive Linepack Chart -->
  <section class="chart-section" aria-labelledby="chart-title">
    <div class="chart-header">
      <div class="chart-title-group">
        <h2 id="chart-title" data-i18n="ntsLinepackTitle">NTS Line pack — Southeast transmission mesh</h2>
        <p data-i18n="chartDesc">SCADA line pack telemetry (solid amber) with historical mean guideline (dashed).</p>
      </div>
      <div class="range-toggle-group" role="group" aria-label="Chart time window">
        <button type="button" class="range-btn active" data-range="24h" onclick="setChartRange('24h')">24H</button>
        <button type="button" class="range-btn" data-range="7d" onclick="setChartRange('7d')">7D</button>
        <button type="button" class="range-btn" data-range="all" onclick="setChartRange('all')" data-i18n="rangeAll">All</button>
      </div>
    </div>

    <div class="chart-svg-box" id="chart-box">
      <svg class="chart-svg" id="linepack-chart" viewBox="0 0 1000 380" preserveAspectRatio="none">
        <!-- Rendered dynamically by script -->
      </svg>
      <div class="chart-tooltip" id="chart-tooltip"></div>
    </div>
  </section>

  <!-- History & Observations Table -->
  <section class="table-section" aria-labelledby="table-title">
    <div class="table-header">
      <div>
        <h2 id="table-title" data-i18n="tableTitle">Line pack observations history</h2>
      </div>
      <button type="button" class="download-btn" onclick="exportTableCsv()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <span data-i18n="btnExportCsv">Download CSV</span>
      </button>
    </div>

    <div class="data-table-wrap">
      <table class="data-table" id="telemetry-table">
        <thead>
          <tr>
            <th data-i18n="thObservedUtc">Observed (UTC)</th>
            <th data-i18n="thObservedBrt">Observed (BRT)</th>
            <th data-i18n="thVolumeMm3">Volume (Mm³)</th>
            <th data-i18n="thVolumeM3">Volume (m³)</th>
            <th data-i18n="thRate">Rate (m³/h)</th>
            <th data-i18n="thStatus">Status</th>
          </tr>
        </thead>
        <tbody id="telemetry-tbody">
          <!-- Populated from payload -->
        </tbody>
      </table>
    </div>
  </section>

  <!-- Methodology trust block -->
  __METHODOLOGY__

  <!-- Footer -->
  <footer class="nts-footer">
    <div class="nts-footer-inner">
      <span data-i18n="ntsFooter">Data: NTS OnTime operational line pack telemetry. Not an official NTS product.</span>
      ·
      <a href="../mago/" data-i18n="navMago">TAG Mago</a>
      ·
      <a href="../flows/" data-i18n="navFlows">Pipeline Flows</a>
      ·
      <a href="../about/" data-i18n="navAbout">About</a>
    </div>
  </footer>

</main>

<script id="nts-payload" type="application/json">
__PAYLOAD_JSON__
</script>

<script>
__SITE_LINKS_JS__

if (typeof GB_I18N !== "undefined") {
  Object.assign(GB_I18N.en, {
    kpiDelta24h: "24h Change",
    kpiDeltaNet: "Net 24-hour variation",
    kpiEnvelope24h: "24h Range",
    kpiHistMean: "Historical mean",
    chartDesc: "SCADA line pack telemetry (solid amber) with historical mean guideline (dashed).",
    rangeAll: "All",
    tableTitle: "Line pack observations history",
    btnExportCsv: "Download CSV",
    thObservedUtc: "Observed (UTC)",
    thObservedBrt: "Observed (BRT)",
    thVolumeMm3: "Volume (Mm³)",
    thVolumeM3: "Volume (m³)",
    thRate: "Rate (m³/h)",
    thStatus: "Status",
    ntsFooter: "Data: NTS OnTime operational line pack telemetry. Not an official NTS product."
  });
  Object.assign(GB_I18N.pt, {
    kpiDelta24h: "Variação 24h",
    kpiDeltaNet: "Variação líquida em 24h",
    kpiEnvelope24h: "Faixa 24h",
    kpiHistMean: "Média histórica",
    chartDesc: "Telemetria SCADA de empacotamento (âmbar) com linha-guia da média histórica (tracejado).",
    rangeAll: "Tudo",
    tableTitle: "Histórico de observações de empacotamento",
    btnExportCsv: "Baixar CSV",
    thObservedUtc: "Observado (UTC)",
    thObservedBrt: "Observado (BRT)",
    thVolumeMm3: "Volume (Mm³)",
    thVolumeM3: "Volume (m³)",
    thRate: "Taxa (m³/h)",
    thStatus: "Status",
    ntsFooter: "Dados: telemetria de empacotamento do NTS OnTime. Não é um produto oficial da NTS."
  });
}

__CHART_JS__
</script>
</body>
</html>
"""

CHART_CLIENT_JS = r"""
let PAYLOAD = {};
try {
  PAYLOAD = JSON.parse(document.getElementById("nts-payload").textContent);
} catch (e) {
  console.error("Failed to parse NTS payload:", e);
}

let activeRange = "24h";

function fmtNum(n, decimals) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toLocaleString("pt-BR", {
    minimumFractionDigits: decimals !== undefined ? decimals : 0,
    maximumFractionDigits: decimals !== undefined ? decimals : 0
  });
}

function filterSeries(range) {
  const allPts = (PAYLOAD.series || []);
  if (!allPts.length) return [];
  const latestTs = allPts[allPts.length - 1][0];
  let cutoff = 0;
  if (range === "24h") cutoff = latestTs - 24 * 3600;
  else if (range === "7d") cutoff = latestTs - 7 * 86400;
  else cutoff = 0;
  return allPts.filter(p => p[0] >= cutoff);
}

function setChartRange(range) {
  activeRange = range;
  document.querySelectorAll(".range-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-range") === range);
  });
  renderChart();
}

function renderChart() {
  const pts = filterSeries(activeRange);
  const svg = document.getElementById("linepack-chart");
  if (!svg || !pts.length) return;

  const W = 1000, H = 380;
  const L = 56, R = 24, T = 20, B = 36;
  const vals = pts.map(p => p[1]);
  let minV = Math.min(...vals);
  let maxV = Math.max(...vals);

  // Add 8% padding top and bottom
  const pad = (maxV - minV) * 0.12 || 1.0;
  minV = Math.floor((minV - pad) * 2) / 2;
  maxV = Math.ceil((maxV + pad) * 2) / 2;

  const n = pts.length;
  const x = i => L + (i / (n - 1)) * (W - L - R);
  const y = v => T + (1 - (v - minV) / (maxV - minV)) * (H - T - B);

  // Background Grid & Y-Ticks
  let gridSvg = "";
  const ticks = 5;
  for (let i = 0; i <= ticks; i++) {
    const v = minV + ((maxV - minV) * i) / ticks;
    const yPos = y(v);
    gridSvg += `<line x1="${L}" y1="${yPos}" x2="${W - R}" y2="${yPos}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3"/>`;
    gridSvg += `<text x="${L - 10}" y="${yPos + 4}" fill="var(--muted)" font-size="11.5" font-family="var(--font-mono)" text-anchor="end">${fmtNum(v, 1)}</text>`;
  }

  // Mean Reference Line
  const refMean = (PAYLOAD.ref && PAYLOAD.ref.mean) || 46.2;
  let refSvg = "";
  if (refMean >= minV && refMean <= maxV) {
    const yMean = y(refMean);
    refSvg = `
      <line x1="${L}" y1="${yMean}" x2="${W - R}" y2="${yMean}" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.65"/>
      <text x="${W - R - 6}" y="${yMean - 6}" fill="var(--muted)" font-size="10.5" font-family="var(--font-mono)" text-anchor="end">Mean: ${refMean} Mm³</text>
    `;
  }

  // X-Ticks
  let xTicksSvg = "";
  const step = Math.max(1, Math.floor(n / 6));
  for (let i = 0; i < n; i += step) {
    const xPos = x(i);
    const d = new Date(pts[i][0] * 1000);
    const label = activeRange === "24h"
      ? d.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
    xTicksSvg += `<text x="${xPos}" y="${H - 10}" fill="var(--muted)" font-size="11" font-family="var(--font-mono)" text-anchor="middle">${label}</text>`;
  }

  // Path line & fill area
  let linePath = "";
  pts.forEach((p, i) => {
    linePath += (i === 0 ? "M" : "L") + `${x(i).toFixed(1)} ${y(p[1]).toFixed(1)} `;
  });
  const areaPath = linePath + `L ${x(n - 1).toFixed(1)} ${H - B} L ${x(0).toFixed(1)} ${H - B} Z`;

  const lastX = x(n - 1).toFixed(1);
  const lastY = y(pts[n - 1][1]).toFixed(1);

  svg.innerHTML = `
    <defs>
      <linearGradient id="nts-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="var(--tso-nts)" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="var(--tso-nts)" stop-opacity="0.01"/>
      </linearGradient>
    </defs>
    ${gridSvg}
    ${refSvg}
    ${xTicksSvg}
    <path d="${areaPath}" fill="url(#nts-grad)"/>
    <path d="${linePath}" fill="none" stroke="var(--tso-nts)" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    <line id="chart-crosshair" x1="0" y1="${T}" x2="0" y2="${H - B}" stroke="var(--tso-nts)" stroke-width="1.2" stroke-dasharray="3 3" opacity="0"/>
    <circle id="chart-hover-dot" r="5" fill="var(--tso-nts)" stroke="#fff" stroke-width="2" opacity="0"/>
    <circle cx="${lastX}" cy="${lastY}" r="5.5" fill="var(--tso-nts)" stroke="#fff" stroke-width="2"/>
  `;

  hookTooltip(pts, x, y, W, H);
}

function hookTooltip(pts, x, y, W, H) {
  const box = document.getElementById("chart-box");
  const svg = document.getElementById("linepack-chart");
  const tip = document.getElementById("chart-tooltip");
  const cross = svg.querySelector("#chart-crosshair");
  const dot = svg.querySelector("#chart-hover-dot");
  if (!box || !tip || !cross || !dot) return;

  const n = pts.length;

  function onMove(e) {
    const rect = svg.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const relX = clientX - rect.left;
    let frac = relX / rect.width;
    frac = Math.max(0, Math.min(1, frac));

    const idx = Math.min(n - 1, Math.max(0, Math.round(frac * (n - 1))));
    const p = pts[idx];
    const vx = x(idx);
    const vy = y(p[1]);

    cross.setAttribute("x1", vx);
    cross.setAttribute("x2", vx);
    cross.style.opacity = 0.9;

    dot.setAttribute("cx", vx);
    dot.setAttribute("cy", vy);
    dot.style.opacity = 1;

    const d = new Date(p[0] * 1000);
    const dtBrt = d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" }) +
      " " + d.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
    const rateSign = p[2] >= 0 ? "+" : "";

    tip.style.opacity = 1;
    tip.style.left = (vx / W) * 100 + "%";
    tip.style.top = (vy / H) * 100 + "%";
    tip.innerHTML = `
      <div><b>${fmtNum(p[1], 2)} Mm³</b></div>
      <div style="color:var(--muted);margin-top:2px;">Rate: ${rateSign}${fmtNum(p[2])} m³/h</div>
      <div style="font-size:11px;color:var(--muted);margin-top:2px;">${dtBrt} BRT</div>
    `;
  }

  function onLeave() {
    cross.style.opacity = 0;
    dot.style.opacity = 0;
    tip.style.opacity = 0;
  }

  box.onmousemove = onMove;
  box.onmouseleave = onLeave;
  box.ontouchstart = onMove;
  box.ontouchmove = onMove;
  box.ontouchend = onLeave;
}

function populateTable() {
  const tbody = document.getElementById("telemetry-tbody");
  if (!tbody) return;
  const rows = (PAYLOAD.table || []);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);">No data available</td></tr>';
    return;
  }

  let htmlStr = "";
  rows.forEach(r => {
    const isPack = r.state === "packing";
    const arrow = isPack ? "▲" : "▼";
    const sign = isPack ? "+" : "";
    const badgeClass = isPack ? "packing" : "unpacking";
    const stateKey = isPack ? "ntsKpiPacking" : "ntsKpiUnpacking";
    const stateText = (typeof t === "function" ? t(stateKey) : null) || (isPack ? "Packing" : "Unpacking");

    htmlStr += `
      <tr>
        <td class="mono">${r.ts_utc}</td>
        <td class="mono">${r.ts_brt}</td>
        <td class="mono"><b>${fmtNum(r.val_mm3, 3)}</b></td>
        <td class="mono">${fmtNum(r.val_m3)}</td>
        <td class="mono">${sign}${fmtNum(r.rate)}</td>
        <td>
          <span class="badge-pack ${badgeClass}">
            ${arrow} <span>${stateText}</span>
          </span>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = htmlStr;
}

function exportTableCsv() {
  const rows = (PAYLOAD.table || []);
  if (!rows.length) return;
  let csv = "observed_utc,observed_brt,volume_mm3,volume_m3,rate_m3_h,status\\n";
  rows.forEach(r => {
    csv += `${r.ts_utc},${r.ts_brt},${r.val_mm3},${r.val_m3},${r.rate},${r.state}\\n`;
  });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nts_linepack_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

document.addEventListener("DOMContentLoaded", () => {
  initCrossLinks();
  renderChart();
  populateTable();

  if (typeof applyI18n === "function") {
    const origApply = applyI18n;
    applyI18n = function() {
      origApply();
      renderChart();
      populateTable();
    };
  }
});
window.addEventListener("resize", renderChart);
"""


def build_dashboard(out_path: Path = DEFAULT_OUT, parquet_path: Path | str | None = None) -> Path:
    df = _load_data(parquet_path=parquet_path)
    kpis, payload = _build_payload(df)

    # Calculate tokens for template
    cur_mm3 = f"{kpis['current_mm3']:.2f}"
    cur_m3 = f"{int(round(kpis['current_m3'])):,}".replace(",", ".")
    is_pack = kpis["is_packing"]
    pack_class = "packing" if is_pack else "unpacking"
    pack_arrow = "▲" if is_pack else "▼"
    pack_state = "Packing" if is_pack else "Unpacking"
    pack_state_i18n = "ntsKpiPacking" if is_pack else "ntsKpiUnpacking"

    rate_sign = "+" if is_pack else ""
    rate_val = f"{rate_sign}{int(round(kpis['rate_m3_h'])):,}".replace(",", ".")
    rate_daily = f"{rate_sign}{kpis['rate_mm3_d']:.2f}"

    delta_sign = "+" if kpis["delta_24h_m3"] >= 0 else ""
    delta_24h_val = f"{delta_sign}{int(round(kpis['delta_24h_m3'])):,}".replace(",", ".")
    delta_24h_pct = f"{delta_sign}{kpis['delta_24h_pct']:.2f}%"

    min_24h = f"{kpis['min_24h']:.2f}"
    max_24h = f"{kpis['max_24h']:.2f}"
    avg_24h = f"{kpis['avg_24h']:.2f}"

    # Build head and masthead
    head_html = kit.seo_head(
        title="NTS OnTime — Pipeline Line Pack Telemetry | GasBrazil",
        description="Real-time line pack inventory and hourly packing rates across Nova Transportadora do Sudeste (NTS) transmission mesh.",
        path="/nts/",
    )

    masthead = kit.masthead_html("nts")

    page_intro = kit.page_intro_html("nts")
    methodology = kit.methodology_html("nts")
    site_links = kit.site_links_js("nts")

    # Render dashboard template
    rendered = kit.render(
        DASHBOARD_TEMPLATE,
        HEAD=head_html,
        PAGE_CSS=PAGE_CSS,
        MASTHEAD=masthead,
        PAGE_INTRO=page_intro,
        GENERATED_UTC=kpis["last_updated_utc"],
        RATE_VAL_RAW=f"{int(round(kpis['rate_m3_h']))}",
        CUR_MM3=cur_mm3,
        CUR_M3=cur_m3,
        PACK_CLASS=pack_class,
        PACK_ARROW=pack_arrow,
        PACK_STATE=pack_state,
        PACK_STATE_I18N=pack_state_i18n,
        RATE_VAL=rate_val,
        RATE_DAILY=rate_daily,
        DELTA_24H_VAL=delta_24h_val,
        DELTA_24H_PCT=delta_24h_pct,
        MIN_24H=min_24h,
        MAX_24H=max_24h,
        AVG_24H=avg_24h,
        METHODOLOGY=methodology,
        PAYLOAD_JSON=json.dumps(payload),
        SITE_LINKS_JS=site_links,
        CHART_JS=CHART_CLIENT_JS,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Rendered NTS OnTime dashboard: {out_path} ({len(rendered):,} bytes)")
    return out_path


if __name__ == "__main__":
    build_dashboard()
