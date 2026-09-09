"""Shared helpers and adapter protocol for TSO Portaria 1/2003 flow files."""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

HERE = Path(__file__).resolve().parent
FLOWS_DIR = HERE.parent
RAW_TSO_DIR = FLOWS_DIR / "raw" / "tso"

VAR_ACTUAL = "Actual Volume (thousand m3)"
VAR_SCHEDULED = "Scheduled Volume (thousand m3)"
TSO_OVERLAY_VARS = frozenset({VAR_ACTUAL, VAR_SCHEDULED})

POINT_TYPE_RECEIPT = "Receipt Point"
POINT_TYPE_DELIVERY = "Delivery Point"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class DiscoveredFile:
    url: str
    filename: str
    label: str = ""


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_key(s: str) -> str:
    s = strip_accents(str(s or "")).casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def synthetic_point_code(source: str, subsystem: str, point_name: str) -> str:
    """Stable synthetic code when ANP codes are unavailable."""
    key = normalize_key(f"{subsystem}|{point_name}")
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_key(point_name))[:48].strip("-")
    return f"{source}:{normalize_key(subsystem).replace(' ', '-')}:{slug}:{digest}"


def empty_points_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "date", "point_code", "point_name", "point_type", "pipeline_code",
        "pipeline_name", "municipality", "uf", "tso", "variable", "value", "source",
    ])


def m3_to_thousand_m3(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def http_get(url: str, *, headers: dict | None = None, timeout: int = 90, max_retries: int = 3) -> bytes:
    hdrs = {**BROWSER_HEADERS, **(headers or {})}
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last_err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_err}")


def http_get_text(url: str, *, headers: dict | None = None) -> str:
    return http_get(url, headers=headers).decode("utf-8", errors="replace")


def download_file(url: str, dest: Path, *, headers: dict | None = None) -> bool:
    """Download url to dest. Returns True on success, False on 404."""
    try:
        data = http_get(url, headers=headers)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_point_type(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    key = normalize_key(raw)
    if "receb" in key:
        return POINT_TYPE_RECEIPT
    if "entreg" in key:
        return POINT_TYPE_DELIVERY
    return None


def parse_wide_prog_real_workbook(
    path: Path,
    *,
    source: str,
    tso: str,
    subsystem: str | None = None,
    pipeline_name: str | None = None,
    crosswalk: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Parse TAG-style wide Prog/Realizado workbooks (and close variants).

    Expected layout (0-indexed rows):
      4: point type (PONTOS DE RECEBIMENTO / PONTOS DE ENTREGA)
      5: DATA + point names
      6: sub-pipeline names (optional metadata)
      7: UF
      8+: daily values in m³/dia (converted to thousand m3)
    """
    with pd.ExcelFile(path, engine="openpyxl") as xl:
        frames: list[pd.DataFrame] = []
        for sheet_name in xl.sheet_names:
            variable = _variable_from_sheet_name(sheet_name)
            if variable is None:
                continue
            # header=None keeps the TAG multi-row header intact
            raw = pd.read_excel(xl, sheet_name=sheet_name, header=None, engine="openpyxl")
            rows = raw.values.tolist()
            frame = _melt_wide_sheet(
                rows,
                source=source,
                tso=tso,
                subsystem=subsystem or _subsystem_from_filename(path.name),
                pipeline_name=pipeline_name or subsystem or path.stem,
                variable=variable,
                crosswalk=crosswalk,
            )
            if frame is not None and not frame.empty:
                frames.append(frame)

    if not frames:
        return empty_points_frame()
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["pipeline_name", "point_name", "variable", "date"]).reset_index(drop=True)


def _variable_from_sheet_name(name: str) -> str | None:
    key = normalize_key(name)
    if "realiz" in key:
        return VAR_ACTUAL
    if "prog" in key or "program" in key:
        return VAR_SCHEDULED
    return None


def _subsystem_from_filename(name: str) -> str:
    stem = Path(name).stem
    # Prog-Real_GASENE_01-2017_a_07-2026 -> GASENE
    m = re.search(r"Prog[-_]?Real[_-](.+?)[_-]\d{2}-\d{4}", stem, re.I)
    if m:
        return m.group(1).replace("-", " ").replace("_", " ").strip()
    return stem


def _melt_wide_sheet(
    rows: list[list],
    *,
    source: str,
    tso: str,
    subsystem: str,
    pipeline_name: str,
    variable: str,
    crosswalk: dict[str, str] | None,
) -> pd.DataFrame | None:
    if len(rows) < 9:
        return None

    header_idx = None
    for i, row in enumerate(rows[:12]):
        cells = [str(c).strip().casefold() if c is not None else "" for c in row]
        if any(c == "data" for c in cells):
            header_idx = i
            break
    if header_idx is None:
        return None

    type_row = rows[header_idx - 1] if header_idx >= 1 else []
    name_row = rows[header_idx]
    pipe_row = rows[header_idx + 1] if header_idx + 1 < len(rows) else []
    uf_row = rows[header_idx + 2] if header_idx + 2 < len(rows) else []
    data_start = header_idx + 3

    date_col = None
    for j, cell in enumerate(name_row):
        if cell is not None and str(cell).strip().casefold() == "data":
            date_col = j
            break
    if date_col is None:
        return None

    # Build column metadata once, then vectorized melt.
    point_cols: list[dict] = []
    last_type = None
    for j in range(date_col + 1, len(name_row)):
        point_name = name_row[j] if j < len(name_row) else None
        if point_name is None or str(point_name).strip() == "":
            continue
        point_name = str(point_name).strip()
        raw_type = type_row[j] if j < len(type_row) else None
        if raw_type is not None and str(raw_type).strip():
            last_type = classify_point_type(str(raw_type)) or last_type
        point_type = last_type or POINT_TYPE_DELIVERY
        uf = uf_row[j] if j < len(uf_row) else None
        uf = str(uf).strip() if uf is not None and str(uf).strip() not in ("", "None") else None
        subpipe = pipe_row[j] if j < len(pipe_row) else None
        subpipe = (
            str(subpipe).strip()
            if subpipe is not None and str(subpipe).strip() not in ("", "None")
            else subsystem
        )
        cw_key = normalize_key(f"{tso}|{point_name}")
        point_code = (crosswalk or {}).get(cw_key) or synthetic_point_code(source, subsystem, point_name)
        point_cols.append({
            "col": j,
            "point_code": point_code,
            "point_name": point_name,
            "point_type": point_type,
            "pipeline_name": subpipe or pipeline_name or subsystem,
            "uf": uf,
        })

    if not point_cols:
        return None

    # Data block: date + selected point columns
    data_rows = []
    for row in rows[data_start:]:
        if not row or date_col >= len(row):
            continue
        raw_date = row[date_col]
        if raw_date is None:
            continue
        if isinstance(raw_date, str) and (
            "unidade" in raw_date.casefold() or not raw_date.strip()
        ):
            continue
        date = pd.to_datetime(raw_date, dayfirst=True, errors="coerce")
        if pd.isna(date):
            continue
        rec = {"date": date.normalize()}
        for pc in point_cols:
            j = pc["col"]
            rec[pc["point_code"]] = row[j] if j < len(row) else None
        data_rows.append(rec)

    if not data_rows:
        return None

    wide = pd.DataFrame(data_rows)
    long = wide.melt(id_vars=["date"], var_name="point_code", value_name="raw_value")
    long["value"] = long["raw_value"].map(m3_to_thousand_m3)
    long = long.dropna(subset=["value"]).drop(columns=["raw_value"])

    meta = pd.DataFrame(point_cols).drop(columns=["col"]).drop_duplicates(subset=["point_code"])
    out = long.merge(meta, on="point_code", how="left")
    out["pipeline_code"] = f"{source}:{normalize_key(subsystem).replace(' ', '-')}"
    out["municipality"] = None
    out["tso"] = tso
    out["variable"] = variable
    out["source"] = source
    if "pipeline_name" not in out.columns or out["pipeline_name"].isna().all():
        out["pipeline_name"] = pipeline_name or subsystem
    return out[[
        "date", "point_code", "point_name", "point_type", "pipeline_code",
        "pipeline_name", "municipality", "uf", "tso", "variable", "value", "source",
    ]]


AdapterFetch = Callable[[Path, bool], list[Path]]
AdapterBuild = Callable[[Path], pd.DataFrame]


@dataclass(frozen=True)
class Adapter:
    source: str
    tso: str
    fetch: AdapterFetch
    build: AdapterBuild


def fetch_all(adapters: Iterable[Adapter], *, force: bool = False) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for adapter in adapters:
        raw_dir = RAW_TSO_DIR / adapter.source
        raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            paths = adapter.fetch(raw_dir, force)
            out[adapter.source] = paths
            print(f"  tso/{adapter.source}: {len(paths)} file(s) ready in {raw_dir}")
        except Exception as e:
            # Soft-fail: keep last-good local files; do not abort ANP build.
            print(f"  tso/{adapter.source} FETCH WARNING: {e}", flush=True)
            out[adapter.source] = sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls"))
    return out


def build_all_points(adapters: Iterable[Adapter]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for adapter in adapters:
        raw_dir = RAW_TSO_DIR / adapter.source
        try:
            df = adapter.build(raw_dir)
        except Exception as e:
            print(f"  tso/{adapter.source} BUILD WARNING: {e}", flush=True)
            continue
        if df is not None and not df.empty:
            frames.append(df)
            print(f"  tso/{adapter.source}: {len(df):,} rows, {df['point_code'].nunique()} points")
    if not frames:
        return empty_points_frame()
    return pd.concat(frames, ignore_index=True)


# Late import wiring so adapters can import from base without cycles.
def _load_adapters() -> list[Adapter]:
    from . import tag, tbg, nts  # noqa: WPS433

    return [tag.ADAPTER, tbg.ADAPTER, nts.ADAPTER]


TSO_SOURCES = ("tag", "tbg", "nts")
