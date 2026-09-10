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


def test_nav_products_aria():
    html_nav = kit.nav_links_html("ons")
    assert 'aria-haspopup="menu"' in html_nav
    assert 'id="gb-products-menu"' in html_nav
    assert 'role="menu"' in html_nav


def test_page_intro_has_breadcrumb_and_title():
    out = kit.page_intro_html("ons")
    assert 'class="crumbs"' in out
    assert 'aria-label="Breadcrumb"' in out
    assert 'href="../"' in out
    assert 'aria-current="page"' in out
    assert '<h1 data-i18n="navOns">ONS Balances</h1>' in out
    # Streamlined by design: no visible description paragraph.
    assert "page-sub" not in out


def test_page_intro_covers_every_dashboard():
    for site in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        out = kit.page_intro_html(site)
        assert "<nav " in out and "<h1" in out


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
