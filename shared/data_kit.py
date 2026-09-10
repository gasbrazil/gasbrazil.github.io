"""
Shared data-layer helpers for GasBrazil (ADR-002 Track A / R2 artifacts).

Canonical schemas live in shared/schemas/. Versioned assumptions live in
shared/transforms.py; cross-product helpers in shared/joins.py. Pipelines
call validate_* after build and publish() into the repo-root lake/ tree
(and, when configured, mirror to Cloudflare R2).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
LAKE_ROOT = REPO_ROOT / "lake"

# Dashboard slug → artifact key prefix under the public R2 artifacts bucket.
ARTIFACT_DOMAINS = ("ons", "flows", "poc", "contratos", "supply", "pld", "precos", "desk", "hub")

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
    "anp_prices": LAKE_ROOT / "supply" / "anp_prices.parquet",
}


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
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 8, "mode": "standard"},
        ),
    )


def _retry(fn: Callable, *, attempts: int = 4, label: str = "r2"):
    """Retry transient failures; last exception is re-raised."""
    delay = 0.6
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — network/SDK surface is broad
            last = exc
            if i == attempts - 1:
                break
            print(f"  {label} retry {i + 1}/{attempts - 1}: {exc}")
            time.sleep(delay)
            delay *= 2
    assert last is not None
    raise last


def _atomic_replace(tmp: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, dest)


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


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
    extra = {"ContentType": content_type, "CacheControl": cache_control}

    def _do():
        client = _r2_client()
        client.upload_file(str(local_path), bucket, key, ExtraArgs=extra)

    _retry(_do, label=f"upload {key}")
    return f"s3://{bucket}/{key}"


def download_from_r2(
    *,
    bucket: str,
    key: str,
    dest: Path | str,
) -> Path | None:
    """Download an R2 object to dest. Returns dest on success, None if missing.

    Writes to a sibling ``.tmp`` then ``os.replace`` so a truncated object
    never occupies the canonical path.
    """
    from botocore.exceptions import ClientError

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")

    def _do():
        _unlink_quiet(tmp)
        client = _r2_client()
        client.download_file(bucket, key, str(tmp))

    try:
        _retry(_do, label=f"download {key}")
    except ClientError as exc:
        _unlink_quiet(tmp)
        code = (exc.response or {}).get("Error", {}).get("Code", "")
        status = (exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound", "404 Not Found") or status == 404:
            return None
        raise
    except Exception:
        _unlink_quiet(tmp)
        raise
    _atomic_replace(tmp, dest)
    return dest


def ensure_lake(
    names: Iterable[str],
    *,
    force: bool = False,
) -> dict[str, Path | None]:
    """Ensure lake parquet files exist locally; pull from R2 when missing.

    Returns {name: local Path or None if unavailable}. Missing remote
    objects (404) degrade to None; auth/5xx errors are re-raised so CI
    does not silently ship an empty Desk.
    """
    lake_bucket = os.environ.get("GASBRAZIL_LAKE_BUCKET", "").strip()
    out: dict[str, Path | None] = {}
    for name in names:
        dest = lake_path(name)
        if dest.exists() and not force:
            out[name] = dest
            continue
        if not (r2_configured() and lake_bucket):
            out[name] = dest if dest.exists() else None
            continue
        rel = dest.relative_to(LAKE_ROOT).as_posix()
        got = download_from_r2(bucket=lake_bucket, key=rel, dest=dest)
        if got is not None:
            print(f"  lake pull {name}: {got} ({got.stat().st_size:,} bytes)")
        else:
            print(f"  lake pull {name}: not in R2")
        out[name] = got if got is not None and got.exists() else None
    return out


def publish(name: str, src: Path | pd.DataFrame) -> Path:
    """Copy or write a parquet into the canonical lake path; mirror to R2 when configured.

    Local write is atomic (tmp + replace) so a crash cannot leave a truncated
    parquet that ``ensure_lake`` would then treat as present.
    """
    dest = lake_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        if isinstance(src, pd.DataFrame):
            src.to_parquet(tmp, index=False)
        else:
            src = Path(src)
            if not src.exists():
                raise FileNotFoundError(src)
            shutil.copy2(src, tmp)
        _atomic_replace(tmp, dest)
    except Exception:
        _unlink_quiet(tmp)
        raise

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
    blob = gzip.compress(raw, compresslevel=compresslevel, mtime=0)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(blob)
        _atomic_replace(tmp, path)
    except Exception:
        _unlink_quiet(tmp)
        raise
    return path


def _public_url(remote_key: str, *, local: str) -> str:
    """Public URL for an artifacts-bucket object, or ``local`` for offline."""
    base = os.environ.get("GASBRAZIL_DATA_BASE_URL", "").strip().rstrip("/")
    bust = os.environ.get("GASBRAZIL_DATA_CACHE_BUST", "").strip()
    if not base:
        return local
    url = f"{base}/{remote_key}"
    if bust:
        url += "?v=" + quote(str(bust), safe="")
    return url


def payload_url(domain: str) -> str:
    """Public URL for a dashboard artifact, or sibling-relative for local/dev."""
    if domain not in ARTIFACT_DOMAINS:
        raise KeyError(f"Unknown artifact domain {domain!r}; known: {ARTIFACT_DOMAINS}")
    return _public_url(f"{domain}/payload.json.gz", local="payload.json.gz")


def published_payload_url(html_path: Path | str) -> str:
    """Read the PAYLOAD_URL already baked into a dashboard shell."""
    text = Path(html_path).read_text(encoding="utf-8")
    match = re.search(r'const PAYLOAD_URL = "([^"]+)"', text)
    if not match:
        raise ValueError(f"PAYLOAD_URL not found in {html_path}")
    return match.group(1)


def published_teaser_markers(html_path: Path | str) -> dict[str, str]:
    """Parse hub teaser ``key: value`` lines from a dashboard HTML comment."""
    text = Path(html_path).read_text(encoding="utf-8")
    out: dict[str, str] = {}
    in_block = False
    for line in text.splitlines():
        if "home-page teaser marker" in line:
            in_block = True
        if not in_block:
            continue
        match = re.match(r"\s+([A-Za-z0-9_]+): (.+)$", line)
        if match:
            val = match.group(2).strip()
            if val.endswith("-->"):
                val = val[:-3].strip()
            out[match.group(1)] = val
        closing = "-->" in line
        opener = "home-page teaser marker" in line
        if closing and not opener:
            break
    return out


def _upload_public_artifact(
    local: Path,
    key: str,
    *,
    content_type: str,
    cache_control: str,
    log_label: str,
) -> None:
    """Upload a public artifact, or fail loudly if HTML will point at R2."""
    art_bucket = os.environ.get("GASBRAZIL_ARTIFACTS_BUCKET", "").strip()
    want_remote = bool(os.environ.get("GASBRAZIL_DATA_BASE_URL", "").strip())
    if r2_configured() and art_bucket:
        uri = upload_to_r2(
            local,
            bucket=art_bucket,
            key=key,
            content_type=content_type,
            cache_control=cache_control,
        )
        print(f"  {log_label}: {uri}")
        return
    if want_remote:
        raise RuntimeError(
            "GASBRAZIL_DATA_BASE_URL is set but R2 credentials / "
            "GASBRAZIL_ARTIFACTS_BUCKET are missing; refusing to emit HTML "
            "that points at an unuploaded artifact"
        )


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
    _upload_public_artifact(
        path,
        f"{domain}/payload.json.gz",
        content_type="application/gzip",
        cache_control="public, max-age=300",
        log_label="R2 artifact",
    )
    return path, payload_url(domain)


def teaser_url() -> str:
    """Public URL for hub teasers aggregate, or local sibling for offline."""
    return _public_url("hub/teasers.json.gz", local="hub/teasers.json.gz")


def write_and_publish_teasers(
    teasers: dict,
    local_dir: Path | str | None = None,
    *,
    compresslevel: int = 9,
) -> tuple[Path, str]:
    """Write hub/teasers.json.gz and upload to R2 when configured."""
    local_dir = Path(local_dir) if local_dir else (REPO_ROOT / "hub")
    local_dir.mkdir(parents=True, exist_ok=True)
    path = write_json_gzip(teasers, local_dir / "teasers.json.gz", compresslevel=compresslevel)
    _upload_public_artifact(
        path,
        "hub/teasers.json.gz",
        content_type="application/gzip",
        cache_control="public, max-age=120",
        log_label="R2 hub teasers",
    )
    return path, teaser_url()
