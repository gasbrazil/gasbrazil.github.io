"""Write a small synthetic CCEE PLD CSV (and rebuild parquet) for offline
local rebuilds without hitting dadosabertos.ccee.org.br.

Layout matches real yearly files: semicolon, latin-1, columns
MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import pld_pipeline as pp

# ~45 calendar days × 4 submarkets — enough for chart + KPI + table smoke tests.
DAYS = 45
END = pd.Timestamp("2026-09-06")
START = END - pd.Timedelta(days=DAYS - 1)

# Base levels roughly in the ballpark of recent SE PLD (R$/MWh).
BASE = {"NORTE": 95.0, "NORDESTE": 110.0, "SUDESTE": 125.0, "SUL": 118.0}
# Small deterministic day-to-day wobble so lines aren't flat.
WOBBLE = {"NORTE": 3.0, "NORDESTE": 5.0, "SUDESTE": 8.0, "SUL": 6.0}


def build_rows() -> list[str]:
    lines = ["MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA"]
    dates = pd.date_range(START, END, freq="D")
    for i, d in enumerate(dates):
        mes = d.strftime("%Y%m")
        dia = d.strftime("%d/%m/%Y")
        for sm, base in BASE.items():
            # Gentle sine-ish oscillation without importing math trig on purpose:
            # alternate ± wobble on a 7-day cycle.
            phase = ((i % 7) - 3) / 3.0
            pld = round(base + WOBBLE[sm] * phase, 2)
            lines.append(f"{mes};{sm};{dia};{pld:.2f}")
    return lines


if __name__ == "__main__":
    pp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Clear real yearly files so an offline build doesn't mix mock + live.
    for old in pp.RAW_DIR.glob("pld_media_diaria_*.csv"):
        old.unlink()
    out = pp.RAW_DIR / "pld_media_diaria_2026.csv"
    rows = build_rows()
    out.write_text("\n".join(rows) + "\n", encoding="latin-1")
    print(f"Wrote {len(rows) - 1} mock rows to {out}")
    pp.build()
