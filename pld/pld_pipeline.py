"""
CCEE PLD (Preço de Liquidação das Diferenças) pipeline.

Fetches yearly CSVs from CCEE's open-data CKAN packages and builds tidy
parquet stores:

  * `pld_media_diaria` → data/pld_daily.parquet
  * `pld_horario`      → data/pld_hourly.parquet  (from HOURLY_FETCH_START_YEAR)

Sources (discover URLs each fetch — download tokens rotate):
  https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_media_diaria
  https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_horario

Daily CSV (semicolon, ISO-8859-2 / latin-1):
  MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA
  202609;NORDESTE;06/09/2026;118.04

Hourly CSV (same encoding; DIA is day-of-month, not a full date):
  MES_REFERENCIA;SUBMERCADO;PERIODO_COMERCIALIZACAO;DIA;HORA;PLD_HORA
  202609;NORDESTE;241;11;0;157.31

Submarkets: NORTE, NORDESTE, SUDESTE, SUL.

Usage:
    python pld_pipeline.py fetch    # download raw yearly CSVs (daily + hourly)
    python pld_pipeline.py build    # raw/*.csv -> data/pld_{daily,hourly}.parquet
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
HOURLY_PACKAGE_API = (
    "https://dadosabertos.ccee.org.br/api/3/action/package_show"
    "?id=pld_horario"
)

# Download URLs rotate; these are known-good fallbacks (verified 2026-09).
# Prefer package_show discovery; use these only when a year's resource is
# missing from the API response.
FALLBACK_URLS: dict[int, str] = {
    2021: "https://pda-download.ccee.org.br/s2aV2TfuTb2EQmKKY2Qg-w/content",
    2022: "https://pda-download.ccee.org.br/toeEwFnrRdi2lT7_ppiRfw/content",
    2023: "https://pda-download.ccee.org.br/WYOTpvY0QrmRKXx0bVT_ng/content",
    2024: "https://pda-download.ccee.org.br/jJSRhSl3SuGfKkCHVcQHxA/content",
    2025: "https://pda-download.ccee.org.br/by-H-ms8SLCvO0rerYBWTQ/content",
    2026: "https://pda-download.ccee.org.br/T09SGpnfRN-2ZaeWfHgrMw/content",
}

# Hourly PLD starts in 2021; we keep a few recent years (not the full
# 2001–2020 weekly historic resource on the same package).
HOURLY_FALLBACK_URLS: dict[int, str] = {
    2024: "https://pda-download.ccee.org.br/rMsBwN6TT-WUW2_LbGUvkw/content",
    2025: "https://pda-download.ccee.org.br/korJMXwpSLGyVlpRMQWduA/content",
    2026: "https://pda-download.ccee.org.br/6A5wq97KTCWv_bvs3CqsQQ/content",
}

# Fetch recent years every run (current year always; prior years if missing).
FETCH_START_YEAR = 2021
HOURLY_FETCH_START_YEAR = 2024
# Re-download the current year even when already cached — CCEE appends
# new days in place.
REFRESH_CURRENT = True

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
DATA_DIR = HERE / "data"
MANIFEST_PATH = RAW_DIR / "_manifest.json"
PARQUET_PATH = DATA_DIR / "pld_daily.parquet"
HOURLY_PARQUET_PATH = DATA_DIR / "pld_hourly.parquet"

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


def discover_year_urls(
    package_api: str = PACKAGE_API,
    fallback: dict[int, str] | None = None,
    *,
    name_contains: str | None = None,
) -> dict[int, str]:
    """Map year → download URL via package_show; fall back to known URLs."""
    urls = dict(fallback or FALLBACK_URLS)
    try:
        raw = _http_get(package_api)
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("success"):
            print("package_show returned success=false; using fallback URLs")
            return urls
        for res in payload["result"].get("resources") or []:
            name = str(res.get("name") or "")
            url = str(res.get("url") or "").strip()
            if name_contains and name_contains not in name.lower():
                continue
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


def _hourly_year_path(year: int) -> Path:
    return RAW_DIR / f"pld_horario_{year}.csv"


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


def _fetch_years(
    *,
    years: list[int],
    discovered: dict[int, str],
    fallback: dict[int, str],
    path_fn,
    manifest_key: str,
    look_for: tuple[str, ...],
) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    now_year = pd.Timestamp.now("UTC").year
    manifest = _load_manifest()
    bucket = manifest.setdefault(manifest_key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        manifest[manifest_key] = bucket
    for year in years:
        url = discovered.get(year) or fallback.get(year)
        if not url:
            print(f"  skip {year}: no URL")
            continue
        out = path_fn(year)
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
        head = data[:240].decode("latin-1", errors="replace").upper()
        if not any(token in head for token in look_for):
            print(f"  FAIL {year}: response does not look like a PLD CSV")
            continue
        out.write_bytes(data)
        bucket[str(year)] = {
            "url": url,
            "bytes": len(data),
            "fetched": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        print(f"  wrote {out.name} ({len(data):,} bytes)")
        time.sleep(0.4)
    _save_manifest(manifest)


def _years_to_fetch(
    discovered: dict[int, str],
    fallback: dict[int, str],
    start_year: int,
    years: list[int] | None,
) -> list[int]:
    if years is not None:
        return sorted(set(years))
    out = sorted(y for y in discovered if y >= start_year)
    for y in fallback:
        if y not in out and y >= start_year:
            out.append(y)
    return sorted(set(out))


def fetch(*, years: list[int] | None = None, hourly_years: list[int] | None = None) -> None:
    """Download daily and hourly yearly CSVs into raw/."""
    print("  daily package…")
    discovered = discover_year_urls(PACKAGE_API, FALLBACK_URLS)
    daily_years = _years_to_fetch(discovered, FALLBACK_URLS, FETCH_START_YEAR, years)
    _fetch_years(
        years=daily_years,
        discovered=discovered,
        fallback=FALLBACK_URLS,
        path_fn=_year_path,
        manifest_key="daily",
        look_for=("PLD", "SUBMERCADO"),
    )

    print("  hourly package…")
    hourly_discovered = discover_year_urls(
        HOURLY_PACKAGE_API,
        HOURLY_FALLBACK_URLS,
        name_contains="pld_horario",
    )
    h_years = _years_to_fetch(
        hourly_discovered, HOURLY_FALLBACK_URLS, HOURLY_FETCH_START_YEAR, hourly_years
    )
    _fetch_years(
        years=h_years,
        discovered=hourly_discovered,
        fallback=HOURLY_FALLBACK_URLS,
        path_fn=_hourly_year_path,
        manifest_key="hourly",
        look_for=("PLD_HORA", "SUBMERCADO", "HORA"),
    )


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


def _strip_cell(s: str) -> str:
    return str(s).strip().strip('"').strip()


def _compose_hourly_date(mes: str, dia: str) -> pd.Timestamp:
    """Build a calendar date from MES_REFERENCIA (YYYYMM) + DIA.

    Current yearly files store DIA as the day-of-month (``11`` or ``01``).
    Older vintages sometimes quote it. A full ``DD/MM/YYYY`` is accepted
    as a fallback, matching the daily-average files.
    """
    mes = _strip_cell(mes)
    dia = _strip_cell(dia)
    if "/" in dia:
        return pd.to_datetime(dia, dayfirst=True, errors="coerce")
    digits = "".join(ch for ch in mes if ch.isdigit())
    if len(digits) >= 6 and dia.isdigit():
        return pd.to_datetime(f"{digits[:4]}-{digits[4:6]}-{int(dia):02d}", errors="coerce")
    return pd.NaT


def _read_hourly_csv(path: Path) -> pd.DataFrame:
    """Read one yearly CCEE hourly PLD CSV into tidy rows."""
    df = pd.read_csv(
        path,
        sep=";",
        encoding="latin-1",
        dtype=str,
        engine="python",
    )
    cols = {c.strip().strip('"').upper(): c for c in df.columns}
    need = ["SUBMERCADO", "MES_REFERENCIA", "DIA", "HORA", "PLD_HORA"]
    for n in need:
        if n not in cols:
            raise ValueError(f"{path.name}: missing column {n}; got {list(df.columns)}")
    raw_sm = df[cols["SUBMERCADO"]].map(_strip_cell).str.upper()
    mes = df[cols["MES_REFERENCIA"]].map(_strip_cell)
    dia = df[cols["DIA"]].map(_strip_cell)
    hora = df[cols["HORA"]].map(_strip_cell)
    pld_raw = df[cols["PLD_HORA"]].map(_strip_cell)
    dates = [_compose_hourly_date(m, d) for m, d in zip(mes.tolist(), dia.tolist())]
    cleaned = pld_raw.str.replace(r"\s+", "", regex=True).str.replace(",", ".", regex=False)
    out = pd.DataFrame({
        "date": pd.to_datetime(dates, errors="coerce"),
        "hour": pd.to_numeric(hora, errors="coerce"),
        "submarket": raw_sm.map(SUBMARKET_MAP),
        "pld": pd.to_numeric(cleaned, errors="coerce"),
    })
    out = out.dropna(subset=["date", "hour", "pld", "submarket"])
    out["hour"] = out["hour"].astype(int)
    out = out[(out["hour"] >= 0) & (out["hour"] <= 23)]
    out["pld"] = out["pld"].astype(float).round(4)
    out = out[["date", "hour", "submarket", "pld"]]
    return out


def _health_lag_days(last) -> int:
    return (pd.Timestamp.now("UTC").date() - pd.Timestamp(last).date()).days


def _shared_imports():
    sys.path.insert(0, str(HERE.parent / "shared"))
    import data_kit as dk  # noqa: E402
    import schemas  # noqa: E402
    import transforms as xf  # noqa: E402
    return dk, schemas, xf


def build_daily() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_DIR.glob("pld_media_diaria_*.csv"))
    if not files:
        raise SystemExit(
            f"No raw daily CSVs in {RAW_DIR}. Run `python pld_pipeline.py fetch` "
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
        raise SystemExit("Daily build produced zero rows")
    dk, schemas, xf = _shared_imports()
    problems = []
    missing_sm = set(SUBMARKET_MAP.values()) - set(df["submarket"].unique())
    if missing_sm:
        problems.append(f"missing submarkets: {sorted(missing_sm)}")
    last = df["date"].max()
    lag_days = _health_lag_days(last)
    if lag_days > xf.PLD_MAX_LAG_DAYS:
        problems.append(
            f"latest date {pd.Timestamp(last).date()} is {lag_days} days behind UTC today"
        )
    if problems:
        print("HEALTH GATE FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    df.to_parquet(PARQUET_PATH, index=False)
    print(
        f"Wrote {PARQUET_PATH} ({len(df):,} rows, "
        f"{pd.Timestamp(df['date'].min()).date()} -> {pd.Timestamp(df['date'].max()).date()})"
    )
    schemas.validate_pld_daily(df)
    dk.publish("pld_daily", PARQUET_PATH)
    return df


def build_hourly() -> pd.DataFrame | None:
    """Build pld_hourly.parquet when yearly hourly CSVs are present.

    Returns the frame, or None when no hourly raw files exist (daily-only
    local rebuilds). Fails the process if files exist but produce no rows
    or fail the health gate — same bar as daily.
    """
    files = sorted(RAW_DIR.glob("pld_horario_*.csv"))
    if not files:
        print("  no pld_horario_*.csv; skipping hourly build")
        return None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for path in files:
        try:
            part = _read_hourly_csv(path)
            print(f"  {path.name}: {len(part):,} rows")
            frames.append(part)
        except Exception as e:
            print(f"  FAIL {path.name}: {e}")
            raise
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["date", "hour", "submarket"], keep="last")
    df = df.sort_values(["date", "hour", "submarket"]).reset_index(drop=True)
    if df.empty:
        raise SystemExit("Hourly build produced zero rows")
    dk, schemas, xf = _shared_imports()
    problems = []
    missing_sm = set(SUBMARKET_MAP.values()) - set(df["submarket"].unique())
    if missing_sm:
        problems.append(f"hourly missing submarkets: {sorted(missing_sm)}")
    last = df["date"].max()
    lag_days = _health_lag_days(last)
    if lag_days > xf.PLD_MAX_LAG_DAYS:
        problems.append(
            f"hourly latest date {pd.Timestamp(last).date()} is {lag_days} days behind UTC today"
        )
    hours = set(int(h) for h in df["hour"].unique())
    if len(hours) < 20:
        problems.append(f"hourly covers only {sorted(hours)} hours-of-day")
    if problems:
        print("HEALTH GATE FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    df.to_parquet(HOURLY_PARQUET_PATH, index=False)
    print(
        f"Wrote {HOURLY_PARQUET_PATH} ({len(df):,} rows, "
        f"{pd.Timestamp(df['date'].min()).date()} -> {pd.Timestamp(df['date'].max()).date()})"
    )
    schemas.validate_pld_hourly(df)
    dk.publish("pld_hourly", HOURLY_PARQUET_PATH)
    return df


def build() -> pd.DataFrame:
    daily = build_daily()
    build_hourly()
    return daily


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "build", "all"])
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        help="Limit daily fetch to these years (default: all discovered ≥ 2021)",
    )
    parser.add_argument(
        "--hourly-years",
        type=int,
        nargs="+",
        help="Limit hourly fetch to these years (default: all discovered ≥ 2024)",
    )
    args = parser.parse_args(argv)
    if args.command in ("fetch", "all"):
        print("Fetching CCEE PLD yearly CSVs…")
        fetch(years=args.years, hourly_years=args.hourly_years)
    if args.command in ("build", "all"):
        print("Building pld_daily.parquet…")
        build_daily()
        print("Building pld_hourly.parquet…")
        build_hourly()


if __name__ == "__main__":
    main()
