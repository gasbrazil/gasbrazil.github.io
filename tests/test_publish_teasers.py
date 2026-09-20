from __future__ import annotations

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


def test_collect_reads_structured_metadata_json(tmp_path, monkeypatch):
    import json

    import data_kit as dk

    ons = tmp_path / "ons"
    ons.mkdir()
    # Structured metadata
    meta = {
        "generated": "2026-09-20 18:00 UTC",
        "kpi_gas_mwmed": 3456,
    }
    (ons / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    # HTML file with older/different marker
    (ons / "index.html").write_text("kpi_gas_mwmed: 9999\n", encoding="utf-8")

    monkeypatch.setattr(pt, "ROOT", tmp_path)
    monkeypatch.setattr(dk, "REPO_ROOT", tmp_path)

    payload = pt.collect()
    assert payload["items"]["ons"]["kpiEn"] == "3,456 MWmed gas"
    assert payload["items"]["ons"]["when"] == "2026-09-20 18:00 UTC"

