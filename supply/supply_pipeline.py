"""
ANP natural-gas supply balance pipeline (PPGN-EL + imports).

Fetches ANP open-data CSVs for production, available gas, flare/loss, own
consumption, reinjection, LGN, and (when available) natural-gas imports,
then builds a tidy monthly national series parquet.

PPGN-EL base:
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/ppgn-el/
Landing (humans):
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-estado-e-localizacao

Imports (stable CSV under ie/gn/; filename end-year drifts annually):
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/ie/gn/
  importacao-gas-natural-2000-<YYYY>.csv
Landing:
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/importacoes-e-exportacoes

Source layout (verified): semicolon-delimited, utf-8-sig, Portuguese month
abbreviations (JAN..DEZ), comma decimals, state/location grain for PPGN-EL.
`build` sums to one national row per calendar month.

Usage:
    python supply_pipeline.py fetch
    python supply_pipeline.py build
    python supply_pipeline.py all
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

PPGN_BASE = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/ppgn-el/"
)
IMPORT_BASE = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/ie/gn/"
)

# Remote name -> local filename under raw/. reinjection is published WITHOUT
# a .csv extension (404 with .csv); we still store it locally with .csv.
PPGN_FILES = {
    "producao-gas-natural-1000m3.csv": "producao-gas-natural-1000m3.csv",
    "gn-disponivel-1000m3.csv": "gn-disponivel-1000m3.csv",
    "queima-e-perda-gn-1000m3.csv": "queima-e-perda-gn-1000m3.csv",
    "consumo-proprio-gn1000m3.csv": "consumo-proprio-gn1000m3.csv",
    "producao-lgn-m3.csv": "producao-lgn-m3.csv",
    "reinjecao-gn-1000m3": "reinjecao-gn-1000m3.csv",
}

# metric key -> (local raw file, preferred value-column stems, unit note)
SERIES_SPECS = {
    "production": ("producao-gas-natural-1000m3.csv", ["producao", "produção"], "1000m3"),
    "available": ("gn-disponivel-1000m3.csv", ["disponivel", "disponível"], "1000m3"),
    "flare_loss": ("queima-e-perda-gn-1000m3.csv", ["queimado", "queima"], "1000m3"),
    "own_use": ("consumo-proprio-gn1000m3.csv", ["consumo"], "1000m3"),
    "reinjection": ("reinjecao-gn-1000m3.csv", ["reinjetado", "reinjecao", "reinjeção"], "1000m3"),
    "lgn": ("producao-lgn-m3.csv", ["producao", "produção"], "m3"),
    "imports": ("importacao-gas-natural.csv", ["importado"], "1000m3"),
}

MONTH_PT = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
DATA_DIR = HERE / "data"
MANIFEST_PATH = RAW_DIR / "_manifest.json"
MONTHLY_PARQUET = DATA_DIR / "supply_monthly.parquet"

HEADERS = {"User-Agent": "gasbrazil-supply-pipeline/1.0 (+https://gasbrazil.com/supply/)"}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm_col(s: str) -> str:
    return _strip_accents(str(s)).casefold().strip()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_manifest(manifest: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _download(url: str, dest: Path) -> bool:
    try:
        data = _http_get(url)
    except urllib.error.HTTPError as e:
        print(f"  FAIL {e.code} {url}")
        return False
    except Exception as e:
        print(f"  FAIL {type(e).__name__} {url}: {e}")
        return False
    if not data or len(data) < 40:
        print(f"  FAIL empty/too-small {url}")
        return False
    # Reject HTML error pages accidentally served as 200
    head = data[:200].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        print(f"  FAIL HTML body {url}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"  OK {dest.name} ({len(data):,} bytes) <- {url}")
    return True


def fetch_ppgn() -> dict:
    """Download PPGN-EL files. Tries reinjection with and without .csv."""
    manifest = _load_manifest()
    results = {}
    for remote, local in PPGN_FILES.items():
        dest = RAW_DIR / local
        urls = [PPGN_BASE + remote]
        if not remote.endswith(".csv"):
            urls.append(PPGN_BASE + remote + ".csv")
        elif remote == "reinjecao-gn-1000m3.csv":
            urls = [PPGN_BASE + "reinjecao-gn-1000m3", PPGN_BASE + remote]
        ok = False
        for url in urls:
            if _download(url, dest):
                results[local] = {"url": url, "bytes": dest.stat().st_size}
                ok = True
                break
        if not ok:
            results[local] = {"error": "not found"}
    # Explicit reinjection fallback if the map entry used the extensionless name
    if "reinjecao-gn-1000m3.csv" not in results or results["reinjecao-gn-1000m3.csv"].get("error"):
        dest = RAW_DIR / "reinjecao-gn-1000m3.csv"
        for url in (PPGN_BASE + "reinjecao-gn-1000m3", PPGN_BASE + "reinjecao-gn-1000m3.csv"):
            if _download(url, dest):
                results["reinjecao-gn-1000m3.csv"] = {"url": url, "bytes": dest.stat().st_size}
                break
    manifest["ppgn"] = results
    manifest["fetched_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_manifest(manifest)
    return results


def fetch_imports() -> dict | None:
    """ANP publishes importacao-gas-natural-2000-<endYear>.csv; end year
    lags the calendar (page may say 2026 while file still ends in 2025).
    Try current year down a few years; keep the first hit."""
    now_year = dt.datetime.now(dt.timezone.utc).year
    dest = RAW_DIR / "importacao-gas-natural.csv"
    tried = []
    for end_year in range(now_year + 1, now_year - 4, -1):
        name = f"importacao-gas-natural-2000-{end_year}.csv"
        url = IMPORT_BASE + name
        tried.append(url)
        if _download(url, dest):
            info = {"url": url, "bytes": dest.stat().st_size, "remote_name": name}
            manifest = _load_manifest()
            manifest["imports"] = info
            _save_manifest(manifest)
            return info
    print("  imports: no stable CSV found among", tried)
    manifest = _load_manifest()
    manifest["imports"] = {"error": "not found", "tried": tried}
    _save_manifest(manifest)
    return None


def cmd_fetch(_args) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("Fetching PPGN-EL…")
    fetch_ppgn()
    print("Fetching natural-gas imports…")
    fetch_imports()


def _read_anp_csv(path: Path) -> pd.DataFrame:
    # utf-8-sig handles BOM; latin-1 fallback for older dumps.
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                path,
                sep=";",
                encoding=enc,
                dtype=str,
                engine="python",
            )
        except Exception:
            continue
    raise RuntimeError(f"Could not read {path}")


def _parse_number(raw) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", "-"}:
        return None
    s = s.replace(" ", "").replace("\u00a0", "")
    # Brazilian: 1.234.567,89 or plain 1234,56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None


def _find_value_col(columns: list[str], stems: list[str]) -> str | None:
    norms = {_norm_col(c): c for c in columns}
    for stem in stems:
        stem_n = _norm_col(stem)
        for n, orig in norms.items():
            if n == stem_n or n.startswith(stem_n):
                return orig
        for n, orig in norms.items():
            if stem_n in n:
                return orig
    return None


def _month_key(year_raw, month_raw) -> str | None:
    try:
        year = int(str(year_raw).strip())
    except (TypeError, ValueError):
        return None
    m = str(month_raw).strip().upper()
    # Accept "JAN", "01", "1"
    if m in MONTH_PT:
        month = MONTH_PT[m]
    else:
        try:
            month = int(m)
        except ValueError:
            return None
    if not (1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}"


def _national_monthly(path: Path, stems: list[str]) -> pd.Series:
    """Sum value column across all states/locations -> Series indexed by YYYY-MM."""
    if not path.exists():
        print(f"  skip missing {path.name}")
        return pd.Series(dtype="float64")
    df = _read_anp_csv(path)
    cols = list(df.columns)
    year_col = next((c for c in cols if _norm_col(c) == "ano"), None)
    month_col = next((c for c in cols if _norm_col(c) in {"mes", "mês"}), None)
    value_col = _find_value_col(cols, stems)
    if not year_col or not month_col or not value_col:
        raise RuntimeError(
            f"{path.name}: could not map columns (have {cols!r}, need year/month/{stems})"
        )
    keys = []
    vals = []
    for _, row in df.iterrows():
        key = _month_key(row[year_col], row[month_col])
        if key is None:
            continue
        num = _parse_number(row[value_col])
        if num is None:
            continue
        keys.append(key)
        vals.append(num)
    if not keys:
        return pd.Series(dtype="float64")
    out = pd.DataFrame({"month": keys, "value": vals}).groupby("month", as_index=True)["value"].sum()
    out.index.name = "month"
    return out


def build_monthly() -> pd.DataFrame:
    series_map: dict[str, pd.Series] = {}
    for metric, (fname, stems, _unit) in SERIES_SPECS.items():
        path = RAW_DIR / fname
        print(f"  aggregating {metric} from {fname}…")
        series_map[metric] = _national_monthly(path, stems)

    all_months = sorted(set().union(*(set(s.index) for s in series_map.values() if len(s))))
    if not all_months:
        return pd.DataFrame(columns=["month", *SERIES_SPECS.keys()])

    rows = []
    for m in all_months:
        row = {"month": m}
        for metric, s in series_map.items():
            v = s.get(m)
            row[metric] = None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)
        rows.append(row)
    df = pd.DataFrame(rows)
    # Prefer production/available coverage window for "data through"
    return df.sort_values("month").reset_index(drop=True)


def cmd_build(_args) -> None:
    print("Building monthly national series…")
    df = build_monthly()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(MONTHLY_PARQUET, index=False)
    print(f"Wrote {len(df):,} months to {MONTHLY_PARQUET}")

    problems = []
    if len(df) == 0:
        problems.append("zero rows in supply_monthly.parquet")
    else:
        # ANP typically lags ~2 months; allow up to ~5 months stale before failing CI
        last = df["month"].dropna().max()
        if last:
            y, m = map(int, str(last).split("-")[:2])
            last_dt = dt.date(y, m, 1)
            today = dt.date.today().replace(day=1)
            # months between
            lag = (today.year - last_dt.year) * 12 + (today.month - last_dt.month)
            if lag > 5:
                problems.append(f"latest month {last} is {lag} months behind (expected ANP lag ~2)")
        for col in ("production", "available"):
            if col in df.columns and df[col].notna().sum() == 0:
                problems.append(f"column {col} is entirely null")
    if problems:
        for p in problems:
            print(f"HEALTH FAIL: {p}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Health OK — months {df['month'].iloc[0]} … {df['month'].iloc[-1]}")


def cmd_all(args) -> None:
    cmd_fetch(args)
    cmd_build(args)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="Download raw CSVs into supply/raw/")
    sub.add_parser("build", help="Build supply/data/supply_monthly.parquet")
    sub.add_parser("all", help="fetch + build")
    args = p.parse_args(argv)
    {"fetch": cmd_fetch, "build": cmd_build, "all": cmd_all}[args.cmd](args)


if __name__ == "__main__":
    main()
