"""Merge ANP and TSO point frames with precedence for Actual/Scheduled."""
from __future__ import annotations

import pandas as pd

from .base import TSO_OVERLAY_VARS, empty_points_frame


def merge_points(anp: pd.DataFrame, tso: pd.DataFrame) -> pd.DataFrame:
    """Prefer TSO Actual/Scheduled over ANP for the same date+point+variable.

    Matching keys (in order):
      1. (date, point_code, variable) when codes already align (crosswalk)
      2. else TSO rows are kept as additional series (synthetic codes)

    Non-overlay ANP variables (Requested, Allocation, Pressure) always kept.
    Ledger is never passed through this function.
    """
    cols = [
        "date", "point_code", "point_name", "point_type", "pipeline_code",
        "pipeline_name", "municipality", "uf", "tso", "variable", "value", "source",
    ]

    if anp is None or anp.empty:
        anp = empty_points_frame()
    else:
        anp = anp.copy()
        if "source" not in anp.columns:
            anp["source"] = "anp"
        anp["date"] = pd.to_datetime(anp["date"]).dt.normalize()

    if tso is None or tso.empty:
        tso = empty_points_frame()
    else:
        tso = tso.copy()
        tso["date"] = pd.to_datetime(tso["date"]).dt.normalize()
        tso = tso[tso["variable"].isin(TSO_OVERLAY_VARS)]

    if anp.empty and tso.empty:
        return empty_points_frame()
    if tso.empty:
        return anp[cols] if set(cols).issubset(anp.columns) else anp
    if anp.empty:
        return tso[cols]

    # Only overlay variables compete; keep all other ANP rows untouched.
    anp_overlay = anp[anp["variable"].isin(TSO_OVERLAY_VARS)].copy()
    anp_other = anp[~anp["variable"].isin(TSO_OVERLAY_VARS)].copy()

    keys = ["date", "point_code", "variable"]
    tso_keys = tso[keys].drop_duplicates()
    if not anp_overlay.empty and not tso_keys.empty:
        merged_flags = anp_overlay.merge(
            tso_keys.assign(_tso_hit=1),
            on=keys,
            how="left",
        )
        keep_anp = merged_flags[merged_flags["_tso_hit"].isna()].drop(columns=["_tso_hit"])
    else:
        keep_anp = anp_overlay

    out = pd.concat([anp_other, keep_anp, tso], ignore_index=True)
    # Deduplicate safety: if both somehow remain, TSO wins
    out["_rank"] = out["source"].map({"anp": 1, "tag": 0, "tbg": 0, "nts": 0}).fillna(2)
    out = (
        out.sort_values(["date", "point_code", "variable", "_rank"])
        .drop_duplicates(subset=keys, keep="first")
        .drop(columns=["_rank"])
    )
    for c in cols:
        if c not in out.columns:
            out[c] = None
    return out[cols].sort_values(["pipeline_name", "point_name", "variable", "date"]).reset_index(drop=True)
