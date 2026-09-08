"""Synthetic ANP PPG-shaped CSVs for local precos dashboard builds without
hitting the live source. Encoding (UTF-16LE + BOM), delimiter, and column
headers match the live Resolution 52/2011 files probed during development."""
from __future__ import annotations

from pathlib import Path

import precos_pipeline as pp

RAW = pp.RAW_DIR

# Exact live headers (UTF-16LE CSVs).
PRODUCER_HEADER = [
    "Ano",
    "Mês",
    "BaciaAgregada",
    "Preço em Reais por MMBtu",
    "Volume em mil metros cúbicos/dia",
]
DISTRIBUTOR_HEADER = [
    "Ano",
    "Mês",
    "TipoMercado",
    "RegiãoAgregada",
    "Preço em Reais por MMBtu",
    "Volume em mil metros cúbicos/dia",
]
MARKETER_HEADER = [
    "Ano",
    "Mês",
    "Preço em Reais por MMBtu",
    "Volume em mil metros cúbicos/dia",
]


def _br(n: float | None) -> str:
    if n is None:
        return ""
    s = f"{n:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _write_utf16(name: str, header: list[str], rows: list[list]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    lines = [";".join(f'"{c}"' for c in header)]
    for r in rows:
        cells = []
        for i, v in enumerate(r):
            if i < 2:  # Ano, Mês — unquoted integers like the live file
                cells.append(str(v))
            elif v == "" or v is None:
                cells.append("")
            elif isinstance(v, str) and v[:1].isdigit():
                cells.append(v)  # Brazilian decimal numbers
            else:
                cells.append(f'"{v}"')
        lines.append(";".join(cells))
    # Live files are UTF-16LE with BOM (encoding name "utf-16" writes BOM).
    path.write_text("\n".join(lines) + "\n", encoding="utf-16")
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> None:
    # Three recent months; one suppressed thermal price (empty) to exercise nulls.
    # Keep within the pipeline health lag window (~6 months).
    months = [(2026, 4), (2026, 5), (2026, 6)]

    producer_rows: list[list] = []
    basin_prices = {
        "Santos": [12.5, 13.1, 12.8],
        "Campos": [9.2, 9.5, 9.0],
        "Demais Bacias": [22.0, 21.5, 23.1],
    }
    basin_vols = {
        "Santos": [11000, 11200, 10800],
        "Campos": [1200, 1150, 1300],
        "Demais Bacias": [2800, 2900, 2750],
    }
    for i, (y, m) in enumerate(months):
        for basin in ("Santos", "Campos", "Demais Bacias"):
            producer_rows.append(
                [y, m, basin, _br(basin_prices[basin][i]), str(basin_vols[basin][i])]
            )

    dist_rows: list[list] = []
    # thermal Norte-Nordeste suppressed in the second month (empty price, volume kept)
    specs = [
        ("Térmico", "Norte-Nordeste", [18.9, None, 19.4], [15000, 14800, 15200]),
        ("Térmico", "Sudeste", [16.2, 16.5, 16.0], [8000, 8200, 7900]),
        ("Não Térmico", "Norte-Nordeste", [49.3, 48.8, 50.1], [7000, 7100, 6900]),
        ("Não Térmico", "Sudeste", [48.8, 47.9, 49.0], [25000, 24800, 25200]),
    ]
    for tipo, reg, prices, vols in specs:
        for i, (y, m) in enumerate(months):
            dist_rows.append([y, m, tipo, reg, _br(prices[i]), str(vols[i])])

    mkt_prices = [55.0, 52.5, 54.2]
    mkt_vols = [9000, 8800, 9100]
    marketer_rows = [
        [y, m, _br(mkt_prices[i]), str(mkt_vols[i])]
        for i, (y, m) in enumerate(months)
    ]

    _write_utf16("vendas-entre-produtores.csv", PRODUCER_HEADER, producer_rows)
    _write_utf16("distribuidoras-consumidores-livres.csv", DISTRIBUTOR_HEADER, dist_rows)
    _write_utf16("vendas-aos-comercializadores.csv", MARKETER_HEADER, marketer_rows)


if __name__ == "__main__":
    main()
