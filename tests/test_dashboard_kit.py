from __future__ import annotations

import html
from pathlib import Path

import pytest

import dashboard_kit as kit


def test_embed_font_face_includes_plex_and_pacaembu():
    css = kit.embed_font_face()
    assert "font-family:'Pacaembu'" in css
    assert "font-family:'IBM Plex Sans'" in css
    assert "IBMPlexSans-Regular.ttf" in css
    assert "Pacaembu-SemiBold.ttf" in css


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
    assert 'class="dd-caret"' in mast
    assert "\u2630" not in mast  # no hamburger; menu hangs off the wordmark
    assert 'data-i18n-aria="navMenu"' in mast
    assert 'data-i18n="navMenu"' not in mast
    assert "navProducts" not in mast


def test_masthead_menu_hangs_off_wordmark():
    mast = kit.masthead_html("ons")
    ident = mast.find('class="masthead-ident"')
    brand = mast.find('id="link-home"')
    menu = mast.find('class="products-dd"')
    trail = mast.find('class="nav-trail"')
    assert ident != -1 and brand != -1 and menu != -1 and trail != -1
    # Wordmark is inside the dropdown; Wiki/About stay to the right of ident.
    assert ident < menu < brand < trail
    assert 'class="products-dd"' in mast[ident:trail]
    assert 'class="products-dd"' not in mast[trail:]
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


def test_products_dropdown_wraps_brand():
    html = kit.products_dropdown_html("home", '<div class="wordmark">GasBrazil</div>')
    assert html.startswith('<div class="products-dd">')
    assert '<div class="wordmark">GasBrazil</div>' in html
    assert html.find("wordmark") < html.find("dd-trigger")
    assert html.find("dd-trigger") < html.find("dd-menu")
    assert "\u2630" not in html
    assert 'class="dd-caret"' in html


def test_table_headers_freeze_inside_scroll_wraps():
    css = kit.THEME_CSS
    assert "border-collapse: separate" in css
    assert ".drill-table-wrap" in css
    assert ".drill-card thead th" not in css
    for wrap in (
        ".table-wrap thead th",
        ".scroll thead th",
        ".meter-table-wrap thead th",
        ".drill-table-wrap thead th",
        ".entlist thead th",
    ):
        assert wrap in css


def test_contratos_drill_table_has_own_scroll_wrap():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "contratos" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    assert 'class="drill-table-wrap"' in src
    assert "max-height: 320px; overflow: auto" not in src
    assert "position: sticky" not in src
    assert "colspan=" not in src
    assert "${metricHeads}" in src
    assert ">Share<" not in src
    assert "col.share" not in src


def test_desk_analysis_section_in_source():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "desk" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    assert 'id="picker-analysis"' in src
    assert "analysisSeries" in src
    assert "renderAnalysis" in src


def test_flows_init_handles_load_errors():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "flows" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "async function init()" in src
    assert "chart-empty" in src
    assert "No flows parquet" in src
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        src = (root / name / "dashboard.py").read_text(encoding="utf-8")
        assert "position: sticky" not in src, name


def test_dashboard_headers_stay_on_one_row():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        src = (root / name / "dashboard.py").read_text(encoding="utf-8")
        assert "header.dash-head" in src
        compact = src.replace(" ", "").replace("\n", "")
        assert "header.dash-head{display:flex;flex-direction:row" in compact
        assert ".header-right{display:flex;align-items:center;gap:6px;flex-wrap:nowrap;width:auto;}" in compact


def test_kpi_strip_has_gap_below_across_dashboards():
    """KPI strips must leave the same buffer as .card → next section."""
    root = Path(__file__).resolve().parents[1]
    theme = (root / "shared" / "theme.css").read_text(encoding="utf-8")
    assert "#kpiTiles," in theme or "#kpiTiles {" in theme
    assert ".kpi-row" in theme
    # Shared rule (and local ONS rule) use the site gap token.
    assert "margin-bottom: var(--gap)" in theme
    ons = (root / "ons" / "dashboard.py").read_text(encoding="utf-8")
    assert "#kpiTiles{margin-bottom:var(--gap)}" in ons.replace(" ", "")
    for name in ("desk", "pld", "precos", "supply"):
        src = (root / name / "dashboard.py").read_text(encoding="utf-8")
        assert "margin-bottom: var(--gap)" in src
        assert ".kpi-row" in src
    flows = (root / "flows" / "dashboard.py").read_text(encoding="utf-8")
    assert ".kpi-card-wrap" in flows
    assert "margin-bottom: var(--gap)" in flows


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
    # paint() must not read `t` unguarded: JS_I18N declares it later in the
    # same script, so an early init would hit the temporal dead zone.
    assert "try {" in js and "typeof t === \"function\"" in js


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


def test_built_dashboards_ship_tooltip_dismiss():
    root = Path(__file__).resolve().parents[1]
    for name in ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos"):
        html = (root / name / "index.html").read_text(encoding="utf-8")
        assert "function hideChartTooltips()" in html, name
        assert 'addEventListener("scroll", hideFromScroll' in html, name
        assert 'addEventListener("pagehide", hideChartTooltips)' in html, name
        assert "if (__gbChartTtScrollLock) return;" in html, name


def test_chart_tooltip_js_binds_mobile_dismiss():
    js = kit.chart_palette_js()

    assert "function hideChartTooltips()" in js
    assert "function bindChartTooltipDismiss()" in js
    assert "bindChartTooltipDismiss();" in js
    assert 'addEventListener("scroll", hideFromScroll' in js
    assert "capture: true, passive: true" in js
    assert 'addEventListener("pagehide", hideChartTooltips)' in js
    assert 'addEventListener("pageshow", hideChartTooltips)' in js
    assert 'addEventListener("hashchange", hideChartTooltips)' in js
    assert 'addEventListener("pointercancel", hideFromScroll, true)' in js
    assert 't.closest("svg")' in js
    assert "if (__gbChartTtScrollLock) return;" in js
    assert "watchChartTooltipAnchor" in js
    assert "IntersectionObserver" in js


def test_chart_tooltip_hides_on_scroll_nav_and_outside_tap(tmp_path):
    """Behavioral check of the inlined tooltip JS against a tiny DOM mock."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the tooltip dismiss harness")

    harness = tmp_path / "tooltip_dismiss.js"
    harness.write_text(
        _CHART_TOOLTIP_DISMISS_HARNESS.replace("__CHART_JS__", kit.chart_palette_js()),
        encoding="utf-8",
    )
    subprocess.run([node, str(harness)], check=True)


_CHART_TOOLTIP_DISMISS_HARNESS = r"""
"use strict";

const windowListeners = {};
const documentListeners = {};
function store(map, type, fn, opts) {
  (map[type] = map[type] || []).push({ fn, opts });
}
function fire(map, type, ev) {
  (map[type] || []).forEach((h) => h.fn(ev || {}));
}

const svg = {
  tagName: "SVG",
  closest(sel) { return sel === "svg" ? this : null; },
};
const outside = {
  tagName: "BUTTON",
  closest() { return null; },
};
const tt = {
  className: "tt",
  style: { display: "none", left: "", top: "" },
  offsetWidth: 120,
  offsetHeight: 40,
  _gbIo: null,
  closest(sel) { return sel === ".tt" ? this : null; },
};

global.window = {
  innerWidth: 390,
  innerHeight: 844,
  __gbChartTtBound: undefined,
  addEventListener(type, fn, opts) { store(windowListeners, type, fn, opts); },
  clearTimeout(id) { clearTimeout(id); },
  setTimeout(fn, ms) { return setTimeout(fn, ms); },
};
global.document = {
  visibilityState: "visible",
  querySelectorAll(sel) { return sel === ".tt" ? [tt] : []; },
  elementFromPoint() { return svg; },
  addEventListener(type, fn, opts) { store(documentListeners, type, fn, opts); },
};
global.IntersectionObserver = function (cb) {
  this.observe = function () {};
  this.disconnect = function () {};
  this._cb = cb;
};

__CHART_JS__

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(window.__gbChartTtBound === true, "dismiss listeners bind on load");
assert((windowListeners.scroll || []).length === 1, "scroll listener");
assert(windowListeners.scroll[0].opts && windowListeners.scroll[0].opts.capture === true,
  "scroll uses capture so overflow containers count");
assert((windowListeners.pagehide || []).length === 1, "pagehide listener");
assert((windowListeners.hashchange || []).length === 1, "hashchange listener");
assert((documentListeners.pointerdown || []).length === 1, "pointerdown listener");
assert((documentListeners.pointercancel || []).length === 1, "pointercancel listener");

placeChartTooltip(tt, 80, 120);
assert(tt.style.display === "block", "tooltip shows");
assert(tt.style.left && tt.style.top, "tooltip is positioned");

fire(windowListeners, "scroll");
assert(tt.style.display === "none", "scroll hides tooltip");

placeChartTooltip(tt, 80, 120);
assert(tt.style.display === "none", "scroll lock blocks reshow mid-gesture");

placeChartTooltip(tt, 80, 120);
// lock still held; simulate lock expiry then show
__gbChartTtScrollLock = false;
placeChartTooltip(tt, 80, 120);
assert(tt.style.display === "block", "tooltip can show after scroll lock");

fire(documentListeners, "pointerdown", { target: svg });
assert(tt.style.display === "block", "tap on chart keeps tooltip");

fire(documentListeners, "pointerdown", { target: outside });
assert(tt.style.display === "none", "tap outside chart hides tooltip");

__gbChartTtScrollLock = false;
placeChartTooltip(tt, 80, 120);
fire(windowListeners, "pagehide");
assert(tt.style.display === "none", "pagehide hides tooltip");

__gbChartTtScrollLock = false;
placeChartTooltip(tt, 80, 120);
fire(windowListeners, "hashchange");
assert(tt.style.display === "none", "hashchange hides tooltip");

__gbChartTtScrollLock = false;
placeChartTooltip(tt, 80, 120);
fire(documentListeners, "pointercancel");
assert(tt.style.display === "none", "pointercancel (scroll takeover) hides tooltip");

console.log("ok");
"""

