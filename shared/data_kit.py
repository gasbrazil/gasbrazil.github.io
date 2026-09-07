"""
Shared data-layer helpers for GasBrazil (ADR-002 Track A).

Canonical schemas live in shared/schemas/. Pipelines call validate_* after
build and optionally publish() into the repo-root lake/ tree so the API and
future cross-product jobs read one layout.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
LAKE_ROOT = REPO_ROOT / "lake"

# Domain → relative lake path (parquet files).
LAKE_PATHS = {
    "flows_points": LAKE_ROOT / "transport" / "flows_points.parquet",
    "flows_ledger": LAKE_ROOT / "transport" / "flows_ledger.parquet",
    "poc_results": LAKE_ROOT / "transport" / "poc_results.parquet",
    "contratos": LAKE_ROOT / "transport" / "contratos.parquet",
    "ons_daily": LAKE_ROOT / "power" / "ons_daily.parquet",
    "pld_daily": LAKE_ROOT / "power" / "pld_daily.parquet",
    "supply_monthly": LAKE_ROOT / "supply" / "supply_monthly.parquet",
}


def lake_path(name: str) -> Path:
    if name not in LAKE_PATHS:
        raise KeyError(f"Unknown lake dataset {name!r}; known: {sorted(LAKE_PATHS)}")
    return LAKE_PATHS[name]


def publish(name: str, src: Path | pd.DataFrame) -> Path:
    """Copy or write a parquet into the canonical lake path."""
    dest = lake_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(src, pd.DataFrame):
        src.to_parquet(dest, index=False)
    else:
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy2(src, dest)
    return dest


def require_columns(df: pd.DataFrame, columns: Iterable[str], *, label: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label}: missing columns {missing}; have {list(df.columns)}")


def coerce_dates(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce")
    if out[col].isna().any():
        bad = int(out[col].isna().sum())
        raise ValueError(f"Column {col!r}: {bad} unparseable date(s)")
    return out


def write_json_gzip(payload: dict, path: Path, *, compresslevel: int = 9) -> Path:
    """Track B artifact: raw gzip JSON (no base64). Smaller than HTML embed."""
    import gzip
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, compresslevel=compresslevel, mtime=0))
    return path
