"""Generates raw/gn_<month>_<year>.csv with a small synthetic-but-realistic
file matching ANP's real layout, for local dev/testing without hitting the
live source. Field shapes and header text match real files inspected during
development (2024-2026 vintage; see flows_pipeline.py's module docstring).

Deliberately exercises the two aggregation traps flows_pipeline.py has to
handle correctly:
  - Pressão Média (kgf/cm²) is broadcast identically to every shipper row at
    a point -> must be aggregated with median(), not sum().
  - The ledger variables (Gás de Uso no Sistema, etc.) are broadcast
    identically to every shipper row for a pipeline -> same median() rule.
Volume Solicitado/Programado/Realizado and Alocação (%) are genuine
per-shipper splits and are summed.
"""
from __future__ import annotations

import csv
from pathlib import Path

import flows_pipeline as fp

MONTH_INDEX = 8  # setembro -- arbitrary past month, avoids colliding with real fetched data
YEAR = 2025
DAYS = 5  # small file is enough to exercise build()

HEADER = fp.META_COLS + [f"{d:02d}/{MONTH_INDEX + 1:02d}/{YEAR}" for d in range(1, DAYS + 1)]


def _row(transp_code, transp_name, point_name, point_code, point_type, muni, uf,
         operator, operator_code, shipper, shipper_code, contract, variable, values):
    assert len(values) == DAYS
    return [
        transp_code, transp_name, point_name, point_code, point_type, muni, uf,
        operator, operator_code, shipper, shipper_code, contract, variable,
        *[f"{v:.2f}".replace(".", ",") for v in values],
    ]


def build_rows() -> list[list[str]]:
    rows = []

    # -- Pipeline 1: two receipt points, two shippers each --------------------
    pipeline1 = dict(transp_code="900001", transp_name="Mock Pipeline Bravo",
                      operator="Mock Transportadora Bravo Ltda - MTB", operator_code="9001001")
    points1 = [
        dict(point_name="Alpha", point_code="500001", point_type="Ponto de Recebimento",
             muni="Alphaville", uf="MT"),
        dict(point_name="Beta", point_code="500002", point_type="Ponto de Entrega",
             muni="Betapolis", uf="MT"),
    ]
    shippers1 = [
        dict(shipper="MOCKGAS", shipper_code="7000001", contract="Firme"),
        dict(shipper="TESTFUEL", shipper_code="7000002", contract="Extraordinário"),
    ]
    # Per-shipper volumes (genuinely additive) -- different per shipper.
    volumes = {
        ("Alpha", "MOCKGAS"): {"Volume Solicitado (mil m³)": [120, 121, 119, 122, 120],
                                "Volume Programado (mil m³)": [118, 119, 117, 120, 118],
                                "Volume Realizado (mil m³)": [117.5, 118.2, 116.8, 119.4, 117.9],
                                "Alocação (%)": [60, 60, 60, 60, 60]},
        ("Alpha", "TESTFUEL"): {"Volume Solicitado (mil m³)": [80, 79, 81, 78, 80],
                                 "Volume Programado (mil m³)": [78, 77, 79, 76, 78],
                                 "Volume Realizado (mil m³)": [77.1, 76.4, 78.0, 75.6, 77.3],
                                 "Alocação (%)": [40, 40, 40, 40, 40]},
        ("Beta", "MOCKGAS"): {"Volume Solicitado (mil m³)": [50, 51, 49, 50, 52],
                               "Volume Programado (mil m³)": [49, 50, 48, 49, 51],
                               "Volume Realizado (mil m³)": [48.6, 49.5, 47.7, 48.9, 50.4],
                               "Alocação (%)": [100, 100, 100, 100, 100]},
        ("Beta", "TESTFUEL"): {"Volume Solicitado (mil m³)": [0, 0, 0, 0, 0],
                                "Volume Programado (mil m³)": [0, 0, 0, 0, 0],
                                "Volume Realizado (mil m³)": [0, 0, 0, 0, 0],
                                "Alocação (%)": [0, 0, 0, 0, 0]},
    }
    # Pressão Média is a single physical reading per point, broadcast to
    # every shipper row -- same value for MOCKGAS and TESTFUEL at each point.
    pressure_by_point = {"Alpha": [82.1, 82.4, 81.9, 82.6, 82.0],
                          "Beta": [75.3, 75.1, 75.6, 75.0, 75.4]}
    # Ledger entries are pipeline-wide, broadcast to every shipper row for
    # that pipeline regardless of which point they're nominally attached to.
    ledger_pipeline1 = {
        "Gás de Uso no Sistema (mil m³)": [-12.3, -12.1, -12.5, -12.0, -12.4],
        "Gás não contado (mil m³)": [0.8, 0.7, 0.9, 0.6, 0.8],
        "Perdas Operacionais (mil m³)": [0.2, 0.2, 0.3, 0.2, 0.2],
        "Perdas Extraordinárias (mil m³)": [0, 0, 0, 0, 0],
        "Desequilíbrio Diário (mil m³)": [-3.5, 2.1, -1.0, 4.2, -0.8],
        "Desequilíbrio Diário Acumulado (mil m³)": [-3.5, -1.4, -2.4, 1.8, 1.0],
        "Empacotamento (mil m³)": [410.0, 412.5, 408.0, 415.0, 411.0],
    }

    for pt in points1:
        for sh in shippers1:
            vols = volumes[(pt["point_name"], sh["shipper"])]
            for var, vals in vols.items():
                rows.append(_row(pipeline1["transp_code"], pipeline1["transp_name"],
                                  pt["point_name"], pt["point_code"], pt["point_type"],
                                  pt["muni"], pt["uf"], pipeline1["operator"], pipeline1["operator_code"],
                                  sh["shipper"], sh["shipper_code"], sh["contract"], var, vals))
            rows.append(_row(pipeline1["transp_code"], pipeline1["transp_name"],
                              pt["point_name"], pt["point_code"], pt["point_type"],
                              pt["muni"], pt["uf"], pipeline1["operator"], pipeline1["operator_code"],
                              sh["shipper"], sh["shipper_code"], sh["contract"],
                              "Pressão Média (kgf/cm²)", pressure_by_point[pt["point_name"]]))
        for sh in shippers1:
            for var, vals in ledger_pipeline1.items():
                rows.append(_row(pipeline1["transp_code"], pipeline1["transp_name"],
                                  "", "", "", "", "", pipeline1["operator"], pipeline1["operator_code"],
                                  sh["shipper"], sh["shipper_code"], "", var, vals))

    # -- Pipeline 2: single delivery point, single shipper (simple case) ------
    pipeline2 = dict(transp_code="900002", transp_name="Mock Pipeline Charlie",
                      operator="Mock Transportadora Charlie Ltda - MTC", operator_code="9002001")
    point2 = dict(point_name="Gamma", point_code="500003", point_type="Ponto de Entrega",
                   muni="Gammaburgo", uf="RJ")
    shipper2 = dict(shipper="SOLOGAS", shipper_code="7000003", contract="Firme")
    vols2 = {"Volume Solicitado (mil m³)": [200, 205, 198, 210, 202],
             "Volume Programado (mil m³)": [198, 202, 196, 207, 200],
             "Volume Realizado (mil m³)": [197.2, 201.0, 195.4, 206.1, 199.5],
             "Alocação (%)": [100, 100, 100, 100, 100]}
    for var, vals in vols2.items():
        rows.append(_row(pipeline2["transp_code"], pipeline2["transp_name"],
                          point2["point_name"], point2["point_code"], point2["point_type"],
                          point2["muni"], point2["uf"], pipeline2["operator"], pipeline2["operator_code"],
                          shipper2["shipper"], shipper2["shipper_code"], shipper2["contract"], var, vals))
    rows.append(_row(pipeline2["transp_code"], pipeline2["transp_name"],
                      point2["point_name"], point2["point_code"], point2["point_type"],
                      point2["muni"], point2["uf"], pipeline2["operator"], pipeline2["operator_code"],
                      shipper2["shipper"], shipper2["shipper_code"], shipper2["contract"],
                      "Pressão Média (kgf/cm²)", [55.0, 55.2, 54.9, 55.3, 55.1]))
    ledger_pipeline2 = {
        "Gás de Uso no Sistema (mil m³)": [-4.0, -3.9, -4.1, -3.8, -4.0],
        "Gás não contado (mil m³)": [0.1, 0.1, 0.1, 0.1, 0.1],
        "Perdas Operacionais (mil m³)": [0, 0, 0, 0, 0],
        "Perdas Extraordinárias (mil m³)": [0, 0, 0, 0, 0],
        "Desequilíbrio Diário (mil m³)": [1.2, -0.5, 0.8, -1.1, 0.3],
        "Desequilíbrio Diário Acumulado (mil m³)": [1.2, 0.7, 1.5, 0.4, 0.7],
        "Empacotamento (mil m³)": [88.0, 87.5, 88.4, 87.0, 87.8],
    }
    for var, vals in ledger_pipeline2.items():
        rows.append(_row(pipeline2["transp_code"], pipeline2["transp_name"],
                          "", "", "", "", "", pipeline2["operator"], pipeline2["operator_code"],
                          shipper2["shipper"], shipper2["shipper_code"], "", var, vals))

    return rows


if __name__ == "__main__":
    fp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = fp.RAW_DIR / f"gn_{fp.MONTHS_PT[MONTH_INDEX]}_{YEAR}.csv"
    rows = build_rows()
    with open(out, "w", encoding="latin1", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"Wrote {len(rows)} mock rows to {out}")
