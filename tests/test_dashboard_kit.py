from __future__ import annotations

import html
import re
from pathlib import Path

import dashboard_kit as kit
import pytest


def test_js_boot_binds_flagbar_header_glow():
    assert "bindFlagbarHeaderGlow" in kit.JS_BOOT
    assert "flag-glow" in kit.JS_BOOT


def test_theme_uses_display_font_on_nav_chrome():
    css = kit.render_theme_css()
    assert ".dd-menu a" in css and "var(--font-display)" in css
    assert ".navlink" in css
    assert "Brand / navigation chrome" in css


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
    assert 'class="brand-mark-dot"' in mast
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


def test_theme_native_selects_follow_dark_mode():
    css = kit.render_theme_css()
    assert "html[data-theme=\"dark\"] select" in css
    assert "color-scheme: dark" in css
    assert "select option" in css


def test_products_dropdown_wraps_brand():
    html = kit.products_dropdown_html("home", '<div class="wordmark">GasBrazil</div>')
    assert html.startswith('<div class="products-dd">')
    assert '<div class="wordmark">GasBrazil</div>' in html
    assert 'class="brand-lockup"' in html
    assert html.find("wordmark") < html.find("brand-mark")
    assert html.find("brand-mark") < html.find("dd-menu")
    assert "\u2630" not in html
    assert 'class="brand-mark-dot"' in html
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
    assert "analysisSeriesColor" in src
    assert 'id="analysis-clear"' in src
    assert "desk-tabs" in src
    assert "analysis-workspace-inner" in src
    assert "analysis-sidebar" in src


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


def test_phase3_theme_css_shortcuts_and_table_tools():
    css = kit.render_theme_css()
    assert ".gb-toast" in css
    assert ".table-copy-btn" in css
    assert "th.has-filter" in css
    assert ".shortcuts-modal-card" in css
    assert ".shortcut-row" in css
    assert ".footer-link-btn" in css


def test_phase3_i18n_strings_and_modal_markup():
    assert "shortcutsTitle:" in kit.JS_I18N
    assert "copyTable:" in kit.JS_I18N
    assert "tableCopied:" in kit.JS_I18N
    assert "shortcutsBtn:" in kit.JS_I18N


def test_phase3_global_shortcuts_and_table_tsv_functions():
    assert "function gbShowToast(" in kit.JS_I18N
    assert "function gbCopyTableAsTsv(" in kit.JS_I18N
    assert "function gbBindTableCopyButtons(" in kit.JS_I18N
    assert "function toggleShortcutsModal(" in kit.JS_I18N
    assert "function initGlobalShortcuts(" in kit.JS_I18N
    assert "/* __GB_I18N_END__ */" in kit.JS_I18N


def test_build_sort_filter_th_has_filter_class():
    assert 'th.classList.add("has-filter")' in kit.JS_TABLE_SORT
    assert 'th.classList.toggle("has-filter", !!filterInput.value)' in kit.JS_TABLE_SORT


def test_command_palette_theme_css_and_markup():
    css = kit.render_theme_css()
    assert ".gb-palette-backdrop" in css
    assert ".gb-palette-card" in css
    assert ".gb-palette-input" in css
    assert ".gb-palette-results" in css
    assert ".gb-search-btn" in css
    assert ".chart-export-btn" in css
    assert ".pulse-dot" in css
    assert "gb-pulse" in css


def test_command_palette_js_and_catalog():
    assert "function toggleCommandPalette(" in kit.JS_I18N
    assert "function getPaletteCatalog(" in kit.JS_I18N
    assert "function renderPaletteResults(" in kit.JS_I18N
    assert "function executePaletteItem(" in kit.JS_I18N
    assert "function gbExportChartPng(" in kit.JS_I18N
    assert "function gbBindChartExportButtons(" in kit.JS_I18N
    assert "e.key === \"k\" || e.key === \"K\"" in kit.JS_I18N
    assert 'modal.id = "gb-command-palette"' in kit.JS_I18N


def test_command_palette_i18n_strings():
    assert "searchBtn:" in kit.JS_I18N
    assert "searchPlaceholder:" in kit.JS_I18N
    assert "paletteDashboards:" in kit.JS_I18N
    assert "palettePoints:" in kit.JS_I18N
    assert "exportPng:" in kit.JS_I18N
    assert "exportPngTitle:" in kit.JS_I18N
    assert "freshLive:" in kit.JS_I18N


def test_masthead_includes_search_button():
    mast = kit.masthead_html("desk")
    assert 'id="gb-search-trigger"' in mast
    assert 'class="gb-search-btn"' in mast
    assert 'data-i18n="searchBtn"' in mast
    assert "Ctrl+K" in mast


def test_mago_heatmap_theme_css_and_i18n():
    css = kit.render_theme_css()
    assert ".hm-summary-grid" in css
    assert ".hm-summary-tile" in css
    assert ".hm-calendar-grid" in css
    assert ".hm-day-card" in css
    assert ".hm-risk-bar" in css
    assert ".hm-poc-callout" in css

    assert "magoHeatmapTitle:" in kit.JS_I18N
    assert "magoHmCompliance:" in kit.JS_I18N
    assert "magoHmAlertHours:" in kit.JS_I18N
    assert "magoHmCriticalHours:" in kit.JS_I18N
    assert "magoHmViewPoc:" in kit.JS_I18N


def test_sub_menu_structure_and_categories():
    cat_ids = [c["id"] for c in kit.NAV_CATEGORIES]
    assert "gas" in cat_ids
    assert "power" in cat_ids

    menu = kit.products_dropdown_html("desk", '<div class="wordmark">GasBrazil</div>')
    assert "dd-sub-wrap" in menu
    assert "dd-sub-trigger" in menu
    assert "dd-sub-menu" in menu
    assert 'data-i18n="navCatGas"' in menu
    assert 'data-i18n="navCatPower"' in menu

    # Clean items without emojis or bloated descriptions
    assert "🔥" not in menu
    assert "⚡" not in menu
    assert "dd-mega-banner" not in menu
    assert "dd-item-desc" not in menu
    assert "dd-badge" not in menu

    # Monitor is present, TAG & NTS standalone are removed from main dropdown
    assert 'href="/monitor/"' in menu
    assert 'href="/mago/"' not in menu
    assert 'href="/nts/"' not in menu


def test_navigation_root_relative_links_for_dual_domain():
    menu = kit.products_dropdown_html("home", '<div class="wordmark">GasBrazil</div>')
    # All dashboard product links must be root-relative for dual-domain support
    assert 'href="/desk/"' in menu
    assert 'href="/ons/"' in menu
    assert 'href="/pld/"' in menu
    assert 'href="/flows/"' in menu
    assert 'href="/monitor/"' in menu
    assert 'href="https://gasbrazil.com/desk/"' not in menu
    assert 'href="https://gasbrazil.com/monitor/"' not in menu

    # Client-side dynamic sync for dual-domain support (gasbrazil.github.io <-> gasbrazil.com)
    js = kit._PRODUCTS_DROPDOWN_JS
    assert "syncCrossLinks" in js
    assert "gasbrazil.github.io" in js


def test_command_palette_and_shortcuts_use_monitor():
    # Palette items catalog inside JS_I18N
    assert '{ cat: "dashboards", id: "monitor"' in kit.JS_I18N
    assert 'url: "/monitor/"' in kit.JS_I18N
    assert '{ cat: "dashboards", id: "mago"' not in kit.JS_I18N
    assert '{ cat: "dashboards", id: "nts"' not in kit.JS_I18N

    # Keywords indexed for pipeline search
    assert '"tag", "nts", "mago"' in kit.JS_I18N

    # Shortcuts in JS_I18N
    assert '"m": "/monitor/"' in kit.JS_I18N
    assert "Pipeline Monitor" in kit.JS_I18N


def test_home_page_clean_structure():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    index_html = (root / "index.html").read_text(encoding="utf-8")
    assert "hub-filter-bar" not in index_html
    assert "hub-filter-btn" not in index_html
    assert "card-cat-badge" not in index_html
    assert "data-category=" not in index_html
    assert "initHubFilters" not in index_html
    assert "kpi-strip" in index_html
    assert "kpi-cell" in index_html
    assert 'class="sources-block"' not in index_html


def test_clean_page_bottoms_and_standard_footers():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    dashboards = ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos", "mago", "nts", "monitor")
    for site in dashboards:
        html = (root / site / "index.html").read_text(encoding="utf-8")
        # No exposed sources block on pages; sources are tucked behind methodology / wiki
        assert 'class="sources"' not in html, f"found exposed sources bar in {site}"
        # No AI copy
        assert "Analytical Firepower" not in html, f"found buzzword in {site}"
        assert "Executive cross-market synthesis" not in html, f"found buzzword in {site}"
        # Methodology details has clean link to wiki
        assert 'data-i18n="navWiki"' in html, f"missing wiki link in {site}"

    # Verify standard footer helper
    footer = kit.standard_footer_html("../")
    assert 'data-i18n="navWiki"' in footer
    assert 'data-i18n="footerAbout"' in footer
    assert 'id="link-shortcuts"' in footer
    assert "eb@gasbrazil.com" in footer


def test_resync_i18n_js_idempotent_and_single_escape_html():
    """Issue 1 regression test: resync_i18n_js must not duplicate escapeHtml on successive runs."""
    from resync_built_shells import resync_escape_html, resync_i18n_js

    root = Path(__file__).resolve().parents[1]
    desk_path = root / "desk" / "index.html"
    content = desk_path.read_text(encoding="utf-8")

    # Run once
    step1 = resync_escape_html(content)
    step1 = resync_i18n_js(step1)
    assert step1.count("function escapeHtml") == 1
    assert not re.search(r"^[ \t]*\[c\]\)\);", step1, re.MULTILINE)

    # Run second time
    step2 = resync_escape_html(step1)
    step2 = resync_i18n_js(step2)
    assert step2 == step1
    assert step2.count("function escapeHtml") == 1
    assert not re.search(r"^[ \t]*\[c\]\)\);", step2, re.MULTILINE)


def test_resync_i18n_js_deduplicates_multiple_copies():
    from resync_built_shells import resync_i18n_js

    dup_html = """
    <script>
    function escapeHtml(s) {
      return 1;
    }
    function escapeHtml(s) {
      return 2;
    }
    function escapeHtml(s) {
      return 3;
    }
    const LANG_KEY = "gasbrazil-lang";
    /* __GB_I18N_END__ */
    </script>
    """
    resynced = resync_i18n_js(dup_html)
    assert resynced.count("function escapeHtml") == 1
    resynced2 = resync_i18n_js(resynced)
    assert resynced2 == resynced
    assert resynced2.count("function escapeHtml") == 1


def test_shells_have_no_broken_escape_html_remnants():
    """Ensure no committed dashboard shell contains orphan [c])); syntax error fragments."""
    root = Path(__file__).resolve().parents[1]
    for html_file in root.glob("*/index.html"):
        content = html_file.read_text(encoding="utf-8")
        assert not re.search(r"^[ \t]*\[c\]\)\);", content, re.MULTILINE), f"Broken escapeHtml fragment found in {html_file}"
