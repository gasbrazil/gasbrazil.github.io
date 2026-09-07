"""
Cross-product lake joins (ADR-002 Track A).

First-class helpers so hub teasers and the API stop inventing ad-hoc merges.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

import transforms as xf


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

    o = ons.copy()
    o["date"] = pd.to_datetime(o["date"]).dt.normalize()
    o = o[o["series"].astype(str) == "cmo"]
    if "entity" in o.columns:
        o = o[o["entity"].astype(str).fillna("") == ""]
    o["subsystem"] = o["subsystem"].astype(str).str.upper()
    # Map ONS subsystem → PLD submarket (identity for N/NE/SE/S).
    inv = {v: k for k, v in xf.PLD_ONS_SUBMARKET_MAP.items()}
    o["submarket"] = o["subsystem"].map(inv)
    o = o.dropna(subset=["submarket"])
    o = o.rename(columns={"value": "cmo"})[["date", "submarket", "cmo"]]

    if date_from is not None:
        p = p[p["date"] >= date_from]
        o = o[o["date"] >= date_from]
    if date_to is not None:
        p = p[p["date"] <= date_to]
        o = o[o["date"] <= date_to]

    out = p.merge(o, on=["date", "submarket"], how="inner")
    out["spread_pld_minus_cmo"] = out["pld"].astype(float) - out["cmo"].astype(float)
    return out.sort_values(["date", "submarket"]).reset_index(drop=True)
