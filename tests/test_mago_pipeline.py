"""Unit tests for TAG Mago client + pipeline normalization."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mago"))

import mago_client  # noqa: E402
import mago_pipeline as mp  # noqa: E402
from mago_client import classify_tag, parse_snapshot_key, rows_from_snapshot  # noqa: E402


def test_parse_snapshot_key():
    snap, cal = parse_snapshot_key("EMPACOTAMENTOS_19_09_2026_23_08_26.json")
    assert snap == datetime(2026, 9, 19, 23, 8, 26, tzinfo=timezone.utc)
    assert cal.isoformat() == "2026-09-19"


def test_classify_tags():
    assert classify_tag("MALHA-INT-1MIN")[0] == "linepack_actual"
    assert classify_tag("Previsao - ZONA_RJ - Diario") == (
        "zone_consumption_forecast",
        None,
        "RJ",
    )


def test_rows_from_snapshot():
    snap = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "Items": [
            {
                "Tag": "MALHA-INT-1MIN",
                "Timestamp": "2026-09-19T13:00:00Z",
                "Value": 68000000.0,
                "Good": True,
            },
            {
                "Tag": "Previsao - ZONA_AL - Diario",
                "Timestamp": "2026-09-20T00:00:00Z",
                "Value": 100.5,
                "Good": True,
            },
            {
                "Tag": "Comercial_Faixa_Severo_Superior_MalhaIntegrada",
                "Timestamp": "2026-09-19T13:00:00Z",
                "Value": 1,
                "Good": True,
            },
        ]
    }
    rows = rows_from_snapshot(snap, payload)
    assert len(rows) == 2
    assert {r["series"] for r in rows} == {"linepack_actual", "zone_consumption_forecast"}


def test_build_from_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "HERE", tmp_path)
    monkeypatch.setattr(mp, "RAW_DIR", tmp_path / "raw" / "snapshots")
    monkeypatch.setattr(mp, "MANIFEST_PATH", tmp_path / "raw" / "_manifest.json")
    monkeypatch.setattr(mp, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(mp, "PARQUET_PATH", tmp_path / "data" / "tag_mago_series.parquet")

    mp.RAW_DIR.mkdir(parents=True)
    snap = datetime(2026, 9, 19, 8, 8, 24, tzinfo=timezone.utc)
    name = "EMPACOTAMENTOS_19_09_2026_08_08_24.json"
    payload = {
        "Items": [
            {
                "Tag": "MALHA-INT-1MIN",
                "Timestamp": "2026-09-19T00:00:00Z",
                "Value": 68000000.0,
                "Good": True,
            },
        ]
        + [
            {
                "Tag": f"Previsao - ZONA_{z} - Diario",
                "Timestamp": "2026-09-19T00:00:00Z",
                "Value": 90.0,
                "Good": True,
            }
            for z in [
                "AL", "BA1", "BA2", "BA3", "BA4", "BA5", "CE1", "CE2", "ES1", "ES2", "ES3",
                "PB", "PE1", "PE2", "RJ", "RN1", "RN2", "RN3", "SE",
            ]
        ]
    }
    (mp.RAW_DIR / name).write_text(json.dumps(payload), encoding="utf-8")
    mp.cmd_build()
    df = pd.read_parquet(mp.PARQUET_PATH)
    assert len(df) >= 20
    assert set(df["series"].unique()) >= {"linepack_actual", "zone_consumption_forecast"}


def test_load_payload_groups_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "HERE", tmp_path)
    monkeypatch.setattr(mp, "RAW_DIR", tmp_path / "raw" / "snapshots")
    monkeypatch.setattr(mp, "MANIFEST_PATH", tmp_path / "raw" / "_manifest.json")
    monkeypatch.setattr(mp, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(mp, "PARQUET_PATH", tmp_path / "data" / "tag_mago_series.parquet")

    import dashboard as md  # noqa: E402

    monkeypatch.setattr(md, "PARQUET_PATH", mp.PARQUET_PATH)

    mp.RAW_DIR.mkdir(parents=True)
    snap = datetime(2026, 9, 19, 8, 8, 24, tzinfo=timezone.utc)
    name = "EMPACOTAMENTOS_19_09_2026_08_08_24.json"
    payload = {
        "Items": [
            {
                "Tag": "MALHA-INT-1MIN",
                "Timestamp": "2026-09-19T00:00:00Z",
                "Value": 68000000.0,
                "Good": True,
            },
            {
                "Tag": "MALHA-INT-1MIN",
                "Timestamp": "2026-09-19T01:00:00Z",
                "Value": 68100000.0,
                "Good": True,
            },
        ]
        + [
            {
                "Tag": f"Previsao - ZONA_{z} - Diario",
                "Timestamp": "2026-09-19T00:00:00Z",
                "Value": 90.0,
                "Good": True,
            }
            for z in [
                "AL", "BA1", "BA2", "BA3", "BA4", "BA5", "CE1", "CE2", "ES1", "ES2", "ES3",
                "PB", "PE1", "PE2", "RJ", "RN1", "RN2", "RN3", "SE",
            ]
        ]
    }
    (mp.RAW_DIR / name).write_text(json.dumps(payload), encoding="utf-8")
    mp.cmd_build()

    result = md.load_payload()
    assert "total" in result["groups"]
    assert result["groupSeries"]["BA"]["times"]
    assert len(result["linepackHistoryRows"]) >= 1
    assert result["linepackHistory"]["times"]
