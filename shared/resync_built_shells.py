#!/usr/bin/env python3
"""Refresh embedded shared theme + products menu in committed dashboard shells.

Dashboard rebuilds normally run via each site's dashboard.py; this helper
patches index.html when parquet/data is unavailable in CI/dev.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import dashboard_kit as kit

ROOT = Path(__file__).resolve().parents[1]
SITES = ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos", "mago")
THEME_START = "/*\n * GasBrazil.com shared design tokens"
TYPO_MARKER = "/* Shared header/label"
PAGE_CSS_MARKERS: dict[str, str] = {
    "desk": "* { box-sizing: border-box; }",
    "flows": "* { box-sizing: border-box; }",
    "pld": "* { box-sizing: border-box; }",
    "precos": "* { box-sizing: border-box; }",
    "supply": "* { box-sizing: border-box; }",
    "mago": "* { box-sizing: border-box; }",
    "contratos": "/* Everything below is this dashboard's own layout/components",
    "poc": "/* Everything below is this dashboard's own layout/components",
    "ons": "/* Everything below is ons-dashboard's own layout/components",
}


def _brand_link_html() -> str:
    home = kit._SITES["home"]
    return (
        f'<a class="masthead-brand" id="link-home" href="{home["custom"]}" '
        f'data-i18n="navHome">{home["label"]}</a>'
    )


def resync_theme(html: str, theme: str, site_id: str) -> str:
    start = html.find(THEME_START)
    if start < 0:
        raise ValueError("shared theme block not found")
    marker = PAGE_CSS_MARKERS[site_id]
    end = html.find(marker, start)
    if end < 0:
        raise ValueError(f"page CSS marker not found for {site_id}: {marker!r}")
    return html[:start] + theme + html[end:]


def resync_typo_weights(html: str) -> str:
    block = kit.typo_weight_css().strip() + "\n"
    if TYPO_MARKER in html:
        # Remove any duplicates first
        while html.count(TYPO_MARKER) > 1:
            html = re.sub(
                r"/\* Shared header/label[\s\S]*?\n\}\n",
                "",
                html,
                count=1,
            )
        html = re.sub(
            r"/\* Shared header/label[\s\S]*?\n\}\n",
            block,
            html,
            count=1,
        )
        return html
    pos = html.find("</style>")
    if pos < 0:
        raise ValueError("no </style> in shell")
    return html[:pos] + block + html[pos:]


def resync_products_dd(html: str, site_id: str) -> str:
    new_dd = kit.products_dropdown_html(site_id, _brand_link_html())
    pattern = r'<div class="products-dd">[\s\S]*?<span class="crumb-sep"'
    if not re.search(pattern, html):
        raise ValueError("products-dd block not found")
    return re.sub(pattern, new_dd + '\n      <span class="crumb-sep"', html, count=1)


def resync_favicon(html: str) -> str:
    return re.sub(
        r'<link rel="icon" href="data:image/png;base64,[A-Za-z0-9+/=]+">',
        '<link rel="icon" href="/shared/favicon.png">',
        html,
    )


def resync_font_preloads(html: str) -> str:
    return re.sub(
        r'<link rel="preload" href="/shared/fonts/([^"]+)\.ttf" as="font" type="font/ttf" crossorigin>',
        r'<link rel="preload" href="/shared/fonts/\1.woff2" as="font" type="font/woff2" crossorigin>',
        html,
    )


def resync_head_hints(html: str) -> str:
    hints = (
        '<link rel="preconnect" href="https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev" crossorigin>\n'
        '<link rel="dns-prefetch" href="https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev">\n'
        '<meta name="theme-color" content="#06080c">\n'
    )
    if "pub-c07957ad735e48b796eae989fa9e678d.r2.dev" not in html:
        m = re.search(r'(<link rel="canonical"[^>]*>\n?)', html)
        if m:
            html = html[:m.end()] + hints + html[m.end():]
        else:
            pos = html.find("</head>")
            if pos >= 0:
                html = html[:pos] + hints + html[pos:]
    return html


def resync_decode_js(html: str) -> str:
    if "function showBootError" in html:
        pattern = r"function b64ToBytes\(b64\) \{[\s\S]*?errorBox\.remove\(\);\s*retryFn\(\);\s*\}\);\s*\}\s*\}\s*\}"
    else:
        pattern = r"function b64ToBytes\(b64\) \{[\s\S]*?return JSON\.parse\(safe\);\s*\}"
    replacement = kit.JS_DECODE.strip()
    return re.sub(pattern, lambda _: replacement, html, count=1)


def resync_i18n_js(html: str) -> str:
    if "/* __GB_I18N_END__ */" in html:
        pattern = r"const LANG_KEY = \"gasbrazil-lang\";[\s\S]*?/\* __GB_I18N_END__ \*/"
    else:
        pattern = r"const LANG_KEY = \"gasbrazil-lang\";[\s\S]*?if \(onChange\) onChange\(next\);\s*\}\);\s*\}"
    replacement = kit.JS_I18N.strip()
    return re.sub(pattern, lambda _: replacement, html, count=1)


def resync_boot_resilience(html: str) -> str:
    pattern = r'(\n  )const (text|json) = await inflateGzipUrl\(PAYLOAD_URL\);\n  DATA = (JSON\.parse|parseDashboardJson)\(\2\);'
    replacement = (
        r'\1try {\n'
        r'\1  const \2 = await inflateGzipUrl(PAYLOAD_URL);\n'
        r'\1  DATA = \3(\2);\n'
        r'\1} catch (err) {\n'
        r'\1  console.error(err);\n'
        r'\1  showBootError(err, () => init());\n'
        r'\1  return;\n'
        r'\1}'
    )
    html = re.sub(pattern, replacement, html, count=1)

    # Specific error handler upgrades for existing try/catch dashboards:
    html = re.sub(
        r'const el = document\.getElementById\("data-notes"\);\s*el\.hidden = false;\s*el\.textContent = String\(err && err\.message \|\| err\);',
        'showBootError(err, () => init());',
        html,
    )
    html = re.sub(
        r'document\.getElementById\("kpi-row"\)\.innerHTML = \'<div class="kpi-cell"><div class="lbl">Error</div>[\s\S]*?</div></div>\';',
        'showBootError(err, () => init());',
        html,
    )
    html = re.sub(
        r'document\.getElementById\("boot"\)\.innerHTML =\s*"Could not load dashboard data\.<br>"\+escapeHtml\(String\(err && err\.message \|\| err\)\);',
        'document.getElementById("boot").innerHTML = ""; showBootError(err, () => boot(), "#boot");',
        html,
    )
    return html


def resync_footer_shortcuts(html: str) -> str:
    if 'id="link-shortcuts"' in html:
        return html
    btn = ' &middot; <button type="button" class="footer-link-btn" id="link-shortcuts" data-i18n="shortcutsBtn">Shortcuts (?)</button>'
    if 'data-i18n="footerAbout"' in html:
        return re.sub(r'(<a [^>]*data-i18n="footerAbout"[^>]*>.*?</a>)', r'\1' + btn, html, count=1)
    if 'mailto:eb@gasbrazil.com' in html:
        return re.sub(r'(\s*&middot;\s*(?:Contact: )?<a href="mailto:eb@gasbrazil.com")', btn + r'\1', html, count=1)
    if '</footer>' in html:
        return html.replace('</footer>', f'{btn}\n</footer>')
    return html


def resync_search_btn(html: str) -> str:
    if 'id="gb-search-trigger"' in html:
        return html
    btn = (
        '<button type="button" class="gb-search-btn" id="gb-search-trigger" aria-label="Search (Ctrl+K)" title="Search (Ctrl+K)">'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
        '<span data-i18n="searchBtn">Search</span> <kbd>Ctrl+K</kbd>'
        '</button>'
    )
    if '<div class="nav-trail">' in html:
        return re.sub(
            r'(<div class="nav-trail">[\s\S]*?)(</div>)',
            rf'\1{btn}\2',
            html,
            count=1,
        )
    return html


def resync_site(site_id: str) -> None:
    path = ROOT / site_id / "index.html"
    html = path.read_text(encoding="utf-8")
    html = resync_theme(html, kit.render_theme_css(), site_id)
    html = resync_typo_weights(html)
    html = resync_products_dd(html, site_id)
    html = resync_favicon(html)
    html = resync_font_preloads(html)
    html = resync_head_hints(html)
    html = resync_decode_js(html)
    html = resync_i18n_js(html)
    html = resync_boot_resilience(html)
    html = resync_footer_shortcuts(html)
    html = resync_search_btn(html)
    path.write_text(html, encoding="utf-8")
    print(f"resynced {path.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    sites = argv if argv else list(SITES)
    for site in sites:
        if site not in kit._SITES and site != "home":
            print(f"skip unknown site {site}", file=sys.stderr)
            continue
        resync_site(site)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

