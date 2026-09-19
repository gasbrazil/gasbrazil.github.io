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
SITES = ("desk", "ons", "pld", "poc", "contratos", "flows", "supply", "precos")
THEME_START = "/*\n * GasBrazil.com shared design tokens"
PAGE_CSS_MARKERS: dict[str, str] = {
    "desk": "* { box-sizing: border-box; }",
    "flows": "* { box-sizing: border-box; }",
    "pld": "* { box-sizing: border-box; }",
    "precos": "* { box-sizing: border-box; }",
    "supply": "* { box-sizing: border-box; }",
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


def resync_products_dd(html: str, site_id: str) -> str:
    new_dd = kit.products_dropdown_html(site_id, _brand_link_html())
    pattern = r'<div class="products-dd">[\s\S]*?<span class="crumb-sep"'
    if not re.search(pattern, html):
        raise ValueError("products-dd block not found")
    return re.sub(pattern, new_dd + '\n      <span class="crumb-sep"', html, count=1)


def resync_site(site_id: str) -> None:
    path = ROOT / site_id / "index.html"
    html = path.read_text(encoding="utf-8")
    html = resync_theme(html, kit.render_theme_css(), site_id)
    html = resync_products_dd(html, site_id)
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
