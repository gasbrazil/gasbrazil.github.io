"""
ANP Resolution 52/2011 natural-gas price disclosure pipeline (PPG).

Fetches three ANP open-data CSVs (producers by basin, distributors to free
consumers by market type/region, sales to marketers) and builds a tidy
long parquet under precos/data/.

Source layout (verified): UTF-16LE with BOM, semicolon-delimited, comma
decimals. Suppressed months appear as empty price cells — preserved as
nulls (no interpolation).

Landing:
  https://www.gov.br/anp/pt-br/assuntos/movimentacao-estocagem-e-comercializacao-de-gas-natural/acompanhamento-do-mercado-de-gas-natural/precos-do-gas-natural-resolucao-anp-no-52-2011

Usage:
    python precos_pipeline.py fetch
    python precos_pipeline.py build
    python precos_pipeline.py all
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

PPG_BASE = (
    "https://www.gov.br/anp/pt-br/assuntos/movimentacao-estocagem-e-comercializacao"
    "-de-gas-natural/acompanhamento-do-mercado-de-gas-natural/ppg/"
)

# Remote name -> local filename under raw/
SOURCE_FILES = {
    "vendas-entre-produtores.csv": "vendas-entre-produtores.csv",
    "distribuidoras-consumidores-livres.csv": "distribuidoras-consumidores-livres.csv",
    "vendas-aos-comercializadores.csv": "vendas-aos-comercializadores.csv",
}

# Local file -> segment key used in the long frame
SEGMENT_BY_FILE = {
    "vendas-entre-produtores.csv": "producers",
    "distribuidoras-consumidores-livres.csv": "distributors",
    "vendas-aos-comercializadores.csv": "marketers",
}

BASIN_MAP = {
    "santos": "Santos",
    "campos": "Campos",
    "demais bacias": "Other basins",
}

MARKET_MAP = {
    "termico": "thermal",
    "nao termico": "non_thermal",
}

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
DATA_DIR = HERE / "data"
MANIFEST_PATH = RAW_DIR / "_manifest.json"
PRICES_PARQUET = DATA_DIR / "anp_prices.parquet"

HEADERS = {"User-Agent": "gasbrazil-precos-pipeline/1.0 (+https://gasbrazil.com/precos/)"}


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
    head = data[:200].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        print(f"  FAIL HTML body {url}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"  OK {dest.name} ({len(data):,} bytes) <- {url}")
    return True


def fetch_sources() -> dict:
    manifest = _load_manifest()
    results = {}
    for remote, local in SOURCE_FILES.items():
        dest = RAW_DIR / local
        url = PPG_BASE + remote
        if _download(url, dest):
            results[local] = {"url": url, "bytes": dest.stat().st_size}
        else:
            results[local] = {"error": "not found", "url": url}
    manifest["ppg"] = results
    manifest["fetched_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_manifest(manifest)
    return results


def cmd_fetch(_args) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("Fetching ANP PPG price CSVs…")
    fetch_sources()


def _read_anp_price_csv(path: Path) -> pd.DataFrame:
    """UTF-16LE (BOM) primary; utf-8-sig / latin-1 fallbacks for mocks."""
    errors: list[str] = []
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                path,
                sep=";",
                encoding=enc,
                dtype=str,
                engine="python",
            )
        except Exception as e:
            errors.append(f"{enc}: {type(e).__name__}: {e}")
    raise RuntimeError(f"Could not read {path}: {'; '.join(errors)}")


def _parse_number(raw) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", "-", "null"}:
        return None
    s = s.replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None


def _month_key(year_raw, month_raw) -> str | None:
    try:
        year = int(str(year_raw).strip())
    except (TypeError, ValueError):
        return None
    m = str(month_raw).strip()
    try:
        month = int(m)
    except ValueError:
        return None
    if not (1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}"


def _find_col(columns: list[str], *stems: str) -> str | None:
    norms = {_norm_col(c): c for c in columns}
    for stem in stems:
        stem_n = _norm_col(stem)
        if stem_n in norms:
            return norms[stem_n]
        for n, orig in norms.items():
            if n.startswith(stem_n) or stem_n in n:
                return orig
    return None


def _map_basin(raw: str | None) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    key = _norm_col(raw)
    return BASIN_MAP.get(key, str(raw).strip() or None)


def _map_market(raw: str | None) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    key = _norm_col(raw)
    return MARKET_MAP.get(key, str(raw).strip() or None)


def _tidy_file(path: Path, segment: str) -> pd.DataFrame:
    if not path.exists():
        print(f"  skip missing {path.name}")
        return pd.DataFrame(
            columns=[
                "month",
                "segment",
                "category",
                "region",
                "price_brl_mmbtu",
                "volume_thousand_m3_day",
            ]
        )
    df = _read_anp_price_csv(path)
    cols = list(df.columns)
    year_col = _find_col(cols, "ano")
    month_col = _find_col(cols, "mes", "mês")
    price_col = _find_col(cols, "preco", "preço")
    volume_col = _find_col(cols, "volume")
    basin_col = _find_col(cols, "bacia")
    market_col = _find_col(cols, "tipomercado", "tipo mercado")
    region_col = _find_col(cols, "regiao", "região")

    if not year_col or not month_col or not price_col:
        raise RuntimeError(
            f"{path.name}: could not map year/month/price columns (have {cols!r})"
        )

    rows: list[dict] = []
    for _, row in df.iterrows():
        month = _month_key(row[year_col], row[month_col])
        if month is None:
            continue
        category = None
        region = None
        if segment == "producers":
            category = _map_basin(row[basin_col] if basin_col else None)
        elif segment == "distributors":
            category = _map_market(row[market_col] if market_col else None)
            if region_col:
                reg = row[region_col]
                region = None if reg is None or (isinstance(reg, float) and pd.isna(reg)) else str(reg).strip()
        price = _parse_number(row[price_col])
        volume = _parse_number(row[volume_col]) if volume_col else None
        rows.append(
            {
                "month": month,
                "segment": segment,
                "category": category,
                "region": region,
                "price_brl_mmbtu": price,
                "volume_thousand_m3_day": volume,
            }
        )
    out = pd.DataFrame(rows)
    print(f"  {path.name}: {len(out):,} rows ({segment})")
    return out


def build_prices() -> pd.DataFrame:
    frames = []
    for fname, segment in SEGMENT_BY_FILE.items():
        frames.append(_tidy_file(RAW_DIR / fname, segment))
    if not frames:
        return pd.DataFrame(
            columns=[
                "month",
                "segment",
                "category",
                "region",
                "price_brl_mmbtu",
                "volume_thousand_m3_day",
            ]
        )
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(
        ["month", "segment", "category", "region"],
        na_position="last",
    ).reset_index(drop=True)


def cmd_build(_args) -> None:
    print("Building ANP prices parquet…")
    df = build_prices()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PRICES_PARQUET, index=False)
    print(f"Wrote {len(df):,} rows to {PRICES_PARQUET}")

    sys.path.insert(0, str(HERE.parent / "shared"))
    import data_kit as dk  # noqa: E402
    import schemas  # noqa: E402

    schemas.validate_anp_prices(df)
    dk.publish("anp_prices", PRICES_PARQUET)

    problems = []
    if len(df) == 0:
        problems.append("zero rows in anp_prices.parquet")
    else:
        last = df["month"].dropna().max()
        if last:
            y, m = map(int, str(last).split("-")[:2])
            last_dt = dt.date(y, m, 1)
            today = dt.date.today().replace(day=1)
            lag = (today.year - last_dt.year) * 12 + (today.month - last_dt.month)
            if lag > 6:
                problems.append(f"latest month {last} is {lag} months behind (expected ANP lag ~2–3)")
        priced = df["price_brl_mmbtu"].notna().sum()
        if priced == 0:
            problems.append("price_brl_mmbtu is entirely null")
        for seg in ("producers", "distributors", "marketers"):
            if (df["segment"] == seg).sum() == 0:
                problems.append(f"segment {seg!r} has zero rows")
    if problems:
        for p in problems:
            print(f"HEALTH FAIL: {p}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Health OK — months {df['month'].iloc[0]} … {df['month'].iloc[-1]} ({len(df):,} rows)")


def cmd_all(args) -> None:
    cmd_fetch(args)
    cmd_build(args)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="Download raw CSVs into precos/raw/")
    sub.add_parser("build", help="Build precos/data/anp_prices.parquet")
    sub.add_parser("all", help="fetch + build")
    args = p.parse_args(argv)
    {"fetch": cmd_fetch, "build": cmd_build, "all": cmd_all}[args.cmd](args)


if __name__ == "__main__":
    main()
