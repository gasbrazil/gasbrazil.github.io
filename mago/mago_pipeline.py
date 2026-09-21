"""
TAG Mago (Monitoramento Automatizado de Gestão Operacional) pipeline.

Fetches hourly JSON snapshots from Mago's public S3 proxy API and builds a
long tidy parquet store covering:

  * Integrated / North line pack (actual, hourly within each snapshot day)
  * Integrated line pack forecast (short horizon)
  * TAG balancing-zone consumption forecasts (7-day hourly horizon)

Source API (same backend for mago.ntag.com.br/empacotamento and
/previsao-consumo):

  GET https://api-mago-prod-lb.ntag.com.br/api/s3/list[?prefix=...]
  GET https://api-mago-prod-lb.ntag.com.br/api/s3/object?key=EMPACOTAMENTOS_*.json

Usage:
    python mago_pipeline.py fetch [--days N] [--backfill-from YYYY-MM-DD]
    python mago_pipeline.py build
    python mago_pipeline.py all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw" / "snapshots"
MANIFEST_PATH = HERE / "raw" / "_manifest.json"
DATA_DIR = HERE / "data"
PARQUET_PATH = DATA_DIR / "tag_mago_series.parquet"

sys.path.insert(0, str(HERE.parent / "shared"))
import data_kit as dk  # noqa: E402
from mago_client import (  # noqa: E402
    MagoObject,
    fetch_object_json,
    filter_objects_by_calendar,
    list_all_objects,
    parse_snapshot_key,
    rows_from_snapshot,
)
from schemas import validate_tag_mago_series  # noqa: E402

DEFAULT_FETCH_DAYS = 14
MAX_STALENESS_DAYS = 2


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"files": {}}


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def _manifest_entry(obj: MagoObject) -> dict:
    return {
        "etag": obj.etag,
        "size": obj.size,
        "last_modified": obj.last_modified.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def cmd_fetch(*, days: int | None, backfill_from: date | None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    files_meta: dict = manifest.setdefault("files", {})

    print("Listing Mago snapshot index…")
    all_objects = list_all_objects()
    empacot = [o for o in all_objects if o.key.startswith("EMPACOTAMENTOS_") and o.key.endswith(".json")]
    print(f"  {len(empacot)} EMPACOTAMENTOS snapshots in API index")

    today = _utc_today()
    if backfill_from:
        start = backfill_from
    elif days is not None:
        start = today - timedelta(days=max(1, days) - 1)
    else:
        start = today - timedelta(days=DEFAULT_FETCH_DAYS - 1)

    candidates = filter_objects_by_calendar(empacot, start=start, end=today)
    print(f"  {len(candidates)} snapshots in window {start} → {today}")

    downloaded = skipped = failed = 0
    for obj in candidates:
        prev = files_meta.get(obj.key) or {}
        if prev.get("etag") and obj.etag and prev.get("etag") == obj.etag:
            if (RAW_DIR / obj.key).exists():
                skipped += 1
                continue
        dest = RAW_DIR / obj.key
        try:
            payload = fetch_object_json(obj.key)
            dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            files_meta[obj.key] = _manifest_entry(obj)
            downloaded += 1
            if downloaded % 25 == 0:
                print(f"  … downloaded {downloaded} snapshots")
        except Exception as e:
            failed += 1
            print(f"  warn: failed {obj.key}: {e}")

    manifest["last_fetch"] = datetime.now(UTC).isoformat()
    manifest["fetch_window"] = {"start": start.isoformat(), "end": today.isoformat()}
    _save_manifest(manifest)
    print(f"Fetch done: downloaded={downloaded} skipped={skipped} failed={failed}")


def _iter_cached_snapshots() -> list[tuple[datetime, Path]]:
    rows: list[tuple[datetime, Path]] = []
    for path in sorted(RAW_DIR.glob("EMPACOTAMENTOS_*.json")):
        snap, _ = parse_snapshot_key(path.name)
        if snap is None:
            continue
        rows.append((snap, path))
    return rows


def cmd_build() -> None:
    snapshots = _iter_cached_snapshots()
    if not snapshots:
        raise SystemExit("No cached Mago snapshots — run fetch first")

    all_rows: list[dict] = []
    for snap_at, path in snapshots:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  warn: skip corrupt {path.name}: {e}")
            continue
        all_rows.extend(rows_from_snapshot(snap_at, payload))

    if not all_rows:
        raise SystemExit("No usable Mago rows in cached snapshots")

    df = pd.DataFrame(all_rows)
    df["snapshot_at"] = pd.to_datetime(df["snapshot_at"], utc=True)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["mesh"] = df["mesh"].astype("string")
    df["zone"] = df["zone"].astype("string")
    df["tag"] = df["tag"].astype(str)
    df["series"] = df["series"].astype(str)
    df["unit"] = df["unit"].astype(str)
    df["source"] = df["source"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    validate_tag_mago_series(df)

    latest_snap = df["snapshot_at"].max()
    age_days = (_utc_today() - latest_snap.date()).days
    if age_days > MAX_STALENESS_DAYS:
        raise SystemExit(
            f"Health gate: newest snapshot {latest_snap} is {age_days} days old "
            f"(max {MAX_STALENESS_DAYS})"
        )

    zones = df.loc[df["series"] == "zone_consumption_forecast", "zone"].dropna().unique()
    if len(zones) < 10:
        raise SystemExit(f"Health gate: expected many TAG zones, got {len(zones)}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.sort_values(["snapshot_at", "series", "zone", "observed_at"], inplace=True)
    df.to_parquet(PARQUET_PATH, index=False)
    print(f"Wrote {len(df):,} rows -> {PARQUET_PATH}")

    try:
        dk.publish("tag_mago_series", PARQUET_PATH)
    except Exception as e:
        print(f"  note: lake publish skipped ({e})")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="TAG Mago snapshot pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Download EMPACOTAMENTOS JSON snapshots")
    f.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"Calendar days to pull (default {DEFAULT_FETCH_DAYS})",
    )
    f.add_argument(
        "--backfill-from",
        type=str,
        default=None,
        help="Inclusive UTC calendar start date (YYYY-MM-DD)",
    )

    sub.add_parser("build", help="Build parquet from cached snapshots")
    sub.add_parser("all", help="fetch + build")

    args = p.parse_args(argv)
    backfill = None
    if getattr(args, "backfill_from", None):
        backfill = date.fromisoformat(args.backfill_from)

    if args.cmd == "fetch":
        cmd_fetch(days=args.days, backfill_from=backfill)
    elif args.cmd == "build":
        cmd_build()
    elif args.cmd == "all":
        cmd_fetch(days=args.days, backfill_from=backfill)
        cmd_build()


if __name__ == "__main__":
    main()
