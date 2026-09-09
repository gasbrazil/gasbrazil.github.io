from __future__ import annotations

import html

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
