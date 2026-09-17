"""NTS Portaria 1/2003 programmed/actual quantity files.

NTS hosts year workbooks behind the MZIQ short-filemanager API (not plain
HTML hrefs). Each workbook has one sheet per month (``Programado (AGO)`` /
``Realizado (AGO)``); values are already in mil m³/dia (thousand m³).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import base
from .crosswalk import load_crosswalk

SOURCE = "nts"
TSO = "NTS"
COMPANY_ID = "ea6d235f-ebee-4bf5-82bc-6bc5698718c1"
CATEGORY = "institucional-sistema-de-transporte-volumes-programados"
API_BASE = f"https://apicatalog.mziq.com/filemanager/company/{COMPANY_ID}"
LANDING_URL = "https://www.ntsbrasil.com/transparencia/"


def _safe_name(title: str, year: int, ext: str = "xlsx") -> str:
    slug = re.sub(r"[^\w.\-]+", "_", title, flags=re.UNICODE).strip("_")[:80] or "nts"
    return f"nts_{slug}_{year}.{ext}"


def discover_urls(*, years: list[int] | None = None) -> list[base.DiscoveredFile]:
    if years is None:
        now = pd.Timestamp.today()
        years = [now.year, now.year - 1]

    found: list[base.DiscoveredFile] = []
    seen: set[str] = set()
    for year in years:
        payload = {
            "company": COMPANY_ID,
            "categories": [CATEGORY],
            "categoryInternalNames": [CATEGORY],
            "language": "pt_BR",
            "published": True,
            "year": year,
            "byYear": True,
            "orderBy": "newest",
        }
        try:
            resp = base.http_post_json(
                f"{API_BASE}/filter/categories/year/meta",
                payload,
                headers={"Referer": LANDING_URL, "Origin": "https://www.ntsbrasil.com"},
            )
        except Exception as e:
            print(f"    NTS catalog warning ({year}): {e}")
            continue
        metas = (resp.get("data") or {}).get("document_metas") or []
        for meta in metas:
            url = meta.get("file_url") or meta.get("permalink")
            if not url or url in seen:
                continue
            title = str(meta.get("file_title") or meta.get("file_name_original") or "nts")
            # Only programmed / actual quantity workbooks.
            if not re.search(r"programad|realizad|quantidade", title, re.I):
                continue
            seen.add(url)
            fname = _safe_name(title, int(meta.get("file_year") or year))
            found.append(base.DiscoveredFile(url=url, filename=fname, label=title))
    return found


def fetch(raw_dir: Path, force: bool = False) -> list[Path]:
    manifest_path = raw_dir / "_manifest.json"
    manifest = base.load_manifest(manifest_path)
    headers = {"Referer": LANDING_URL}

    try:
        discovered = discover_urls()
    except Exception as e:
        print(f"    NTS discover warning: {e}")
        discovered = []

    paths: list[Path] = []
    for item in discovered:
        dest = raw_dir / item.filename
        if dest.exists() and not force:
            paths.append(dest)
            continue
        try:
            if not base.download_file(item.url, dest, headers=headers):
                continue
            head = dest.read_bytes()[:8]
            # Skip non-Excel payloads (MZIQ sometimes serves PDF/HTML)
            if head[:2] != b"PK" and head[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                dest.unlink(missing_ok=True)
                print(f"    NTS skip non-Excel {item.filename}")
                continue
            manifest[item.filename] = {
                "url": item.url,
                "sha256": base.file_sha256(dest),
                "bytes": dest.stat().st_size,
            }
            paths.append(dest)
            print(f"    fetched NTS {item.filename}")
        except Exception as e:
            print(f"    NTS fetch failed for {item.filename}: {e}")
            if dest.exists():
                paths.append(dest)

    for local in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if local not in paths:
            paths.append(local)

    base.save_manifest(manifest_path, manifest)
    return paths


def _variable_from_name(name: str) -> str | None:
    key = base.normalize_key(name)
    if "realiz" in key:
        return base.VAR_ACTUAL
    if "prog" in key or "program" in key:
        return base.VAR_SCHEDULED
    return None


def _point_type_from_name(name: str) -> str:
    key = base.normalize_key(name)
    if key.startswith("ptr") or "receb" in key:
        return base.POINT_TYPE_RECEIPT
    return base.POINT_TYPE_DELIVERY


def _parse_nts_sheet(
    path: Path,
    sheet_name: str,
    *,
    variable: str,
    crosswalk: dict[str, str],
) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
    rows = raw.values.tolist()
    # Find the header row of point names (PTE …) followed by a units row.
    name_idx = None
    for i, row in enumerate(rows[:30]):
        texts = [
            str(c).strip()
            for c in row
            if c is not None and not (isinstance(c, float) and pd.isna(c)) and str(c).strip()
        ]
        # NTS point names are typically ``PTE …`` / ``PTR …``; accept a
        # couple of hits so small fixtures and sparse sheets still parse.
        if sum(1 for t in texts if t.casefold().startswith("pt")) >= 2:
            name_idx = i
            break
    if name_idx is None:
        return base.empty_points_frame()

    name_row = rows[name_idx]
    # Date column: first column that yields datetimes in the data block.
    data_start = name_idx + 1
    # Skip units row if present
    if data_start < len(rows):
        unit_cells = [
            str(c).casefold()
            for c in rows[data_start]
            if c is not None and not (isinstance(c, float) and pd.isna(c))
        ]
        if any("m³" in u or "m3" in u or "mil" in u for u in unit_cells):
            data_start += 1

    date_col = None
    for j in range(min(6, len(name_row))):
        header = name_row[j] if j < len(name_row) else None
        header_txt = (
            str(header).strip()
            if header is not None and not (isinstance(header, float) and pd.isna(header))
            else ""
        )
        # Date column header is blank / NaT — never a PTE/PTR point name.
        if header_txt and not header_txt.casefold() in ("nat", "nan", "none"):
            continue
        hits = 0
        for row in rows[data_start:data_start + 10]:
            if j >= len(row):
                continue
            if not pd.isna(pd.to_datetime(row[j], errors="coerce")):
                hits += 1
        if hits >= 1:
            date_col = j
            break
    if date_col is None:
        return base.empty_points_frame()

    point_cols: list[dict] = []
    for j, cell in enumerate(name_row):
        if j <= date_col:
            continue
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        point_name = str(cell).strip()
        if not point_name or "total" in point_name.casefold():
            continue
        if point_name.casefold().startswith("("):
            continue
        cw_key = base.normalize_key(f"{TSO}|{point_name}")
        point_code = crosswalk.get(cw_key) or base.synthetic_point_code(SOURCE, "NTS", point_name)
        point_cols.append({
            "col": j,
            "point_code": point_code,
            "point_name": point_name,
            "point_type": _point_type_from_name(point_name),
        })
    if not point_cols:
        return base.empty_points_frame()

    records: list[dict] = []
    for row in rows[data_start:]:
        if date_col >= len(row):
            continue
        date = pd.to_datetime(row[date_col], errors="coerce")
        if pd.isna(date):
            continue
        date = date.normalize()
        for pc in point_cols:
            j = pc["col"]
            if j >= len(row):
                continue
            raw_v = row[j]
            if raw_v is None or (isinstance(raw_v, float) and pd.isna(raw_v)):
                continue
            try:
                value = float(raw_v)
            except (TypeError, ValueError):
                continue
            records.append({
                "date": date,
                "point_code": pc["point_code"],
                "point_name": pc["point_name"],
                "point_type": pc["point_type"],
                "pipeline_code": f"{SOURCE}:nts",
                "pipeline_name": "NTS Transport System",
                "municipality": None,
                "uf": None,
                "tso": TSO,
                "variable": variable,
                "value": value,  # already thousand m³/day
                "source": SOURCE,
            })

    if not records:
        return base.empty_points_frame()
    return pd.DataFrame.from_records(records)


def build(raw_dir: Path) -> pd.DataFrame:
    crosswalk = load_crosswalk().get("nts", {})
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if path.name.startswith("_"):
            continue
        file_var = _variable_from_name(path.name)
        try:
            xl = pd.ExcelFile(path, engine="openpyxl")
        except Exception as e:
            print(f"    NTS parse skip {path.name}: {e}")
            continue
        for sheet in xl.sheet_names:
            variable = _variable_from_name(sheet) or file_var
            if variable is None:
                continue
            try:
                df = _parse_nts_sheet(path, sheet, variable=variable, crosswalk=crosswalk)
            except Exception as e:
                print(f"    NTS parse skip {path.name} / {sheet}: {e}")
                continue
            if not df.empty:
                frames.append(df)
        # Fall back to TAG-shaped parser for any seeded Prog-Real-like files.
        try:
            legacy = base.parse_wide_prog_real_workbook(
                path,
                source=SOURCE,
                tso=TSO,
                subsystem="NTS",
                pipeline_name="NTS Transport System",
                crosswalk=crosswalk,
            )
            if not legacy.empty:
                frames.append(legacy)
        except Exception:
            pass

    if not frames:
        return base.empty_points_frame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["date", "point_code", "variable", "source"], keep="last")


ADAPTER = base.Adapter(source=SOURCE, tso=TSO, fetch=fetch, build=build)
