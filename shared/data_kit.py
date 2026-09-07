"""
Shared data-layer helpers for GasBrazil (ADR-002 Track A / R2 artifacts).

Canonical schemas live in shared/schemas/. Versioned assumptions live in
shared/transforms.py; cross-product helpers in shared/joins.py. Pipelines
call validate_* after build and publish() into the repo-root lake/ tree
(and, when configured, mirror to Cloudflare R2).
"""
from __future__ import annotations

import os
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
    "ons_entities": LAKE_ROOT / "power" / "ons_entities.parquet",
    "pld_daily": LAKE_ROOT / "power" / "pld_daily.parquet",
    "supply_monthly": LAKE_ROOT / "supply" / "supply_monthly.parquet",
}

# Dashboard slug → artifact key prefix under the public R2 artifacts bucket.
ARTIFACT_DOMAINS = ("ons", "flows", "poc", "contratos", "supply", "pld")


def lake_path(name: str) -> Path:
    if name not in LAKE_PATHS:
        raise KeyError(f"Unknown lake dataset {name!r}; known: {sorted(LAKE_PATHS)}")
    return LAKE_PATHS[name]


def r2_configured() -> bool:
    return bool(
        os.environ.get("R2_ENDPOINT_URL")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
    )


def _r2_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"].rstrip("/"),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def upload_to_r2(
    local_path: Path | str,
    *,
    bucket: str,
    key: str,
    content_type: str = "application/octet-stream",
    cache_control: str = "public, max-age=300",
) -> str:
    """Upload a file to an R2 bucket. Returns s3://bucket/key."""
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(local_path)
    client = _r2_client()
    extra = {"ContentType": content_type, "CacheControl": cache_control}
    client.upload_file(
        str(local_path),
        bucket,
        key,
        ExtraArgs=extra,
    )
    return f"s3://{bucket}/{key}"


def publish(name: str, src: Path | pd.DataFrame) -> Path:
    """Copy or write a parquet into the canonical lake path; mirror to R2 when configured."""
    dest = lake_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(src, pd.DataFrame):
        src.to_parquet(dest, index=False)
    else:
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy2(src, dest)

    lake_bucket = os.environ.get("GASBRAZIL_LAKE_BUCKET", "").strip()
    if r2_configured() and lake_bucket:
        rel = dest.relative_to(LAKE_ROOT).as_posix()
        uri = upload_to_r2(
            dest,
            bucket=lake_bucket,
            key=rel,
            content_type="application/vnd.apache.parquet",
            cache_control="private, max-age=300",
        )
        print(f"  R2 lake: {uri}")
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


def payload_url(domain: str) -> str:
    """Public URL for a dashboard artifact, or sibling-relative for local/dev."""
    if domain not in ARTIFACT_DOMAINS:
        raise KeyError(f"Unknown artifact domain {domain!r}; known: {ARTIFACT_DOMAINS}")
    base = os.environ.get("GASBRAZIL_DATA_BASE_URL", "").strip().rstrip("/")
    bust = os.environ.get("GASBRAZIL_DATA_CACHE_BUST", "").strip()
    if not base:
        return "payload.json.gz"
    url = f"{base}/{domain}/payload.json.gz"
    if bust:
        url += f"?v={bust}"
    return url


def write_and_publish_artifact(
    domain: str,
    payload: dict,
    local_dir: Path | str,
    *,
    compresslevel: int = 9,
) -> tuple[Path, str]:
    """Write payload.json.gz locally, upload to R2 artifacts bucket when configured.

    Returns (local_path, url_for_html). Does not set Content-Encoding: gzip so
    the browser receives raw gzip bytes for DecompressionStream.
    """
    if domain not in ARTIFACT_DOMAINS:
        raise KeyError(f"Unknown artifact domain {domain!r}; known: {ARTIFACT_DOMAINS}")
    local_dir = Path(local_dir)
    path = write_json_gzip(payload, local_dir / "payload.json.gz", compresslevel=compresslevel)

    art_bucket = os.environ.get("GASBRAZIL_ARTIFACTS_BUCKET", "").strip()
    if r2_configured() and art_bucket:
        uri = upload_to_r2(
            path,
            bucket=art_bucket,
            key=f"{domain}/payload.json.gz",
            content_type="application/gzip",
            cache_control="public, max-age=300",
        )
        print(f"  R2 artifact: {uri}")
    elif os.environ.get("GASBRAZIL_DATA_BASE_URL", "").strip() and not r2_configured():
        print(
            "  warning: GASBRAZIL_DATA_BASE_URL is set but R2 credentials are missing; "
            "HTML will point at R2 while the local payload was not uploaded"
        )

    return path, payload_url(domain)
