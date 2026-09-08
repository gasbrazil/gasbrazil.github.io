"""TAG Portaria 1/2003 Prog-Real cumulative workbooks."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from . import base
from .crosswalk import load_crosswalk

TRANSPARENCY_URL = "https://ntag.com.br/transparencia/"
SOURCE = "tag"
TSO = "TAG"

# Fallback URLs when HTML discovery fails (filenames change with coverage).
FALLBACK_URLS = [
    "https://www.ntag.com.br/wp-content/uploads/2026/08/Prog-Real_GASENE_01-2017_a_07-2026.xlsx",
    "https://www.ntag.com.br/wp-content/uploads/2026/08/Prog-Real_MALHAS-NE_01-2017_a_07-2026.xlsx",
    "https://www.ntag.com.br/wp-content/uploads/2026/08/Prog-Real_PILAR-IPOJUCA_01-2017_a_07-2026.xlsx",
    "https://www.ntag.com.br/wp-content/uploads/2026/08/Prog-Real_URUCU-MANAUS_01-2017_a_07-2026.xlsx",
]

SUBSYSTEM_LABELS = {
    "gasene": "GASENE",
    "malhas ne": "Malhas Nordeste",
    "malhas-ne": "Malhas Nordeste",
    "pilar ipojuca": "Pilar-Ipojuca",
    "pilar-ipojuca": "Pilar-Ipojuca",
    "urucu manaus": "Urucu-Manaus",
    "urucu-manaus": "Urucu-Manaus",
}


def discover_urls() -> list[base.DiscoveredFile]:
    html = base.http_get_text(
        TRANSPARENCY_URL,
        headers={"Referer": "https://ntag.com.br/"},
    )
    found: list[base.DiscoveredFile] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href=["\']([^"\']*Prog-Real[^"\']+\.xlsx)["\']',
        html,
        flags=re.I,
    ):
        url = urljoin(TRANSPARENCY_URL, m.group(1))
        if url in seen:
            continue
        seen.add(url)
        found.append(base.DiscoveredFile(url=url, filename=Path(url).name))
    if found:
        return found
    return [
        base.DiscoveredFile(url=u, filename=Path(u).name) for u in FALLBACK_URLS
    ]


def fetch(raw_dir: Path, force: bool = False) -> list[Path]:
    manifest_path = raw_dir / "_manifest.json"
    manifest = base.load_manifest(manifest_path)
    headers = {"Referer": "https://ntag.com.br/"}

    try:
        discovered = discover_urls()
    except Exception as e:
        print(f"    TAG discover warning: {e}; using cached files / fallbacks")
        discovered = [base.DiscoveredFile(url=u, filename=Path(u).name) for u in FALLBACK_URLS]

    paths: list[Path] = []
    for item in discovered:
        dest = raw_dir / item.filename
        key = item.filename
        if dest.exists() and not force:
            paths.append(dest)
            continue
        try:
            ok = base.download_file(item.url, dest, headers=headers)
            if not ok:
                print(f"    TAG 404: {item.url}")
                if dest.exists():
                    paths.append(dest)
                continue
            manifest[key] = {
                "url": item.url,
                "sha256": base.file_sha256(dest),
                "bytes": dest.stat().st_size,
            }
            paths.append(dest)
            print(f"    fetched TAG {item.filename}")
        except Exception as e:
            print(f"    TAG fetch failed for {item.filename}: {e}")
            if dest.exists():
                paths.append(dest)

    # Keep any locally seeded Prog-Real files even if discovery missed them.
    for local in sorted(raw_dir.glob("Prog-Real*.xlsx")):
        if local not in paths:
            paths.append(local)

    base.save_manifest(manifest_path, manifest)
    return paths


def _subsystem_label(filename: str) -> str:
    stem = Path(filename).stem
    m = re.search(r"Prog-Real_(.+?)_\d{2}-\d{4}", stem, re.I)
    raw = m.group(1) if m else stem
    key = base.normalize_key(raw.replace("_", " ").replace("-", " "))
    for needle, label in SUBSYSTEM_LABELS.items():
        if base.normalize_key(needle) in key or key in base.normalize_key(needle):
            return label
    return raw.replace("_", " ").replace("-", " ")


def build(raw_dir: Path) -> pd.DataFrame:
    crosswalk = load_crosswalk().get("tag", {})
    frames: list[pd.DataFrame] = []
    for path in sorted(raw_dir.glob("Prog-Real*.xlsx")):
        subsystem = _subsystem_label(path.name)
        df = base.parse_wide_prog_real_workbook(
            path,
            source=SOURCE,
            tso=TSO,
            subsystem=subsystem,
            pipeline_name=subsystem,
            crosswalk=crosswalk,
        )
        if not df.empty:
            frames.append(df)
    if not frames:
        return base.empty_points_frame()
    return pd.concat(frames, ignore_index=True)


ADAPTER = base.Adapter(source=SOURCE, tso=TSO, fetch=fetch, build=build)
