"""TBG Portaria 1/2003 programmed/actual quantity files."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

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


def discover_urls() -> list[base.DiscoveredFile]:
    found: list[base.DiscoveredFile] = []
    seen: set[str] = set()
    for landing in LANDING_URLS:
        try:
            html = base.http_get_text(landing, headers={"Referer": "https://www.tbg.com.br/"})
        except Exception:
            continue
        for m in re.finditer(r'href=["\']([^"\']+\.(?:xlsx|xls|pdf))["\']', html, flags=re.I):
            href = m.group(1)
            url = urljoin(landing, href)
            name = Path(url.split("?")[0]).name
            blob = f"{name} {href}".casefold()
            if not re.search(r"program|realiz|quantidade|prog.?real|volume", blob):
                # Keep spreadsheet downloads near Portaria pages even without
                # keyword match — TBG often uses opaque document-library names.
                if not re.search(r"\.(xlsx|xls)$", url, re.I):
                    continue
            if url in seen:
                continue
            seen.add(url)
            found.append(base.DiscoveredFile(url=url, filename=name or f"tbg_{len(found)}.xlsx"))
    return found


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
        if not re.search(r"\.(xlsx|xls)$", item.filename, re.I):
            continue  # skip PDFs for now
        dest = raw_dir / item.filename
        if dest.exists() and not force:
            paths.append(dest)
            continue
        try:
            if base.download_file(item.url, dest, headers=headers):
                manifest[item.filename] = {
                    "url": item.url,
                    "sha256": base.file_sha256(dest),
                    "bytes": dest.stat().st_size,
                }
                paths.append(dest)
                print(f"    fetched TBG {item.filename}")
        except Exception as e:
            print(f"    TBG fetch failed for {item.filename}: {e}")
            if dest.exists():
                paths.append(dest)

    for local in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if local not in paths:
            paths.append(local)

    base.save_manifest(manifest_path, manifest)
    return paths


def build(raw_dir: Path) -> pd.DataFrame:
    crosswalk = load_crosswalk().get("tbg", {})
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if path.name.startswith("_"):
            continue
        try:
            df = base.parse_wide_prog_real_workbook(
                path,
                source=SOURCE,
                tso=TSO,
                subsystem="GASBOL",
                pipeline_name="Gasoduto Bolívia-Brasil",
                crosswalk=crosswalk,
            )
        except Exception as e:
            print(f"    TBG parse skip {path.name}: {e}")
            continue
        if not df.empty:
            frames.append(df)
    if not frames:
        return base.empty_points_frame()
    return pd.concat(frames, ignore_index=True)


ADAPTER = base.Adapter(source=SOURCE, tso=TSO, fetch=fetch, build=build)
