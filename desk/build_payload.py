"""Assemble a lean Market Desk payload from lake / sibling parquet stores.

Missing sources degrade to empty series + notes — never raise for absent files.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "shared"))
import joins  # noqa: E402
import transforms as xf  # noqa: E402

# POC PCR convention: MMBtu per 1000 m³ (same factor as poc/dashboard.py).
MMBTU_PER_1000_M3 = 28.8081
COMPARE_DAYS = 90


def _first_existing(*candidates: Path) -> Optional[Path]:
    for p in candidates:
        if p.exists():
            return p
    return None


def _read_parquet(*candidates: Path) -> Optional[pd.DataFrame]:
    path = _first_existing(*candidates)
    if path is None:
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _num(v: Any, nd: int = 2) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _latest_ons_value(
    ons: pd.DataFrame,
    series: str,
    subsystem: str,
) -> tuple[Optional[float], Optional[str]]:
    need = {"date", "subsystem", "series", "value"}
    if not need.issubset(ons.columns):
        return None, None
    o = ons.copy()
    o["date"] = pd.to_datetime(o["date"], errors="coerce")
    o = o.dropna(subset=["date"])
    o = o[o["series"].astype(str) == series]
    o = o[o["subsystem"].astype(str).str.upper() == subsystem.upper()]
    if "entity" in o.columns:
        o = o[o["entity"].astype(str).fillna("") == ""]
    if o.empty:
        return None, None
    o = o.sort_values("date")
    last = o.iloc[-1]
    return _num(last["value"], 1), last["date"].strftime("%Y-%m-%d")


def _kpi_pld_se(pld: pd.DataFrame) -> tuple[Optional[float], Optional[str]]:
    need = {"date", "submarket", "pld"}
    if not need.issubset(pld.columns):
        return None, None
    p = pld.copy()
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    p = p.dropna(subset=["date", "pld"])
    p = p[p["submarket"].astype(str).str.upper() == "SE"]
    if p.empty:
        return None, None
    p = p.sort_values("date")
    last = p.iloc[-1]
    return _num(last["pld"], 2), last["date"].strftime("%Y-%m-%d")


def _kpi_anp(anp: pd.DataFrame) -> dict:
    out = {
        "santos": None,
        "nonThermalSe": None,
        "month": None,
        "monthNonThermalSe": None,
    }
    if anp is None or anp.empty or "month" not in anp.columns:
        return out
    a = anp.copy()
    a["month"] = a["month"].astype(str).str.slice(0, 7)
    price_col = "price_brl_mmbtu" if "price_brl_mmbtu" in a.columns else "price"
    if price_col not in a.columns:
        return out

    prod = a.iloc[0:0]
    if "segment" in a.columns:
        prod = a[a["segment"] == "producers"]
    if "category" in a.columns:
        santos = prod[prod["category"].astype(str) == "Santos"].dropna(subset=[price_col])
        if len(santos):
            santos = santos.sort_values("month")
            out["santos"] = _num(santos.iloc[-1][price_col], 2)
            out["month"] = str(santos.iloc[-1]["month"])

    dist = a.iloc[0:0]
    if "segment" in a.columns:
        dist = a[a["segment"] == "distributors"]
    if "category" in dist.columns and "region" in dist.columns:
        nt = dist[
            (dist["category"].astype(str) == "non_thermal")
            & (dist["region"].astype(str).str.contains("Sudeste", case=False, na=False))
        ].dropna(subset=[price_col])
        if len(nt):
            nt = nt.sort_values("month")
            out["nonThermalSe"] = _num(nt.iloc[-1][price_col], 2)
            out["monthNonThermalSe"] = str(nt.iloc[-1]["month"])
    return out


def _kpi_poc_7d(poc: pd.DataFrame) -> dict:
    out = {"avgPrice": None, "trades": None, "when": None}
    if poc is None or poc.empty or "Trade Date" not in poc.columns or "Price" not in poc.columns:
        return out
    p = poc.copy()
    p["Trade Date"] = pd.to_datetime(p["Trade Date"], errors="coerce")
    p = p.dropna(subset=["Trade Date", "Price"])
    if p.empty:
        return out
    last = p["Trade Date"].max()
    week = p[p["Trade Date"] >= (last - pd.Timedelta(days=7))]
    out["when"] = last.strftime("%Y-%m-%d")
    out["trades"] = int(len(week))
    if week["Price"].notna().any():
        out["avgPrice"] = _num(week["Price"].mean(), 2)
    return out


def _kpi_flows_7d(flows: pd.DataFrame) -> dict:
    out = {"total": None, "when": None}
    if flows is None or flows.empty:
        return out
    need = {"date", "variable", "value"}
    if not need.issubset(flows.columns):
        return out
    f = flows.copy()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    f = f.dropna(subset=["date"])
    present = set(f["variable"].astype(str).unique())
    var = None
    for candidate in (
        "Actual Volume (thousand m3)",
        "Volume Realizado (mil m³)",
        "Volume Realizado",
    ):
        if candidate in present:
            var = candidate
            break
    if var is None:
        return out
    realized = f[f["variable"].astype(str) == var]
    if realized.empty:
        return out
    last = realized["date"].max()
    recent = realized[realized["date"] >= (last - pd.Timedelta(days=6))]
    out["when"] = last.strftime("%Y-%m-%d")
    out["total"] = _num(recent["value"].sum(), 1)
    return out


def _series_pld_cmo_cvu(pld: Optional[pd.DataFrame], ons: Optional[pd.DataFrame]) -> dict:
    empty = {"dates": [], "pld": [], "cmo": [], "cvu": [], "note": None}
    if pld is None or pld.empty:
        empty["note"] = "PLD parquet missing - chart empty."
        return empty
    if ons is None or ons.empty:
        # Still show PLD SE alone if available.
        p = pld.copy()
        p["date"] = pd.to_datetime(p["date"], errors="coerce")
        p = p.dropna(subset=["date", "pld"])
        p = p[p["submarket"].astype(str).str.upper() == "SE"].sort_values("date")
        if p.empty:
            empty["note"] = "No SE PLD rows."
            return empty
        last = p["date"].max()
        p = p[p["date"] >= (last - pd.Timedelta(days=COMPARE_DAYS))]
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in p["date"]],
            "pld": [_num(v, 2) for v in p["pld"]],
            "cmo": [None] * len(p),
            "cvu": [None] * len(p),
            "note": "ONS daily missing - CMO/CVU empty.",
        }
    try:
        last = pd.to_datetime(pld["date"], errors="coerce").max()
        date_from = last - pd.Timedelta(days=COMPARE_DAYS) if pd.notna(last) else None
        joined = joins.join_pld_cmo_cvu(pld, ons, date_from=date_from, how="left")
        joined = joined[joined["submarket"].astype(str).str.upper() == "SE"]
        joined = joined.sort_values("date")
        if joined.empty:
            empty["note"] = "No SE overlap for PLD/CMO/CVU."
            return empty
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in joined["date"]],
            "pld": [_num(v, 2) for v in joined["pld"]],
            "cmo": [_num(v, 2) for v in joined["cmo"]],
            "cvu": [_num(v, 2) for v in joined["cvu_gas_med"]],
            "note": None,
        }
    except Exception as exc:
        empty["note"] = f"PLD/CMO/CVU join skipped: {exc}"
        return empty


def _series_poc_anp(poc: Optional[pd.DataFrame], anp: Optional[pd.DataFrame]) -> dict:
    empty = {"months": [], "poc": [], "anpSantos": [], "anpNonThermalSe": [], "note": None}
    if poc is None or poc.empty or anp is None or anp.empty:
        missing = []
        if poc is None or poc.empty:
            missing.append("POC")
        if anp is None or anp.empty:
            missing.append("ANP")
        empty["note"] = f"{' + '.join(missing)} missing - monthly compare empty."
        return empty
    try:
        joined = joins.join_poc_vs_anp_monthly(poc, anp)
        months = sorted(joined["month"].astype(str).unique().tolist())
        santos = []
        non_th = []
        poc_avg = []
        for m in months:
            part = joined[joined["month"].astype(str) == m]
            poc_vals = part["poc_avg_price"].dropna()
            poc_avg.append(_num(poc_vals.iloc[0], 2) if len(poc_vals) else None)

            s = part[
                (part.get("segment", pd.Series(dtype=str)) == "producers")
                & (part.get("category", pd.Series(dtype=str)).astype(str) == "Santos")
            ]
            price_col = "price" if "price" in part.columns else "price_brl_mmbtu"
            if len(s) and price_col in s.columns and s[price_col].notna().any():
                santos.append(_num(s[price_col].iloc[0], 2))
            else:
                santos.append(None)

            nt = part[
                (part.get("segment", pd.Series(dtype=str)) == "distributors")
                & (part.get("category", pd.Series(dtype=str)).astype(str) == "non_thermal")
                & (
                    part.get("region", pd.Series(dtype=str))
                    .astype(str)
                    .str.contains("Sudeste", case=False, na=False)
                )
            ]
            if len(nt) and price_col in nt.columns and nt[price_col].notna().any():
                non_th.append(_num(nt[price_col].iloc[0], 2))
            else:
                non_th.append(None)

        return {
            "months": months,
            "poc": poc_avg,
            "anpSantos": santos,
            "anpNonThermalSe": non_th,
            "note": None,
        }
    except Exception as exc:
        empty["note"] = f"POC vs ANP join skipped: {exc}"
        return empty


def _util_table(
    contratos: Optional[pd.DataFrame],
    flows: Optional[pd.DataFrame],
) -> dict:
    empty: dict = {"rows": [], "asOf": None, "note": None}
    if contratos is None or contratos.empty or flows is None or flows.empty:
        missing = []
        if contratos is None or contratos.empty:
            missing.append("contratos")
        if flows is None or flows.empty:
            missing.append("flows")
        empty["note"] = f"{' + '.join(missing)} missing - utilization empty."
        return empty
    try:
        joined = joins.join_capacity_vs_flows(contratos, flows)
        rows = []
        for _, r in joined.iterrows():
            rows.append(
                {
                    "tso": str(r["tso"]),
                    "contracted": _num(r.get("contracted_thousand_m3_d"), 1),
                    "realized": _num(r.get("realized_avg_thousand_m3_d"), 1),
                    "utilization": _num(r.get("utilization"), 3),
                }
            )
        as_of = None
        if "as_of" in joined.columns and len(joined):
            as_of = joined["as_of"].iloc[0]
        return {"rows": rows, "asOf": as_of, "note": None}
    except Exception as exc:
        empty["note"] = f"Capacity vs flows join skipped: {exc}"
        return empty


def build_payload() -> dict:
    heat = xf.ONS_GAS_HEAT
    notes: list[str] = []

    ons = _read_parquet(
        ROOT / "lake" / "power" / "ons_daily.parquet",
        ROOT / "ons" / "data" / "daily.parquet",
    )
    pld = _read_parquet(
        ROOT / "lake" / "power" / "pld_daily.parquet",
        ROOT / "pld" / "data" / "pld_daily.parquet",
    )
    anp = _read_parquet(
        ROOT / "lake" / "supply" / "anp_prices.parquet",
        ROOT / "precos" / "data" / "anp_prices.parquet",
    )
    poc = _read_parquet(
        ROOT / "lake" / "transport" / "poc_results.parquet",
        ROOT / "poc" / "data" / "poc_results.parquet",
    )
    flows = _read_parquet(
        ROOT / "lake" / "transport" / "flows_points.parquet",
        ROOT / "flows" / "data" / "flows_points.parquet",
    )
    contratos = _read_parquet(
        ROOT / "lake" / "transport" / "contratos.parquet",
        ROOT / "contratos" / "data" / "contratos.parquet",
    )

    gen_gas, gen_when = (None, None)
    cmo_se, cmo_when = (None, None)
    if ons is not None and not ons.empty:
        gen_gas, gen_when = _latest_ons_value(ons, "gen_gas", "SIN")
        if gen_gas is None:
            gen_gas, gen_when = _latest_ons_value(ons, "thermal_gas", "SIN")
        cmo_se, cmo_when = _latest_ons_value(ons, "cmo", "SE")
    else:
        notes.append("ONS daily parquet not found.")

    pld_se, pld_when = (None, None)
    if pld is not None and not pld.empty:
        pld_se, pld_when = _kpi_pld_se(pld)
    else:
        notes.append("PLD parquet not found.")

    anp_kpi = _kpi_anp(anp) if anp is not None else {
        "santos": None, "nonThermalSe": None, "month": None, "monthNonThermalSe": None,
    }
    if anp is None:
        notes.append("ANP prices parquet not found.")

    poc_kpi = _kpi_poc_7d(poc) if poc is not None else {
        "avgPrice": None, "trades": None, "when": None,
    }
    if poc is None:
        notes.append("POC parquet not found.")

    flows_kpi = _kpi_flows_7d(flows) if flows is not None else {
        "total": None, "when": None,
    }
    if flows is None:
        notes.append("Flows parquet not found.")

    compare = _series_pld_cmo_cvu(pld, ons)
    poc_anp = _series_poc_anp(poc, anp)
    util = _util_table(contratos, flows)
    for block in (compare, poc_anp, util):
        if block.get("note"):
            notes.append(block["note"])

    # Default gas price for spark calculator: Santos ANP, else POC 7d avg.
    default_gas = anp_kpi.get("santos") or poc_kpi.get("avgPrice")

    through_candidates = [
        d for d in (pld_when, cmo_when, gen_when, anp_kpi.get("month"), poc_kpi.get("when"), flows_kpi.get("when"))
        if d
    ]
    data_through = max(through_candidates) if through_candidates else None

    _now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated": _now.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedIso": _now.isoformat(),
        "dataThrough": data_through,
        "notes": notes,
        "kpi": {
            "genGasSin": gen_gas,
            "genGasWhen": gen_when,
            "pldSe": pld_se,
            "pldWhen": pld_when,
            "cmoSe": cmo_se,
            "cmoWhen": cmo_when,
            "anpSantos": anp_kpi.get("santos"),
            "anpSantosMonth": anp_kpi.get("month"),
            "anpNonThermalSe": anp_kpi.get("nonThermalSe"),
            "anpNonThermalSeMonth": anp_kpi.get("monthNonThermalSe"),
            "pocAvg7d": poc_kpi.get("avgPrice"),
            "pocTrades7d": poc_kpi.get("trades"),
            "pocWhen": poc_kpi.get("when"),
            "flowsTotal7d": flows_kpi.get("total"),
            "flowsWhen": flows_kpi.get("when"),
        },
        "compareSe": compare,
        "pocAnpMonthly": poc_anp,
        "utilization": util,
        "spark": {
            "defaultGasPrice": default_gas,
            "heatRateCcgt": float(heat["heat_rate_combined_cycle_kcal_per_kwh"]),
            "heatRateOcgt": float(heat["heat_rate_simple_cycle_kcal_per_kwh"]),
            "natgasKcalPerM3": float(heat["natgas_kcal_per_m3"]),
            "mmbtuPer1000M3": MMBTU_PER_1000_M3,
            "pldSe": pld_se,
            "cmoSe": cmo_se,
            "formulaEn": (
                "Implied CVU (R$/MWh) = gas (R$/MMBtu) × heat rate (kcal/kWh) × 1000 "
                f"/ ({heat['natgas_kcal_per_m3']:g} kcal/m³ × {MMBTU_PER_1000_M3} MMBtu/1000 m³). "
                "Same PCS / PCR conventions as ONS estimated burn and POC R$/m³."
            ),
            "formulaPt": (
                "CVU implícito (R$/MWh) = gás (R$/MMBtu) × heat rate (kcal/kWh) × 1000 "
                f"/ ({heat['natgas_kcal_per_m3']:g} kcal/m³ × {MMBTU_PER_1000_M3} MMBtu/1000 m³). "
                "Mesmas convenções de PCS/PCR do consumo estimado ONS e do R$/m³ POC."
            ),
        },
        "sourcesPresent": {
            "ons": ons is not None and not ons.empty,
            "pld": pld is not None and not pld.empty,
            "anp": anp is not None and not anp.empty,
            "poc": poc is not None and not poc.empty,
            "flows": flows is not None and not flows.empty,
            "contratos": contratos is not None and not contratos.empty,
        },
    }


if __name__ == "__main__":
    import json

    payload = build_payload()
    print(json.dumps({k: payload[k] for k in ("generated", "dataThrough", "kpi", "notes", "sourcesPresent")}, indent=2))
