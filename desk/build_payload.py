"""Assemble a lean Desk payload from lake / sibling parquet stores.

Missing sources degrade to empty series + notes — never raise for absent files.
Pulls lake parquet from R2 via data_kit.ensure_lake when local files are absent.
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

# POC PCR convention: same factor as poc/dashboard.py. MMBTU_PER_1000_M3 is
# MMBtu per 1000 m3 of gas, so converting a R$/MMBtu price to R$/m3 means
# multiplying by the MMBtu content of one m3 (MMBTU_PER_1000_M3 / 1000), not
# dividing by the per-1000-m3 factor directly.
# R$/m³ = R$/MMBtu × MMBTU_PER_1000_M3 / 1000.
MMBTU_PER_1000_M3 = 28.8081
COMPARE_DAYS = 90
SPARK_FALLBACK_GAS_M3 = 1.2  # illustrative R$/m³ when no GUS trade exists


def _mmbtu_to_m3(price_mmbtu: Optional[float], nd: int = 3) -> Optional[float]:
    if price_mmbtu is None:
        return None
    return _num(float(price_mmbtu) * MMBTU_PER_1000_M3 / 1000.0, nd)


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


def _latest_ons_national_sum(
    ons: pd.DataFrame,
    series: str,
) -> tuple[Optional[float], Optional[str]]:
    """Sum a per-subsystem ONS series to a national (SIN) total.

    ONS never publishes a pre-aggregated "SIN" subsystem -- only SE/CO, S,
    NE, and N -- so a national figure has to be summed across whichever of
    those four have data for the latest date, not filtered on a "SIN" value
    that doesn't exist in the data.
    """
    need = {"date", "subsystem", "series", "value"}
    if not need.issubset(ons.columns):
        return None, None
    o = ons.copy()
    o["date"] = pd.to_datetime(o["date"], errors="coerce")
    o = o.dropna(subset=["date"])
    o = o[o["series"].astype(str) == series]
    if "entity" in o.columns:
        o = o[o["entity"].astype(str).fillna("") == ""]
    if o.empty:
        return None, None
    daily = o.groupby("date", as_index=False)["value"].sum().sort_values("date")
    last = daily.iloc[-1]
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
    out = {"avgPrice": None, "avgPriceM3": None, "trades": None, "when": None}
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
        avg = _num(week["Price"].mean(), 2)
        out["avgPrice"] = avg
        out["avgPriceM3"] = _mmbtu_to_m3(avg)
    return out


def _last_gus_trade(poc: Optional[pd.DataFrame]) -> dict:
    """Most recent GUS acquisition trade price (on-system gas)."""
    out = {"priceM3": None, "priceMmbtu": None, "when": None, "tso": None}
    if poc is None or poc.empty:
        return out
    need = {"Trade Date", "Price"}
    if not need.issubset(poc.columns):
        return out
    p = poc.copy()
    p["Trade Date"] = pd.to_datetime(p["Trade Date"], errors="coerce")
    p = p.dropna(subset=["Trade Date", "Price"])
    if "Transaction Type" in p.columns:
        tt = p["Transaction Type"].astype(str)
        gus = p[tt.isin(["GUS", "Aquisição de GUS", "GUS Acquisition"])]
        if gus.empty:
            # Fall back to raw finalidade strings if type was not normalized.
            gus = p[tt.str.contains("GUS", case=False, na=False)]
        p = gus if not gus.empty else p.iloc[0:0]
    if p.empty:
        return out
    p = p.sort_values("Trade Date")
    last = p.iloc[-1]
    mmbtu = _num(last["Price"], 2)
    out["priceMmbtu"] = mmbtu
    out["priceM3"] = _mmbtu_to_m3(mmbtu)
    out["when"] = pd.Timestamp(last["Trade Date"]).strftime("%Y-%m-%d")
    if "Transporter (TSO)" in p.columns:
        out["tso"] = str(last["Transporter (TSO)"]) if pd.notna(last["Transporter (TSO)"]) else None
    elif "TSO" in p.columns:
        out["tso"] = str(last["TSO"]) if pd.notna(last["TSO"]) else None
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
    """PLD / CMO / CVU series for all CCEE submarkets (SE, S, NE, N)."""
    empty = {
        "dates": [],
        "bySubmarket": {},
        "defaultSubmarket": "SE",
        "note": None,
    }
    sms = ["SE", "S", "NE", "N"]
    if pld is None or pld.empty:
        empty["note"] = "PLD parquet missing - chart empty."
        return empty

    p = pld.copy()
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    p = p.dropna(subset=["date", "pld"])
    p["submarket"] = p["submarket"].astype(str).str.upper()
    p = p[p["submarket"].isin(sms)]
    if p.empty:
        empty["note"] = "No PLD rows."
        return empty
    last = p["date"].max()
    date_from = last - pd.Timedelta(days=COMPARE_DAYS) if pd.notna(last) else None

    if ons is None or ons.empty:
        by_sm: dict = {}
        dates = sorted(
            d.strftime("%Y-%m-%d")
            for d in p.loc[p["date"] >= date_from, "date"].unique()
        ) if date_from is not None else []
        for sm in sms:
            part = p[(p["submarket"] == sm) & (p["date"] >= date_from)].sort_values("date")
            lookup = {d.strftime("%Y-%m-%d"): _num(v, 2) for d, v in zip(part["date"], part["pld"])}
            by_sm[sm] = {
                "pld": [lookup.get(d) for d in dates],
                "cmo": [None] * len(dates),
                "cvu": [None] * len(dates),
            }
        return {
            "dates": dates,
            "bySubmarket": by_sm,
            "defaultSubmarket": "SE",
            "note": "ONS daily missing - CMO/CVU empty.",
        }

    try:
        joined = joins.join_pld_cmo_cvu(pld, ons, date_from=date_from, how="left")
        joined["submarket"] = joined["submarket"].astype(str).str.upper()
        joined = joined[joined["submarket"].isin(sms)].copy()
        joined["date"] = pd.to_datetime(joined["date"], errors="coerce")
        joined = joined.dropna(subset=["date"]).sort_values("date")
        if joined.empty:
            empty["note"] = "No PLD/CMO/CVU overlap."
            return empty
        joined["d"] = joined["date"].dt.strftime("%Y-%m-%d")
        dates = sorted(joined["d"].unique().tolist())
        by_sm = {}
        for sm in sms:
            part = (
                joined[joined["submarket"] == sm]
                .drop_duplicates("d", keep="last")
                .set_index("d")
            )
            by_sm[sm] = {
                "pld": [_num(part.loc[d, "pld"], 2) if d in part.index else None for d in dates],
                "cmo": [_num(part.loc[d, "cmo"], 2) if d in part.index else None for d in dates],
                "cvu": [
                    _num(part.loc[d, "cvu_gas_med"], 2) if d in part.index else None
                    for d in dates
                ],
            }
        return {
            "dates": dates,
            "bySubmarket": by_sm,
            "defaultSubmarket": "SE",
            "note": None,
        }
    except Exception as exc:
        empty["note"] = f"PLD/CMO/CVU join skipped: {exc}"
        return empty


def _series_poc_anp(poc: Optional[pd.DataFrame], anp: Optional[pd.DataFrame]) -> dict:
    empty = {"months": [], "poc": [], "anpSantos": [], "anpNonThermalSe": [], "note": None}
    has_poc = poc is not None and not poc.empty
    has_anp = anp is not None and not anp.empty
    if not has_poc and not has_anp:
        empty["note"] = "POC + ANP missing - monthly compare empty."
        return empty
    if has_poc and has_anp:
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

    # Partial: one source only — still plot what we have.
    months: list[str] = []
    poc_avg: list = []
    santos: list = []
    non_th: list = []
    if has_poc:
        p = poc.copy()
        p["Trade Date"] = pd.to_datetime(p["Trade Date"], errors="coerce")
        p = p.dropna(subset=["Trade Date", "Price"])
        p["month"] = p["Trade Date"].dt.strftime("%Y-%m")
        g = p.groupby("month")["Price"].mean()
        months = sorted(g.index.astype(str).tolist())
        poc_avg = [_num(g[m], 2) for m in months]
        santos = [None] * len(months)
        non_th = [None] * len(months)
        return {
            "months": months,
            "poc": poc_avg,
            "anpSantos": santos,
            "anpNonThermalSe": non_th,
            "note": "ANP missing - showing POC only.",
        }
    a = anp.copy()
    a["month"] = a["month"].astype(str).str.slice(0, 7)
    price_col = "price_brl_mmbtu" if "price_brl_mmbtu" in a.columns else "price"
    months = sorted(a["month"].dropna().unique().tolist())
    for m in months:
        part = a[a["month"] == m]
        s = part[(part.get("segment", pd.Series(dtype=str)) == "producers") & (part.get("category", pd.Series(dtype=str)).astype(str) == "Santos")]
        santos.append(_num(s[price_col].iloc[0], 2) if len(s) and s[price_col].notna().any() else None)
        nt = part[
            (part.get("segment", pd.Series(dtype=str)) == "distributors")
            & (part.get("category", pd.Series(dtype=str)).astype(str) == "non_thermal")
            & (part.get("region", pd.Series(dtype=str)).astype(str).str.contains("Sudeste", case=False, na=False))
        ]
        non_th.append(_num(nt[price_col].iloc[0], 2) if len(nt) and nt[price_col].notna().any() else None)
        poc_avg.append(None)
    return {
        "months": months,
        "poc": poc_avg,
        "anpSantos": santos,
        "anpNonThermalSe": non_th,
        "note": "POC missing - showing ANP only.",
    }


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

    # Pull canonical lake mirrors from R2 when local/sibling parquet are absent
    # (typical in CI — product data/ trees are gitignored).
    try:
        import data_kit as dk  # noqa: E402

        dk.ensure_lake(
            (
                "ons_daily",
                "pld_daily",
                "anp_prices",
                "poc_results",
                "flows_points",
                "contratos",
            )
        )
    except Exception as exc:
        notes.append(f"Lake restore skipped: {exc}")

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
        gen_gas, gen_when = _latest_ons_national_sum(ons, "thermal_gas")
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
        "avgPrice": None, "avgPriceM3": None, "trades": None, "when": None,
    }
    if poc is None:
        notes.append("POC parquet not found.")

    gus = _last_gus_trade(poc)

    flows_kpi = _kpi_flows_7d(flows) if flows is not None else {
        "total": None, "when": None,
    }
    if flows is None:
        notes.append("Flows parquet not found.")

    compare = _series_pld_cmo_cvu(pld, ons)
    # KPI CMO/PLD stay SE-default (largest load center); spark uses same.
    se_block = (compare.get("bySubmarket") or {}).get("SE") or {}
    if pld_se is None and se_block.get("pld"):
        for i in range(len(se_block["pld"]) - 1, -1, -1):
            if se_block["pld"][i] is not None:
                pld_se = se_block["pld"][i]
                break
    if cmo_se is None and se_block.get("cmo"):
        for i in range(len(se_block["cmo"]) - 1, -1, -1):
            if se_block["cmo"][i] is not None:
                cmo_se = se_block["cmo"][i]
                break

    poc_anp = _series_poc_anp(poc, anp)
    # Desk gas prices are shown in R$/m³ (POC convention).
    for key in ("poc", "anpSantos", "anpNonThermalSe"):
        if key in poc_anp and isinstance(poc_anp[key], list):
            poc_anp[key] = [_mmbtu_to_m3(v) for v in poc_anp[key]]
    util = _util_table(contratos, flows)
    for block in (compare, poc_anp, util):
        if block.get("note"):
            notes.append(block["note"])

    # Spark default: last GUS trade (R$/m³), else POC 7d avg m³, else fallback.
    if gus.get("priceM3") is not None:
        default_gas = gus["priceM3"]
        gas_source = "gus_last"
    elif poc_kpi.get("avgPriceM3") is not None:
        default_gas = poc_kpi["avgPriceM3"]
        gas_source = "poc_7d"
    else:
        default_gas = SPARK_FALLBACK_GAS_M3
        gas_source = "fallback"

    through_candidates = [
        d for d in (
            pld_when, cmo_when, gen_when, anp_kpi.get("month"),
            gus.get("when"), poc_kpi.get("when"), flows_kpi.get("when"),
        )
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
            "gusLast": gus.get("priceM3"),
            "gusWhen": gus.get("when"),
            "gusTso": gus.get("tso"),
            "anpSantos": _mmbtu_to_m3(anp_kpi.get("santos")),
            "anpSantosMonth": anp_kpi.get("month"),
            "anpNonThermalSe": _mmbtu_to_m3(anp_kpi.get("nonThermalSe")),
            "anpNonThermalSeMonth": anp_kpi.get("monthNonThermalSe"),
            "pocAvg7d": poc_kpi.get("avgPriceM3"),
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
            "gasPriceSource": gas_source,
            "gasUnit": "R$/m3",
            "heatRateCcgt": float(heat["heat_rate_combined_cycle_kcal_per_kwh"]),
            "heatRateOcgt": float(heat["heat_rate_simple_cycle_kcal_per_kwh"]),
            "natgasKcalPerM3": float(heat["natgas_kcal_per_m3"]),
            "mmbtuPer1000M3": MMBTU_PER_1000_M3,
            "pldSe": pld_se,
            "cmoSe": cmo_se,
            "formulaEn": (
                "Implied CVU (R$/MWh) = gas (R$/m³) × heat rate (kcal/kWh) × 1000 "
                f"/ {heat['natgas_kcal_per_m3']:g} kcal/m³."
            ),
            "formulaPt": (
                "CVU implícito (R$/MWh) = gás (R$/m³) × heat rate (kcal/kWh) × 1000 "
                f"/ {heat['natgas_kcal_per_m3']:g} kcal/m³."
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
