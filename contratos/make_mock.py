"""
Generates synthetic Oferta de Capacidade contract data, shaped exactly like
the raw GraphQL rows contratos_pipeline.py's `fetch` writes to
data/raw_contratos.json, so `build` and the dashboard can be exercised
offline without hitting the live API.

Usage: python make_mock.py
"""
import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "raw_contratos.json"

random.seed(7)

SHIPPERS = [
    "PETRÓLEO BRASILEIRO S.A. – PETROBRAS", "Galp Energia Brasil S.A.", "Shell Energy do Brasil Gas LTDA",
    "Compass Comercialização S.A.", "Vibra Energia S.A.", "ENEVA COMERCIALIZADORA DE ENERGIA",
    "J&F S.A.", "PROQUIGEL QUÍMICA S.A.", "PetroReconcavo", "Potiguar E&P",
    "Companhia de Gás de Santa Catarina", "Tradener Ltda.", "GAS BRIDGE COMERCIALIZADORA S.A.",
]
POINTS = ["BA4", "MG1", "RJ2", "SP3", "SC1", "SP1", "SP2", "SP4", "BA3", "BA5", "PB", "Guamaré", "EMED GASCAR"]
PRODUCTS = ["Longo Prazo", "Anual Extraordinário", "Flexível Anual", "Mensal"]
QUALITIES = ["Restrita", "Livre", None]
FLOWS = ["Entrada", "Saída"]
ADITIVOS = [None, None, None, "1", "2", "3", "MGA", "SHE", "ENE"]


def rand_date(y0, y1):
    y = random.randint(y0, y1)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d} 00:00:00.0"


def make_transporte_row(i):
    tso = random.choice([1, 2, 3])
    start = rand_date(2021, 2026)
    end_year = int(start[:4]) + random.randint(0, 4)
    end = f"{end_year:04d}-12-31 23:59:00.0"
    aditivo = random.choice(ADITIVOS)
    return {
        "idTso": str(tso),
        "nomeCarregador": random.choice(SHIPPERS),
        "dataInicio": start,
        "dataFim": end,
        "tipoContrato": "PEDIDO_LEILAO" if random.random() < 0.02 else "PEDIDO",
        "numeroPedido": f"CLP{1000 + i}{random.choice(POINTS)[:2].upper()}-S{end_year}-MCK",
        "tipoProduto": random.choice(PRODUCTS),
        "nomePontoZona": random.choice(POINTS),
        "fluxoPontoZona": random.choice(FLOWS),
        "statusContrato": random.choice(["Ativo", "Concluído"]),
        "pedidoComAditivo": f"Aditivo Nº {aditivo}" if aditivo else "Contrato de Transporte",
        "relacaoAcionariaTransportadora": 0.0,
        "nomeQualidade": random.choice(QUALITIES) or "-",
        "nrCapacidade": f"{round(random.uniform(1, 3000), 2)}",
        "vlTarifaAlocada": f"{round(random.uniform(0.5, 7.5), 4)}",
        "vlMultiplicador": f"{round(random.choice([1.0, 1.0, 1.0, 0.85]), 4)}",
        "__typename": "ContratosCarregador",
    }


def make_master_row(i):
    tso = random.choice([1, 2, 3])
    start = "2024-01-01 00:00:00.0"
    return {
        "idTso": str(tso),
        "nomeCarregador": random.choice(SHIPPERS),
        "dataInicio": start,
        "dataFim": "2028-12-31 23:59:00.0",
        "tipoContrato": "CONTRATO MASTER DE TRANSPORTE",
        "numeroPedido": f"MASTER-POC-{'TBG' if tso == 1 else 'TAG' if tso == 2 else 'NTS'}-{100 + i}",
        "tipoProduto": None,
        "nomePontoZona": None,
        "fluxoPontoZona": None,
        "statusContrato": "Contrato Master Habilitado",
        "pedidoComAditivo": "Contrato de Transporte",
        "relacaoAcionariaTransportadora": 0.0,
        "nomeQualidade": "-",
        "nrCapacidade": "-",
        "vlTarifaAlocada": "-",
        "vlMultiplicador": "-",
        "__typename": "ContratosCarregador",
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = [make_transporte_row(i) for i in range(300)] + [make_master_row(i) for i in range(40)]
    random.shuffle(rows)
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"Wrote {len(rows)} mock records to {RAW_PATH}")


if __name__ == "__main__":
    main()
