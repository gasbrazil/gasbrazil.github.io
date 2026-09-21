"""Unit tests for TAG Mago client + pipeline normalization."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mago"))

import mago_pipeline as mp  # noqa: E402
from mago_client import classify_tag, parse_snapshot_key, rows_from_snapshot  # noqa: E402


def test_parse_snapshot_key():
    snap, cal = parse_snapshot_key("EMPACOTAMENTOS_19_09_2026_23_08_26.json")
    assert snap == datetime(2026, 9, 19, 23, 8, 26, tzinfo=UTC)
    assert cal.isoformat() == "2026-09-19"


def test_classify_tags():
    assert classify_tag("MALHA-INT-1MIN")[0] == "linepack_actual"
    assert classify_tag("Previsao - ZONA_RJ - Diario") == (
        "zone_consumption_forecast",
        None,
        "RJ",
    )


def test_rows_from_snapshot():
    snap = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
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


def _load_mago_dashboard():
    import importlib.util

    path = ROOT / "mago" / "dashboard.py"
    spec = importlib.util.spec_from_file_location("mago_dashboard_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_load_payload_groups_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "HERE", tmp_path)
    monkeypatch.setattr(mp, "RAW_DIR", tmp_path / "raw" / "snapshots")
    monkeypatch.setattr(mp, "MANIFEST_PATH", tmp_path / "raw" / "_manifest.json")
    monkeypatch.setattr(mp, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(mp, "PARQUET_PATH", tmp_path / "data" / "tag_mago_series.parquet")

    md = _load_mago_dashboard()
    monkeypatch.setattr(md, "PARQUET_PATH", mp.PARQUET_PATH)


    mp.RAW_DIR.mkdir(parents=True)
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
    assert "toleranceBands" in result
    assert "toleranceBandsList" in result
    assert "kpiZone" in result
    assert result["linepackHistoryRows"][0]["zone"] in [
        "severo_superior", "alto_superior", "baixo_superior",
        "marginal", "baixo_inferior", "alto_inferior", "severo_inferior", "unknown"
    ]
    assert "linepackHeatmap" in result
    assert "linepackHeatmapSummary" in result
    assert result["linepackHeatmapSummary"]["totalDays"] >= 1
    assert result["linepackHeatmapSummary"]["compliancePct"] >= 0.0


def test_rows_from_snapshot_with_tolerance_bands():
    snap = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    payload = {
        "Items": [
            {
                "Tag": "Comercial_Faixa_Severo_Superior_MalhaIntegrada",
                "Timestamp": "2026-09-19T12:00:00Z",
                "Value": 75500000.0,
                "Good": True,
            },
            {
                "Tag": "Comercial_Faixa_Marginal_Superior_MalhaIntegrada",
                "Timestamp": "2026-09-19T12:00:00Z",
                "Value": 72000000.0,
                "Good": True,
            },
            {
                "Tag": "Comercial_Faixa_Marginal_Inferior_MalhaIntegrada",
                "Timestamp": "2026-09-19T12:00:00Z",
                "Value": 69000000.0,
                "Good": True,
            },
        ]
    }
    rows = rows_from_snapshot(snap, payload)
    assert len(rows) == 3
    for r in rows:
        assert r["series"] == "linepack_tolerance_band"
        assert r["mesh"] == "integrated"
    zones = {r["zone"] for r in rows}
    assert zones == {"severo_superior", "marginal_superior", "marginal_inferior"}


def test_determine_linepack_zone():
    md = _load_mago_dashboard()
    bands = {
        "severo_superior": 75_500_000.0,
        "baixo_superior": 74_500_000.0,
        "marginal_superior": 72_000_000.0,
        "marginal_inferior": 69_000_000.0,
        "baixo_inferior": 67_500_000.0,
        "severo_inferior": 66_000_000.0,
    }

    # Severo Superior
    z = md.determine_linepack_zone(76_000_000.0, bands)
    assert z["key"] == "severo_superior"
    assert z["isAlert"] is True
    assert z["isCritical"] is True

    # Alto Superior
    z = md.determine_linepack_zone(75_000_000.0, bands)
    assert z["key"] == "alto_superior"
    assert z["isAlert"] is True
    assert z["isCritical"] is False

    # Baixo Superior
    z = md.determine_linepack_zone(73_000_000.0, bands)
    assert z["key"] == "baixo_superior"
    assert z["isAlert"] is False

    # Marginal (Target Operating Envelope)
    z = md.determine_linepack_zone(70_500_000.0, bands)
    assert z["key"] == "marginal"
    assert z["isAlert"] is False

    # Baixo Inferior
    z = md.determine_linepack_zone(68_000_000.0, bands)
    assert z["key"] == "baixo_inferior"
    assert z["isAlert"] is False

    # Alto Inferior (Alert)
    z = md.determine_linepack_zone(67_000_000.0, bands)
    assert z["key"] == "alto_inferior"
    assert z["isAlert"] is True

    # Severo Inferior (Critical Curtailment Risk)
    z = md.determine_linepack_zone(65_000_000.0, bands)
    assert z["key"] == "severo_inferior"
    assert z["isAlert"] is True
    assert z["isCritical"] is True

    # None / Missing
    z = md.determine_linepack_zone(None, bands)
    assert z["key"] == "unknown"
    assert z["isAlert"] is False


def test_build_linepack_heatmap():
    md = _load_mago_dashboard()
    sample_rows = [
        # Day 1: All marginal
        {
            "observedAt": "2026-09-18T01:00",
            "valueMm3": 70.5,
            "valueM3": 70500000.0,
            "zone": "marginal",
            "zoneLabel": "Target Operating (Marginal)",
            "zoneLabelPt": "Marginal (Ideal)",
            "badgeClass": "badge-target",
            "isAlert": False,
            "isCritical": False,
        },
        {
            "observedAt": "2026-09-18T02:00",
            "valueMm3": 70.8,
            "valueM3": 70800000.0,
            "zone": "marginal",
            "zoneLabel": "Target Operating (Marginal)",
            "zoneLabelPt": "Marginal (Ideal)",
            "badgeClass": "badge-target",
            "isAlert": False,
            "isCritical": False,
        },
        # Day 2: 1 marginal, 1 alto_inferior (Alert)
        {
            "observedAt": "2026-09-19T01:00",
            "valueMm3": 69.5,
            "valueM3": 69500000.0,
            "zone": "marginal",
            "zoneLabel": "Target Operating (Marginal)",
            "zoneLabelPt": "Marginal (Ideal)",
            "badgeClass": "badge-target",
            "isAlert": False,
            "isCritical": False,
        },
        {
            "observedAt": "2026-09-19T02:00",
            "valueMm3": 67.2,
            "valueM3": 67200000.0,
            "zone": "alto_inferior",
            "zoneLabel": "Low Alert (Alto)",
            "zoneLabelPt": "Alto (Inferior)",
            "badgeClass": "badge-warning",
            "isAlert": True,
            "isCritical": False,
        },
        # Day 3: 1 severo_inferior (Critical)
        {
            "observedAt": "2026-09-20T01:00",
            "valueMm3": 65.5,
            "valueM3": 65500000.0,
            "zone": "severo_inferior",
            "zoneLabel": "Critical Low (Severo)",
            "zoneLabelPt": "Severo (Inferior)",
            "badgeClass": "badge-danger",
            "isAlert": True,
            "isCritical": True,
        },
    ]

    poc_actions = {
        "2026-09-19": [
            {
                "processCode": "TAG-PC-001",
                "transactionType": "Op. Bal.",
                "price": 35.0,
                "volumeAccepted": 100000,
            }
        ]
    }

    heatmap, summary = md._build_linepack_heatmap(sample_rows, poc_actions)

    assert len(heatmap) == 3
    # Day 1: normal
    assert heatmap[0]["date"] == "2026-09-18"
    assert heatmap[0]["riskStatus"] == "normal"
    assert heatmap[0]["compliancePct"] == 100.0
    assert heatmap[0]["hoursAlto"] == 0
    assert heatmap[0]["hoursSevero"] == 0
    assert heatmap[0]["pocActions"] == []

    # Day 2: alert
    assert heatmap[1]["date"] == "2026-09-19"
    assert heatmap[1]["riskStatus"] == "alert"
    assert heatmap[1]["compliancePct"] == 50.0
    assert heatmap[1]["hoursAlto"] == 1
    assert len(heatmap[1]["pocActions"]) == 1

    # Day 3: critical
    assert heatmap[2]["date"] == "2026-09-20"
    assert heatmap[2]["riskStatus"] == "critical"
    assert heatmap[2]["compliancePct"] == 0.0
    assert heatmap[2]["hoursSevero"] == 1

    # Summary
    assert summary["totalDays"] == 3
    assert summary["totalHours"] == 5
    assert summary["totalAlertHours"] == 1
    assert summary["totalCriticalHours"] == 1
    assert summary["alertDaysCount"] == 2  # both day 2 (alert) and day 3 (critical)
    assert summary["criticalDaysCount"] == 1
    assert summary["hasPocActions"] is True


