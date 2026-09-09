from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "poc"))
import poc_pipeline as poc  # noqa: E402


def test_poc_transform_preserves_null_volumes():
    raw = [{
        "siglaTransportadora": "TAG",
        "codigoProcesso": "TAG-PC-0001/2026",
        "dataValidade": "2026-08-26T11:00:59.000+00:00",
        "inicioAtendimento": "2026-08-26T15:00:00.000+00:00",
        "fimAtendimento": "2026-08-27T02:59:00.000+00:00",
        "finalidadeProcesso": "Balanceamento Operacional",
        "volumeTotal": None,
        "pcr": 9400,
        "pontoZonas": [{"idPontoZona": 25, "nomePontoZona": "BA3"}],
        "formaAtendimento": [{"id": 2, "nome": "Retirada"}],
        "precoMedioProcesso": 33.51,
        "periodoAtendimentoTotal": "26/08/2026 - 26/08/2026",
        "propostasAceitas": [{
            "pontoZonaId": 25,
            "volumeGas": None,
            "volumeAceito": None,
            "valor": None,
            "preco": 33.51,
            "formaAtendimentoId": 2,
        }],
    }]
    df = poc.transform(raw)
    assert len(df) == 1
    assert pd_isna(df.loc[0, "Volume Accepted"])
    assert pd_isna(df.loc[0, "Total Volume"])


def pd_isna(v) -> bool:
    import pandas as pd
    return bool(pd.isna(v))
