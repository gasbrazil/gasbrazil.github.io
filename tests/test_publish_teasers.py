from __future__ import annotations

from pathlib import Path

import publish_teasers as pt


def test_collect_reads_markers(tmp_path, monkeypatch):
    ons = tmp_path / "ons"
    ons.mkdir()
    (ons / "index.html").write_text(
        "<!-- generated: 2026-09-09 12:00 UTC\n     kpi_gas_mwmed: 1234 -->",
        encoding="utf-8",
    )
    monkeypatch.setattr(pt, "ROOT", tmp_path)
    payload = pt.collect()
    assert payload["items"]["ons"]["kpiEn"] == "1,234 MWmed gas"
    status = pt.status_from_teasers(payload)
    assert status["ons_kpi"] == "1,234 MWmed gas"


def test_collect_skips_bad_numbers(tmp_path, monkeypatch):
    pld = tmp_path / "pld"
    pld.mkdir()
    (pld / "index.html").write_text("kpi_se: not-a-number\n", encoding="utf-8")
    monkeypatch.setattr(pt, "ROOT", tmp_path)
    payload = pt.collect()
    assert "pld" not in payload["items"]
