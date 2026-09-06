"""Synthetic ANP-shaped CSVs for local supply dashboard builds without
hitting the live source. Field names and delimiter match real PPGN-EL /
import files inspected during development."""
from __future__ import annotations

import csv
from pathlib import Path

import supply_pipeline as sp

RAW = sp.RAW_DIR


def _write(name: str, header: list[str], rows: list[list]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> None:
    # Two states × two months so national sum is non-trivial.
    months = [("2024", "JAN"), ("2024", "FEV"), ("2024", "MAR")]
    states = [
        ("REGIÃO SUDESTE", "RIO DE JANEIRO", "MAR"),
        ("REGIÃO NORTE", "AMAZONAS", "TERRA"),
    ]
    # Base national-ish levels (thousand m3), split across states.
    prod = {("2024", "JAN"): (420000, 80000), ("2024", "FEV"): (410000, 78000), ("2024", "MAR"): (430000, 82000)}
    avail = {("2024", "JAN"): (280000, 50000), ("2024", "FEV"): (275000, 48000), ("2024", "MAR"): (290000, 52000)}
    flare = {("2024", "JAN"): (12000, 3000), ("2024", "FEV"): (11000, 2800), ("2024", "MAR"): (12500, 3100)}
    own = {("2024", "JAN"): (35000, 8000), ("2024", "FEV"): (34000, 7800), ("2024", "MAR"): (36000, 8200)}
    reinj = {("2024", "JAN"): (90000, 20000), ("2024", "FEV"): (88000, 19000), ("2024", "MAR"): (92000, 21000)}
    lgn = {("2024", "JAN"): (55000, 0), ("2024", "FEV"): (54000, 0), ("2024", "MAR"): (56000, 0)}
    imports = {("2024", "JAN"): 220000.5, ("2024", "FEV"): 210000.25, ("2024", "MAR"): 230500.75}

    def rows_for(values: dict) -> list[list]:
        out = []
        for (y, m), (v0, v1) in values.items():
            for i, (reg, uf, loc) in enumerate(states):
                v = v0 if i == 0 else v1
                out.append([y, m, reg, uf, "GÁS NATURAL", loc, str(v).replace(".", ",")])
        return out

    _write(
        "producao-gas-natural-1000m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "LOCALIZAÇÃO", "PRODUÇÃO"],
        rows_for(prod),
    )
    _write(
        "gn-disponivel-1000m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "LOCALIZAÇÃO", "DISPONÍVEL"],
        rows_for(avail),
    )
    _write(
        "queima-e-perda-gn-1000m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "LOCALIZAÇÃO", "QUEIMADO"],
        rows_for(flare),
    )
    _write(
        "consumo-proprio-gn1000m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "LOCALIZAÇÃO", "CONSUMO"],
        rows_for(own),
    )
    _write(
        "reinjecao-gn-1000m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "LOCALIZAÇÃO", "REINJETADO"],
        rows_for(reinj),
    )
    lgn_rows = []
    for (y, m), (v0, v1) in lgn.items():
        for i, (reg, uf, _loc) in enumerate(states):
            v = v0 if i == 0 else v1
            if v:
                lgn_rows.append([y, m, reg, uf, "LGN", str(v)])
    _write(
        "producao-lgn-m3.csv",
        ["ANO", "MÊS", "GRANDE REGIÃO", "UNIDADE DA FEDERAÇÃO", "PRODUTO", "PRODUÇÃO"],
        lgn_rows,
    )
    imp_rows = [[y, m, "GÁS NATURAL", "IMPORTAÇÃO", str(v).replace(".", ","), "0"]
                for (y, m), v in imports.items()]
    _write(
        "importacao-gas-natural.csv",
        ["ANO", "MÊS", "PRODUTO", "OPERAÇÃO COMERCIAL", "IMPORTADO", "DISPÊNDIO"],
        imp_rows,
    )
    # silence unused
    _ = months


if __name__ == "__main__":
    main()
