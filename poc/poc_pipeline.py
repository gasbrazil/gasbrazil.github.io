"""
POC (Oferta de Capacidade) pipeline.

Fetches Brazilian natural gas transportadora balancing/linepack/GUS auction
results from the public "Portal de Oferta de Capacidade" API, replicates the
transform logic of the "Resultados (Includes Null)" Power Query from
POC Resultados.xlsx, and writes a tidy parquet store.

API: https://www.ofertadecapacidade.com.br/PEG/api/public/painel/oferta/resultado-processos
Site: https://www.ofertadecapacidade.com.br/PEG/resultado

Usage:
    python poc_pipeline.py fetch    # pulls raw JSON to data/raw_processos.json
    python poc_pipeline.py build    # transforms raw JSON -> data/poc_results.parquet
    python poc_pipeline.py all      # fetch + build
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd

BASE_URL = "https://www.ofertadecapacidade.com.br/PEG/api/public/painel/oferta/resultado-processos"
# Full history: the API has ~350-400 records total (as of 2026), so pulling
# the whole range every run is cheap and gives a complete rebuild each time
# (no incremental/delta logic needed).
DATA_INICIO = "2015-01-01"
DATA_FIM = "2030-12-31"
PAGE_SIZE = 100

DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "raw_processos.json"
PARQUET_PATH = DATA_DIR / "poc_results.parquet"

TRANSACTION_TYPE_MAP = {
    "Aquisição de GUS": "GUS Acquisition",
    "Balanceamento Residual": "Residual Balancing",
    "Balanceamento Operacional": "Operational Balancing",
    "Linepack": "Linepack",
}

SERVICE_TYPE_MAP = {
    "Transferência de titularidade": "Title Transfer",
    "Injeção física": "Physical Injection",
    "Retirada ou aumento da retirada no ponto de saída": "Withdrawal or Withdrawal Increase at the Delivery Point",
    "Redução no ponto de entrada": "Reduction at the Receipt Point",
}

FINAL_COLUMNS = [
    "Transporter (TSO)",
    "codigoProcesso",
    "Trade Date",
    "Flow Date Start",
    "Flow Date End",
    "Flow Days",
    "Trade Timing",
    "Start Service",
    "End Service",
    "Transaction Type",
    "Delivery Point",
    "Service Type",
    "Price",
    "Avg Process Price",
    "Volume Accepted",
    "Total Value",
    "Volume Offered",
    "Total Volume",
    "pcr",
]


def fetch_all(base_url=BASE_URL, data_inicio=DATA_INICIO, data_fim=DATA_FIM, page_size=PAGE_SIZE,
              max_retries=4, sleep_between=0.3):
    """Fetch every page of /resultado-processos and return the combined content list."""
    all_content = []
    page = 0
    total_pages = 1
    headers = {"User-Agent": "poc-dashboard-pipeline/1.0 (+https://poc.gasbrazil.com)"}
    while page < total_pages:
        url = f"{base_url}?dataInicio={data_inicio}&dataFim={data_fim}&size={page_size}&page={page}"
        last_err = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"Failed to fetch page {page} after {max_retries} attempts: {last_err}")

        processos = payload["processos"]
        total_pages = processos["totalPages"]
        all_content.extend(processos["content"])
        print(f"  fetched page {page + 1}/{total_pages} ({len(processos['content'])} records)")
        page += 1
        if sleep_between:
            time.sleep(sleep_between)

    return all_content


def cmd_fetch(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching POC results {DATA_INICIO}..{DATA_FIM} ...")
    content = fetch_all()
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False)
    print(f"Wrote {len(content)} raw records to {RAW_PATH}")


def _lookup_name(lst, id_field, id_value, name_field):
    if id_value is None or not lst:
        return None
    for item in lst:
        if item.get(id_field) == id_value:
            return item.get(name_field)
    return None


def _split_flow_date(periodo):
    """'dd/MM/yyyy - dd/MM/yyyy' -> (start_date, end_date) as pandas Timestamps, or (None, None)."""
    if not periodo or not isinstance(periodo, str) or len(periodo) < 21:
        return None, None
    start_txt = periodo[0:10]
    end_txt = periodo[-10:]
    try:
        start = pd.to_datetime(start_txt, format="%d/%m/%Y")
    except (ValueError, TypeError):
        start = None
    try:
        end = pd.to_datetime(end_txt, format="%d/%m/%Y")
    except (ValueError, TypeError):
        end = None
    return start, end


def _trade_timing(flow_date_start, trade_date):
    if pd.isna(flow_date_start) or pd.isna(trade_date):
        return "No Trade"
    diff = (flow_date_start.normalize() - trade_date.normalize()).days
    if diff == 0:
        return "Same Day"
    if diff == 1:
        return "Day Ahead"
    if diff > 1:
        return f"Forward ({diff}d)"
    return f"Prior Day ({abs(diff)}d)"


def transform(raw_content):
    """Port of the 'Resultados (Includes Null)' Power Query. One row per accepted bid;
    processes with no accepted bids get a single row with null bid fields."""
    rows = []
    for rec in raw_content:
        proposals = rec.get("propostasAceitas") or []
        if not proposals:
            proposals = [{
                "pontoZonaId": None, "volumeGas": None, "volumeAceito": None,
                "valor": None, "preco": None, "formaAtendimentoId": None,
            }]
        for p in proposals:
            delivery_point = _lookup_name(rec.get("pontoZonas"), "idPontoZona", p.get("pontoZonaId"), "nomePontoZona")
            service_type_raw = _lookup_name(rec.get("formaAtendimento"), "id", p.get("formaAtendimentoId"), "nome")
            rows.append({
                "Transporter (TSO)": rec.get("siglaTransportadora"),
                "codigoProcesso": rec.get("codigoProcesso"),
                "Trade Date": rec.get("dataValidade"),
                "Start Service": rec.get("inicioAtendimento"),
                "End Service": rec.get("fimAtendimento"),
                "Transaction Type": rec.get("finalidadeProcesso"),
                "Delivery Point": delivery_point,
                "Service Type": service_type_raw,
                "Price": p.get("preco"),
                "Avg Process Price": rec.get("precoMedioProcesso"),
                "Volume Accepted": p.get("volumeAceito") or 0,
                "Total Value": p.get("valor") or 0,
                "Volume Offered": p.get("volumeGas") or 0,
                "Total Volume": rec.get("volumeTotal") or 0,
                "pcr": rec.get("pcr"),
                "_periodo": rec.get("periodoAtendimentoTotal"),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=FINAL_COLUMNS)

    for col in ("Trade Date", "Start Service", "End Service"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce").dt.tz_localize(None)

    flow = df["_periodo"].apply(_split_flow_date)
    df["Flow Date Start"] = flow.apply(lambda t: t[0])
    df["Flow Date End"] = flow.apply(lambda t: t[1])
    df.drop(columns=["_periodo"], inplace=True)

    df["Trade Timing"] = df.apply(lambda r: _trade_timing(r["Flow Date Start"], r["Trade Date"]), axis=1)

    def flow_days(r):
        if pd.isna(r["Flow Date Start"]) or pd.isna(r["Flow Date End"]):
            return 0
        return (r["Flow Date End"] - r["Flow Date Start"]).days + 1

    df["Flow Days"] = df.apply(flow_days, axis=1)

    df["Transaction Type"] = df["Transaction Type"].map(lambda v: TRANSACTION_TYPE_MAP.get(v, v))

    def translate_service_type(v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        v = v.strip() if isinstance(v, str) else v
        return SERVICE_TYPE_MAP.get(v, v)

    df["Service Type"] = df["Service Type"].map(translate_service_type)

    df = df[FINAL_COLUMNS]
    return df


def cmd_build(args):
    if not RAW_PATH.exists():
        print(f"No raw data at {RAW_PATH} -- run 'fetch' first", file=sys.stderr)
        sys.exit(1)
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw_content = json.load(f)

    df = transform(raw_content)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)
    print(f"Wrote {len(df)} rows ({df['codigoProcesso'].nunique()} processes) to {PARQUET_PATH}")

    # Basic integrity tripwires -- fail loudly rather than silently publish garbage.
    problems = []
    if len(df) == 0:
        problems.append("zero rows produced")
    if df["codigoProcesso"].isna().any():
        problems.append("some rows missing codigoProcesso")
    if df["Trade Date"].isna().all():
        problems.append("Trade Date entirely null")
    if problems:
        print("HEALTH GATE FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("build")
    sub.add_parser("all")
    args = parser.parse_args()

    if args.cmd in ("fetch", "all"):
        cmd_fetch(args)
    if args.cmd in ("build", "all"):
        cmd_build(args)


if __name__ == "__main__":
    main()
