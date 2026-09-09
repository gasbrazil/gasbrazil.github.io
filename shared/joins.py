"""
Cross-product lake joins (ADR-002 Track A).

First-class helpers so hub teasers and the API stop inventing ad-hoc merges.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

import transforms as xf


def _subsystem_rows(ons: pd.DataFrame) -> pd.DataFrame:
    """Keep subsystem-level ONS rows (empty entity). NaN-safe across pandas 2/3."""
    if "entity" not in ons.columns:
        return ons
    entity = ons["entity"].fillna("").astype(str).str.strip()
    # fillna before astype so pandas 2.x does not turn NA into the literal
    # "nan" and drop every subsystem CMO row.
    lowered = entity.str.casefold()
    empty = entity.eq("") | lowered.isin(("nan", "none", "<na>"))
    return ons[empty]


def join_pld_cmo(
    pld: pd.DataFrame,
    ons: pd.DataFrame,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Daily PLD vs ONS CMO by submarket.

    Expects canonical columns:
      pld: date, submarket, pld
      ons: date, subsystem, series, value  (entity empty = subsystem row)
    """
    need_pld = {"date", "submarket", "pld"}
    need_ons = {"date", "subsystem", "series", "value"}
    if not need_pld.issubset(pld.columns):
        raise ValueError(f"pld missing {need_pld - set(pld.columns)}")
    if not need_ons.issubset(ons.columns):
        raise ValueError(f"ons missing {need_ons - set(ons.columns)}")

    p = pld.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    p["submarket"] = p["submarket"].astype(str).str.upper()

    if date_from is not None:
        p = p[p["date"] >= date_from]
    if date_to is not None:
        p = p[p["date"] <= date_to]

    cmo = _ons_series_by_submarket(ons, "cmo", value_name="cmo")
    if date_from is not None:
        cmo = cmo[cmo["date"] >= date_from]
    if date_to is not None:
        cmo = cmo[cmo["date"] <= date_to]

    out = p.merge(cmo, on=["date", "submarket"], how="inner")
    out["spread_pld_minus_cmo"] = out["pld"].astype(float) - out["cmo"].astype(float)
    return out.sort_values(["date", "submarket"]).reset_index(drop=True)


def _ons_series_by_submarket(
    ons: pd.DataFrame,
    series: str,
    *,
    value_name: str,
) -> pd.DataFrame:
    """Subsystem-level ONS series → PLD submarket codes."""
    need = {"date", "subsystem", "series", "value"}
    if not need.issubset(ons.columns):
        raise ValueError(f"ons missing {need - set(ons.columns)}")
    o = ons.copy()
    o["date"] = pd.to_datetime(o["date"]).dt.normalize()
    o = o[o["series"].astype(str) == series]
    o = _subsystem_rows(o)
    o["subsystem"] = o["subsystem"].astype(str).str.upper()
    inv = {v: k for k, v in xf.PLD_ONS_SUBMARKET_MAP.items()}
    o["submarket"] = o["subsystem"].map(inv)
    o = o.dropna(subset=["submarket"])
    return o.rename(columns={"value": value_name})[["date", "submarket", value_name]]


def join_pld_cmo_cvu(
    pld: pd.DataFrame,
    ons: pd.DataFrame,
    *,
    cvu_series: str = "cvu_gas_med",
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    how: str = "left",
) -> pd.DataFrame:
    """Daily PLD vs ONS CMO vs gas-fleet CVU rollup by submarket.

    CVU columns are ONS planning variable unit costs for gas-fired plants
    (R$/MWh), not market prices. Default ``cvu_gas_med`` is the median.
    """
    need_pld = {"date", "submarket", "pld"}
    if not need_pld.issubset(pld.columns):
        raise ValueError(f"pld missing {need_pld - set(pld.columns)}")
    p = pld.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    p["submarket"] = p["submarket"].astype(str).str.upper()
    if date_from is not None:
        p = p[p["date"] >= date_from]
    if date_to is not None:
        p = p[p["date"] <= date_to]

    cmo = _ons_series_by_submarket(ons, "cmo", value_name="cmo")
    cvu = _ons_series_by_submarket(ons, cvu_series, value_name="cvu_gas_med")
    if date_from is not None:
        cmo = cmo[cmo["date"] >= date_from]
        cvu = cvu[cvu["date"] >= date_from]
    if date_to is not None:
        cmo = cmo[cmo["date"] <= date_to]
        cvu = cvu[cvu["date"] <= date_to]

    out = p.merge(cmo, on=["date", "submarket"], how=how)
    out = out.merge(cvu, on=["date", "submarket"], how=how)
    out["spread_pld_minus_cmo"] = out["pld"].astype(float) - out["cmo"].astype(float)
    return out.sort_values(["date", "submarket"]).reset_index(drop=True)


def join_poc_vs_anp_monthly(
    poc: pd.DataFrame,
    anp: pd.DataFrame,
) -> pd.DataFrame:
    """Monthly mean POC auction price vs ANP disclosed prices.

    Expects:
      poc: Trade Date, Price (R$/MMBtu)
      anp: month (YYYY-MM), segment, price_brl_mmbtu (or price)
    """
    need_poc = {"Trade Date", "Price"}
    if not need_poc.issubset(poc.columns):
        raise ValueError(f"poc missing {need_poc - set(poc.columns)}")
    price_col = "price_brl_mmbtu" if "price_brl_mmbtu" in anp.columns else "price"
    if "month" not in anp.columns or "segment" not in anp.columns:
        raise ValueError("anp missing month/segment")
    if price_col not in anp.columns:
        raise ValueError(f"anp missing {price_col}")

    p = poc.copy()
    p["Trade Date"] = pd.to_datetime(p["Trade Date"], errors="coerce")
    p = p.dropna(subset=["Trade Date", "Price"])
    p["month"] = p["Trade Date"].dt.strftime("%Y-%m")
    poc_m = (
        p.groupby("month", as_index=False)["Price"]
        .mean()
        .rename(columns={"Price": "poc_avg_price"})
    )

    a = anp.copy()
    a["month"] = a["month"].astype(str).str.slice(0, 7)
    a = a.rename(columns={price_col: "price"})
    out = a.merge(poc_m, on="month", how="left")
    out["spread_anp_minus_poc"] = out["price"].astype(float) - out["poc_avg_price"].astype(float)
    return out.sort_values(["month", "segment"]).reset_index(drop=True)


def join_capacity_vs_flows(
    contratos: pd.DataFrame,
    flows_points: pd.DataFrame,
    *,
    flow_variable: str | None = None,
) -> pd.DataFrame:
    """Active contracted capacity vs recent realized receipt/delivery by TSO.

    Expects:
      contratos: Transporter (TSO), Status, Contracted Capacity (000 m3/d)
      flows_points: date, tso, variable, value (thousand m³/d-ish daily volumes)

    ``flow_variable`` defaults to the lake English name
    ``Actual Volume (thousand m3)``; falls back to the Portuguese source
    label ``Volume Realizado (mil m³)`` when that is what the frame has.
    """
    cap_col = "Contracted Capacity (000 m3/d)"
    tso_col = "Transporter (TSO)"
    need_c = {tso_col, cap_col}
    need_f = {"date", "tso", "variable", "value"}
    if not need_c.issubset(contratos.columns):
        raise ValueError(f"contratos missing {need_c - set(contratos.columns)}")
    if not need_f.issubset(flows_points.columns):
        raise ValueError(f"flows missing {need_f - set(flows_points.columns)}")

    c = contratos.copy()
    if "Status" in c.columns:
        c = c[c["Status"].astype(str).str.casefold() != "concluded"]
    c["tso"] = c[tso_col].astype(str).str.upper().str.strip()
    cap = c.groupby("tso", as_index=False)[cap_col].sum().rename(
        columns={cap_col: "contracted_thousand_m3_d"}
    )

    f = flows_points.copy()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    f = f.dropna(subset=["date"])
    if flow_variable is None:
        present = set(f["variable"].astype(str).unique())
        for candidate in (
            "Actual Volume (thousand m3)",
            "Volume Realizado (mil m³)",
            "Volume Realizado",
        ):
            if candidate in present:
                flow_variable = candidate
                break
        else:
            flow_variable = "Actual Volume (thousand m3)"
    f = f[f["variable"].astype(str) == flow_variable]
    f["tso"] = f["tso"].astype(str).str.upper().str.strip()
    # Prefer TSO Portaria overlays over ANP when both exist for a transporter,
    # so utilization does not double-count synthetic-coded TAG/TBG/NTS meters
    # alongside ANP point codes for the same physical network.
    if "source" in f.columns:
        f["_src"] = f["source"].astype(str).str.casefold()
        tso_with_overlay = set(f.loc[f["_src"].isin(("tag", "tbg", "nts")), "tso"])
        if tso_with_overlay:
            keep = ~f["tso"].isin(tso_with_overlay) | f["_src"].isin(("tag", "tbg", "nts"))
            f = f.loc[keep]
        f = f.drop(columns=["_src"])
    # Average daily realized over the last 30 days of data per TSO.
    last = f["date"].max()
    window = f[f["date"] >= (last - pd.Timedelta(days=xf.CAPACITY_FLOW_WINDOW_DAYS))]
    flow = (
        window.groupby("tso", as_index=False)["value"]
        .mean()
        .rename(columns={"value": "realized_avg_thousand_m3_d"})
    )

    out = cap.merge(flow, on="tso", how="outer")
    contracted = out["contracted_thousand_m3_d"].astype(float)
    realized = out["realized_avg_thousand_m3_d"].astype(float)
    out["utilization"] = np.divide(
        realized,
        contracted,
        out=np.full(len(out), np.nan, dtype=float),
        where=contracted > 0,
    )
    out["as_of"] = last.strftime("%Y-%m-%d") if pd.notna(last) else None
    return out.sort_values("tso").reset_index(drop=True)
