"""
Oferta de Capacidade "Contratos" (gas transport contracts) pipeline.

Fetches Brazilian gas-pipeline transport contract data from the Portal de
Oferta de Capacidade's GraphQL API, covering the two confirmed contract
families:

  - "Contrato de Transporte": tipoContrato PEDIDO / PEDIDO_LEILAO,
    statusContrato ATIVO / CONCLUIDO -- individual transport contracts and
    their amendments (pedidoComAditivo).
  - "Contrato Master": tipoContrato CONTRATO MASTER DE TRANSPORTE,
    statusContrato HABILITADO -- master transport contracts.

Two smaller categories visible on the site's own UI -- "Contrato de
Transporte Legado" and "Conexão de Acesso" -- are NOT served by this
GraphQL resolver. This was confirmed by exhaustively querying
`contratosCarregador` across every value its statusContrato enum accepts
(there are only three: ATIVO, CONCLUIDO, HABILITADO -- both non-HABILITADO
values are covered by the "transporte" branch below) and by introspecting
the full GraphQL schema (33 types total, nothing named legado/conexão/
acesso). That data comes from a different, not-yet-identified endpoint and
is not included here yet -- see the project README.

API:  https://ofertadecapacidade.com.br/v2/api/graphql
Site: https://ofertadecapacidade.com.br/home/contratos

Usage:
    python contratos_pipeline.py fetch   # pulls raw JSON to data/raw_contratos.json
    python contratos_pipeline.py build   # transforms raw JSON -> data/contratos.parquet
    python contratos_pipeline.py all     # fetch + build
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd

GRAPHQL_URL = "https://ofertadecapacidade.com.br/v2/api/graphql"

QUERY = """query getContratos($idTso: [Int], $idCarregador: Int, $tipoContrato: [String], $statusContrato: [StatusContrato], $idProduto: Int, $idCarregadorPrincipal: Int) {
  contratosCarregador(
    idTso: $idTso
    idCarregador: $idCarregador
    tipoContrato: $tipoContrato
    statusContrato: $statusContrato
    idProduto: $idProduto
    idCarregadorPrincipal: $idCarregadorPrincipal
  ) {
    idTso
    nomeCarregador
    dataInicio
    dataFim
    tipoContrato
    numeroPedido
    tipoProduto
    nomePontoZona
    fluxoPontoZona
    statusContrato
    pedidoComAditivo
    relacaoAcionariaTransportadora
    nomeQualidade
    nrCapacidade
    vlTarifaAlocada
    vlMultiplicador
    __typename
  }
}"""

# Two confirmed request "shapes" -- statusContrato is a 3-value GraphQL enum
# (ATIVO, CONCLUIDO, HABILITADO) and it alone determines which family of rows
# comes back. tipoContrato IS a real filter arg on top of that, but passing an
# empty list ([], not null -- null crashes the resolver) means "no filter", so
# each call below returns every row for that family. See project memory
# (api-research.md, or ask Eric) for how this was reverse-engineered directly
# against the live API (schema introspection + controlled test queries), not
# guessed from the UI.
BRANCHES = {
    "transporte": ["ATIVO", "CONCLUIDO"],
    "master": ["HABILITADO"],
}

TSO_NAMES = {"1": "TBG", "2": "TAG", "3": "NTS"}

# Display values below are English translations of what the API returns --
# CONTRACT_CATEGORY_MAP's *keys* (tipoContrato) and BRANCHES' values
# (statusContrato) above are the API's own enum vocabulary and must stay
# as-is; only the right-hand display strings are ours to translate.
CONTRACT_CATEGORY_MAP = {
    "PEDIDO": "Transport Contract",
    "PEDIDO_LEILAO": "Transport Contract (Auction)",
    "CONTRATO MASTER DE TRANSPORTE": "Master Contract",
}

# statusContrato as returned in each row (not the query-filter enum above) is
# a Portuguese human-readable label, not the plain ATIVO/CONCLUIDO/HABILITADO
# code -- translate it too.
STATUS_MAP = {
    "Ativo": "Active",
    "Concluído": "Concluded",
    "Contrato Master Habilitado": "Master Contract Enabled",
}

PRODUCT_TYPE_MAP = {
    "Diário": "Daily",
    "Anual Extraordinário": "Extraordinary Annual",
    "Flexível Anual": "Flexible Annual",
    "Mensal": "Monthly",
    "Oferta Anual": "Annual Offer",
    "Trimestral": "Quarterly",
    "Interruptível": "Interruptible",
    "Longo Prazo": "Long Term",
}

QUALITY_MAP = {
    "Livre": "Free",
    "Restrita": "Restricted",
}

FLOW_MAP = {"Entrada": "Entry", "Saída": "Exit", "Saida": "Exit"}

NUMERIC_DASH_COLS = [
    "relacaoAcionariaTransportadora", "nrCapacidade", "vlTarifaAlocada", "vlMultiplicador",
]
STRING_DASH_COLS = ["tipoProduto", "nomePontoZona", "nomeQualidade"]

DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "raw_contratos.json"
PARQUET_PATH = DATA_DIR / "contratos.parquet"

HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/plain, */*",
    "User-Agent": "poc-contratos-pipeline/1.0 (+https://poc2.gasbrazil.com)",
}


def fetch_branch(status_contrato, max_retries=4, sleep_between=1.5):
    """POST one getContratos call for a given statusContrato list. Raises after
    exhausting retries; the empty-tipoContrato convention is explained above."""
    body = {
        "operationName": "getContratos",
        "variables": {
            "idTso": [1, 2, 3],
            "idCarregador": None,
            "tipoContrato": [],
            "statusContrato": status_contrato,
            "idProduto": None,
        },
        "query": QUERY,
    }
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(GRAPHQL_URL, data=data, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL errors for status={status_contrato}: {payload['errors']}")
            rows = payload.get("data", {}).get("contratosCarregador") if payload.get("data") else None
            if rows is None:
                raise RuntimeError(f"Empty/malformed response for status={status_contrato}: {payload}")
            return rows
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as e:
            last_err = e
            print(f"  attempt {attempt + 1}/{max_retries} failed: {e}", file=sys.stderr)
            time.sleep(sleep_between * (attempt + 1))
    raise RuntimeError(f"Failed to fetch status={status_contrato} after {max_retries} attempts: {last_err}")


def fetch_all():
    all_rows = []
    for name, status_list in BRANCHES.items():
        print(f"Fetching '{name}' branch (statusContrato={status_list}) ...")
        rows = fetch_branch(status_list)
        print(f"  {len(rows)} rows")
        all_rows.extend(rows)
        time.sleep(1.0)  # be polite between branch calls
    return all_rows


def cmd_fetch(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Fetching contract data from Oferta de Capacidade ...")
    rows = fetch_all()
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"Wrote {len(rows)} raw records to {RAW_PATH}")


def _to_num(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v in ("", "-"):
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_str_or_none(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return None if v in ("", "-") else v
    return v


def _translate_amendment(v):
    """pedidoComAditivo is 'Contrato de Transporte' (i.e. it repeats the raw
    category label) when a contract has no amendment, or 'Aditivo Nº <n>'
    when it does -- translate both shapes to English."""
    if v is None:
        return v
    if isinstance(v, str) and v.startswith("Aditivo Nº"):
        return "Amendment No." + v[len("Aditivo Nº"):]
    return CONTRACT_CATEGORY_MAP.get(v, v)


def transform(raw_rows):
    """Port of the field mapping/cleanup the dashboard needs: TSO id -> name,
    tipoContrato -> a readable category, '-' placeholders -> None, dates
    parsed, English column names AND English category/status/product-type/
    quality display values for the dashboard's display layer."""
    if not raw_rows:
        return pd.DataFrame()

    df = pd.DataFrame(raw_rows)

    tso_str = df["idTso"].astype(str)
    transporter = tso_str.map(TSO_NAMES)
    transporter = transporter.where(transporter.notna(), tso_str)

    category = df["tipoContrato"].map(CONTRACT_CATEGORY_MAP)
    category = category.where(category.notna(), df["tipoContrato"])

    status = df["statusContrato"].map(STATUS_MAP)
    status = status.where(status.notna(), df["statusContrato"])

    amendment = df["pedidoComAditivo"].map(_translate_amendment)
    is_amendment = df["pedidoComAditivo"].fillna("").str.startswith("Aditivo")

    start = pd.to_datetime(df["dataInicio"], errors="coerce")
    end = pd.to_datetime(df["dataFim"], errors="coerce")

    for col in NUMERIC_DASH_COLS:
        df[col] = df[col].map(_to_num)
    for col in STRING_DASH_COLS:
        df[col] = df[col].map(_to_str_or_none)

    product_type = df["tipoProduto"].map(PRODUCT_TYPE_MAP)
    product_type = product_type.where(product_type.notna(), df["tipoProduto"])

    quality = df["nomeQualidade"].map(QUALITY_MAP)
    quality = quality.where(quality.notna(), df["nomeQualidade"])

    flow = df["fluxoPontoZona"].map(FLOW_MAP)
    flow = flow.where(flow.notna(), df["fluxoPontoZona"])

    out = pd.DataFrame({
        "Transporter (TSO)": transporter,
        "Contract Number": df["numeroPedido"],
        "Contract Category": category,
        "Amendment": amendment,
        "Is Amendment": is_amendment,
        "Shipper": df["nomeCarregador"],
        "Start Date": start,
        "End Date": end,
        "Product Type": product_type,
        "Point/Zone": df["nomePontoZona"],
        "Flow": flow,
        "Status": status,
        "Quality": quality,
        "Contracted Capacity (000 m3/d)": df["nrCapacidade"],
        "Allocated Tariff (R$/MMBtu)": df["vlTarifaAlocada"],
        "Tariff Multiplier": df["vlMultiplicador"],
        "Transporter Ownership %": df["relacaoAcionariaTransportadora"],
    })

    out = out.sort_values(["Transporter (TSO)", "Contract Number"], kind="stable").reset_index(drop=True)
    return out


def cmd_build(args):
    if not RAW_PATH.exists():
        print(f"No raw data at {RAW_PATH} -- run 'fetch' first", file=sys.stderr)
        sys.exit(1)
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw_rows = json.load(f)

    df = transform(raw_rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)
    n_contracts = df["Contract Number"].nunique() if len(df) else 0
    print(f"Wrote {len(df)} rows ({n_contracts} distinct contract numbers) to {PARQUET_PATH}")

    # Basic integrity tripwires -- fail loudly rather than silently publish garbage.
    problems = []
    if len(df) == 0:
        problems.append("zero rows produced")
    elif df["Contract Number"].isna().any():
        problems.append("some rows missing Contract Number")
    elif df["Start Date"].isna().all():
        problems.append("Start Date entirely null")
    else:
        categories = set(df["Contract Category"].unique())
        expected = {"Transport Contract", "Master Contract"}
        if not expected <= categories:
            problems.append(f"expected categories missing: {sorted(expected - categories)}, got: {sorted(categories)}")
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
