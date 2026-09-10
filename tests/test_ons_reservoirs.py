from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ons"))
import ons_pipeline as op  # noqa: E402


def test_clip_usable_volume_floors_negatives_and_caps_overflow():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01"] * 4),
        "subsystem": ["SE", "SE", "S", "NE"],
        "entity": ["ESTRELA", "TABOCA", "MONTE CLARO", "SOBRADINHO"],
        "series": ["res_volutil_pct"] * 4,
        "value": [-1916.85, -262.91, 193.61, 47.5],
    })
    out = op.clip_usable_volume(df)
    by_name = out.set_index("entity")["value"]
    assert by_name["ESTRELA"] == 0.0
    assert by_name["TABOCA"] == 0.0
    assert by_name["MONTE CLARO"] == 100.0
    assert by_name["SOBRADINHO"] == 47.5


def test_clip_usable_volume_leaves_other_series_alone():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01", "2026-09-01"]),
        "subsystem": ["SE", "SE"],
        "entity": ["ESTRELA", "ESTRELA"],
        "series": ["res_volutil_pct", "res_level_m"],
        "value": [-10.0, 480.2],
    })
    out = op.clip_usable_volume(df)
    vol = out.loc[out["series"] == "res_volutil_pct", "value"].iloc[0]
    lvl = out.loc[out["series"] == "res_level_m", "value"].iloc[0]
    assert vol == 0.0
    assert lvl == 480.2


def test_normalize_entities_strips_then_dedupes():
    ent = pd.DataFrame({
        "kind": ["reservoir", "reservoir", "reservoir"],
        "entity": ["CANASTRA", "CANASTRA ", "ESTRELA"],
        "subsystem": ["s", "S", "SE"],
        "group": ["JACUI", "JACUI", "PARANAIBA"],
    })
    out = op.normalize_entities(ent)
    assert len(out) == 2
    canastra = out[out["entity"] == "CANASTRA"].iloc[0]
    assert canastra["subsystem"] == "S"
    assert set(out["entity"]) == {"CANASTRA", "ESTRELA"}
