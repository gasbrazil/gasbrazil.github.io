"""HTTP client for NTS (Nova Transportadora do Sudeste) OnTime linepack telemetry.

The NTS OnTime application at https://www.ntsbrasil.com/ontime/ serves real-time
pipeline linepack inventory and packing/unpacking rate telemetry via:
    GET https://www.ntsbrasil.com/wp-json/ontime/v1/estoque

Note: Requests MUST use the www.ntsbrasil.com host to avoid SSL certificate
SAN mismatch errors on the apex domain.
"""
from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dt_time

logger = logging.getLogger(__name__)

API_BASE = "https://www.ntsbrasil.com/wp-json/ontime/v1"
ENDPOINT_ESTOQUE = f"{API_BASE}/estoque"

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.ntsbrasil.com/ontime/",
    "Origin": "https://www.ntsbrasil.com",
}

PRESETS = ("today", "yesterday", "1h", "12h", "3d", "7d")


class NtsApiError(RuntimeError):
    """Raised when the NTS OnTime API fails or returns invalid/synthetic data."""


@dataclass(frozen=True)
class NtsDataPoint:
    timestamp: datetime
    value_m3: float
    value_mm3: float


@dataclass(frozen=True)
class NtsStats:
    atual_m3: float | None
    min_m3: float | None
    max_m3: float | None
    media_m3: float | None
    delta_m3: float | None
    delta_pct: float | None
    taxa_m3h: float | None

    @classmethod
    def from_dict(cls, data: dict | None) -> NtsStats:
        if not data or not isinstance(data, dict):
            return cls(None, None, None, None, None, None, None)

        def _to_float(val: object) -> float | None:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        return cls(
            atual_m3=_to_float(data.get("atual")),
            min_m3=_to_float(data.get("min")),
            max_m3=_to_float(data.get("max")),
            media_m3=_to_float(data.get("media")),
            delta_m3=_to_float(data.get("delta")),
            delta_pct=_to_float(data.get("delta_pct")),
            taxa_m3h=_to_float(data.get("taxa_m3h")),
        )


@dataclass(frozen=True)
class NtsSnapshot:
    tag: str
    unit: str
    range_name: str
    from_time: datetime | None
    to_time: datetime | None
    count: int
    points: list[NtsDataPoint]
    stats: NtsStats
    fetched_at: datetime


def _parse_iso_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp with optional timezone offset (defaults to UTC)."""
    clean = ts_str.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _request_json(url: str, *, timeout: int = 15, max_retries: int = 3) -> dict:
    """Send HTTPS GET request with exponential backoff."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                if resp.status != 200:
                    raise NtsApiError(f"HTTP {resp.status} fetching {url}")
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                return data
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as err:
            last_err = err
            sleep_sec = 1.5 * (2**attempt)
            logger.warning(
                "NTS API request failed (attempt %d/%d): %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries,
                err,
                sleep_sec,
            )
            time.sleep(sleep_sec)

    raise NtsApiError(f"Failed to fetch {url} after {max_retries} attempts: {last_err}") from last_err


def _parse_payload(data: dict) -> NtsSnapshot:
    if not isinstance(data, dict):
        raise NtsApiError(f"Unexpected response type: {type(data)}")

    points_raw = data.get("points")
    if not isinstance(points_raw, list):
        raise NtsApiError("Response missing 'points' array")

    parsed_points: list[NtsDataPoint] = []
    for item in points_raw:
        if not isinstance(item, dict):
            continue
        t_raw = item.get("t")
        v_raw = item.get("v")
        if t_raw is None or v_raw is None:
            continue
        try:
            ts = _parse_iso_ts(str(t_raw))
            val = float(v_raw)
            parsed_points.append(
                NtsDataPoint(
                    timestamp=ts,
                    value_m3=val,
                    value_mm3=round(val / 1_000_000.0, 4),
                )
            )
        except Exception:
            continue

    from_time = _parse_iso_ts(str(data["from"])) if data.get("from") else None
    to_time = _parse_iso_ts(str(data["to"])) if data.get("to") else None

    return NtsSnapshot(
        tag=str(data.get("tag") or "NTS-ESTOQ"),
        unit=str(data.get("unit") or "m3"),
        range_name=str(data.get("range") or "custom"),
        from_time=from_time,
        to_time=to_time,
        count=len(parsed_points),
        points=parsed_points,
        stats=NtsStats.from_dict(data.get("stats")),
        fetched_at=datetime.now(UTC),
    )


def fetch_preset(preset: str = "today", *, timeout: int = 15) -> NtsSnapshot:
    """Fetch linepack snapshot using a supported preset ('today', 'yesterday', '7d', etc.)."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}; allowed: {PRESETS}")
    url = f"{ENDPOINT_ESTOQUE}?range={urllib.parse.quote(preset)}"
    data = _request_json(url, timeout=timeout)
    return _parse_payload(data)


def fetch_custom(from_dt: datetime, to_dt: datetime, *, timeout: int = 15) -> NtsSnapshot:
    """Fetch linepack snapshot for an arbitrary datetime window."""
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=UTC)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=UTC)

    f_str = from_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_str = to_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{ENDPOINT_ESTOQUE}?from={urllib.parse.quote(f_str)}&to={urllib.parse.quote(t_str)}"
    data = _request_json(url, timeout=timeout)
    return _parse_payload(data)


def fetch_day(target_date: date, *, timeout: int = 15) -> NtsSnapshot:
    """Fetch full 24h linepack snapshot for a specific calendar date (UTC)."""
    start_dt = datetime.combine(target_date, dt_time.min, tzinfo=UTC)
    end_dt = datetime.combine(target_date, dt_time.max, tzinfo=UTC)
    return fetch_custom(start_dt, end_dt, timeout=timeout)


def fetch_live() -> NtsSnapshot:
    """Fetch the latest real-time linepack snapshot ('today')."""
    return fetch_preset("today")
