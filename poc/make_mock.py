"""Generates data/raw_processos.json with synthetic-but-realistic records for local
testing without hitting the live API. Field shapes match real API responses
inspected on 2026-08-27 (see dashboard-changes.md)."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

PONTO_ZONAS = [
    {"idPontoZona": 22, "nomePontoZona": "AL"},
    {"idPontoZona": 23, "nomePontoZona": "SE"},
    {"idPontoZona": 25, "nomePontoZona": "BA3"},
    {"idPontoZona": 31, "nomePontoZona": "RJ"},
    {"idPontoZona": 3, "nomePontoZona": "TECAB"},
    {"idPontoZona": 5, "nomePontoZona": "Cacimbas"},
]

FORMA_ATENDIMENTO = [
    {"id": 1, "nome": "Redução no ponto de entrada"},
    {"id": 2, "nome": "Retirada ou aumento da retirada no ponto de saída"},
    {"id": 3, "nome": "Transferência de titularidade"},
    {"id": 4, "nome": "Injeção física"},
]

records = [
    # Normal single accepted bid
    {
        "nomeTransportadora": "Transportadora Associada de Gás", "siglaTransportadora": "TAG",
        "codigoProcesso": "TAG-PC-0212/2026", "categoria": "V",
        "validade": "2026-08-26T11:00:59.000+00:00", "inicioAtendimento": "2026-08-26T15:00:00.000+00:00",
        "fimAtendimento": "2026-08-27T02:59:00.000+00:00", "dataValidade": "2026-08-26T11:00:59.000+00:00",
        "finalidadeProcesso": "Balanceamento Operacional", "volumeTotal": 1500000, "pcr": 9400,
        "pontoZonas": PONTO_ZONAS, "formaAtendimento": FORMA_ATENDIMENTO,
        "precoMedioProcesso": 33.51, "periodoAtendimentoTotal": "26/08/2026 - 26/08/2026",
        "propostasAceitas": [
            {"pontoZonaId": 25, "volumeGas": 100000, "volumeAceito": 100000, "valor": 124999.60,
             "preco": 33.51, "formaAtendimentoId": 2},
        ],
    },
    # No accepted bids -> null-bid synth row
    {
        "nomeTransportadora": "Nova Transportadora do Sudeste", "siglaTransportadora": "NTS",
        "codigoProcesso": "NTS-PC-0044/2026", "categoria": "C",
        "validade": "2026-08-20T20:00:59.000+00:00", "inicioAtendimento": "2026-08-21T15:00:00.000+00:00",
        "fimAtendimento": "2026-08-22T02:59:00.000+00:00", "dataValidade": "2026-08-20T20:00:59.000+00:00",
        "finalidadeProcesso": "Aquisição de GUS", "volumeTotal": None, "pcr": 9400,
        "pontoZonas": PONTO_ZONAS, "formaAtendimento": FORMA_ATENDIMENTO,
        "precoMedioProcesso": None, "periodoAtendimentoTotal": "21/08/2026 - 21/08/2026",
        "propostasAceitas": [],
    },
    # Multiple accepted bids, forward flow date, untranslated finalidade ("Congestionamento")
    {
        "nomeTransportadora": "Transportadora Brasileira Gasoduto Bolívia-Brasil", "siglaTransportadora": "TBG",
        "codigoProcesso": "TBG-PC-0099/2026", "categoria": "V",
        "validade": "2026-08-10T20:00:59.000+00:00", "inicioAtendimento": "2026-08-15T15:00:00.000+00:00",
        "fimAtendimento": "2026-08-18T02:59:00.000+00:00", "dataValidade": "2026-08-10T20:00:59.000+00:00",
        "finalidadeProcesso": "Congestionamento", "volumeTotal": 500000, "pcr": 9400,
        "pontoZonas": PONTO_ZONAS, "formaAtendimento": FORMA_ATENDIMENTO,
        "precoMedioProcesso": 40.10, "periodoAtendimentoTotal": "15/08/2026 - 17/08/2026",
        "propostasAceitas": [
            {"pontoZonaId": 31, "volumeGas": 200000, "volumeAceito": 180000, "valor": 7218.00,
             "preco": 40.10, "formaAtendimentoId": 1},
            {"pontoZonaId": 3, "volumeGas": 150000, "volumeAceito": 150000, "valor": 6015.00,
             "preco": 40.10, "formaAtendimentoId": 4},
        ],
    },
    # Linepack, same-day trade timing
    {
        "nomeTransportadora": "Transportadora Associada de Gás", "siglaTransportadora": "TAG",
        "codigoProcesso": "TAG-PC-0201/2026", "categoria": "V",
        "validade": "2026-07-01T11:00:59.000+00:00", "inicioAtendimento": "2026-07-01T15:00:00.000+00:00",
        "fimAtendimento": "2026-07-01T23:59:00.000+00:00", "dataValidade": "2026-07-01T11:00:59.000+00:00",
        "finalidadeProcesso": "Linepack", "volumeTotal": 80000, "pcr": 9400,
        "pontoZonas": PONTO_ZONAS, "formaAtendimento": FORMA_ATENDIMENTO,
        "precoMedioProcesso": 28.00, "periodoAtendimentoTotal": "01/07/2026 - 01/07/2026",
        "propostasAceitas": [
            {"pontoZonaId": 23, "volumeGas": 80000, "volumeAceito": 80000, "valor": 2240.00,
             "preco": 28.00, "formaAtendimentoId": 3},
        ],
    },
]

if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "raw_processos.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(records)} mock records to {out}")
