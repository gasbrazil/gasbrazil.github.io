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
from mago_client import DEFAULT_FAIXAS_INTEGRATED  # noqa: E402

HERE = Path(__file__).parent
PARQUET_PATH = HERE / "data" / "tag_mago_series.parquet"
DEFAULT_OUT = HERE / "index.html"

FAIXA_INFO = [
    {
        "key": "severo_superior",
        "name_en": "Critical High",
        "name_pt": "Severo (Superior)",
        "color": "#ef4444",
        "badge_class": "badge-danger",
        "desc_en": "Critical overpack: venting / relief risk, maximum imbalance penalty",
        "desc_pt": "Empacotamento crítico elevado: risco de alívio e penalidades máximas",
    },
    {
        "key": "alto_superior",
        "name_en": "High Alert",
        "name_pt": "Alto (Superior)",
        "color": "#f59e0b",
        "badge_class": "badge-warning",
        "desc_en": "High inventory: network balancing actions / penalties apply",
        "desc_pt": "Inventário elevado: ações comerciais e penalidades aplicáveis",
    },
    {
        "key": "baixo_superior",
        "name_en": "Mild High",
        "name_pt": "Baixo (Superior)",
        "color": "#10b981",
        "badge_class": "badge-success",
        "desc_en": "Mild high inventory above target operating envelope",
        "desc_pt": "Inventário moderadamente alto, acima da faixa ideal",
    },
    {
        "key": "marginal",
        "name_en": "Target Operating",
        "name_pt": "Marginal (Operação Ideal)",
        "color": "#10b981",
        "badge_class": "badge-target",
        "desc_en": "Optimal operating envelope: standard transport, zero imbalance penalty",
        "desc_pt": "Faixa de operação ideal: transporte neutro sem penalidades",
    },
    {
        "key": "baixo_inferior",
        "name_en": "Mild Low",
        "name_pt": "Baixo (Inferior)",
        "color": "#10b981",
        "badge_class": "badge-success",
        "desc_en": "Mild low inventory below target operating envelope",
        "desc_pt": "Inventário moderadamente baixo, abaixo da faixa ideal",
    },
    {
        "key": "alto_inferior",
        "name_en": "Low Alert",
        "name_pt": "Alto (Inferior)",
        "color": "#f59e0b",
        "badge_class": "badge-warning",
        "desc_en": "Low inventory: transport system alert, balancing injections needed",
        "desc_pt": "Inventário reduzido: alerta no sistema, compras de gás pela transportadora",
    },
    {
        "key": "severo_inferior",
        "name_en": "Critical Low",
        "name_pt": "Severo (Inferior)",
        "color": "#ef4444",
        "badge_class": "badge-danger",
        "desc_en": "Critical underpack: risk of system depressurization and supply curtailment",
        "desc_pt": "Empacotamento criticamente baixo: risco de despressurização e corte",
    },
]


def determine_linepack_zone(val_m3: float | None, bands: dict[str, float]) -> dict:
    if val_m3 is None or pd.isna(val_m3):
        return {
            "key": "unknown",
            "name": "Unknown",
            "namePt": "Desconhecido",
            "color": "#9ca3af",
            "badgeClass": "badge-unknown",
            "isAlert": False,
            "isCritical": False,
        }
    sev_sup = bands["severo_superior"]
    bx_sup = bands["baixo_superior"]
    mg_sup = bands["marginal_superior"]
    mg_inf = bands["marginal_inferior"]
    bx_inf = bands["baixo_inferior"]
    sev_inf = bands["severo_inferior"]

    if val_m3 >= sev_sup:
        k = "severo_superior"
    elif val_m3 >= bx_sup:
        k = "alto_superior"
    elif val_m3 >= mg_sup:
        k = "baixo_superior"
    elif val_m3 >= mg_inf:
        k = "marginal"
    elif val_m3 >= bx_inf:
        k = "baixo_inferior"
    elif val_m3 >= sev_inf:
        k = "alto_inferior"
    else:
        k = "severo_inferior"

    info = next((item for item in FAIXA_INFO if item["key"] == k), FAIXA_INFO[3])
    return {
        "key": k,
        "name": info["name_en"],
        "namePt": info["name_pt"],
        "color": info["color"],
        "badgeClass": info["badge_class"],
        "isAlert": k in ("severo_superior", "alto_superior", "alto_inferior", "severo_inferior"),
        "isCritical": k in ("severo_superior", "severo_inferior"),
    }


def _extract_tolerance_bands(snap_df: pd.DataFrame) -> dict[str, float]:
    bands = dict(DEFAULT_FAIXAS_INTEGRATED)
    faixas_df = snap_df[
        (snap_df["series"] == "linepack_tolerance_band") & (snap_df["mesh"] == "integrated")
    ]
    if not faixas_df.empty:
        for band_key in DEFAULT_FAIXAS_INTEGRATED:
            band_rows = faixas_df[faixas_df["zone"] == band_key]
            if not band_rows.empty:
                val = band_rows.sort_values("observed_at")["value"].iloc[-1]
                if val and not pd.isna(val) and val >= 1_000_000:
                    bands[band_key] = round(float(val), 2)
    return bands


def _linepack_history(df: pd.DataFrame, default_bands: dict[str, float]) -> tuple[dict, list[dict]]:
    lp = df[(df["series"] == "linepack_actual") & (df["mesh"] == "integrated")].copy()
    if lp.empty:
        return {"times": [], "values": []}, []
    lp = lp.sort_values(["observed_at", "snapshot_at"])
    lp = lp.drop_duplicates(subset=["observed_at"], keep="last")
    series = _series_pack(lp)

    bands_by_snap: dict[pd.Timestamp, dict[str, float]] = {}
    faixas_all = df[
        (df["series"] == "linepack_tolerance_band") & (df["mesh"] == "integrated")
    ]
    if not faixas_all.empty:
        for snap_ts, group in faixas_all.groupby("snapshot_at"):
            snap_bands = dict(default_bands)
            for b_key in default_bands:
                b_match = group[group["zone"] == b_key]
                if not b_match.empty:
                    val = b_match.sort_values("observed_at")["value"].iloc[-1]
                    if val and not pd.isna(val) and val >= 1_000_000:
                        snap_bands[b_key] = round(float(val), 2)
            bands_by_snap[snap_ts] = snap_bands

    rows: list[dict] = []
    for _, row in lp.iterrows():
        val = _num(row["value"])
        snap_ts = pd.Timestamp(row["snapshot_at"])
        active_bands = bands_by_snap.get(snap_ts, default_bands)
        zone_info = determine_linepack_zone(val, active_bands)
        rows.append(
            {
                "observedAt": pd.Timestamp(row["observed_at"]).strftime("%Y-%m-%dT%H:%M"),
                "snapshotAt": snap_ts.strftime("%Y-%m-%dT%H:%M"),
                "valueM3": val,
                "valueMm3": None if val is None else round(val / 1_000_000, 4),
                "zone": zone_info["key"],
                "zoneLabel": zone_info["name"],
                "zoneLabelPt": zone_info["namePt"],
                "badgeClass": zone_info["badgeClass"],
                "isAlert": zone_info["isAlert"],
                "isCritical": zone_info["isCritical"],
            }
        )
    return series, rows


def _load_poc_balancing_correlation() -> dict[str, list[dict]]:
    """Scan available POC parquet stores for TAG transport balancing events."""
    candidates = [
        HERE.parents[0] / "poc" / "data" / "poc_results.parquet",
        HERE.parents[0] / "lake" / "poc" / "poc_results.parquet",
        HERE.parents[0] / "lake" / "transport" / "poc_results.parquet",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            pdf = pd.read_parquet(p)
            if "Transporter (TSO)" not in pdf.columns:
                continue
            is_tag = pdf["Transporter (TSO)"].astype(str).str.contains("TAG|Associada", case=False, na=False)
            tag_df = pdf[is_tag].copy()
            if tag_df.empty:
                continue
            date_col = "Trade Date" if "Trade Date" in tag_df.columns else "Flow Date Start"
            if date_col not in tag_df.columns:
                continue
            tag_df = tag_df.dropna(subset=[date_col])
            tag_df["_dt"] = pd.to_datetime(tag_df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
            by_date: dict[str, list[dict]] = {}
            for _, r in tag_df.iterrows():
                d_str = r["_dt"]
                if not d_str or pd.isna(d_str):
                    continue
                by_date.setdefault(d_str, []).append({
                    "processCode": str(r.get("codigoProcesso") or ""),
                    "transactionType": str(r.get("Transaction Type") or ""),
                    "serviceType": str(r.get("Service Type") or ""),
                    "price": _num(r.get("Price")),
                    "volumeAccepted": _num(r.get("Volume Accepted")),
                    "date": d_str,
                })
            return by_date
        except Exception:
            continue
    return {}


def _build_linepack_heatmap(
    lp_rows: list[dict],
    poc_by_date: dict[str, list[dict]] | None = None,
) -> tuple[list[dict], dict]:
    """Group hourly linepack records by UTC day and calculate risk breach statistics."""
    if not lp_rows:
        return [], {
            "totalDays": 0,
            "totalHours": 0,
            "compliancePct": 100.0,
            "totalAlertHours": 0,
            "totalCriticalHours": 0,
            "alertDaysCount": 0,
            "criticalDaysCount": 0,
            "hasPocActions": False,
        }
    poc_map = poc_by_date or {}
    days_dict: dict[str, list[dict]] = {}
    for r in lp_rows:
        day = str(r.get("observedAt") or "")[:10]
        if day:
            days_dict.setdefault(day, []).append(r)

    daily_heatmap: list[dict] = []
    tot_alert_hours = 0
    tot_critical_hours = 0
    tot_hours = 0
    tot_compliant_hours = 0
    alert_days = 0
    critical_days = 0
    has_poc = False

    sorted_days = sorted(days_dict.keys())
    for day in sorted_days:
        items = days_dict[day]
        n_hours = len(items)
        tot_hours += n_hours

        h_marginal = sum(1 for x in items if x.get("zone") == "marginal")
        h_baixo = sum(1 for x in items if x.get("zone") in ("baixo_superior", "baixo_inferior"))
        h_alto = sum(1 for x in items if x.get("zone") in ("alto_superior", "alto_inferior"))
        h_severo = sum(1 for x in items if x.get("zone") in ("severo_superior", "severo_inferior"))

        tot_alert_hours += h_alto
        tot_critical_hours += h_severo
        tot_compliant_hours += (h_marginal + h_baixo)

        vals_mm3 = [x["valueMm3"] for x in items if x.get("valueMm3") is not None]
        min_mm3 = round(min(vals_mm3), 3) if vals_mm3 else None
        max_mm3 = round(max(vals_mm3), 3) if vals_mm3 else None
        avg_mm3 = round(sum(vals_mm3) / len(vals_mm3), 3) if vals_mm3 else None

        if h_severo > 0:
            risk_status = "critical"
            critical_days += 1
            alert_days += 1
            peak_item = next((x for x in items if x.get("zone") in ("severo_superior", "severo_inferior")), items[0])
        elif h_alto > 0:
            risk_status = "alert"
            alert_days += 1
            peak_item = next((x for x in items if x.get("zone") in ("alto_superior", "alto_inferior")), items[0])
        elif h_baixo > 0:
            risk_status = "mild"
            peak_item = next((x for x in items if x.get("zone") in ("baixo_superior", "baixo_inferior")), items[0])
        else:
            risk_status = "normal"
            peak_item = items[0]

        compliance_pct = round(((h_marginal + h_baixo) / n_hours) * 100, 1) if n_hours else 100.0

        try:
            dt_obj = dt.date.fromisoformat(day)
            day_label = dt_obj.strftime("%d %b")
            weekday = dt_obj.strftime("%a")
        except Exception:
            day_label = day
            weekday = ""

        poc_actions = poc_map.get(day, [])
        if poc_actions:
            has_poc = True

        daily_heatmap.append({
            "date": day,
            "dayLabel": day_label,
            "weekday": weekday,
            "totalHours": n_hours,
            "hoursMarginal": h_marginal,
            "hoursBaixo": h_baixo,
            "hoursAlto": h_alto,
            "hoursSevero": h_severo,
            "minMm3": min_mm3,
            "maxMm3": max_mm3,
            "avgMm3": avg_mm3,
            "riskStatus": risk_status,
            "peakZone": peak_item.get("zone"),
            "peakZoneLabel": peak_item.get("zoneLabel"),
            "peakZoneLabelPt": peak_item.get("zoneLabelPt"),
            "badgeClass": peak_item.get("badgeClass"),
            "compliancePct": compliance_pct,
            "pocActions": poc_actions,
        })

    overall_compliance = round((tot_compliant_hours / tot_hours) * 100, 1) if tot_hours else 100.0

    summary = {
        "totalDays": len(sorted_days),
        "totalHours": tot_hours,
        "compliancePct": overall_compliance,
        "totalAlertHours": tot_alert_hours,
        "totalCriticalHours": tot_critical_hours,
        "alertDaysCount": alert_days,
        "criticalDaysCount": critical_days,
        "hasPocActions": has_poc,
    }
    return daily_heatmap, summary


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

    tolerance_bands = _extract_tolerance_bands(snap_df)
    lp_hist_series, lp_hist_rows = _linepack_history(df, tolerance_bands)
    poc_map = _load_poc_balancing_correlation()
    daily_heatmap, heatmap_summary = _build_linepack_heatmap(lp_hist_rows, poc_map)

    latest_lp = None
    if len(lp_actual):
        latest_lp = _num(lp_actual.sort_values("observed_at")["value"].iloc[-1])

    current_zone = determine_linepack_zone(latest_lp, tolerance_bands)

    bands_list = [
        {
            "key": "severo_superior",
            "name": "Severo (Superior)",
            "nameEn": "Critical High",
            "color": "#ef4444",
            "badgeClass": "badge-danger",
            "range": f"≥ {tolerance_bands['severo_superior'] / 1_000_000:.2f} Mm³",
            "descEn": "Critical overpack: venting / relief risk, maximum imbalance penalty",
            "descPt": "Empacotamento crítico elevado: risco de alívio e penalidades máximas",
        },
        {
            "key": "alto_superior",
            "name": "Alto (Superior)",
            "nameEn": "High Alert",
            "color": "#f59e0b",
            "badgeClass": "badge-warning",
            "range": f"{tolerance_bands['baixo_superior'] / 1_000_000:.2f} – {tolerance_bands['severo_superior'] / 1_000_000:.2f} Mm³",
            "descEn": "High inventory: network balancing actions / penalties apply",
            "descPt": "Inventário elevado: ações comerciais e penalidades aplicáveis",
        },
        {
            "key": "baixo_superior",
            "name": "Baixo (Superior)",
            "nameEn": "Mild High",
            "color": "#10b981",
            "badgeClass": "badge-success",
            "range": f"{tolerance_bands['marginal_superior'] / 1_000_000:.2f} – {tolerance_bands['baixo_superior'] / 1_000_000:.2f} Mm³",
            "descEn": "Mild high inventory above target operating envelope",
            "descPt": "Inventário moderadamente alto, acima da faixa ideal",
        },
        {
            "key": "marginal",
            "name": "Marginal (Ideal)",
            "nameEn": "Target Operating",
            "color": "#10b981",
            "badgeClass": "badge-target",
            "range": f"{tolerance_bands['marginal_inferior'] / 1_000_000:.2f} – {tolerance_bands['marginal_superior'] / 1_000_000:.2f} Mm³",
            "descEn": "Optimal operating envelope: standard transport, zero imbalance penalty",
            "descPt": "Faixa de operação ideal: transporte neutro sem penalidades",
        },
        {
            "key": "baixo_inferior",
            "name": "Baixo (Inferior)",
            "nameEn": "Mild Low",
            "color": "#10b981",
            "badgeClass": "badge-success",
            "range": f"{tolerance_bands['baixo_inferior'] / 1_000_000:.2f} – {tolerance_bands['marginal_inferior'] / 1_000_000:.2f} Mm³",
            "descEn": "Mild low inventory below target operating envelope",
            "descPt": "Inventário moderadamente baixo, abaixo da faixa ideal",
        },
        {
            "key": "alto_inferior",
            "name": "Alto (Inferior)",
            "nameEn": "Low Alert",
            "color": "#f59e0b",
            "badgeClass": "badge-warning",
            "range": f"{tolerance_bands['severo_inferior'] / 1_000_000:.2f} – {tolerance_bands['baixo_inferior'] / 1_000_000:.2f} Mm³",
            "descEn": "Low inventory: transport system alert, balancing injections needed",
            "descPt": "Inventário reduzido: alerta no sistema, compras de gás pela transportadora",
        },
        {
            "key": "severo_inferior",
            "name": "Severo (Inferior)",
            "nameEn": "Critical Low",
            "color": "#ef4444",
            "badgeClass": "badge-danger",
            "range": f"≤ {tolerance_bands['severo_inferior'] / 1_000_000:.2f} Mm³",
            "descEn": "Critical underpack: risk of system depressurization and supply curtailment",
            "descPt": "Empacotamento criticamente baixo: risco de despressurização e corte",
        },
    ]

    now = dt.datetime.now(dt.UTC)
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
        "linepackHeatmap": daily_heatmap,
        "linepackHeatmapSummary": heatmap_summary,
        "pocCorrelation": poc_map,
        "toleranceBands": tolerance_bands,
        "toleranceBandsList": bands_list,
        "kpiZone": current_zone,
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
.zone-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 550; line-height: 1.3; }
.zone-badge::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.badge-target { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.badge-success { background: rgba(16, 185, 129, 0.12); color: #10b981; }
.badge-warning { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.badge-danger { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.badge-unknown { background: rgba(156, 163, 175, 0.15); color: #9ca3af; }
.zone-pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; border: 1px solid transparent; }
.zone-pill.badge-target { background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
.zone-pill.badge-success { background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.25); color: #10b981; }
.zone-pill.badge-warning { background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.3); color: #f59e0b; }
.zone-pill.badge-danger { background: rgba(239, 68, 68, 0.14); border-color: rgba(239, 68, 68, 0.35); color: #ef4444; }
.legend-band { display: inline-flex; align-items: center; font-size: 11px; }
.legend-band::before { content: ""; display: inline-block; width: 10px; height: 8px; border-radius: 2px; background: var(--band-color, #888); margin-right: 4px; }
.faixas-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
.faixas-table th, .faixas-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: left; }
.faixas-table th { background: var(--bg); color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
.faixas-table td.range { font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
.faixas-table tr:hover td { background: var(--accent-soft); }
.hist-filter-group { display: inline-flex; gap: 4px; margin-left: auto; }
.hist-filter-btn { border: 1px solid var(--border-strong); background: var(--bg); color: var(--muted); font-size: 11px; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-family: var(--font); }
.hist-filter-btn:hover { background: var(--accent-soft); color: var(--text); }
.hist-filter-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text); font-weight: 600; }
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
    <div class="kpi"><div class="label" data-i18n="magoKpiZone">Operating Zone</div><div class="val" id="kpi-zone">—</div></div>
    <div class="kpi"><div class="label" data-i18n="magoKpiSnapshot">Snapshot (UTC)</div><div class="val" id="kpi-snap">—</div></div>
  </div>

  <section class="panel panel-tight">
    <div class="panel-head-row">
      <div>
        <h2 data-i18n="magoLinepackTitle">Line pack — integrated mesh</h2>
        <p class="sub compact" data-i18n="magoLinepackSub">Hourly actual (solid) and short-horizon forecast (dashed) with TAG commercial tolerance risk bands.</p>
      </div>
      <div id="linepack-zone-pill" class="zone-pill">—</div>
    </div>
    <div class="chart-box chart-sm"><div id="chart-lp"></div></div>
    <div class="legend">
      <span style="color:var(--tso-tag,#0066cc)" data-i18n="magoLegendActual">Actual</span>
      <span class="dash" style="color:#888" data-i18n="magoLegendForecast">Forecast</span>
    </div>
  </section>

  <section class="panel panel-tight" id="faixas-panel">
    <h2 data-i18n="magoFaixasTitle">Operating Risk & Imbalance Tolerance Bands</h2>
    <p class="sub compact" data-i18n="magoFaixasSub">Commercial balancing tolerance thresholds established for TAG's integrated pipeline system. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions.</p>
    <div id="faixas-grid"></div>
  </section>

  <section class="panel panel-tight" id="heatmap-panel">
    <div class="panel-head-row">
      <div>
        <h2 data-i18n="magoHeatmapTitle">Operating Risk & Imbalance Breach Heatmap</h2>
        <p class="sub compact" data-i18n="magoHeatmapSub">Daily historical tracking of TAG integrated inventory across commercial tolerance tiers and correlation with transport balancing actions.</p>
      </div>
      <div class="hist-filter-group">
        <button type="button" id="btn-hm-all" class="hist-filter-btn active" data-i18n="magoHmAll">All Days</button>
        <button type="button" id="btn-hm-alerts" class="hist-filter-btn" data-i18n="magoHmAlerts">Alerts & Breaches</button>
        <button type="button" id="btn-hm-critical" class="hist-filter-btn" data-i18n="magoHmCritical">Critical Only</button>
      </div>
    </div>
    <div class="hm-summary-grid" id="hm-summary-grid"></div>
    <div class="hm-calendar-grid" id="hm-calendar-grid"></div>
    <div class="hm-poc-callout" id="hm-poc-callout"></div>
  </section>

  <details class="panel-fold">
    <summary data-i18n="magoLinepackHistTitle">Line pack history</summary>
    <div class="fold-body">
      <p class="sub compact" data-i18n="magoLinepackHistSub">Hourly integrated inventory from cached snapshots (newest wins on overlap).</p>
      <div id="hm-selected-day-indicator" style="display:none;margin-bottom:8px;padding:4px 10px;background:var(--accent-soft);border:1px solid var(--accent);border-radius:4px;font-size:11px;align-items:center;justify-content:space-between;">
        <span><strong id="hm-filter-day-text"></strong></span>
        <button type="button" id="btn-clear-day-filter" style="border:none;background:none;color:var(--accent);font-weight:600;cursor:pointer;font-size:11px;">✕ Clear</button>
      </div>
      <div class="chart-box chart-sm"><div id="chart-lp-hist"></div></div>
      <div class="toolbar">
        <button type="button" id="btn-lp-csv" data-i18n="magoLpCsv">Download line pack CSV</button>
        <div class="hist-filter-group">
          <button type="button" id="btn-hist-all" class="hist-filter-btn active" data-i18n="magoHistAll">All Hours</button>
          <button type="button" id="btn-hist-alerts" class="hist-filter-btn" data-i18n="magoHistAlerts">Alerts & Breaches Only</button>
        </div>
      </div>
      <div class="data-table-wrap">
        <table class="lp-table" id="lp-table">
          <thead><tr>
            <th data-col="observedAt" data-i18n="magoColObserved">Observed (UTC)</th>
            <th data-col="valueMm3" class="num" data-i18n="magoColMm3">Mm³</th>
            <th data-col="valueM3" class="num" data-i18n="magoColM3">m³</th>
            <th data-col="zone" data-i18n="magoColZone">Operating Zone</th>
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
GB_I18N.en.magoColZone = "Operating Zone";
GB_I18N.pt.magoColZone = "Faixa Operacional";
GB_I18N.en.magoColSnapshot = "Source snapshot";
GB_I18N.pt.magoColSnapshot = "Snapshot de origem";
GB_I18N.en.magoKpiZone = "Operating Zone";
GB_I18N.pt.magoKpiZone = "Faixa Operacional";
GB_I18N.en.magoFaixasTitle = "Operating Risk & Imbalance Tolerance Bands";
GB_I18N.pt.magoFaixasTitle = "Faixas de Tolerância e Risco Operacional";
GB_I18N.en.magoFaixasSub = "TAG commercial balancing tolerance thresholds. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions.";
GB_I18N.pt.magoFaixasSub = "Limites comerciais de tolerância da TAG. Desvios fora da faixa marginal geram penalidades de desbalanceamento ou ações operacionais de compra/venda de gás.";
GB_I18N.en.magoHistAll = "All Hours";
GB_I18N.pt.magoHistAll = "Todas as Horas";
GB_I18N.en.magoHistAlerts = "Alerts & Breaches Only";
GB_I18N.pt.magoHistAlerts = "Apenas Alertas e Violações (Alto e Severo)";
GB_I18N.en.magoFaixaTier = "Operational Risk Tier";
GB_I18N.pt.magoFaixaTier = "Nível de Risco Operacional";
GB_I18N.en.magoFaixaRange = "Line Pack Threshold";
GB_I18N.pt.magoFaixaRange = "Faixa de Empacotamento";
GB_I18N.en.magoFaixaBalancing = "Commercial & Physical Balancing Consequence";
GB_I18N.pt.magoFaixaBalancing = "Consequência Comercial e Operacional";
GB_I18N.en.magoLegendActual = "Actual";
GB_I18N.pt.magoLegendActual = "Realizado";
GB_I18N.en.magoLegendForecast = "Forecast";
GB_I18N.pt.magoLegendForecast = "Estimativa";
GB_I18N.en.magoLegendSev = "Severe";
GB_I18N.pt.magoLegendSev = "Severo";
GB_I18N.en.magoLegendAlt = "High Alert";
GB_I18N.pt.magoLegendAlt = "Alto (Alerta)";
GB_I18N.en.magoLegendMarg = "Target";
GB_I18N.pt.magoLegendMarg = "Marginal (Ideal)";
GB_I18N.en.magoAxisSevere = "Severe";
GB_I18N.pt.magoAxisSevere = "Severo";
GB_I18N.en.magoAxisHigh = "High";
GB_I18N.pt.magoAxisHigh = "Alto";
GB_I18N.en.magoAxisMild = "Mild";
GB_I18N.pt.magoAxisMild = "Baixo";
GB_I18N.en.magoAxisTarget = "Target";
GB_I18N.pt.magoAxisTarget = "Marginal";
GB_I18N.en.magoAxisLow = "Low";
GB_I18N.pt.magoAxisLow = "Alerta";

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
let lpFilter = "all";

function fmtMm3(v) {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  return (v / 1e6).toFixed(2) + " Mm³";
}

function setKpis() {
  document.getElementById("kpi-lp").textContent = DATA.kpiLinepackMm3 != null
    ? DATA.kpiLinepackMm3.toFixed(2) + " Mm³" : fmtMm3(DATA.kpiLinepackM3);
  document.getElementById("kpi-snap").textContent = DATA.snapshotAt || "—";
  const z = DATA.kpiZone;
  const kpiZoneEl = document.getElementById("kpi-zone");
  const pillEl = document.getElementById("linepack-zone-pill");
  if (z) {
    const lang = document.documentElement.getAttribute("data-lang") || "en";
    const label = lang === "pt" ? (z.namePt || z.name) : z.name;
    if (kpiZoneEl) {
      kpiZoneEl.innerHTML = `<span class="zone-badge ${escapeHtml(z.badgeClass || '')}">${escapeHtml(label)}</span>`;
    }
    if (pillEl) {
      pillEl.className = "zone-pill " + (z.badgeClass || "");
      pillEl.textContent = label;
    }
  }
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

function drawLines(hostId, seriesList, yFmt, bands) {
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
  if (bands) {
    const bVals = Object.values(bands).filter(v => v != null && isFinite(v));
    if (bVals.length) {
      lo = Math.min(lo, ...bVals);
      hi = Math.max(hi, ...bVals);
    }
  }
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const W = Math.max(640, host.clientWidth || 640), H = hostId === "chart-zones" ? 240 : 220;
  const ML = 52, MR = bands ? 84 : 10, MT = 12, MB = 26;
  const plotLeft = ML, plotWidth = W - ML - MR, plotTop = MT, plotBottom = H - MB;
  const x = v => ML + plotWidth * ((v - minX) / (maxX - minX || 1));
  const y = v => MT + (plotBottom - plotTop) * (1 - (v - lo) / (hi - lo || 1));
  const svg = chartSvg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  svg.style.width = "100%"; svg.style.height = H + "px";

  if (bands) {
    const sevSup = bands.severo_superior;
    const bSup = bands.baixo_superior;
    const mSup = bands.marginal_superior;
    const mInf = bands.marginal_inferior;
    const bInf = bands.baixo_inferior;
    const sevInf = bands.severo_inferior;

    const zoneRects = [
      { topVal: hi, botVal: sevSup, color: "rgba(239, 68, 68, 0.09)" },
      { topVal: sevSup, botVal: bSup, color: "rgba(245, 158, 11, 0.08)" },
      { topVal: bSup, botVal: mSup, color: "rgba(16, 185, 129, 0.05)" },
      { topVal: mSup, botVal: mInf, color: "rgba(16, 185, 129, 0.12)" },
      { topVal: mInf, botVal: bInf, color: "rgba(16, 185, 129, 0.05)" },
      { topVal: bInf, botVal: sevInf, color: "rgba(245, 158, 11, 0.08)" },
      { topVal: sevInf, botVal: lo, color: "rgba(239, 68, 68, 0.09)" },
    ];

    zoneRects.forEach(zr => {
      if (zr.topVal == null || zr.botVal == null) return;
      const y1 = Math.max(plotTop, Math.min(plotBottom, y(zr.topVal)));
      const y2 = Math.max(plotTop, Math.min(plotBottom, y(zr.botVal)));
      const rH = y2 - y1;
      if (rH > 0) {
        svg.appendChild(chartSvg("rect", {
          x: plotLeft,
          y: y1,
          width: plotWidth,
          height: rH,
          fill: zr.color,
          stroke: "none",
        }));
      }
    });
  }

  for (let i = 0; i <= 4; i++) {
    const t = lo + (hi - lo) * (i / 4);
    const yy = y(t);
    svg.appendChild(chartSvg("line", { x1: ML, x2: W - MR, y1: yy, y2: yy, stroke: "var(--border)", "stroke-width": 1 }));
    const lb = chartSvg("text", { x: ML - 6, y: yy + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 11 });
    lb.textContent = yFmt(t); svg.appendChild(lb);
  }

  if (bands) {
    const axisX = plotLeft + plotWidth;
    const lang = document.documentElement.getAttribute("data-lang") || "en";
    const isPt = lang === "pt";

    svg.appendChild(chartSvg("line", {
      x1: axisX,
      x2: axisX,
      y1: plotTop,
      y2: plotBottom,
      stroke: "var(--border)",
      "stroke-width": 1,
    }));

    const guides = [
      { key: "sev_sup", val: bands.severo_superior, color: "#ef4444", labelEn: "Critical High Threshold", labelPt: "Limite Severo Superior" },
      { key: "alt_sup", val: bands.baixo_superior, color: "#f59e0b", labelEn: "High Alert Threshold", labelPt: "Limite Alerta Alto" },
      { key: "marg_sup", val: bands.marginal_superior, color: "#10b981", labelEn: "Target Upper Limit", labelPt: "Limite Marginal Superior" },
      { key: "marg_inf", val: bands.marginal_inferior, color: "#10b981", labelEn: "Target Lower Limit", labelPt: "Limite Marginal Inferior" },
      { key: "alt_inf", val: bands.baixo_inferior, color: "#f59e0b", labelEn: "Low Alert Threshold", labelPt: "Limite Alerta Baixo" },
      { key: "sev_inf", val: bands.severo_inferior, color: "#ef4444", labelEn: "Critical Low Threshold", labelPt: "Limite Severo Inferior" },
    ];
    guides.forEach(g => {
      if (g.val == null || !isFinite(g.val)) return;
      const gy = y(g.val);
      if (gy < plotTop - 2 || gy > plotBottom + 2) return;
      const line = chartSvg("line", {
        x1: plotLeft,
        x2: axisX,
        y1: gy,
        y2: gy,
        stroke: g.color,
        "stroke-width": 1,
        "stroke-dasharray": "3 3",
        opacity: 0.65,
      });
      const tip = chartSvg("title");
      tip.textContent = `${isPt ? g.labelPt : g.labelEn}: ${(g.val / 1e6).toFixed(2)} Mm³`;
      line.appendChild(tip);
      svg.appendChild(line);

      svg.appendChild(chartSvg("line", {
        x1: axisX,
        x2: axisX + 3,
        y1: gy,
        y2: gy,
        stroke: g.color,
        "stroke-width": 1.2,
      }));

      const rLabel = chartSvg("text", {
        x: axisX + 5,
        y: gy + 3,
        fill: g.color,
        "font-size": 9,
        "font-weight": 600,
        "font-family": "var(--font-mono, monospace)",
      });
      rLabel.textContent = `${(g.val / 1e6).toFixed(1)}M`;
      const tipText = chartSvg("title");
      tipText.textContent = `${isPt ? g.labelPt : g.labelEn}: ${(g.val / 1e6).toFixed(2)} Mm³`;
      rLabel.appendChild(tipText);
      svg.appendChild(rLabel);
    });

    const sevSup = bands.severo_superior;
    const bSup = bands.baixo_superior;
    const mSup = bands.marginal_superior;
    const mInf = bands.marginal_inferior;
    const bInf = bands.baixo_inferior;
    const sevInf = bands.severo_inferior;

    const axisRanges = [
      {
        topVal: hi,
        botVal: sevSup,
        color: "#ef4444",
        nameEn: "Severe",
        namePt: "Severo",
        fullEn: "Critical High (≥ " + (sevSup / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Severo Superior (≥ " + (sevSup / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: sevSup,
        botVal: bSup,
        color: "#f59e0b",
        nameEn: "High",
        namePt: "Alto",
        fullEn: "High Alert (" + (bSup / 1e6).toFixed(2) + " – " + (sevSup / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Alerta Alto (" + (bSup / 1e6).toFixed(2) + " – " + (sevSup / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: bSup,
        botVal: mSup,
        color: "rgba(16, 185, 129, 0.75)",
        nameEn: "Mild",
        namePt: "Baixo",
        fullEn: "Mild High (" + (mSup / 1e6).toFixed(2) + " – " + (bSup / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Baixo Risco Superior (" + (mSup / 1e6).toFixed(2) + " – " + (bSup / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: mSup,
        botVal: mInf,
        color: "#10b981",
        nameEn: "Target",
        namePt: "Marginal",
        fullEn: "Target Operating (" + (mInf / 1e6).toFixed(2) + " – " + (mSup / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Faixa Marginal Ideal (" + (mInf / 1e6).toFixed(2) + " – " + (mSup / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: mInf,
        botVal: bInf,
        color: "rgba(16, 185, 129, 0.75)",
        nameEn: "Mild",
        namePt: "Baixo",
        fullEn: "Mild Low (" + (bInf / 1e6).toFixed(2) + " – " + (mInf / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Baixo Risco Inferior (" + (bInf / 1e6).toFixed(2) + " – " + (mInf / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: bInf,
        botVal: sevInf,
        color: "#f59e0b",
        nameEn: "Low",
        namePt: "Alerta",
        fullEn: "Low Alert (" + (sevInf / 1e6).toFixed(2) + " – " + (bInf / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Alerta Baixo (" + (sevInf / 1e6).toFixed(2) + " – " + (bInf / 1e6).toFixed(2) + " Mm³)",
      },
      {
        topVal: sevInf,
        botVal: lo,
        color: "#ef4444",
        nameEn: "Severe",
        namePt: "Severo",
        fullEn: "Critical Low (≤ " + (sevInf / 1e6).toFixed(2) + " Mm³)",
        fullPt: "Severo Inferior (≤ " + (sevInf / 1e6).toFixed(2) + " Mm³)",
      },
    ];

    axisRanges.forEach(rng => {
      if (rng.topVal == null || rng.botVal == null) return;
      const yTop = Math.max(plotTop, Math.min(plotBottom, y(rng.topVal)));
      const yBot = Math.max(plotTop, Math.min(plotBottom, y(rng.botVal)));
      const spanH = yBot - yTop;
      if (spanH < 8) return;

      const rail = chartSvg("rect", {
        x: axisX + 34,
        y: yTop + 1,
        width: 3,
        height: Math.max(1, spanH - 2),
        rx: 1.5,
        fill: rng.color,
        opacity: 0.85,
      });
      const railTip = chartSvg("title");
      railTip.textContent = isPt ? rng.fullPt : rng.fullEn;
      rail.appendChild(railTip);
      svg.appendChild(rail);

      if (spanH >= 14) {
        const midY = (yTop + yBot) / 2;
        const textEl = chartSvg("text", {
          x: axisX + 41,
          y: midY + 3.5,
          fill: rng.color,
          "font-size": 9,
          "font-weight": 700,
          "letter-spacing": "0.02em",
        });
        textEl.textContent = isPt ? rng.namePt : rng.nameEn;
        const textTip = chartSvg("title");
        textTip.textContent = isPt ? rng.fullPt : rng.fullEn;
        textEl.appendChild(textTip);
        svg.appendChild(textEl);
      }
    });
  }

  const numTicks = 4;
  for (let i = 0; i <= numTicks; i++) {
    const tMs = minX + (maxX - minX) * (i / numTicks);
    const tx = x(tMs);
    const d = new Date(tMs);
    const timeStr = (d.getUTCMonth() + 1) + "/" + d.getUTCDate() + " " + String(d.getUTCHours()).padStart(2, "0") + "h";
    const tLabel = chartSvg("text", {
      x: tx,
      y: H - 8,
      "text-anchor": i === 0 ? "start" : (i === numTicks ? "end" : "middle"),
      fill: "var(--muted)",
      "font-size": 10,
    });
    tLabel.textContent = timeStr;
    svg.appendChild(tLabel);
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
  ], v => (v / 1e6).toFixed(1), DATA.toleranceBands);
}

function packLinepackHistory() {
  const pts = (LP_HIST.times || []).map((t, i) => ({ x: tsMs(t), y: LP_HIST.values[i] }));
  drawLines("chart-lp-hist", [
    { points: pts, color: "var(--tso-tag,#0066cc)", dashed: false },
  ], v => (v / 1e6).toFixed(2), DATA.toleranceBands);
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

function renderFaixasTable() {
  const host = document.getElementById("faixas-grid");
  if (!host) return;
  const list = DATA.toleranceBandsList || [];
  if (!list.length) {
    host.innerHTML = '<div class="chart-empty">No tolerance band data available.</div>';
    return;
  }
  const lang = document.documentElement.getAttribute("data-lang") || "en";
  const isPt = lang === "pt";
  const thTier = isPt ? "Nível de Risco Operacional" : "Operational Risk Tier";
  const thRange = isPt ? "Faixa de Empacotamento" : "Line Pack Threshold";
  const thBal = isPt ? "Consequência Comercial e Operacional" : "Commercial & Physical Balancing Consequence";

  let html = `<div style="overflow-x:auto"><table class="faixas-table">
    <thead><tr>
      <th data-i18n="magoFaixaTier">${thTier}</th>
      <th data-i18n="magoFaixaRange">${thRange}</th>
      <th data-i18n="magoFaixaBalancing">${thBal}</th>
    </tr></thead>
    <tbody>`;
  list.forEach(b => {
    const name = isPt ? b.name : (b.nameEn || b.name);
    const desc = isPt ? b.descPt : (b.descEn || b.descPt);
    html += `<tr>
      <td><span class="zone-badge ${escapeHtml(b.badgeClass || '')}">${escapeHtml(name)}</span></td>
      <td class="range">${escapeHtml(b.range)}</td>
      <td>${escapeHtml(desc)}</td>
    </tr>`;
  });
  html += `</tbody></table></div>`;
  host.innerHTML = html;
}

let heatmapFilter = "all";
let selectedHeatmapDate = null;

function renderHeatmap() {
  const summaryHost = document.getElementById("hm-summary-grid");
  const calendarHost = document.getElementById("hm-calendar-grid");
  const pocHost = document.getElementById("hm-poc-callout");
  if (!summaryHost || !calendarHost) return;

  const rawHeatmap = DATA.linepackHeatmap || [];
  const summary = DATA.linepackHeatmapSummary || {};
  const lang = document.documentElement.getAttribute("data-lang") || "en";
  const isPt = lang === "pt";

  const compVal = summary.compliancePct != null ? summary.compliancePct.toFixed(1) + "%" : "—";
  const compClass = (summary.compliancePct || 0) >= 95 ? "val-ok" : ((summary.compliancePct || 0) >= 80 ? "val-warn" : "val-danger");
  const alertH = summary.totalAlertHours != null ? summary.totalAlertHours + "h" : "0h";
  const alertClass = (summary.totalAlertHours || 0) > 0 ? "val-warn" : "val-ok";
  const critH = summary.totalCriticalHours != null ? summary.totalCriticalHours + "h" : "0h";
  const critClass = (summary.totalCriticalHours || 0) > 0 ? "val-danger" : "val-ok";
  const daysN = summary.totalDays != null ? summary.totalDays : rawHeatmap.length;

  summaryHost.innerHTML = `
    <div class="hm-summary-tile ${compClass}">
      <span class="hm-label" data-i18n="magoHmCompliance">${isPt ? "Conformidade Operacional" : "Envelope Compliance"}</span>
      <span class="hm-val">${compVal}</span>
      <span class="hm-sub">${isPt ? "Horas em faixa ideal / moderada" : "Hours in target / mild envelope"}</span>
    </div>
    <div class="hm-summary-tile ${alertClass}">
      <span class="hm-label" data-i18n="magoHmAlertHours">${isPt ? "Horas em Alerta (Alto)" : "Alert Hours"}</span>
      <span class="hm-val">${alertH}</span>
      <span class="hm-sub">${summary.alertDaysCount || 0} ${isPt ? "dias com alertas" : "days with alerts"}</span>
    </div>
    <div class="hm-summary-tile ${critClass}">
      <span class="hm-label" data-i18n="magoHmCriticalHours">${isPt ? "Horas Críticas (Severo)" : "Critical Hours"}</span>
      <span class="hm-val">${critH}</span>
      <span class="hm-sub">${summary.criticalDaysCount || 0} ${isPt ? "dias críticos" : "critical days"}</span>
    </div>
    <div class="hm-summary-tile">
      <span class="hm-label" data-i18n="magoHmDaysMonitored">${isPt ? "Dias Monitorados" : "Days Monitored"}</span>
      <span class="hm-val">${daysN}</span>
      <span class="hm-sub">${summary.totalHours || 0} ${isPt ? "amostras horárias" : "hourly observations"}</span>
    </div>
  `;

  let filteredDays = rawHeatmap.slice();
  if (heatmapFilter === "alerts") {
    filteredDays = filteredDays.filter(d => d.riskStatus === "alert" || d.riskStatus === "critical");
  } else if (heatmapFilter === "critical") {
    filteredDays = filteredDays.filter(d => d.riskStatus === "critical");
  }

  if (!filteredDays.length) {
    calendarHost.innerHTML = `<div class="chart-empty" style="grid-column:1/-1;padding:1.5rem;text-align:center;color:var(--muted);">${
      isPt ? "Nenhum dia encontrado para o filtro selecionado." : "No days recorded for the selected filter."
    }</div>`;
  } else {
    calendarHost.innerHTML = filteredDays.map(d => {
      const isSelected = selectedHeatmapDate === d.date;
      const peakLabel = isPt ? (d.peakZoneLabelPt || d.peakZoneLabel || d.peakZone) : (d.peakZoneLabel || d.peakZone);
      const riskClass = "risk-" + (d.riskStatus || "normal");

      const totH = d.totalHours || 24;
      const pctMarginal = ((d.hoursMarginal || 0) / totH) * 100;
      const pctBaixo = ((d.hoursBaixo || 0) / totH) * 100;
      const pctAlto = ((d.hoursAlto || 0) / totH) * 100;
      const pctSevero = ((d.hoursSevero || 0) / totH) * 100;

      let pocBadgeHtml = "";
      if (d.pocActions && d.pocActions.length) {
        pocBadgeHtml = `<div class="hm-poc-badge" title="${escapeHtml(d.pocActions.map(p => p.transactionType + ' ' + p.processCode).join(', '))}">⚡ POC (${d.pocActions.length})</div>`;
      }

      return `
        <div class="hm-day-card ${riskClass} ${isSelected ? 'active' : ''}" data-date="${escapeHtml(d.date)}" title="${isPt ? 'Clique para filtrar histórico horário' : 'Click to inspect hourly history'}">
          <div class="hm-day-head">
            <div>
              <span class="hm-day-date">${escapeHtml(d.dayLabel || d.date)}</span>
              <span class="hm-day-weekday">${escapeHtml(d.weekday || '')}</span>
            </div>
            <span class="zone-badge ${escapeHtml(d.badgeClass || '')}">${escapeHtml(peakLabel || '')}</span>
          </div>

          <div class="hm-risk-bar" title="${isPt ? `Marginal: ${d.hoursMarginal || 0}h | Baixo: ${d.hoursBaixo || 0}h | Alto: ${d.hoursAlto || 0}h | Severo: ${d.hoursSevero || 0}h` : `Marginal: ${d.hoursMarginal || 0}h | Mild: ${d.hoursBaixo || 0}h | Alert: ${d.hoursAlto || 0}h | Critical: ${d.hoursSevero || 0}h`}">
            ${pctMarginal > 0 ? `<div class="hm-risk-seg seg-marginal" style="width:${pctMarginal.toFixed(1)}%"></div>` : ''}
            ${pctBaixo > 0 ? `<div class="hm-risk-seg seg-baixo" style="width:${pctBaixo.toFixed(1)}%"></div>` : ''}
            ${pctAlto > 0 ? `<div class="hm-risk-seg seg-alto" style="width:${pctAlto.toFixed(1)}%"></div>` : ''}
            ${pctSevero > 0 ? `<div class="hm-risk-seg seg-severo" style="width:${pctSevero.toFixed(1)}%"></div>` : ''}
          </div>

          <div class="hm-day-stats">
            <div class="stat-item">
              <span>Min:</span>
              <span class="stat-val">${d.minMm3 != null ? d.minMm3.toFixed(2) : '—'} Mm³</span>
            </div>
            <div class="stat-item">
              <span>Max:</span>
              <span class="stat-val">${d.maxMm3 != null ? d.maxMm3.toFixed(2) : '—'} Mm³</span>
            </div>
            <div class="stat-item">
              <span>${isPt ? 'Média' : 'Avg'}:</span>
              <span class="stat-val">${d.avgMm3 != null ? d.avgMm3.toFixed(2) : '—'} Mm³</span>
            </div>
            <div class="stat-item">
              <span>${isPt ? 'Alerta' : 'Alert'}:</span>
              <span class="stat-val" style="color:${(d.hoursAlto || 0) + (d.hoursSevero || 0) > 0 ? 'var(--warn-ink)' : 'inherit'}">${(d.hoursAlto || 0) + (d.hoursSevero || 0)}h</span>
            </div>
          </div>
          ${pocBadgeHtml}
        </div>
      `;
    }).join("");

    calendarHost.querySelectorAll(".hm-day-card").forEach(card => {
      card.addEventListener("click", () => {
        const dtStr = card.getAttribute("data-date");
        if (selectedHeatmapDate === dtStr) {
          selectedHeatmapDate = null;
        } else {
          selectedHeatmapDate = dtStr;
        }
        renderHeatmap();
        renderLpTable();
        const fold = document.querySelector("details.panel-fold");
        if (fold && selectedHeatmapDate) {
          fold.open = true;
          fold.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      });
    });
  }

  if (pocHost) {
    const pocTextEn = "Under ANP Res. 52/2011 and TAG's Network Code, inventory breaches into High Alert or Critical require operational balancing tenders to prevent network depressurization or overpressurization. Transport balancing transactions and clearing prices are settled on Brazil's Portal de Oferta de Capacidade (POC).";
    const pocTextPt = "Sob a Resolução ANP 52/2011 e o Código de Rede da TAG, desvios para faixas de Alerta (Alto) ou Crítico (Severo) exigem compras/vendas de gás para balanceamento operacional. As ofertas de capacidade e preços de liquidação são transacionados no Portal de Oferta de Capacidade (POC).";
    pocHost.innerHTML = `
      <p><strong>${isPt ? "Correlação com Leilões no POC:" : "POC Commercial Balancing Correlation:"}</strong> ${isPt ? pocTextPt : pocTextEn}</p>
      <a href="/poc/?search=TAG" class="hm-poc-btn" data-i18n="magoHmViewPoc">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        ${isPt ? "Ver Leilões de Balanceamento no POC" : "View TAG Balancing on POC"}
      </a>
    `;
  }
}

function sortedLpRows() {
  let rows = LP_ROWS.slice();
  if (selectedHeatmapDate) {
    rows = rows.filter(r => (r.observedAt || "").startsWith(selectedHeatmapDate));
  }
  if (lpFilter === "alerts") {
    rows = rows.filter(r => r.isAlert || r.isCritical);
  }
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
  if (!tbody) return;
  const lang = document.documentElement.getAttribute("data-lang") || "en";
  const isPt = lang === "pt";

  const ind = document.getElementById("hm-selected-day-indicator");
  const indText = document.getElementById("hm-filter-day-text");
  if (ind && indText) {
    if (selectedHeatmapDate) {
      ind.style.display = "flex";
      indText.textContent = (isPt ? "Filtrando por data: " : "Filtering by date: ") + selectedHeatmapDate;
    } else {
      ind.style.display = "none";
    }
  }

  const rows = sortedLpRows();
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:1rem;">No records match the active filter.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const label = isPt ? (r.zoneLabelPt || r.zoneLabel || r.zone) : (r.zoneLabel || r.zone);
    const badge = r.zone ? `<span class="zone-badge ${escapeHtml(r.badgeClass || '')}">${escapeHtml(label || '')}</span>` : '—';
    return `
    <tr>
      <td>${escapeHtml(r.observedAt)}</td>
      <td class="num">${r.valueMm3 != null ? r.valueMm3.toFixed(4) : "—"}</td>
      <td class="num">${r.valueM3 != null ? r.valueM3.toFixed(2) : "—"}</td>
      <td>${badge}</td>
      <td>${escapeHtml(r.snapshotAt)}</td>
    </tr>`;
  }).join("");
}

function downloadLpCsv() {
  const header = ["observed_utc", "mm3", "m3", "operating_zone", "is_alert", "source_snapshot_utc"];
  const lines = [header.map(csvEscape).join(",")];
  sortedLpRows().forEach(r => {
    lines.push([
      r.observedAt,
      r.valueMm3 != null ? r.valueMm3 : "",
      r.valueM3 != null ? r.valueM3 : "",
      r.zone || "",
      r.isAlert ? "true" : "false",
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
  renderFaixasTable();
  renderHeatmap();
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

  const DEFAULT_FAIXAS = {
    severo_superior: 75500000.0,
    baixo_superior: 74500000.0,
    marginal_superior: 72000000.0,
    marginal_inferior: 69000000.0,
    baixo_inferior: 67500000.0,
    severo_inferior: 66000000.0,
  };
  if (!DATA.toleranceBands || !Object.keys(DATA.toleranceBands).length) {
    DATA.toleranceBands = DEFAULT_FAIXAS;
  }
  const tb = DATA.toleranceBands;
  if (!DATA.toleranceBandsList || !DATA.toleranceBandsList.length) {
    DATA.toleranceBandsList = [
      {
        key: "severo_superior",
        name: "Severo (Superior)",
        nameEn: "Critical High",
        color: "#ef4444",
        badgeClass: "badge-danger",
        range: "≥ " + (tb.severo_superior / 1e6).toFixed(2) + " Mm³",
        descEn: "Critical overpack: venting / relief risk, maximum imbalance penalty",
        descPt: "Empacotamento crítico elevado: risco de alívio e penalidades máximas",
      },
      {
        key: "alto_superior",
        name: "Alto (Superior)",
        nameEn: "High Alert",
        color: "#f59e0b",
        badgeClass: "badge-warning",
        range: (tb.baixo_superior / 1e6).toFixed(2) + " – " + (tb.severo_superior / 1e6).toFixed(2) + " Mm³",
        descEn: "High inventory: network balancing actions / penalties apply",
        descPt: "Inventário elevado: ações comerciais e penalidades aplicáveis",
      },
      {
        key: "baixo_superior",
        name: "Baixo (Superior)",
        nameEn: "Mild High",
        color: "#10b981",
        badgeClass: "badge-success",
        range: (tb.marginal_superior / 1e6).toFixed(2) + " – " + (tb.baixo_superior / 1e6).toFixed(2) + " Mm³",
        descEn: "Mild high inventory above target operating envelope",
        descPt: "Inventário moderadamente alto, acima da faixa ideal",
      },
      {
        key: "marginal",
        name: "Marginal (Ideal)",
        nameEn: "Target Operating",
        color: "#10b981",
        badgeClass: "badge-target",
        range: (tb.marginal_inferior / 1e6).toFixed(2) + " – " + (tb.marginal_superior / 1e6).toFixed(2) + " Mm³",
        descEn: "Optimal operating envelope: standard transport, zero imbalance penalty",
        descPt: "Faixa de operação ideal: transporte neutro sem penalidades",
      },
      {
        key: "baixo_inferior",
        name: "Baixo (Inferior)",
        nameEn: "Mild Low",
        color: "#10b981",
        badgeClass: "badge-success",
        range: (tb.baixo_inferior / 1e6).toFixed(2) + " – " + (tb.marginal_inferior / 1e6).toFixed(2) + " Mm³",
        descEn: "Mild low inventory below target operating envelope",
        descPt: "Inventário moderadamente baixo, abaixo da faixa ideal",
      },
      {
        key: "alto_inferior",
        name: "Alto (Inferior)",
        nameEn: "Low Alert",
        color: "#f59e0b",
        badgeClass: "badge-warning",
        range: (tb.severo_inferior / 1e6).toFixed(2) + " – " + (tb.baixo_inferior / 1e6).toFixed(2) + " Mm³",
        descEn: "Low inventory: transport system alert, balancing injections needed",
        descPt: "Inventário reduzido: alerta no sistema, compras de gás pela transportadora",
      },
      {
        key: "severo_inferior",
        name: "Severo (Inferior)",
        nameEn: "Critical Low",
        color: "#ef4444",
        badgeClass: "badge-danger",
        range: "≤ " + (tb.severo_inferior / 1e6).toFixed(2) + " Mm³",
        descEn: "Critical underpack: risk of system depressurization and supply curtailment",
        descPt: "Empacotamento criticamente baixo: risco de despressurização e corte",
      },
    ];
  }

  function calcMagoZone(valM3) {
    if (valM3 == null || !isFinite(valM3)) return null;
    if (valM3 >= tb.severo_superior) return { key: "severo_superior", name: "Critical High", namePt: "Severo (Superior)", color: "#ef4444", badgeClass: "badge-danger", isAlert: true, isCritical: true };
    if (valM3 >= tb.baixo_superior) return { key: "alto_superior", name: "High Alert", namePt: "Alto (Superior)", color: "#f59e0b", badgeClass: "badge-warning", isAlert: true, isCritical: false };
    if (valM3 >= tb.marginal_superior) return { key: "baixo_superior", name: "Mild High", namePt: "Baixo (Superior)", color: "#10b981", badgeClass: "badge-success", isAlert: false, isCritical: false };
    if (valM3 >= tb.marginal_inferior) return { key: "marginal", name: "Target Operating", namePt: "Marginal (Ideal)", color: "#10b981", badgeClass: "badge-target", isAlert: false, isCritical: false };
    if (valM3 >= tb.baixo_inferior) return { key: "baixo_inferior", name: "Mild Low", namePt: "Baixo (Inferior)", color: "#10b981", badgeClass: "badge-success", isAlert: false, isCritical: false };
    if (valM3 >= tb.severo_inferior) return { key: "alto_inferior", name: "Low Alert", namePt: "Alto (Inferior)", color: "#f59e0b", badgeClass: "badge-warning", isAlert: true, isCritical: false };
    return { key: "severo_inferior", name: "Critical Low", namePt: "Severo (Inferior)", color: "#ef4444", badgeClass: "badge-danger", isAlert: true, isCritical: true };
  }

  if (!DATA.kpiZone) {
    let latestLp = DATA.kpiLinepackM3;
    if (latestLp == null && DATA.kpiLinepackMm3 != null) latestLp = DATA.kpiLinepackMm3 * 1e6;
    if (latestLp == null && LP.actual && LP.actual.values && LP.actual.values.length) {
      latestLp = LP.actual.values[LP.actual.values.length - 1];
    }
    if (latestLp != null) {
      DATA.kpiZone = calcMagoZone(latestLp);
    }
  }

  LP_ROWS.forEach(r => {
    if (!r.zone) {
      let val = r.valueM3;
      if (val == null && r.valueMm3 != null) val = r.valueMm3 * 1e6;
      if (val != null) {
        const z = calcMagoZone(val);
        if (z) {
          r.zone = z.key;
          r.zoneLabel = z.name;
          r.zoneLabelPt = z.namePt;
          r.badgeClass = z.badgeClass;
          r.isAlert = z.isAlert;
          r.isCritical = z.isCritical;
        }
      }
    }
  });
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

  const btnAll = document.getElementById("btn-hist-all");
  const btnAlerts = document.getElementById("btn-hist-alerts");
  if (btnAll && btnAlerts) {
    btnAll.addEventListener("click", () => {
      lpFilter = "all";
      btnAll.classList.add("active");
      btnAlerts.classList.remove("active");
      renderLpTable();
    });
    btnAlerts.addEventListener("click", () => {
      lpFilter = "alerts";
      btnAlerts.classList.add("active");
      btnAll.classList.remove("active");
      renderLpTable();
    });
  }

  const btnHmAll = document.getElementById("btn-hm-all");
  const btnHmAlerts = document.getElementById("btn-hm-alerts");
  const btnHmCritical = document.getElementById("btn-hm-critical");
  if (btnHmAll && btnHmAlerts && btnHmCritical) {
    btnHmAll.addEventListener("click", () => {
      heatmapFilter = "all";
      btnHmAll.classList.add("active");
      btnHmAlerts.classList.remove("active");
      btnHmCritical.classList.remove("active");
      renderHeatmap();
    });
    btnHmAlerts.addEventListener("click", () => {
      heatmapFilter = "alerts";
      btnHmAlerts.classList.add("active");
      btnHmAll.classList.remove("active");
      btnHmCritical.classList.remove("active");
      renderHeatmap();
    });
    btnHmCritical.addEventListener("click", () => {
      heatmapFilter = "critical";
      btnHmCritical.classList.add("active");
      btnHmAll.classList.remove("active");
      btnHmAlerts.classList.remove("active");
      renderHeatmap();
    });
  }

  const btnClearDay = document.getElementById("btn-clear-day-filter");
  if (btnClearDay) {
    btnClearDay.addEventListener("click", () => {
      selectedHeatmapDate = null;
      renderHeatmap();
      renderLpTable();
    });
  }

  initThemeToggle("theme-toggle", () => { packLinepack(); packLinepackHistory(); packZones(); });
  initLangToggle("lang-toggle", () => {
    renderFilters();
    setKpis();
    renderFaixasTable();
    renderHeatmap();
    renderLpTable();
    packLinepack();
    packLinepackHistory();
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
    print(f"Wrote {out_path} ({len(html):,} bytes), payload -> {payload_href}")
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_dashboard(out)
