"""Write a small synthetic CCEE PLD CSV (and rebuild parquet) for offline
local rebuilds without hitting dadosabertos.ccee.org.br.

Daily layout matches real yearly files: semicolon, latin-1, columns
MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA.

Hourly layout matches real yearly files:
MES_REFERENCIA;SUBMERCADO;PERIODO_COMERCIALIZACAO;DIA;HORA;PLD_HORA
with DIA as day-of-month (not a full date).
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

# Extra R$/MWh added on weekday peak hours (18–20) so peak/off-peak is visible.
PEAK_PREMIUM = 22.0


def _day_pld(i: int, sm: str) -> float:
    phase = ((i % 7) - 3) / 3.0
    return round(BASE[sm] + WOBBLE[sm] * phase, 2)


def build_daily_rows() -> list[str]:
    lines = ["MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA"]
    dates = pd.date_range(START, END, freq="D")
    for i, d in enumerate(dates):
        mes = d.strftime("%Y%m")
        dia = d.strftime("%d/%m/%Y")
        for sm in BASE:
            lines.append(f"{mes};{sm};{dia};{_day_pld(i, sm):.2f}")
    return lines


def build_hourly_rows() -> list[str]:
    lines = ["MES_REFERENCIA;SUBMERCADO;PERIODO_COMERCIALIZACAO;DIA;HORA;PLD_HORA"]
    dates = pd.date_range(START, END, freq="D")
    for i, d in enumerate(dates):
        mes = d.strftime("%Y%m")
        dia = d.strftime("%d")
        weekday = int(d.dayofweek)
        for hour in range(24):
            period = i * 24 + hour + 1
            is_peak = weekday < 5 and hour in (18, 19, 20)
            # Overnight slightly cheaper; afternoon a gentle lift.
            shape = 1.0 + 0.04 * ((hour - 4) / 10.0 if hour >= 8 else (4 - hour) / 8.0)
            for sm in BASE:
                pld = round(_day_pld(i, sm) * shape + (PEAK_PREMIUM if is_peak else 0.0), 2)
                lines.append(f"{mes};{sm};{period};{dia};{hour};{pld:.2f}")
    return lines


if __name__ == "__main__":
    pp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Clear real yearly files so an offline build doesn't mix mock + live.
    for old in pp.RAW_DIR.glob("pld_media_diaria_*.csv"):
        old.unlink()
    for old in pp.RAW_DIR.glob("pld_horario_*.csv"):
        old.unlink()
    daily_out = pp.RAW_DIR / "pld_media_diaria_2026.csv"
    daily_rows = build_daily_rows()
    daily_out.write_text("\n".join(daily_rows) + "\n", encoding="latin-1")
    print(f"Wrote {len(daily_rows) - 1} mock daily rows to {daily_out}")
    hourly_out = pp.RAW_DIR / "pld_horario_2026.csv"
    hourly_rows = build_hourly_rows()
    hourly_out.write_text("\n".join(hourly_rows) + "\n", encoding="latin-1")
    print(f"Wrote {len(hourly_rows) - 1} mock hourly rows to {hourly_out}")
    pp.build()
