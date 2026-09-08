"""NTS Portaria 1/2003 programmed/actual quantity files."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from . import base
from .crosswalk import load_crosswalk

SOURCE = "nts"
TSO = "NTS"
LANDING_URLS = [
    "https://www.ntsbrasil.com/transparencia/",
    "https://www.ntsbrasil.com/en/transport-system/",
]


def discover_urls() -> list[base.DiscoveredFile]:
    found: list[base.DiscoveredFile] = []
    seen: set[str] = set()
    for landing in LANDING_URLS:
        try:
            html = base.http_get_text(landing, headers={"Referer": "https://www.ntsbrasil.com/"})
        except Exception:
            continue
        # Pair nearby text with mzfilemanager / xlsx links when possible.
        for m in re.finditer(
            r'(?:href=["\']([^"\']+)["\'][^>]*>)?([^<]{0,120}?)(?:Programad|Realizad|Quantidade|Volumes)[^<]{0,80}',
            html,
            flags=re.I,
        ):
            pass  # keyword presence only; collect links below

        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
            href = m.group(1)
            url = urljoin(landing, href)
            if "mzfilemanager" not in url.casefold() and not re.search(r"\.(xlsx|xls)(\?|$)", url, re.I):
                continue
            # Prefer volume-related anchors: inspect surrounding 200 chars
            start = max(0, m.start() - 200)
            ctx = html[start:m.end() + 200].casefold()
            if not re.search(r"programad|realizad|quantidade|volume|prog.?real", ctx):
                # Still keep .xlsx from transparency pages
                if not re.search(r"\.(xlsx|xls)(\?|$)", url, re.I):
                    continue
            if url in seen:
                continue
            seen.add(url)
            name = Path(url.split("?")[0]).name
            if not re.search(r"\.(xlsx|xls)$", name, re.I):
                name = f"nts_{len(found):03d}.xlsx"
            found.append(base.DiscoveredFile(url=url, filename=name, label=ctx[:80]))
    return found


def fetch(raw_dir: Path, force: bool = False) -> list[Path]:
    manifest_path = raw_dir / "_manifest.json"
    manifest = base.load_manifest(manifest_path)
    headers = {"Referer": "https://www.ntsbrasil.com/transparencia/"}

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
            if base.download_file(item.url, dest, headers=headers):
                # Skip non-Excel payloads (MZIQ sometimes serves PDF/HTML)
                head = dest.read_bytes()[:8]
                if head[:2] != b"PK" and head[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    dest.unlink(missing_ok=True)
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


def build(raw_dir: Path) -> pd.DataFrame:
    crosswalk = load_crosswalk().get("nts", {})
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_dir.glob("*.xlsx")) + sorted(raw_dir.glob("*.xls")):
        if path.name.startswith("_"):
            continue
        try:
            df = base.parse_wide_prog_real_workbook(
                path,
                source=SOURCE,
                tso=TSO,
                subsystem="NTS",
                pipeline_name="NTS Transport System",
                crosswalk=crosswalk,
            )
        except Exception as e:
            print(f"    NTS parse skip {path.name}: {e}")
            continue
        if not df.empty:
            frames.append(df)
    if not frames:
        return base.empty_points_frame()
    return pd.concat(frames, ignore_index=True)


ADAPTER = base.Adapter(source=SOURCE, tso=TSO, fetch=fetch, build=build)
