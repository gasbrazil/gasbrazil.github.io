"""Synthetic Mago snapshots for offline dashboard / test builds."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mago_pipeline as mp
from mago_client import TAG_LINEPACK_FORECAST, TAG_LINEPACK_INTEGRATED

ZONES = [
    "AL", "BA1", "BA2", "BA3", "BA4", "BA5", "CE1", "CE2", "ES1", "ES2", "ES3",
    "PB", "PE1", "PE2", "RJ", "RN1", "RN2", "RN3", "SE",
]


def _item(tag: str, ts: datetime, value: float) -> dict:
    return {
        "Tag": tag,
        "Timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Value": value,
        "UnitsAbbreviation": "",
        "Good": True,
        "Questionable": False,
        "Substituted": False,
        "Annotated": False,
    }


def build_snapshot(snapshot_at: datetime) -> dict:
    day_start = snapshot_at.replace(hour=0, minute=0, second=0, microsecond=0)
    items: list[dict] = []
    base_lp = 68_500_000.0 + (snapshot_at.day % 5) * 120_000.0
    for h in range(25):
        ts = day_start + timedelta(hours=h)
        items.append(_item(TAG_LINEPACK_INTEGRATED, ts, base_lp + h * 8_000))
    for h in range(49):
        ts = day_start + timedelta(hours=h)
        items.append(_item(TAG_LINEPACK_FORECAST, ts, base_lp + 20_000 + h * 500))
    for zone in ZONES:
        zbase = 90.0 + (hash(zone) % 17)
        for d in range(7):
            ts = day_start + timedelta(days=d)
            items.append(
                _item(f"Previsao - ZONA_{zone} - Diario", ts, round(zbase + d * 0.4, 4))
            )
    return {"Items": items}


if __name__ == "__main__":
    mp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for old in mp.RAW_DIR.glob("EMPACOTAMENTOS_*.json"):
        old.unlink()
    now = datetime.now(timezone.utc).replace(minute=8, second=24, microsecond=0)
    for d in range(3):
        snap = now - timedelta(days=d)
        name = (
            f"EMPACOTAMENTOS_{snap.day:02d}_{snap.month:02d}_{snap.year}_"
            f"{snap.hour:02d}_{snap.minute:02d}_{snap.second:02d}.json"
        )
        path = mp.RAW_DIR / name
        path.write_text(json.dumps(build_snapshot(snap), ensure_ascii=False), encoding="utf-8")
        print(f"Wrote mock snapshot {path.name}")
    mp.cmd_build()
