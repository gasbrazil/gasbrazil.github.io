"""TBG Portaria 1/2003 programmed/actual quantity files.

TBG publishes monthly packs on its Liferay document library — typically a
ZIP (``ANP Agosto 2026.zip``) that contains Excel workbooks for Volumes
Entregues / Recebidos, plus standalone PDFs we ignore. Layout is paired
Programado/Realizado columns (already in Mm³ = thousand m³), not TAG's
m³/dia Prog-Real sheet shape.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urljoin

import pandas as pd

from . import base
from .crosswalk import load_crosswalk

SOURCE = "tbg"
TSO = "TBG"
LANDING_URLS = [
    "https://www.tbg.com.br/informacoes-a-anp",
    "https://www.tbg.com.br/informa%C3%A7%C3%A3o-a-anp-a-partir-de-2026",
    "https://www.tbg.com.br/anp",
]

# Prefer recent monthly packs so we do not re-download years of history.
_MONTH_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _slug_filename(name: str, fallback: str) -> str:
    name = unquote(name).split("?")[0]
    name = Path(name).name or fallback
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    return name[:180] or fallback


def _filename_from_url(url: str, fallback: str) -> str:
    """Liferay URLs end in ``/file.zip/<uuid>`` — prefer the ``.zip``/``.xlsx`` segment."""
    path = unquote(url.split("?")[0])
    parts = [p for p in path.split("/") if p]
    for part in reversed(parts):
        if re.search(r"\.(zip|xlsx|xls)$", part, re.I):
            return _slug_filename(part, fallback)
    return _slug_filename(parts[-1] if parts else fallback, fallback)


def _month_key_from_blob(blob: str) -> tuple[int, int] | None:
    key = base.normalize_key(blob)
    year_m = re.search(r"(20\d{2})", key)
    if not year_m:
        return None
    year = int(year_m.group(1))
    for name, month in _MONTH_PT.items():
        if base.normalize_key(name) in key:
            return year, month
    return None


def discover_urls() -> list[base.DiscoveredFile]:
    found: list[base.DiscoveredFile] = []
    seen: set[str] = set()
    for landing in LANDING_URLS:
        try:
            html = base.http_get_text(landing, headers={"Referer": "https://www.tbg.com.br/"})
        except Exception:
            continue
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
            href = unquote(m.group(1))
            url = urljoin(landing, href)
            if url in seen:
                continue
            blob = f"{Path(url.split('?')[0]).name} {href}"
            key = blob.casefold()
            is_zip = ".zip" in key
            is_xlsx = bool(re.search(r"\.(xlsx|xls)(\?|$)", key))
            if not (is_zip or is_xlsx):
                continue
            # Monthly ANP Portaria packs + volumes programado/realizado sheets.
            if not re.search(
                r"anp.*\.zip|volumes?\s*(entregues|recebidos)|programad|realizad|prog.?real",
                key,
                re.I,
            ):
                if not (is_zip and "anp" in key):
                    continue
            seen.add(url)
            fname = _filename_from_url(url, f"tbg_{len(found)}.bin")
            found.append(base.DiscoveredFile(url=url, filename=fname, label=blob[:120]))

    # Keep the newest few monthly ZIPs + any direct xlsx; drop ancient history.
    zips: list[tuple[tuple[int, int], base.DiscoveredFile]] = []
    other: list[base.DiscoveredFile] = []
    for item in found:
        if item.filename.casefold().endswith(".zip"):
            mk = _month_key_from_blob(item.label or item.filename) or (0, 0)
            zips.append((mk, item))
        else:
            other.append(item)
    zips.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in zips[:6]] + other


def _extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    out: list[Path] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if not re.search(r"\.(xlsx|xls)$", name, re.I):
                    continue
                # Prefer volumes programado/realizado / entregues / recebidos.
                if not re.search(r"volume|program|realiz|entreg|receb", name, re.I):
                    continue
                target = dest_dir / _slug_filename(name, f"from_{zip_path.stem}.xlsx")
                target.write_bytes(zf.read(info))
                out.append(target)
                print(f"    extracted TBG {target.name} from {zip_path.name}")
    except zipfile.BadZipFile as e:
        print(f"    TBG zip skip {zip_path.name}: {e}")
    return out


def fetch(raw_dir: Path, force: bool = False) -> list[Path]:
    manifest_path = raw_dir / "_manifest.json"
    manifest = base.load_manifest(manifest_path)
    headers = {"Referer": "https://www.tbg.com.br/informacoes-a-anp"}

    try:
        discovered = discover_urls()
    except Exception as e:
        print(f"    TBG discover warning: {e}")
        discovered = []

    paths: list[Path] = []
    for item in discovered:
        dest = raw_dir / item.filename
        if dest.exists() and not force:
            if item.filename.casefold().endswith(".zip"):
                paths.extend(_extract_zip(dest, raw_dir))
            else:
                paths.append(dest)
            continue
        try:
            if not base.download_file(item.url, dest, headers=headers):
                continue
            manifest[item.filename] = {
                "url": item.url,
                "sha256": base.file_sha256(dest),
                "bytes": dest.stat().st_size,
            }
            print(f"    fetched TBG {item.filename}")
            if item.filename.casefold().endswith(".zip"):
                paths.extend(_extract_zip(dest, raw_dir))
            elif re.search(r"\.(xlsx|xls)$", item.filename, re.I):
                paths.append(dest)
        except Exception as e:
            print(f"    TBG fetch failed for {item.filename}: {e}")
            if dest.exists() and re.search(r"\.(xlsx|xls)$", item.filename, re.I):
                paths.append(dest)
            elif dest.exists() and item.filename.casefold().endswith(".zip"):
                paths.extend(_extract_zip(dest, raw_dir))

    for local in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if local not in paths:
            paths.append(local)

    base.save_manifest(manifest_path, manifest)
    # Deduplicate while preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _find_prog_real_header(rows: list[list]) -> int | None:
    for i, row in enumerate(rows[:20]):
        cells = [str(c).strip().casefold() if c is not None and not (isinstance(c, float) and pd.isna(c)) else "" for c in row]
        if any(c == "programado" for c in cells) and any(c == "realizado" for c in cells):
            return i
    return None


def _parse_paired_prog_real_sheet(
    path: Path,
    *,
    sheet_name: str,
    point_type: str,
    crosswalk: dict[str, str],
) -> pd.DataFrame:
    """Melt TBG paired Programado/Realizado columns (values already thousand m³)."""
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
    rows = raw.values.tolist()
    header_idx = _find_prog_real_header(rows)
    if header_idx is None or header_idx < 1:
        return base.empty_points_frame()

    header = rows[header_idx]
    # Point names sit on the nearest non-empty row above the Programado line
    # (Entregues: names then ANP codes then Programado; Recebidos: names then Programado).
    name_row = None
    code_row = None
    for back in range(1, min(4, header_idx + 1)):
        candidate = rows[header_idx - back]
        nonempty = [
            c for c in candidate
            if c is not None and not (isinstance(c, float) and pd.isna(c)) and str(c).strip()
        ]
        if not nonempty:
            continue
        # Row of mostly integers → ANP point codes
        if sum(isinstance(c, (int, float)) and not isinstance(c, bool) for c in nonempty) >= max(2, len(nonempty) // 2):
            code_row = candidate
            continue
        name_row = candidate
        break
    if name_row is None:
        return base.empty_points_frame()

    # Map each Programado / Realizado column to a point.
    pairs: list[dict] = []
    last_name = None
    last_code = None
    for j, cell in enumerate(header):
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        label = str(cell).strip().casefold()
        if label not in ("programado", "realizado"):
            continue
        # Point name: same col, or previous col when names are left-aligned on Programado.
        name = None
        for src_row in (name_row,):
            for col in (j, j - 1):
                if col < 0 or col >= len(src_row):
                    continue
                raw_name = src_row[col]
                if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)):
                    continue
                text = str(raw_name).strip()
                if not text or text.casefold() in ("programado", "realizado", "nan"):
                    continue
                if text.casefold().startswith("total"):
                    name = None
                    break
                name = text
                break
            if name:
                break
        if name:
            last_name = name
        else:
            name = last_name
        if not name:
            continue

        code = None
        if code_row is not None:
            for col in (j, j - 1):
                if col < 0 or col >= len(code_row):
                    continue
                raw_code = code_row[col]
                if isinstance(raw_code, (int, float)) and not pd.isna(raw_code):
                    code = str(int(raw_code))
                    last_code = code
                    break
        if code is None:
            code = last_code

        variable = base.VAR_SCHEDULED if label == "programado" else base.VAR_ACTUAL
        cw_key = base.normalize_key(f"{TSO}|{name}")
        point_code = crosswalk.get(cw_key) or code or base.synthetic_point_code(SOURCE, "GASBOL", name)
        pairs.append({
            "col": j,
            "point_code": str(point_code),
            "point_name": name,
            "variable": variable,
        })

    if not pairs:
        return base.empty_points_frame()

    # Date column: first datetime-like cell to the left of the first value col.
    first_val_col = min(p["col"] for p in pairs)
    records: list[dict] = []
    for row in rows[header_idx + 1:]:
        date = None
        for j in range(0, first_val_col):
            if j >= len(row):
                break
            cell = row[j]
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                continue
            # Day-of-month integers (1..31) in column A must not become 1970-01-01.
            if isinstance(cell, (int, float)) and not isinstance(cell, bool) and float(cell) < 40000:
                # Excel serial dates for 2020+ are >= ~43831; day-of-month is 1..31.
                if float(cell) <= 31:
                    continue
            dt = pd.to_datetime(cell, dayfirst=True, errors="coerce")
            if pd.isna(dt):
                continue
            if dt.year < 1990 or dt.year > 2100:
                continue
            date = dt.normalize()
            break
        if date is None:
            continue
        for p in pairs:
            j = p["col"]
            if j >= len(row):
                continue
            raw = row[j]
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            records.append({
                "date": date,
                "point_code": p["point_code"],
                "point_name": p["point_name"],
                "point_type": point_type,
                "pipeline_code": f"{SOURCE}:gasbol",
                "pipeline_name": "Gasoduto Bolívia-Brasil",
                "municipality": None,
                "uf": None,
                "tso": TSO,
                "variable": p["variable"],
                "value": value,  # already thousand m³
                "source": SOURCE,
            })

    if not records:
        return base.empty_points_frame()
    return pd.DataFrame.from_records(records)


def _guess_point_type(path: Path, sheet_name: str) -> str:
    blob = f"{path.name} {sheet_name}".casefold()
    if "receb" in blob:
        return base.POINT_TYPE_RECEIPT
    if "entreg" in blob or "saíd" in blob or "said" in blob:
        return base.POINT_TYPE_DELIVERY
    return base.POINT_TYPE_DELIVERY


def build(raw_dir: Path) -> pd.DataFrame:
    crosswalk = load_crosswalk().get("tbg", {})
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if path.name.startswith("_"):
            continue
        try:
            xl = pd.ExcelFile(path, engine="openpyxl")
        except Exception as e:
            print(f"    TBG parse skip {path.name}: {e}")
            continue
        for sheet in xl.sheet_names:
            # Skip capacity / summary sheets.
            key = base.normalize_key(sheet)
            if "ocios" in key or "resumo" in key:
                continue
            try:
                df = _parse_paired_prog_real_sheet(
                    path,
                    sheet_name=sheet,
                    point_type=_guess_point_type(path, sheet),
                    crosswalk=crosswalk,
                )
            except Exception as e:
                print(f"    TBG parse skip {path.name} / {sheet}: {e}")
                continue
            if not df.empty:
                frames.append(df)
        # Also try TAG-shaped workbooks if someone seeded them.
        try:
            legacy = base.parse_wide_prog_real_workbook(
                path,
                source=SOURCE,
                tso=TSO,
                subsystem="GASBOL",
                pipeline_name="Gasoduto Bolívia-Brasil",
                crosswalk=crosswalk,
            )
            if not legacy.empty:
                frames.append(legacy)
        except Exception:
            pass

    if not frames:
        return base.empty_points_frame()
    out = pd.concat(frames, ignore_index=True)
    # Prefer explicit ANP codes / later files: drop exact duplicate keys keeping last.
    out = out.drop_duplicates(
        subset=["date", "point_code", "variable", "source"],
        keep="last",
    )
    return out


ADAPTER = base.Adapter(source=SOURCE, tso=TSO, fetch=fetch, build=build)
