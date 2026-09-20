"""HTTP client for TAG Mago operational snapshots (S3 proxy API).

The Mago web apps at https://mago.ntag.com.br/ load hourly JSON snapshots
via ``GET {API}/api/s3/list`` and ``GET {API}/api/s3/object?key=...``.
Both Empacotamento (line pack) and Previsão de consumo read the same
``EMPACOTAMENTOS_*.json`` objects; tags inside Items distinguish series.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

API_BASE = "https://api-mago-prod-lb.ntag.com.br"

# Matches Mago frontend: EMPACOTAMENTOS_DD_MM_YYYY_HH_MM_SS.json
FILE_PATTERN = re.compile(
    r"^EMPACOTAMENTOS_(\d{2})_(\d{2})_(\d{4})_(\d{2})_(\d{2})_(\d{2})\.json$"
)

ZONE_TAG_PATTERN = re.compile(r"^Previsao - ZONA_([A-Z0-9]+) - Diario$")

TAG_LINEPACK_INTEGRATED = "MALHA-INT-1MIN"
TAG_LINEPACK_NORTH = "MALHA-NOR-1MIN"
TAG_LINEPACK_FORECAST = "Previsao - EMPACOTAMENTO - MalhaIntegrada"

FAIXA_TAG_MAP: dict[str, tuple[str, str]] = {
    "Comercial_Faixa_Severo_Superior_MalhaIntegrada": ("severo_superior", "integrated"),
    "Comercial_Faixa_Baixo_Superior_MalhaIntegrada": ("baixo_superior", "integrated"),
    "Comercial_Faixa_Marginal_Superior_MalhaIntegrada": ("marginal_superior", "integrated"),
    "Comercial_Faixa_Marginal_Inferior_MalhaIntegrada": ("marginal_inferior", "integrated"),
    "Comercial_Faixa_Baixo_Inferior_MalhaIntegrada": ("baixo_inferior", "integrated"),
    "Comercial_Faixa_Severo_Inferior_MalhaIntegrada": ("severo_inferior", "integrated"),
}

DEFAULT_FAIXAS_INTEGRATED: dict[str, float] = {
    "severo_superior": 76_500_000.0,
    "baixo_superior": 72_500_000.0,
    "marginal_superior": 71_500_000.0,
    "marginal_inferior": 69_500_000.0,
    "baixo_inferior": 68_500_000.0,
    "severo_inferior": 65_500_000.0,
}

HEADERS = {
    "Accept": "application/json",
    "Origin": "https://mago.ntag.com.br",
    "Referer": "https://mago.ntag.com.br/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
}

LIST_PAGE_SIZE = 1000
MAX_LIST_PAGES = 200


@dataclass(frozen=True)
class MagoObject:
    key: str
    last_modified: datetime
    size: int
    etag: str | None = None
    snapshot_at: datetime | None = None
    calendar_date: date | None = None

    @classmethod
    def from_api(cls, row: dict) -> MagoObject:
        key = str(row.get("Key") or "")
        lm_raw = row.get("LastModified")
        if isinstance(lm_raw, datetime):
            lm = lm_raw if lm_raw.tzinfo else lm_raw.replace(tzinfo=UTC)
        else:
            lm = datetime.fromisoformat(str(lm_raw).replace("Z", "+00:00"))
        snap, cal = parse_snapshot_key(key)
        return cls(
            key=key,
            last_modified=lm,
            size=int(row.get("Size") or 0),
            etag=(str(row["ETag"]).strip('"') if row.get("ETag") else None),
            snapshot_at=snap,
            calendar_date=cal,
        )


def parse_snapshot_key(key: str) -> tuple[datetime | None, date | None]:
    m = FILE_PATTERN.match(key)
    if not m:
        return None, None
    dd, mm, yyyy, hh, mi, ss = (int(x) for x in m.groups())
    snap = datetime(yyyy, mm, dd, hh, mi, ss, tzinfo=UTC)
    return snap, date(yyyy, mm, dd)


def _http_json(url: str, *, timeout: int = 120, attempts: int = 4) -> dict:
    delay = 0.8
    last_err: BaseException | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if i + 1 >= attempts:
                break
            time.sleep(delay)
            delay *= 2
    assert last_err is not None
    raise last_err


def list_objects_page(
    *,
    prefix: str | None = None,
    continuation_token: str | None = None,
) -> tuple[list[MagoObject], str | None, bool]:
    params: dict[str, str] = {}
    if prefix:
        params["prefix"] = prefix
    if continuation_token:
        params["continuationToken"] = continuation_token
    q = urllib.parse.urlencode(params)
    url = f"{API_BASE}/api/s3/list"
    if q:
        url = f"{url}?{q}"
    payload = _http_json(url)
    objects = [MagoObject.from_api(o) for o in (payload.get("objects") or [])]
    token = payload.get("nextContinuationToken")
    truncated = bool(payload.get("isTruncated"))
    return objects, (str(token) if token else None), truncated


def list_all_objects(*, prefix: str | None = None) -> list[MagoObject]:
    out: list[MagoObject] = []
    token: str | None = None
    for _ in range(MAX_LIST_PAGES):
        page, token, truncated = list_objects_page(prefix=prefix, continuation_token=token)
        out.extend(page)
        if not truncated or not token:
            break
    return out


def fetch_object_json(key: str) -> dict:
    url = f"{API_BASE}/api/s3/object?key={urllib.parse.quote(key, safe='')}"
    payload = _http_json(url, timeout=180)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object for {key}, got {type(payload)}")
    return payload


def normalize_item(raw: dict) -> dict | None:
    tag = str(raw.get("Tag") or "").strip()
    if not tag:
        return None
    if raw.get("Good") is False:
        return None
    ts_raw = raw.get("Timestamp")
    if not ts_raw:
        return None
    observed_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    val_raw = raw.get("Value")
    if isinstance(val_raw, dict):
        if str(val_raw.get("Name") or "").casefold() == "no data":
            return None
        val_raw = val_raw.get("Value")
    try:
        value = float(val_raw)
    except (TypeError, ValueError):
        return None

    series, mesh, zone = classify_tag(tag)
    if series is None:
        return None

    unit = ""
    if series.startswith("linepack"):
        unit = "m3"
        if value < 1_000_000:
            return None
    elif series == "zone_consumption_forecast":
        unit = "Mm3_d"

    return {
        "observed_at": observed_at,
        "series": series,
        "mesh": mesh,
        "zone": zone,
        "tag": tag,
        "value": value,
        "unit": unit,
        "source": "mago",
    }


def classify_tag(tag: str) -> tuple[str | None, str | None, str | None]:
    if tag == TAG_LINEPACK_INTEGRATED:
        return "linepack_actual", "integrated", None
    if tag == TAG_LINEPACK_NORTH:
        return "linepack_actual", "north", None
    if tag == TAG_LINEPACK_FORECAST:
        return "linepack_forecast", "integrated", None
    if tag in FAIXA_TAG_MAP:
        band, mesh = FAIXA_TAG_MAP[tag]
        return "linepack_tolerance_band", mesh, band
    m = ZONE_TAG_PATTERN.match(tag)
    if m:
        return "zone_consumption_forecast", None, m.group(1)
    return None, None, None


def rows_from_snapshot(snapshot_at: datetime, payload: dict) -> list[dict]:
    items = payload.get("Items") or []
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        norm = normalize_item(item)
        if norm is None:
            continue
        rows.append({"snapshot_at": snapshot_at, **norm})
    return rows


def filter_objects_by_calendar(
    objects: Iterable[MagoObject],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[MagoObject]:
    out: list[MagoObject] = []
    for obj in objects:
        if obj.calendar_date is None:
            continue
        if start and obj.calendar_date < start:
            continue
        if end and obj.calendar_date > end:
            continue
        out.append(obj)
    out.sort(key=lambda o: (o.snapshot_at or o.last_modified, o.key))
    return out
