"""Desk must rebuild its payload from the lake in CI, not reuse a stale artifact."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_desk_dashboard():
    import sys

    desk_dir = ROOT / "desk"
    if str(desk_dir) not in sys.path:
        sys.path.insert(0, str(desk_dir))
    path = desk_dir / "dashboard.py"
    spec = importlib.util.spec_from_file_location("desk_dashboard_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _stub_kit(monkeypatch, kit):
    monkeypatch.setattr(
        kit,
        "render",
        lambda template, **kw: (
            f"<!-- generated: {kw.get('GENERATED')} data_through: {kw.get('DATA_THROUGH')} -->\n"
            f'const PAYLOAD_URL = "{kw.get("PAYLOAD_URL")}";\n'
        ),
    )
    monkeypatch.setattr(kit, "render_theme_css", lambda: "")
    monkeypatch.setattr(kit, "share_link_button_html", lambda *a, **k: "")
    monkeypatch.setattr(kit, "refreshed_local_js", lambda: "")
    monkeypatch.setattr(kit, "chart_palette_js", lambda: "")
    monkeypatch.setattr(kit, "site_links_js", lambda *a, **k: "")
    monkeypatch.setattr(kit, "masthead_html", lambda *a, **k: "")
    monkeypatch.setattr(kit, "methodology_html", lambda *a, **k: "")
    monkeypatch.setattr(kit, "embed_favicon", lambda: "")
    monkeypatch.setattr(kit, "font_preload_html", lambda: "")
    monkeypatch.setattr(kit, "JS_DECODE", "")
    monkeypatch.setattr(kit, "JS_ESCAPE_HTML", "")
    monkeypatch.setattr(kit, "JS_TABLE_SORT", "")
    monkeypatch.setattr(kit, "JS_QUERY_STATE", "")
    monkeypatch.setattr(kit, "JS_THEME_TOGGLE", "")
    monkeypatch.setattr(kit, "JS_BOOT", "")
    monkeypatch.setattr(kit, "JS_I18N", "")


def test_desk_rebuilds_when_lake_bucket_configured_without_local_parquet(
    tmp_path, monkeypatch
):
    """Regression: #17 gated rebuild on local parquet only, so scheduled CI
    runs (empty lake/) reused the last published payload forever."""
    desk = _load_desk_dashboard()
    import data_kit as dk
    import dashboard_kit as kit

    fake_desk = tmp_path / "desk"
    fake_desk.mkdir()
    (tmp_path / "lake").mkdir()
    (tmp_path / "poc" / "data").mkdir(parents=True)
    out = fake_desk / "index.html"
    calls = {"build": 0, "publish": 0}

    def fake_build():
        calls["build"] += 1
        return {
            "generated": "2026-09-16 12:00 UTC",
            "dataThrough": "2026-09-16",
            "kpi": {"pldSe": 100.0, "genGasSin": 200.0},
            "notes": [],
        }

    def fake_publish(domain, payload, local_dir, **kwargs):
        calls["publish"] += 1
        path = Path(local_dir) / "payload.json.gz"
        path.write_bytes(b"gz")
        return path, "https://example.test/desk/payload.json.gz?v=fresh"

    monkeypatch.setattr(desk, "HERE", fake_desk)
    monkeypatch.setattr(desk, "DEFAULT_OUT", out)
    monkeypatch.setattr(desk, "build_payload", fake_build)
    monkeypatch.setenv("GASBRAZIL_LAKE_BUCKET", "lake-test")
    monkeypatch.setattr(dk, "r2_configured", lambda: True)
    monkeypatch.setattr(dk, "write_and_publish_artifact", fake_publish)
    _stub_kit(monkeypatch, kit)

    result = desk.write_dashboard(out)
    assert calls["build"] == 1
    assert calls["publish"] == 1
    text = result.read_text(encoding="utf-8")
    assert "2026-09-16 12:00 UTC" in text
    assert "2026-09-16" in text
    assert "v=fresh" in text


def test_desk_reuses_published_payload_when_offline(tmp_path, monkeypatch):
    desk = _load_desk_dashboard()
    import data_kit as dk
    import dashboard_kit as kit

    fake_desk = tmp_path / "desk"
    fake_desk.mkdir()
    (tmp_path / "lake").mkdir()
    (tmp_path / "poc" / "data").mkdir(parents=True)
    out = fake_desk / "index.html"
    out.write_text(
        "<!-- home-page teaser marker, read by ../build_home.py:\n"
        "     generated: 2026-09-10 18:06 UTC\n"
        "     kpi_pld_se: 142.68\n"
        "     kpi_gen_gas: 3496.2\n"
        "     data_through: 2026-09-10 -->\n"
        'const PAYLOAD_URL = "https://example.test/desk/payload.json.gz?v=stale";\n',
        encoding="utf-8",
    )
    calls = {"build": 0}

    monkeypatch.setattr(desk, "HERE", fake_desk)
    monkeypatch.setattr(desk, "DEFAULT_OUT", out)
    monkeypatch.setattr(
        desk, "build_payload", lambda: (_ for _ in ()).throw(AssertionError("no rebuild"))
    )
    monkeypatch.delenv("GASBRAZIL_LAKE_BUCKET", raising=False)
    monkeypatch.setattr(dk, "r2_configured", lambda: False)
    _stub_kit(monkeypatch, kit)

    result = desk.write_dashboard(out)
    assert calls["build"] == 0
    text = result.read_text(encoding="utf-8")
    assert "2026-09-10 18:06 UTC" in text
    assert "v=stale" in text


def test_desk_source_requires_lake_or_local_before_reuse():
    src = (ROOT / "desk" / "dashboard.py").read_text(encoding="utf-8")
    assert "lake_ready" in src
    assert "has_local or lake_ready" in src
    assert "GASBRAZIL_LAKE_BUCKET" in src
    assert "r2_configured()" in src
