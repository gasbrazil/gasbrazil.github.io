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


def test_build_home_preserves_committed_hub_data_when_offline(tmp_path, monkeypatch):
    import data_kit as dk

    import build_home

    fake_index = tmp_path / "index.html"
    fake_index.write_text(
        """
    <a class="kpi-cell" href="monitor/" data-slug="monitor">
      <div class="kpi-val" data-en="TAG 69.43 Mm³ · NTS 43.59 Mm³" data-pt="TAG 69.43 Mm³ · NTS 43.59 Mm³">TAG 69.43 Mm³ · NTS 43.59 Mm³</div>
      <div class="kpi-when" data-refresh="2026-09-26 05:27 UTC"></div>
      <svg class="kpi-spark" viewBox="0 0 120 28" width="120" height="28"><polyline points="1,2 3,4"/></svg>
    </a>
    <script>
    const TEASERS_URL = "https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev/hub/teasers.json.gz?v=9999";
    </script>
    """,
        encoding="utf-8",
    )

    import publish_teasers as pt

    monkeypatch.setattr(build_home, "ROOT", tmp_path)
    monkeypatch.setattr(pt, "ROOT", tmp_path)
    monkeypatch.setattr(build_home, "DEFAULT_OUT", fake_index)
    monkeypatch.setattr(dk, "r2_configured", lambda: False)

    st = build_home.collect_status()
    assert st["teasers_url"] == "https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev/hub/teasers.json.gz?v=9999"
    assert '<polyline points="1,2 3,4"/>' in st["monitor_spark"]
    assert st["monitor_kpi"] == "TAG 69.43 Mm³ · NTS 43.59 Mm³"


