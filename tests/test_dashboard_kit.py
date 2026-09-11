from __future__ import annotations

import html

import pytest

import dashboard_kit as kit


def test_seo_head_escapes_title_and_description():
    head = kit.seo_head(
        title='PLD <script>alert(1)</script>',
        description='Say "hi" & more',
        path="/pld/",
    )
    assert "<script>" not in head
    assert html.escape("PLD <script>alert(1)</script>", quote=True) in head
    assert "&quot;hi&quot;" in head
    assert 'hreflang="en"' not in head
    assert "hreflang=\"x-default\"" in head


def test_render_is_single_pass():
    template = "A __FIRST__ then __SECOND__"
    out = kit.render(template, FIRST="__SECOND__", SECOND="Z")
    assert out == "A __SECOND__ then Z"


def test_favicon_fallback_encodes_hash():
    uri = kit.embed_favicon(favicon_path="/no/such/favicon.png", fallback_hex="#03183D")
    assert "fill='%2303183D'" in uri


def test_masthead_menu_aria():
    mast = kit.masthead_html("ons")
    assert 'aria-haspopup="menu"' in mast
    assert 'id="gb-products-menu"' in mast
    assert 'role="menu"' in mast
    assert "\u2630" in mast  # hamburger glyph on the Menu trigger
    # Icon-only: aria-label via data-i18n-aria, never a visible "Menu" span.
    assert 'data-i18n-aria="navMenu"' in mast
    assert 'data-i18n="navMenu"' not in mast
    assert "navProducts" not in mast


def test_masthead_menu_lives_in_nav_trail():
    mast = kit.masthead_html("ons")
    ident = mast.find('class="masthead-ident"')
    trail = mast.find('class="nav-trail"')
    menu = mast.find('class="products-dd"')
    assert ident != -1 and trail != -1 and menu != -1
    assert ident < trail < menu
    # Quiet 1px rule, not a › breadcrumb glyph.
    assert '<span class="crumb-sep" aria-hidden="true"></span>' in mast
    assert "›" not in mast


def test_masthead_merges_brand_and_title():
    mast = kit.masthead_html("ons")
    assert mast.count("GasBrazil") == 1  # brand once; no repeated wordmark
    assert 'id="link-home"' in mast
    assert '<h1 data-i18n="navOns">ONS Balances</h1>' in mast
    assert 'aria-current="page"' in mast
    # Streamlined by design: no separate breadcrumb nav above the title.
    assert 'aria-label="Breadcrumb"' not in mast


def test_masthead_covers_every_dashboard():
    for site in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        mast = kit.masthead_html(site)
        assert 'class="masthead"' in mast and "<h1" in mast


def test_masthead_rejects_unknown_site():
    with pytest.raises(KeyError):
        kit.masthead_html("nope")


def test_dashboard_headers_stay_on_one_row():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        src = (root / name / "dashboard.py").read_text(encoding="utf-8")
        assert "header.dash-head" in src
        compact = src.replace(" ", "").replace("\n", "")
        assert "header.dash-head{display:flex;flex-direction:row" in compact
        assert ".header-right{display:flex;align-items:center;gap:6px;flex-wrap:nowrap;width:auto;}" in compact


def test_page_intro_is_title_only():
    out = kit.page_intro_html("ons")
    assert out == '<h1 data-i18n="navOns">ONS Balances</h1>'
    # Streamlined by design: no visible description paragraph.
    assert "page-sub" not in out


def test_page_intro_covers_every_dashboard():
    for site in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        out = kit.page_intro_html(site)
        assert out.startswith("<h1") and "<nav " not in out


def test_page_intro_rejects_unknown_site():
    with pytest.raises(KeyError):
        kit.page_intro_html("nope")


def test_staleness_helper_ships_with_asof_js():
    js = kit.refreshed_local_js()
    assert "initStalenessBadgeFor" in js
    assert "STALE_MAX_LAG_DAYS" in js
    for site in ("ons", "pld", "contratos", "flows", "supply", "precos", "desk"):
        assert f'"{site}"' in js


def test_methodology_has_collapsed_rows():
    out = kit.methodology_html("pld")
    assert out.startswith('<details class="method">')
    assert 'data-i18n="methodTitle"' in out
    assert 'data-i18n="methodSources"' in out
    assert 'data-i18n="methodAssump"' in out
    assert 'data-i18n="methodLimits"' in out
    assert 'data-i18n="methodAssump_pld"' in out
    assert 'data-i18n="aboutCoverPld"' in out
    assert 'data-i18n="sourcePld"' in out
    assert "<table" not in out


def test_methodology_covers_every_dashboard():
    for site in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        out = kit.methodology_html(site)
        assert "<details" in out and "<summary" in out


def test_methodology_rejects_unknown_site():
    with pytest.raises(KeyError):
        kit.methodology_html("nope")


def test_methodology_defaults_match_i18n_pack():
    # Builder defaults show pre-hydration; drift from GB_I18N would flash
    # mismatched text on every language toggle.
    for defaults in (kit._METHOD_ASSUMP_DEFAULTS, kit._METHOD_LIMITS_DEFAULTS):
        for text in defaults.values():
            assert text in kit.JS_I18N


def test_share_link_strings_bilingual():
    assert 'copyLink: "Copy link"' in kit.JS_I18N
    assert 'linkCopied: "Copied"' in kit.JS_I18N
    assert 'copyLink: "Copiar link"' in kit.JS_I18N
    assert 'linkCopied: "Copiado"' in kit.JS_I18N


def test_share_link_button_matches_i18n_pack():
    out = kit.share_link_button_html()
    assert 'id="btn-share"' in out
    assert 'data-i18n="copyLink"' in out
    assert "Copy link" in out
    assert "Copy link" in kit.JS_I18N


def test_theme_toggle_paints_icon_immediately():
    js = kit.JS_THEME_TOGGLE
    assert "dataset.themeWired" in js
    assert 'if (document.getElementById("theme-toggle")) initThemeToggle("theme-toggle");' in js


def test_query_state_helper_degrades_to_defaults():
    js = kit.JS_QUERY_STATE
    for fn in ("gbQueryParams", "gbWriteQuery", "gbValidDate",
               "gbValidEnum", "gbValidList", "gbCopyLink"):
        assert fn in js
    # Cache-bust token never leaks into shared links.
    assert 'sp.delete("refreshed")' in js
    # Unknown/partial params degrade: allow-list filtering, never a throw.
    assert "gbValidList" in js and "gbValidEnum" in js and "gbValidDate" in js
    # Clipboard with a non-clipboard fallback (non-secure contexts).
    assert "navigator.clipboard" in js and "execCommand" in js


def test_csv_download_prepends_utf8_bom():
    js = kit.JS_CSV_HELPERS
    assert "downloadTextFile" in js
    assert "\\uFEFF" in js
    assert "isCsv" in js
