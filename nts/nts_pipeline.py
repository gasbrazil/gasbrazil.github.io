"""NTS OnTime linepack telemetry pipeline.

Fetches real-time and historical linepack snapshots from the NTS OnTime REST API
and builds a canonical tidy parquet store:
    nts/data/nts_linepack_series.parquet
    lake/transport/nts_linepack_series.parquet

Usage:
    python nts_pipeline.py fetch [--days N] [--backfill-all]
    python nts_pipeline.py build
    python nts_pipeline.py all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW_DIR = HERE / "raw" / "snapshots"
MANIFEST_PATH = HERE / "raw" / "_manifest.json"
DATA_DIR = HERE / "data"
PARQUET_PATH = DATA_DIR / "nts_linepack_series.parquet"
LAKE_PATH = ROOT / "lake" / "transport" / "nts_linepack_series.parquet"

sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(HERE))

import data_kit as dk  # noqa: E402
import nts_client  # noqa: E402
from schemas import validate_nts_ontime_series  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# First available data date on NTS backend
NTS_START_DATE = date(2025, 5, 15)
DEFAULT_FETCH_DAYS = 7


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


def _save_raw_snapshot(filename: str, payload: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / filename
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def cmd_fetch(*, days: int | None = None, backfill_all: bool = False) -> None:
    """Fetch recent or historical NTS snapshots."""
    manifest = _load_manifest()
    files_meta: dict = manifest.setdefault("files", {})
    today = _utc_today()

    if backfill_all:
        logger.info("Backfilling all historical snapshots from %s to %s", NTS_START_DATE, today)
        cur = NTS_START_DATE
        step_days = 2
        while cur <= today:
            end = min(cur + timedelta(days=step_days - 1), today)
            fname = f"NTS_ESTOQUE_{cur.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.json"
            if fname not in files_meta:
                logger.info("Fetching window %s -> %s...", cur, end)
                try:
                    dt_start = datetime.combine(cur, datetime.min.time(), tzinfo=UTC)
                    dt_end = datetime.combine(end, datetime.max.time(), tzinfo=UTC)
                    snap = nts_client.fetch_custom(dt_start, dt_end)
                    if snap.points:
                        payload = {
                            "tag": snap.tag,
                            "unit": snap.unit,
                            "range": snap.range_name,
                            "from": snap.from_time.isoformat() if snap.from_time else None,
                            "to": snap.to_time.isoformat() if snap.to_time else None,
                            "count": snap.count,
                            "points": [{"t": p.timestamp.isoformat(), "v": p.value_m3} for p in snap.points],
                            "stats": {
                                "atual": snap.stats.atual_m3,
                                "min": snap.stats.min_m3,
                                "max": snap.stats.max_m3,
                                "media": snap.stats.media_m3,
                                "delta": snap.stats.delta_m3,
                                "delta_pct": snap.stats.delta_pct,
                                "taxa_m3h": snap.stats.taxa_m3h,
                            },
                        }
                        _save_raw_snapshot(fname, payload)
                        files_meta[fname] = {
                            "points": snap.count,
                            "fetched_at": datetime.now(UTC).isoformat(),
                        }
                        _save_manifest(manifest)
                except Exception as e:
                    logger.warning("Failed to fetch %s -> %s: %s", cur, end, e)
            cur += timedelta(days=step_days)

    fetch_days = days or DEFAULT_FETCH_DAYS
    logger.info("Fetching recent %d days of snapshots...", fetch_days)

    # 1. Fetch live "today"
    try:
        live_snap = nts_client.fetch_live()
        fname = f"NTS_ESTOQUE_today_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        payload = {
            "tag": live_snap.tag,
            "unit": live_snap.unit,
            "range": "today",
            "from": live_snap.from_time.isoformat() if live_snap.from_time else None,
            "to": live_snap.to_time.isoformat() if live_snap.to_time else None,
            "count": live_snap.count,
            "points": [{"t": p.timestamp.isoformat(), "v": p.value_m3} for p in live_snap.points],
            "stats": {
                "atual": live_snap.stats.atual_m3,
                "min": live_snap.stats.min_m3,
                "max": live_snap.stats.max_m3,
                "media": live_snap.stats.media_m3,
                "delta": live_snap.stats.delta_m3,
                "delta_pct": live_snap.stats.delta_pct,
                "taxa_m3h": live_snap.stats.taxa_m3h,
            },
        }
        _save_raw_snapshot(fname, payload)
        files_meta[fname] = {"points": live_snap.count, "fetched_at": datetime.now(UTC).isoformat()}
        _save_manifest(manifest)
        logger.info("Saved live today snapshot: %d points", live_snap.count)
    except Exception as e:
        logger.warning("Failed to fetch live today snapshot: %s", e)

    # 2. Fetch recent day windows
    for i in range(1, fetch_days + 1):
        target_d = today - timedelta(days=i)
        fname = f"NTS_ESTOQUE_day_{target_d.strftime('%Y%m%d')}.json"
        if fname in files_meta:
            continue
        try:
            logger.info("Fetching calendar day %s...", target_d)
            day_snap = nts_client.fetch_day(target_d)
            if day_snap.points:
                payload = {
                    "tag": day_snap.tag,
                    "unit": day_snap.unit,
                    "range": f"day_{target_d}",
                    "from": day_snap.from_time.isoformat() if day_snap.from_time else None,
                    "to": day_snap.to_time.isoformat() if day_snap.to_time else None,
                    "count": day_snap.count,
                    "points": [{"t": p.timestamp.isoformat(), "v": p.value_m3} for p in day_snap.points],
                    "stats": {
                        "atual": day_snap.stats.atual_m3,
                        "min": day_snap.stats.min_m3,
                        "max": day_snap.stats.max_m3,
                        "media": day_snap.stats.media_m3,
                        "delta": day_snap.stats.delta_m3,
                        "delta_pct": day_snap.stats.delta_pct,
                        "taxa_m3h": day_snap.stats.taxa_m3h,
                    },
                }
                _save_raw_snapshot(fname, payload)
                files_meta[fname] = {"points": day_snap.count, "fetched_at": datetime.now(UTC).isoformat()}
                _save_manifest(manifest)
        except Exception as e:
            logger.warning("Failed to fetch day %s: %s", target_d, e)

    _save_manifest(manifest)
    logger.info("Fetch complete. Total tracked raw files: %d", len(files_meta))


def cmd_build() -> pd.DataFrame:
    """Read all raw snapshots, deduplicate, calculate rates, validate, and write Parquet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.glob("NTS_ESTOQUE_*.json"))
    if not files:
        logger.warning("No raw NTS snapshots found in %s; fetching 7 days...", RAW_DIR)
        cmd_fetch(days=7)
        files = sorted(RAW_DIR.glob("NTS_ESTOQUE_*.json"))

    records: list[dict] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pts = data.get("points") or []
            f_time = data.get("to") or data.get("from") or datetime.now(UTC).isoformat()
            for p in pts:
                records.append({
                    "timestamp": p["t"],
                    "value_m3": float(p["v"]),
                    "observed_at": f_time,
                })
        except Exception as err:
            logger.warning("Skipping malformed raw file %s: %s", f.name, err)

    if not records:
        raise RuntimeError("No linepack records extracted from raw files")

    df = pd.DataFrame(records)
    # Parse timestamps and standardize to UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)

    # Deduplicate: latest observed_at wins
    df = df.sort_values(["timestamp", "observed_at"]).drop_duplicates(subset=["timestamp"], keep="last")
    df = df.reset_index(drop=True)

    # Calculate value_mm3
    df["value_mm3"] = (df["value_m3"] / 1_000_000.0).round(4)
    df["source"] = "nts"

    # Calculate rate of change in m3/hour
    # First sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    dt_hours = df["timestamp"].diff().dt.total_seconds() / 3600.0
    dv_m3 = df["value_m3"].diff()

    # Rate: avoid dividing by zero or abnormally large gaps (> 4 hours)
    rate = np.where((dt_hours > 0) & (dt_hours <= 4.0), dv_m3 / dt_hours, 0.0)
    df["rate_m3_h"] = np.round(rate, 2)

    # Validate against canonical schema
    validate_nts_ontime_series(df)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAKE_PATH.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(PARQUET_PATH, index=False)
    logger.info("Wrote %d records to %s", len(df), PARQUET_PATH)

    df.to_parquet(LAKE_PATH, index=False)
    logger.info("Synced to lake: %s", LAKE_PATH)

    return df


def cmd_all() -> None:
    cmd_fetch()
    cmd_build()
    from dashboard import build_dashboard
    build_dashboard()


def main() -> None:
    parser = argparse.ArgumentParser(description="NTS OnTime pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    fetch_p = sub.add_parser("fetch", help="Fetch NTS snapshots")
    fetch_p.add_argument("--days", type=int, default=DEFAULT_FETCH_DAYS, help="Recent days to fetch")
    fetch_p.add_argument("--backfill-all", action="store_true", help="Backfill history to May 2025")

    sub.add_parser("build", help="Build parquet from snapshots")
    sub.add_parser("all", help="Fetch, build, and regenerate dashboard")

    args = parser.parse_args()
    if args.cmd == "fetch":
        cmd_fetch(days=args.days, backfill_all=args.backfill_all)
    elif args.cmd == "build":
        cmd_build()
    elif args.cmd == "all":
        cmd_all()


if __name__ == "__main__":
    main()
