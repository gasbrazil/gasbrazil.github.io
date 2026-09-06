"""
CCEE daily-average PLD (Preço de Liquidação das Diferenças) pipeline.

Fetches yearly CSVs from CCEE's open-data CKAN package `pld_media_diaria`
and builds a tidy daily parquet store.

Source (discover URLs each fetch — download tokens rotate):
  https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_media_diaria

CSV layout (semicolon, ISO-8859-2 / latin-1):
  MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA
  202609;NORDESTE;06/09/2026;118.04

Submarkets: NORTE, NORDESTE, SUDESTE, SUL.

Output:
  data/pld_daily.parquet — columns: date, submarket, pld (float R$/MWh)

Usage:
    python pld_pipeline.py fetch    # download raw/pld_media_diaria_<year>.csv
    python pld_pipeline.py build    # raw/*.csv -> data/pld_daily.parquet
    python pld_pipeline.py all      # fetch + build
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

PACKAGE_API = (
    "https://dadosabertos.ccee.org.br/api/3/action/package_show"
    "?id=pld_media_diaria"
)

# Download URLs rotate; these are known-good fallbacks for 2021–2026
# (verified 2026-09). Prefer package_show discovery; use these only when
# a year's resource is missing from the API response.
FALLBACK_URLS: dict[int, str] = {
    2021: "https://pda-download.ccee.org.br/s2aV2TfuTb2EQmKKY2Qg-w/content",
    2022: "https://pda-download.ccee.org.br/toeEwFnrRdi2lT7_ppiRfw/content",
    2023: "https://pda-download.ccee.org.br/WYOTpvY0QrmRKXx0bVT_ng/content",
    2024: "https://pda-download.ccee.org.br/jJSRhSl3SuGfKkCHVcQHxA/content",
    2025: "https://pda-download.ccee.org.br/by-H-ms8SLCvO0rerYBWTQ/content",
    2026: "https://pda-download.ccee.org.br/T09SGpnfRN-2ZaeWfHgrMw/content",
}

# Fetch recent years every run (current year always; prior years if missing).
FETCH_START_YEAR = 2021
# Re-download the current year (and optionally last year early in Jan) even
# when already cached — CCEE appends new days in place.
REFRESH_CURRENT = True

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
DATA_DIR = HERE / "data"
MANIFEST_PATH = RAW_DIR / "_manifest.json"
PARQUET_PATH = DATA_DIR / "pld_daily.parquet"

HEADERS = {"User-Agent": "gasbrazil-pld-pipeline/1.0 (+https://gasbrazil.com/pld/)"}

# Canonical English short codes used in the parquet / dashboard.
SUBMARKET_MAP = {
    "NORTE": "N",
    "NORDESTE": "NE",
    "SUDESTE": "SE",
    "SUL": "S",
}
SUBMARKET_LABELS = {
    "N": "North",
    "NE": "Northeast",
    "SE": "Southeast",
    "S": "South",
}


def _http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def discover_year_urls() -> dict[int, str]:
    """Map year → download URL via package_show; fall back to FALLBACK_URLS."""
    urls = dict(FALLBACK_URLS)
    try:
        raw = _http_get(PACKAGE_API)
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("success"):
            print("package_show returned success=false; using fallback URLs")
            return urls
        for res in payload["result"].get("resources") or []:
            name = str(res.get("name") or "")
            url = str(res.get("url") or "").strip()
            m = re.search(r"(20\d{2})", name)
            if not m or not url:
                continue
            year = int(m.group(1))
            urls[year] = url
        print(f"Discovered {len(urls)} year URLs via package_show")
    except Exception as e:
        print(f"package_show failed ({e}); using fallback URLs")
    return urls


def _year_path(year: int) -> Path:
    return RAW_DIR / f"pld_media_diaria_{year}.csv"


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_manifest(manifest: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def fetch(*, years: list[int] | None = None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    discovered = discover_year_urls()
    now_year = pd.Timestamp.now("UTC").year
    if years is None:
        years = sorted(y for y in discovered if y >= FETCH_START_YEAR)
        # Prefer at least the known fallback range so a partial API response
        # still pulls history we care about.
        for y in FALLBACK_URLS:
            if y not in years and y >= FETCH_START_YEAR:
                years.append(y)
        years = sorted(set(years))

    manifest = _load_manifest()
    for year in years:
        url = discovered.get(year) or FALLBACK_URLS.get(year)
        if not url:
            print(f"  skip {year}: no URL")
            continue
        out = _year_path(year)
        is_current = year >= now_year - (0 if REFRESH_CURRENT else 1)
        if out.exists() and not is_current and year < now_year:
            print(f"  cached {out.name}")
            continue
        print(f"  fetch {year} <- {url[:80]}...")
        try:
            data = _http_get(url)
        except urllib.error.HTTPError as e:
            print(f"  FAIL {year}: HTTP {e.code}")
            continue
        except Exception as e:
            print(f"  FAIL {year}: {e}")
            continue
        # Sanity: header should mention PLD / SUBMERCADO
        head = data[:200].decode("latin-1", errors="replace").upper()
        if "PLD" not in head and "SUBMERCADO" not in head:
            print(f"  FAIL {year}: response does not look like a PLD CSV")
            continue
        out.write_bytes(data)
        manifest[str(year)] = {
            "url": url,
            "bytes": len(data),
            "fetched": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        print(f"  wrote {out.name} ({len(data):,} bytes)")
        time.sleep(0.4)
    _save_manifest(manifest)


def _read_csv(path: Path) -> pd.DataFrame:
    """Read one yearly CCEE PLD CSV into tidy rows."""
    # Encoding: files are ISO-8859-2 / latin-1; latin-1 never fails on bytes.
    df = pd.read_csv(
        path,
        sep=";",
        encoding="latin-1",
        dtype=str,
        engine="python",
    )
    cols = {c.strip().upper(): c for c in df.columns}
    need = ["SUBMERCADO", "DIA", "PLD_MEDIA_DIA"]
    for n in need:
        if n not in cols:
            raise ValueError(f"{path.name}: missing column {n}; got {list(df.columns)}")
    out = pd.DataFrame({
        "submarket_raw": df[cols["SUBMERCADO"]].astype(str).str.strip().str.upper(),
        "dia": df[cols["DIA"]].astype(str).str.strip(),
        "pld_raw": df[cols["PLD_MEDIA_DIA"]].astype(str).str.strip(),
    })
    out["date"] = pd.to_datetime(out["dia"], dayfirst=True, errors="coerce")
    # Decimal may be "." (current) or "," (older vintages).
    cleaned = (
        out["pld_raw"]
        .str.replace(r"\s+", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    out["pld"] = pd.to_numeric(cleaned, errors="coerce")
    out["submarket"] = out["submarket_raw"].map(SUBMARKET_MAP)
    out = out.dropna(subset=["date", "pld", "submarket"])
    out = out[["date", "submarket", "pld"]]
    out["pld"] = out["pld"].astype(float).round(4)
    return out


def build() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.glob("pld_media_diaria_*.csv"))
    if not files:
        raise SystemExit(
            f"No raw CSVs in {RAW_DIR}. Run `python pld_pipeline.py fetch` "
            "or `python make_mock.py` first."
        )
    frames = []
    for path in files:
        try:
            part = _read_csv(path)
            print(f"  {path.name}: {len(part):,} rows")
            frames.append(part)
        except Exception as e:
            print(f"  FAIL {path.name}: {e}")
            raise
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["date", "submarket"], keep="last")
    df = df.sort_values(["date", "submarket"]).reset_index(drop=True)
    if df.empty:
        raise SystemExit("Build produced zero rows")
    # Health: expect all four submarkets; data shouldn't be older than ~14 days
    # for the current year file (CCEE publishes daily with a short lag).
    missing_sm = set(SUBMARKET_MAP.values()) - set(df["submarket"].unique())
    if missing_sm:
        print(f"  WARN missing submarkets: {sorted(missing_sm)}")
    last = df["date"].max()
    lag_days = (pd.Timestamp.now("UTC").date() - pd.Timestamp(last).date()).days
    if lag_days > 21:
        print(f"  WARN latest date {pd.Timestamp(last).date()} is {lag_days} days behind UTC today")
    df.to_parquet(PARQUET_PATH, index=False)
    print(
        f"Wrote {PARQUET_PATH} ({len(df):,} rows, "
        f"{pd.Timestamp(df['date'].min()).date()} -> {pd.Timestamp(df['date'].max()).date()})"
    )
    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "build", "all"])
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        help="Limit fetch to these years (default: all discovered ≥ 2021)",
    )
    args = parser.parse_args(argv)
    if args.command in ("fetch", "all"):
        print("Fetching CCEE PLD yearly CSVs…")
        fetch(years=args.years)
    if args.command in ("build", "all"):
        print("Building pld_daily.parquet…")
        build()


if __name__ == "__main__":
    main()
