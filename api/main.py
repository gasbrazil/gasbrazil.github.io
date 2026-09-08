"""
GasBrazil read-only query API (ADR-002 Track C).

Reads canonical lake parquet when present, else falls back to each
dashboard's data/*.parquet. Does not proxy ANP/ONS/CCEE live.

Run locally:
  pip install -r api/requirements.txt
  uvicorn api.main:app --reload --port 8000

OpenAPI: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import data_kit as dk  # noqa: E402
import joins  # noqa: E402
import transforms as xf  # noqa: E402

app = FastAPI(
    title="GasBrazil API",
    version="0.1.0",
    description=(
        "Read-only slices of GasBrazil's open-data lake. "
        "Ingest remains CI-side; this service only queries parquet."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gasbrazil.com",
        "https://gasbrazil.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",  # file:// during local HTML checks
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Fallback paths when lake/ has not been published yet.
_FALLBACKS = {
    "flows_points": ROOT / "flows" / "data" / "flows_points.parquet",
    "flows_ledger": ROOT / "flows" / "data" / "flows_ledger.parquet",
    "pld_daily": ROOT / "pld" / "data" / "pld_daily.parquet",
    "supply_monthly": ROOT / "supply" / "data" / "supply_monthly.parquet",
    "poc_results": ROOT / "poc" / "data" / "poc_results.parquet",
    "contratos": ROOT / "contratos" / "data" / "contratos.parquet",
    "ons_daily": ROOT / "ons" / "data" / "daily.parquet",
    "ons_entities": ROOT / "ons" / "data" / "entities.parquet",
}


def _load(name: str) -> pd.DataFrame:
    lake = dk.lake_path(name)
    path = lake if lake.exists() else _FALLBACKS.get(name)
    if path is None or not Path(path).exists():
        raise HTTPException(
            status_code=503,
            detail=f"Dataset {name!r} not built yet (no lake/ or project parquet).",
        )
    return pd.read_parquet(path)


def _parse_day(s: Optional[str]) -> Optional[pd.Timestamp]:
    if not s:
        return None
    try:
        return pd.Timestamp(s)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid date {s!r}") from exc


def _records(df: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    if len(df) > limit:
        df = df.head(limit)
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    return out.astype(object).where(pd.notna(out), None).to_dict(orient="records")


@app.get("/health")
def health() -> dict[str, Any]:
    present = {
        name: (dk.lake_path(name).exists() or _FALLBACKS[name].exists())
        for name in _FALLBACKS
    }
    return {
        "ok": True,
        "datasets": present,
        "transforms": xf.registry_summary(),
    }


@app.get("/v1/flows/points")
def flows_points(
    tso: Optional[str] = None,
    point_code: Optional[str] = None,
    variable: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict[str, Any]:
    df = _load("flows_points")
    d0, d1 = _parse_day(date_from), _parse_day(date_to)
    if d0 is not None:
        df = df[df["date"] >= d0]
    if d1 is not None:
        df = df[df["date"] <= d1]
    if tso:
        df = df[df["tso"].astype(str).str.upper() == tso.upper()]
    if point_code:
        df = df[df["point_code"].astype(str) == point_code]
    if variable:
        df = df[df["variable"].astype(str) == variable]
    if source and "source" in df.columns:
        df = df[df["source"].astype(str).str.casefold() == source.casefold()]
    df = df.sort_values(["date", "tso", "point_code"])
    return {"count": int(len(df)), "limit": limit, "rows": _records(df, limit)}


@app.get("/v1/pld/daily")
def pld_daily(
    submarket: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict[str, Any]:
    df = _load("pld_daily")
    d0, d1 = _parse_day(date_from), _parse_day(date_to)
    if d0 is not None:
        df = df[df["date"] >= d0]
    if d1 is not None:
        df = df[df["date"] <= d1]
    if submarket:
        sm = submarket.upper()
        df = df[df["submarket"].astype(str).str.upper() == sm]
    df = df.sort_values(["date", "submarket"])
    return {"count": int(len(df)), "limit": limit, "rows": _records(df, limit)}


@app.get("/v1/supply/monthly")
def supply_monthly(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    df = _load("supply_monthly")
    # month is YYYY-MM string in the store
    if date_from:
        df = df[df["month"].astype(str) >= date_from[:7]]
    if date_to:
        df = df[df["month"].astype(str) <= date_to[:7]]
    df = df.sort_values("month")
    return {"count": int(len(df)), "limit": limit, "rows": _records(df, limit)}


@app.get("/v1/ons/balances")
def ons_balances(
    subsystem: Optional[str] = None,
    series: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict[str, Any]:
    df = _load("ons_daily")
    if "date" not in df.columns:
        raise HTTPException(503, "ons_daily missing date column")
    d0, d1 = _parse_day(date_from), _parse_day(date_to)
    if d0 is not None:
        df = df[pd.to_datetime(df["date"]) >= d0]
    if d1 is not None:
        df = df[pd.to_datetime(df["date"]) <= d1]
    if subsystem and "subsystem" in df.columns:
        df = df[df["subsystem"].astype(str) == subsystem]
    if series and "series" in df.columns:
        df = df[df["series"].astype(str) == series]
    # Prefer subsystem-level rows (empty entity) when present
    if "entity" in df.columns:
        sub = df[df["entity"].astype(str) == ""]
        if len(sub):
            df = sub
    sort_cols = [c for c in ("date", "subsystem", "series") if c in df.columns]
    df = df.sort_values(sort_cols)
    return {"count": int(len(df)), "limit": limit, "rows": _records(df, limit)}


@app.get("/v1/power/pld-cmo")
def power_pld_cmo(
    submarket: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict[str, Any]:
    """Cross-product join: CCEE PLD vs ONS CMO by submarket/day."""
    try:
        joined = joins.join_pld_cmo(
            _load("pld_daily"),
            _load("ons_daily"),
            date_from=_parse_day(date_from),
            date_to=_parse_day(date_to),
        )
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    if submarket:
        sm = submarket.upper()
        joined = joined[joined["submarket"].astype(str).str.upper() == sm]
    return {
        "count": int(len(joined)),
        "limit": limit,
        "transform": "pld_ons_submarket_map",
        "rows": _records(joined, limit),
    }
