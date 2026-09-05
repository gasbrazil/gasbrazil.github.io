"""
Pipeline Flows pipeline.

Fetches ANP's (Agência Nacional do Petróleo, Gás Natural e Biocombustíveis)
monthly "movimentação de gás natural em gasodutos de transporte" CSVs --
daily physical flow at every receipt/delivery point on Brazil's gas
transport pipelines, plus pipeline-wide balancing entries (system-use gas,
losses, daily imbalance, linepack) -- and builds two tidy daily parquet
stores.

Source file (one per month, wide format: one row per pipeline/point/
shipper/contract/variable combination, one column per day of that month):
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/
    arquivos-movimentacao-de-gas-natural-em-gasodutos-de-transporte/<year>/
    gn_<month-pt>_<year>.csv
Landing page (for humans, not scraped -- file names are generated directly):
  https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/
    dados-consolidados-movimentacao-de-gas-natural-em-gasodutos-de-transporte

Two confirmed filename conventions coexist on the server: most months use
underscores (gn_junho_2026.csv), but 2021 and 2023 files were published with
hyphens instead (gn-junho-2023.csv), and one 2023 file (November) breaks that
year's own pattern and uses an underscore. `fetch` tries both separators for
every candidate month rather than assuming one. 2022 has no published files
at all (confirmed by exhaustive probing, not assumed) -- a real gap in ANP's
publication, not a bug in this pipeline.

Two output tables, because the source mixes two different granularities in
one file:
  - data/flows_points.parquet: point-level flow (Volume Solicitado/
    Programado/Realizado, Alocação %, Pressão Média), summed across shipper
    and contract per (point, variable, date) -- i.e. total physical
    throughput at that receipt/delivery point, not broken out by which
    shipper's gas it was.
  - data/flows_ledger.parquet: pipeline-wide balancing entries (Gás de Uso
    no Sistema, Gás não contado, Perdas Operacionais/Extraordinárias,
    Desequilíbrio Diário [Acumulado], Empacotamento), summed across
    shipper/contract per (pipeline, variable, date).
Shipper- and contract-level detail exists in the source but is discarded at
build time to keep the store and the dashboard's embedded payload a
reasonable size -- POC Contracts already covers shipper/contract-level
detail for capacity; this dashboard is about physical flow.

Usage:
    python flows_pipeline.py fetch    # download raw/gn_<month>_<year>.csv files
    python flows_pipeline.py build    # raw/*.csv -> data/flows_points.parquet + data/flows_ledger.parquet
    python flows_pipeline.py all      # fetch + build
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE_URL = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-movimentacao-de-gas-natural-em-gasodutos-de-transporte"

# First year any file has ever been found under this URL scheme (2021, some
# months only -- see module docstring). Probed once, kept as a fixed floor
# rather than re-discovered every run: cheap to keep, and if ANP ever
# republishes something older this is the one line to change.
CANDIDATE_START_YEAR = 2021
CANDIDATE_START_MONTH = 1

# Recent months get re-fetched every run even if already cached, because ANP
# revises recently-published data (confirmed in the metadata PDF: the
# Jan-Apr 2024 files were revised in place after a new TBG receiving point
# was added). Same rationale as ons-dashboard's "ONS revises recent days"
# handling, just at monthly granularity.
REFRESH_LAST_N_MONTHS = 3

MONTHS_PT = [
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
DATA_DIR = HERE / "data"
MANIFEST_PATH = RAW_DIR / "_manifest.json"
POINTS_PARQUET = DATA_DIR / "flows_points.parquet"
LEDGER_PARQUET = DATA_DIR / "flows_ledger.parquet"

HEADERS = {"User-Agent": "gasbrazil-flows-pipeline/1.0 (+https://gasbrazil.com/flows/)"}

# ---------------------------------------------------------------------------
# Column names as ANP publishes them (stable across years -- checked against
# sample files from 2024, 2025, 2026 during development). The 13 metadata
# columns always come first; every column after them is a day-of-month date
# column (DD/MM/YYYY), varying in count with the month's length.
# ---------------------------------------------------------------------------
COL_TRANSP_CODE = "Código da Instalação de Transporte"
COL_TRANSP_NAME = "Nome da Instalação de Transporte"
COL_POINT_NAME = "Nome da Instalação de Gasoduto"
COL_POINT_CODE = "Código da Instalação de Gasoduto"
COL_POINT_TYPE = "Tipo da instalação de Gasoduto"
COL_MUNICIPALITY = "Nome do Município da Instalação de Gasoduto"
COL_UF = "Nome da UF da Instalação de Gasoduto"
COL_OPERATOR = "Nome do Operador da instalação de Gasoduto"
COL_SHIPPER = "Nome do Carregador que usa a Instalação de Gasoduto"
COL_CONTRACT = "Nome do Contrato da Instalação de Gasoduto"
COL_VARIABLE = "Nome da Variável"

META_COLS = [
    COL_TRANSP_CODE, COL_TRANSP_NAME, COL_POINT_NAME, COL_POINT_CODE, COL_POINT_TYPE,
    COL_MUNICIPALITY, COL_UF, COL_OPERATOR, "Código do Operador da Instalação de Gasoduto",
    COL_SHIPPER, "Código do Carregador que usa a Instalação de Gasoduto", COL_CONTRACT, COL_VARIABLE,
]

# Point-level variables: recorded per (pipeline, point, shipper, contract).
# Summed across shipper/contract at build time -> total flow at that point.
POINT_VARIABLES_EN = {
    "Volume Solicitado (mil m³)": "Volume Requested (thousand m3)",
    "Volume Programado (mil m³)": "Volume Scheduled (thousand m3)",
    "Volume Realizado (mil m³)": "Volume Realized (thousand m3)",
    "Alocação (%)": "Allocation (%)",
    "Pressão Média (kgf/cm²)": "Average Pressure (kgf/cm2)",
}

# Pipeline-wide ledger variables: recorded per (pipeline, shipper, contract),
# no specific point. Summed across shipper/contract -> pipeline-wide total.
LEDGER_VARIABLES_EN = {
    "Gás de Uso no Sistema (mil m³)": "System Use Gas (thousand m3)",
    "Gás não contado (mil m³)": "Unaccounted-for Gas (thousand m3)",
    "Perdas Operacionais (mil m³)": "Operational Losses (thousand m3)",
    "Perdas Extraordinárias (mil m³)": "Extraordinary Losses (thousand m3)",
    "Desequilíbrio Diário (mil m³)": "Daily Imbalance (thousand m3)",
    "Desequilíbrio Diário Acumulado (mil m³)": "Cumulative Daily Imbalance (thousand m3)",
    "Empacotamento (mil m³)": "Linepack (thousand m3)",
}

POINT_TYPE_EN = {
    "Ponto de Recebimento": "Receipt Point",
    "Ponto de Entrega": "Delivery Point",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# 2021 files (see module docstring) name variables without the unit suffix
# ("Volume Solicitado" instead of "Volume Solicitado (mil m³)") and with one
# confirmed typo ("Desequilibrio Diário", missing the accent on the i). Build
# a case-insensitive lookup from every plausible raw spelling -> the
# canonical Portuguese key used in POINT_VARIABLES_EN / LEDGER_VARIABLES_EN,
# so 2021's data isn't silently dropped over formatting drift.
def _variable_key(raw: str) -> str:
    return " ".join(raw.split()).casefold()


_ALL_VARIABLES = {**POINT_VARIABLES_EN, **LEDGER_VARIABLES_EN}
_VARIABLE_ALIASES = {_variable_key(k): k for k in _ALL_VARIABLES}
for _canonical in _ALL_VARIABLES:
    _no_unit = _canonical.rsplit(" (", 1)[0]  # "Volume Solicitado (mil m³)" -> "Volume Solicitado"
    _VARIABLE_ALIASES.setdefault(_variable_key(_no_unit), _canonical)
_VARIABLE_ALIASES[_variable_key("Desequilibrio Diário")] = "Desequilíbrio Diário (mil m³)"


def _canonicalize_variable(raw):
    if not isinstance(raw, str):
        return None
    return _VARIABLE_ALIASES.get(_variable_key(raw), raw)


def tso_from_operator(operator_name: str | None) -> str | None:
    """'Nova Transportadora do Sudeste S.A. - NTS' -> 'NTS'. The operator
    name always ends with ' - <SHORT CODE>' in the source data; falls back
    to the full name if that pattern isn't found (defensive, not expected
    to trigger against real data)."""
    if not operator_name or not isinstance(operator_name, str):
        return None
    if " - " in operator_name:
        return operator_name.rsplit(" - ", 1)[1].strip()
    return operator_name.strip()


def month_range(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_manifest(manifest: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _try_download(url: str, dest: Path, max_retries: int = 3, sleep_between: float = 1.0) -> bool:
    """GET url -> dest. Returns True on success (200), False on a real 404
    (file not published), raises after exhausting retries on anything else
    (network hiccup, 5xx, etc.) so a transient failure doesn't silently look
    like 'not published'."""
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                dest.write_bytes(resp.read())
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            last_err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        time.sleep(sleep_between * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_err}")


def cmd_fetch(args) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    today = pd.Timestamp.today()
    end_year, end_month = today.year, today.month

    months = list(month_range(CANDIDATE_START_YEAR, CANDIDATE_START_MONTH, end_year, end_month))
    recent_cutoff = set(months[-REFRESH_LAST_N_MONTHS:]) if not args.force else set(months)

    fetched, skipped_cached, not_published, failed = 0, 0, 0, []
    for y, m in months:
        month_pt = MONTHS_PT[m - 1]
        dest = RAW_DIR / f"gn_{month_pt}_{y}.csv"
        key = f"{y}-{m:02d}"

        if dest.exists() and (y, m) not in recent_cutoff:
            skipped_cached += 1
            continue

        known_sep = manifest.get(key, {}).get("sep")
        seps_to_try = [known_sep] + [s for s in ("_", "-") if s != known_sep] if known_sep else ["_", "-"]

        found = False
        for sep in seps_to_try:
            url = f"{BASE_URL}/{y}/gn{sep}{month_pt}{sep}{y}.csv"
            try:
                if _try_download(url, dest):
                    manifest[key] = {"sep": sep, "url": url}
                    fetched += 1
                    found = True
                    print(f"  fetched {key}: {url}")
                    break
            except RuntimeError as e:
                failed.append((key, str(e)))
        if not found and not any(k == key for k, _ in failed):
            not_published += 1
            manifest.pop(key, None)
            if dest.exists():
                dest.unlink()  # was published before, isn't now -- don't keep stale data under a valid-looking filename
        time.sleep(0.15)

    _save_manifest(manifest)
    print(
        f"Fetch complete: {fetched} downloaded, {skipped_cached} cached, "
        f"{not_published} not published, {len(failed)} failed."
    )
    if failed:
        for key, err in failed:
            print(f"  FAILED {key}: {err}", file=sys.stderr)
        # A handful of transient failures shouldn't fail the whole run (next
        # scheduled fetch will retry them); only fail loudly if MOST months
        # that should exist failed, which points at something systemic.
        if len(failed) > max(3, len(months) // 10):
            print("Too many failures -- treating as a systemic problem.", file=sys.stderr)
            sys.exit(2)


import re

# Number formatting is NOT consistent across monthly files: some (e.g. most
# 2026 files) parse cleanly with pandas' decimal="," straight away; others
# (e.g. Dec 2024) pad every value with stray leading/trailing spaces and
# write a negative as "- 1234,56" (a space between the minus sign and the
# digits) rather than "-1234,56", which breaks decimal="," silently -- the
# whole column falls back to a string dtype and groupby.sum() then
# concatenates strings instead of summing, corrupting the data without
# raising an error. So every value is read as a string and explicitly
# cleaned here rather than trusting read_csv's numeric inference.
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _clean_numeric(raw: str):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if s == "" or s == "-":
        return None
    s = s.replace(" ", "")  # "- 1234,56" -> "-1234,56"
    if "," in s:
        # "," is always the decimal separator here; "." (when present) is a
        # thousands separator and gets dropped.
        s = s.replace(".", "").replace(",", ".")
    if not _NUMERIC_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_col(name: str) -> str:
    """Case/whitespace-insensitive key for matching metadata column headers
    across the source's own inconsistent capitalization -- e.g. 2021's
    'Tipo da Instalação do Gasoduto' vs. later years' 'Tipo da instalação de
    Gasoduto' (capital I, 'do' vs 'de'). Accents are left alone: they're
    consistent enough across years that stripping them risks a false match
    between genuinely different fields."""
    return " ".join(name.split()).casefold()


_META_COL_ALIASES = {_normalize_col(c): c for c in META_COLS}
# 2021 files (the earliest available -- see module docstring) use "do
# Gasoduto" instead of "de Gasoduto" for these two columns, on top of the
# capitalization differences the case/whitespace-insensitive match above
# already handles. Confirmed directly against a 2021 raw file, not guessed.
_META_COL_ALIASES[_normalize_col("Tipo da Instalação do Gasoduto")] = COL_POINT_TYPE
_META_COL_ALIASES[_normalize_col("Nome do Contrato da Instalação do Gasoduto")] = COL_CONTRACT


def _read_month_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="latin1", dtype=str)
    rename = {}
    for actual in df.columns:
        canonical = _META_COL_ALIASES.get(_normalize_col(actual))
        if canonical and canonical != actual:
            rename[actual] = canonical
    if rename:
        df = df.rename(columns=rename)
    missing = [c for c in META_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing expected columns {missing}")
    date_cols = [c for c in df.columns if c not in META_COLS]
    for c in date_cols:
        df[c] = df[c].map(_clean_numeric)
    return df, date_cols


def _melt_month(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    long_df = df.melt(id_vars=META_COLS, value_vars=date_cols, var_name="date_str", value_name="value")
    # Zero is kept, not filtered out: for Volume Realizado a zero is a real,
    # meaningful "this point wasn't flowing that day" -- exactly the signal
    # a pricing/flows dashboard exists to show. Only genuinely missing cells
    # (NaN -- the point/variable combo wasn't reported that day at all) are
    # dropped, so "no data" and "zero flow" stay distinguishable downstream.
    long_df = long_df.dropna(subset=["value"])
    long_df[COL_VARIABLE] = long_df[COL_VARIABLE].map(_canonicalize_variable)
    long_df["date"] = pd.to_datetime(long_df["date_str"], format="%d/%m/%Y", errors="coerce")
    long_df = long_df.dropna(subset=["date"])
    return long_df


def build_tables(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    csv_files = sorted(raw_dir.glob("gn_*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No raw CSVs in {raw_dir} -- run 'fetch' first")

    point_frames, ledger_frames = [], []
    for path in csv_files:
        try:
            df, date_cols = _read_month_csv(path)
        except ValueError as e:
            print(f"  SKIPPING {path.name}: {e}", file=sys.stderr)
            continue
        long_df = _melt_month(df, date_cols)
        if long_df.empty:
            continue

        is_point_var = long_df[COL_VARIABLE].isin(POINT_VARIABLES_EN)
        is_ledger_var = long_df[COL_VARIABLE].isin(LEDGER_VARIABLES_EN)

        pts = long_df[is_point_var & long_df[COL_POINT_CODE].notna() & (long_df[COL_POINT_CODE] != "")]
        if not pts.empty:
            point_frames.append(pts)

        led = long_df[is_ledger_var]
        if not led.empty:
            ledger_frames.append(led)

        print(f"  parsed {path.name}: {len(pts)} point rows, {len(led)} ledger rows (after zero/blank filtering)")

    points_long = pd.concat(point_frames, ignore_index=True) if point_frames else pd.DataFrame()
    ledger_long = pd.concat(ledger_frames, ignore_index=True) if ledger_frames else pd.DataFrame()

    points_df = _aggregate_points(points_long)
    ledger_df = _aggregate_ledger(ledger_long)
    return points_df, ledger_df


def _aggregate_points(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return pd.DataFrame(columns=[
            "date", "point_code", "point_name", "point_type", "pipeline_code", "pipeline_name",
            "municipality", "uf", "tso", "variable", "value",
        ])
    # Volume Solicitado/Programado/Realizado and Alocação are genuine
    # per-shipper splits at a point -- confirmed directly (different
    # shippers at the same point on the same day carry different, non-zero
    # values, and Alocação's per-shipper shares add to ~100%) -- so summing
    # across shipper/contract gives the point's true total. Pressão Média is
    # different: it's a single physical reading broadcast identically onto
    # every shipper row at that point (confirmed directly, same value
    # repeated across 16 shippers), so it uses median instead of sum for the
    # same reason flows_ledger's pipeline-wide variables do -- summing it
    # would multiply a real pressure reading by however many shippers were
    # active that day.
    is_broadcast = long_df[COL_VARIABLE] == "Pressão Média (kgf/cm²)"
    summed = (
        long_df[~is_broadcast]
        .groupby([COL_POINT_CODE, COL_VARIABLE, "date"], as_index=False)["value"].sum()
    )
    medianed = (
        long_df[is_broadcast]
        .groupby([COL_POINT_CODE, COL_VARIABLE, "date"], as_index=False)["value"].median()
    )
    grouped = pd.concat([summed, medianed], ignore_index=True)
    # Metadata is (almost always) constant per point code; take the most
    # recently seen row per point as the canonical label/location/operator
    # (a point occasionally gets a cleaner name or corrected municipality in
    # a later month -- most recent wins over first-seen).
    meta = (
        long_df.sort_values("date")
        .drop_duplicates(subset=[COL_POINT_CODE], keep="last")
        [[COL_POINT_CODE, COL_POINT_NAME, COL_POINT_TYPE, COL_TRANSP_CODE, COL_TRANSP_NAME,
          COL_MUNICIPALITY, COL_UF, COL_OPERATOR]]
    )
    out = grouped.merge(meta, on=COL_POINT_CODE, how="left")
    out["tso"] = out[COL_OPERATOR].map(tso_from_operator)
    out["variable"] = out[COL_VARIABLE].map(POINT_VARIABLES_EN)
    out["point_type"] = out[COL_POINT_TYPE].map(POINT_TYPE_EN)
    out = out.rename(columns={
        COL_POINT_CODE: "point_code", COL_POINT_NAME: "point_name",
        COL_TRANSP_CODE: "pipeline_code", COL_TRANSP_NAME: "pipeline_name",
        COL_MUNICIPALITY: "municipality", COL_UF: "uf",
    })[[
        "date", "point_code", "point_name", "point_type", "pipeline_code", "pipeline_name",
        "municipality", "uf", "tso", "variable", "value",
    ]]
    return out.sort_values(["pipeline_name", "point_name", "variable", "date"]).reset_index(drop=True)


def _aggregate_ledger(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return pd.DataFrame(columns=["date", "pipeline_code", "pipeline_name", "tso", "variable", "value"])
    # NOT a sum: these ledger variables are published as one pipeline-wide
    # total, broadcast identically onto every shipper/contract row active on
    # that pipeline that day (confirmed directly -- e.g. GASBEL's "Gás de
    # Uso no Sistema" carried the exact same value across all 16 of its
    # shippers on a given date). Summing across shipper/contract like the
    # point-level table does would multiply the true total by however many
    # shippers happened to be active, inflating it by 10-20x. median() is
    # robust to the rare row that's missing/differs while collapsing back to
    # that one real total the rest of the time.
    grouped = (
        long_df.groupby([COL_TRANSP_CODE, COL_VARIABLE, "date"], as_index=False)["value"].median()
    )
    meta = (
        long_df.sort_values("date")
        .drop_duplicates(subset=[COL_TRANSP_CODE], keep="last")
        [[COL_TRANSP_CODE, COL_TRANSP_NAME, COL_OPERATOR]]
    )
    out = grouped.merge(meta, on=COL_TRANSP_CODE, how="left")
    out["tso"] = out[COL_OPERATOR].map(tso_from_operator)
    out["variable"] = out[COL_VARIABLE].map(LEDGER_VARIABLES_EN)
    out = out.rename(columns={COL_TRANSP_CODE: "pipeline_code", COL_TRANSP_NAME: "pipeline_name"})[[
        "date", "pipeline_code", "pipeline_name", "tso", "variable", "value",
    ]]
    return out.sort_values(["pipeline_name", "variable", "date"]).reset_index(drop=True)


def cmd_build(args) -> None:
    points_df, ledger_df = build_tables()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    points_df.to_parquet(POINTS_PARQUET, index=False)
    ledger_df.to_parquet(LEDGER_PARQUET, index=False)
    print(f"Wrote {len(points_df):,} rows ({points_df['point_code'].nunique() if len(points_df) else 0} points) to {POINTS_PARQUET}")
    print(f"Wrote {len(ledger_df):,} rows ({ledger_df['pipeline_code'].nunique() if len(ledger_df) else 0} pipelines) to {LEDGER_PARQUET}")

    # Health gate -- fail loudly rather than silently publish a broken/empty dashboard.
    problems = []
    if len(points_df) == 0:
        problems.append("zero point-level rows produced")
    if len(ledger_df) == 0:
        problems.append("zero ledger rows produced")
    if len(points_df):
        latest = points_df["date"].max()
        # Monthly publication with a multi-week lag (see README) -- flag if
        # the newest data we have is implausibly old, not just "not today".
        staleness_days = (pd.Timestamp.today().normalize() - latest).days
        if staleness_days > 75:
            problems.append(f"latest point data is {staleness_days} days old ({latest.date()})")
        if points_df["point_code"].isna().any():
            problems.append("some rows missing point_code")
    if problems:
        print("HEALTH GATE FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--force", action="store_true", help="re-download every month, ignoring the local cache")
    sub.add_parser("build")
    p_all = sub.add_parser("all")
    p_all.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.cmd in ("fetch", "all"):
        cmd_fetch(args)
    if args.cmd in ("build", "all"):
        cmd_build(args)


if __name__ == "__main__":
    main()
