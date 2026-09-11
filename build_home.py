#!/usr/bin/env python3
"""
Builds the GasBrazil.com landing page, About page, and branded 404.

Static chrome -- no live fetch -- but it still runs through
shared/dashboard_kit.py so colors and font come from the same theme as
ons/, poc/, and contratos/. KPI teasers are read from committed HTML
comment markers (and light parquet scrapes) at build time.
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import dashboard_kit as kit  # noqa: E402

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "index.html"


def _fmt_num(n: float, digits: int = 0) -> str:
    s = f"{n:,.{digits}f}"
    return s


def _last_non_null(arr: list) -> tuple[int | None, float | None]:
    for i in range(len(arr) - 1, -1, -1):
        v = arr[i]
        if v is not None:
            try:
                return i, float(v)
            except (TypeError, ValueError):
                continue
    return None, None


def _ons_teaser_from_html(text: str) -> tuple[str | None, str | None, str | None]:
    """Pull ONS hub teaser from HTML comment markers (ADR-002 Track B).

    Falls back to a light HTML scrape for older committed shells that still
    embed a literal gas-generation figure.
    """
    kpi = kpi_pt = when = None
    m = re.search(r"generated:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC)", text)
    if m:
        when = m.group(1)
    g = re.search(r"kpi_gas_mwmed:\s*([0-9]+)", text)
    if g and g.group(1):
        n = f"{int(g.group(1)):,}"
        kpi = f"{n} MWmed gas"
        kpi_pt = f"{n} MWmed a gás"
    # Legacy embed path (pre–Track B shells) — keep until CI has republished.
    if kpi is None or when is None:
        emb = re.search(r'id="payload">([A-Za-z0-9+/=]+)</script>', text)
        if emb:
            try:
                data = json.loads(gzip.decompress(base64.b64decode(emb.group(1))))
                if when is None and data.get("generated"):
                    when = str(data["generated"])
                if kpi is None:
                    series = data.get("series") or {}
                    arr = series.get("gen_gas|SIN|") or series.get("gen_gas|SIN") or []
                    _idx, val = _last_non_null(arr if isinstance(arr, list) else [])
                    if val is not None:
                        n = f"{int(round(val)):,}"
                        kpi = f"{n} MWmed gas"
                        kpi_pt = f"{n} MWmed a gás"
            except Exception:
                pass
    if when is None:
        m = re.search(r"Last refreshed\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC)", text)
        if m:
            when = m.group(1)
    if kpi is None:
        g = re.search(r"Gas verified generation.*?([0-9][0-9,]*)\s*MWmed", text, re.S)
        if g:
            kpi = f"{g.group(1)} MWmed gas"
            kpi_pt = f"{g.group(1)} MWmed a gás"
    return kpi, kpi_pt, when


def _sparkline_svg(values: list[float], *, width: int = 120, height: int = 28) -> str:
    """Compact polyline sparkline for hub KPI cells. Empty input → \"\"."""
    nums = [float(v) for v in values if v is not None]
    if len(nums) < 2:
        return ""
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1.0
    pad = 2
    pts = []
    n = len(nums)
    for i, v in enumerate(nums):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = height - pad - (height - 2 * pad) * ((v - lo) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="kpi-spark" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" aria-hidden="true">'
        f'<polyline points="{" ".join(pts)}"/></svg>'
    )


def collect_status() -> dict:
    """Headline numbers for the hub cards. Missing stores degrade to None."""
    import data_kit as dk  # noqa: E402
    import publish_teasers as pt  # noqa: E402

    status: dict = {
        "ons_kpi": None,
        "ons_kpi_pt": None,
        "ons_when": None,
        "poc_kpi": None,
        "poc_kpi_pt": None,
        "poc_when": None,
        "contratos_kpi": None,
        "contratos_kpi_pt": None,
        "contratos_when": None,
        "flows_kpi": None,
        "flows_kpi_pt": None,
        "flows_when": None,
        "supply_kpi": None,
        "supply_kpi_pt": None,
        "supply_when": None,
        "pld_kpi": None,
        "pld_kpi_pt": None,
        "pld_when": None,
        "precos_kpi": None,
        "precos_kpi_pt": None,
        "precos_when": None,
        "desk_kpi": None,
        "desk_kpi_pt": None,
        "desk_when": None,
        "supply_spark": "",
        "pld_spark": "",
        "poc_spark": "",
        "teasers_url": dk.teaser_url(),
    }
    for key, val in pt.status_from_teasers().items():
        if val:
            status[key] = val

    # Legacy ONS embed fallback when the committed shell has no KPI marker.
    if not status["ons_kpi"]:
        ons_html = ROOT / "ons" / "index.html"
        if ons_html.exists():
            kpi, kpi_pt, when = _ons_teaser_from_html(ons_html.read_text(encoding="utf-8"))
            status["ons_kpi"] = kpi
            status["ons_kpi_pt"] = kpi_pt
            status["ons_when"] = when or status["ons_when"]

    try:
        import pandas as pd

        poc = ROOT / "poc" / "data" / "poc_results.parquet"
        if poc.exists():
            df = pd.read_parquet(poc)
            if "Trade Date" in df.columns:
                dates = pd.to_datetime(df["Trade Date"], errors="coerce")
                latest = dates.max()
                if pd.notna(latest):
                    status["poc_when"] = latest.strftime("%Y-%m-%d")
                    cutoff = latest - pd.Timedelta(days=7)
                    week = df.loc[dates >= cutoff]
                    if "Price" in week.columns and week["Price"].notna().any():
                        avg = float(week["Price"].mean())
                        n = int(week["Price"].notna().sum())
                        status["poc_kpi"] = f"{avg:.2f} R$/MMBtu · {n} trades (7d)"
                        status["poc_kpi_pt"] = f"{avg:.2f} R$/MMBtu · {n} negócios (7d)"

        con = ROOT / "contratos" / "data" / "contratos.parquet"
        if con.exists():
            df = pd.read_parquet(con)
            status_col = df["Status"].astype(str) if "Status" in df.columns else None
            if status_col is not None:
                active = df[status_col.str.casefold() != "concluded"]
            else:
                active = df
            cap_col = "Contracted Capacity (000 m3/d)"
            cap = float(active[cap_col].sum()) if cap_col in active.columns else 0
            n = len(active)
            status["contratos_kpi"] = f"{n:,} contracts · {_fmt_num(cap, 0)} thousand m³/d"
            status["contratos_kpi_pt"] = f"{n:,} contratos · {_fmt_num(cap, 0)} mil m³/d"
            status["contratos_when"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

        # Hub sparklines (last ~24 points) from committed / rebuilt parquet.
        if poc.exists() and "Trade Date" in pd.read_parquet(poc, columns=["Trade Date"]).columns:
            pdf = pd.read_parquet(poc)
            if "Price" in pdf.columns and "Trade Date" in pdf.columns:
                pdf = pdf.dropna(subset=["Trade Date", "Price"]).copy()
                pdf["Trade Date"] = pd.to_datetime(pdf["Trade Date"], errors="coerce")
                pdf = pdf.dropna(subset=["Trade Date"]).sort_values("Trade Date")
                daily = pdf.groupby(pdf["Trade Date"].dt.floor("D"))["Price"].mean().tail(24)
                status["poc_spark"] = _sparkline_svg(daily.tolist())

        supply_pq = ROOT / "supply" / "data" / "supply_monthly.parquet"
        if supply_pq.exists():
            sdf = pd.read_parquet(supply_pq)
            col = "production" if "production" in sdf.columns else None
            if col and "month" in sdf.columns:
                sdf = sdf.dropna(subset=["month", col]).sort_values("month")
                status["supply_spark"] = _sparkline_svg(sdf[col].tail(24).tolist())

        pld_pq = ROOT / "pld" / "data" / "pld_daily.parquet"
        if pld_pq.exists():
            ldf = pd.read_parquet(pld_pq)
            ldf["date"] = pd.to_datetime(ldf["date"], errors="coerce")
            se = ldf[ldf["submarket"].astype(str).str.upper().isin(["SE", "SUDESTE"])]
            se = se.dropna(subset=["date", "pld"]).sort_values("date")
            status["pld_spark"] = _sparkline_svg(se["pld"].tail(45).tolist())
    except Exception:
        pass
    return status


SHARED_PAGE_CSS = """
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background-color: var(--bg); background-image: var(--bg-grad);
  background-attachment: fixed; color: var(--text); font-family: var(--font);
  font-weight: 300; display: flex; flex-direction: column; min-height: 100vh;
}
#theme-toggle {
  background: var(--panel); border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm); width: 34px; height: 34px; cursor: pointer; color: var(--text);
  display: flex; align-items: center; justify-content: center;
}
#theme-toggle svg { width: 17px; height: 17px; }
/* Match dashboard .wrap: shared --content-w / --content-max (~1280px). */
main.hub { flex: 1; width: var(--content-w); max-width: var(--content-max); margin: 0 auto;
  padding: 40px 0 48px; }
@media (max-width: 900px) { main.hub { width: auto; padding: 28px 16px 40px; } }
/* Home's own header row -- wordmark-menu left, Wiki/About + PT/theme right. */
.hub-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.hub-header .products-dd { align-items: center; }
.hub-header .dd-trigger { height: 32px; }
.hub-controls { display: flex; align-items: center; gap: 6px 14px; flex: none; }
.hub-controls .nav-trail { margin-left: 0; }
.hub-controls #theme-toggle { position: static; }
.wordmark { font-size: 30px; font-weight: 600; letter-spacing: -.02em; line-height: 1.1; }
.wordmark .dot { color: var(--accent); }
.wordmark a { color: inherit; text-decoration: none; }
.tagline { color: var(--text); font-weight: 600; font-size: 15px; margin: 10px 0 0;
  max-width: 36em; line-height: 1.45; }
/* Full-width flagband — do not override shared .flagbar width. */
.flagbar { margin: 18px 0 0; }
/* KPI strip is the only product launcher on the hub (description cards removed). */
.kpi-strip {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 8px; margin-top: 16px;
}
@media (max-width: 900px) { .kpi-strip { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .kpi-strip { grid-template-columns: 1fr; } }
.kpi-cell {
  position: relative; overflow: hidden;
  background: var(--panel-grad); border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 8px 10px; text-decoration: none; color: var(--text);
  display: flex; flex-direction: column; gap: 2px; min-width: 0;
  box-shadow: 0 1px 0 rgba(255,255,255,.55) inset, 0 1px 3px rgba(0,39,118,.04);
  transition: border-color .3s ease, transform .3s ease, background .3s ease, box-shadow .3s ease;
}
.kpi-cell::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--brz-blue); opacity: 0; transition: opacity .3s ease;
}
.kpi-cell:nth-child(3n+1)::before { background: var(--brz-green); }
.kpi-cell:nth-child(3n+2)::before { background: var(--brz-yellow); }
.kpi-cell:nth-child(3n+3)::before { background: var(--brz-blue); }
.kpi-cell:hover {
  border-color: var(--border-strong); background: var(--panel-grad-hover);
  transform: translateY(-4px); box-shadow: var(--elevate);
}
.kpi-cell:hover::before { opacity: 1; }
.kpi-cell .kpi-label { font-size: 13px; font-weight: 600; color: var(--text); letter-spacing: -.01em;
  display: flex; align-items: baseline; gap: 6px; }
/* Wayfinding affordance: KPI cells are links that open dashboards. The arrow
   slides in on hover/focus so the cards read as launchers, not stat widgets. */
.kpi-cell .kpi-label::after {
  content: "\\2192"; color: var(--accent); font-weight: 400; font-size: 12px;
  opacity: 0; transform: translateX(-4px);
  transition: opacity .25s ease, transform .25s ease;
}
.kpi-cell:hover .kpi-label::after, .kpi-cell:focus-visible .kpi-label::after {
  opacity: 1; transform: none;
}
[data-theme="dark"] .kpi-cell .kpi-label::after { color: var(--brz-yellow); }
.kpi-cell .kpi-role { font-size: 11px; font-weight: 300; color: var(--muted); line-height: 1.3; }
.kpi-cell .kpi-val { font-size: 12px; font-weight: 400; color: var(--muted2);
  line-height: 1.35; min-height: 1.1em; margin-top: 2px; font-variant-numeric: tabular-nums; }
.kpi-cell .kpi-when { font-size: 10px; font-weight: 300; color: var(--muted); min-height: 1em; margin-top: auto; padding-top: 4px; }
.kpi-spark { display: block; width: 100%; height: 20px; margin-top: 2px; color: var(--accent); }
.kpi-spark polyline { fill: none; stroke: currentColor; stroke-width: 1.5;
  stroke-linejoin: round; stroke-linecap: round; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 12px; margin-top: 20px; }
@media (max-width: 720px) { .cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .cards { grid-template-columns: 1fr; } }
.card {
  position: relative; overflow: hidden;
  background: var(--panel-grad); border: 1px solid var(--border); border-radius: var(--radius);
  padding: var(--card-pad);
  text-align: left; text-decoration: none; color: var(--text);
  box-shadow: 0 1px 0 rgba(255,255,255,.55) inset, 0 1px 3px rgba(0,39,118,.04);
  transition: border-color .3s ease, transform .3s ease, background .3s ease, box-shadow .3s ease;
  display: flex; flex-direction: column;
}
.card:hover {
  border-color: var(--border-strong); background: var(--panel-grad-hover);
  transform: translateY(-4px); box-shadow: var(--elevate);
}
.card .name { font-size: 14px; font-weight: 400; display: flex; align-items: center;
  gap: 8px; }
.card .name .dot { width: 6px; height: 6px; border-radius: 50%; flex: none; background: var(--accent); }
.card .desc { color: var(--muted); font-weight: 300; font-size: 12.5px; margin-top: 6px;
  line-height: 1.45; flex: 1; }
.hub-page-title { font-size: 22px; font-weight: 600; margin: 20px 0 0; letter-spacing: -.01em; }
.sources-block { margin-top: 28px; }
.sources-block .label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); font-weight: 300; margin-bottom: 10px; }
.sources-block .row { display: flex; flex-wrap: wrap; gap: 8px; }
.sources-block a {
  font-size: 12px; font-weight: 400; color: var(--muted2); text-decoration: none;
  border: 1px solid var(--ring); border-radius: var(--radius-sm); padding: 5px 12px;
  white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;
  background: var(--panel-grad);
  transition: border-color .3s ease, transform .3s ease, background .3s ease, box-shadow .3s ease, color .3s ease;
}
.sources-block a:hover {
  background: var(--panel-grad-hover); color: var(--text); border-color: var(--border-strong);
  transform: translateY(-2px); box-shadow: var(--elevate);
}
[data-theme="dark"] .sources-block a:hover {
  border-color: rgba(255, 223, 0, .35);
  box-shadow: var(--elevate), 0 0 0 1px rgba(255, 223, 0, .12);
}
.sources-block .ext-icon { width: 10px; height: 10px; display: inline-block; flex: none; opacity: .75; }
.prose { margin-top: 8px; max-width: 42em; }
.prose h2 { font-size: 16px; font-weight: 400; margin: 22px 0 6px; }
.prose p, .prose li { font-size: 14px; font-weight: 300; line-height: 1.6; color: var(--muted2); }
.prose ul { padding-left: 1.2em; }
[data-theme="dark"] .kpi-cell,
[data-theme="dark"] .card {
  box-shadow: 0 1px 0 rgba(255,255,255,.05) inset, 0 1px 3px rgba(0,0,0,.35);
  border-color: rgba(255,255,255,.08);
}
[data-theme="dark"] .kpi-cell:hover,
[data-theme="dark"] .card:hover {
  border-color: rgba(255, 223, 0, .35);
  box-shadow: var(--elevate), 0 0 0 1px rgba(255, 223, 0, .12);
}
footer.site { padding: 20px 24px; color: var(--muted); font-weight: 300; font-size: 13px; text-align: center; line-height: 1.7; }
/* Keyboard users: every hub link and control gets a visible focus ring. */
.kpi-cell:focus-visible, .card:focus-visible,
.sources-block a:focus-visible, .hub-controls button:focus-visible,
footer.site a:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
[data-theme="dark"] .kpi-cell:focus-visible, [data-theme="dark"] .card:focus-visible,
[data-theme="dark"] .sources-block a:focus-visible,
[data-theme="dark"] .hub-controls button:focus-visible,
[data-theme="dark"] footer.site a:focus-visible {
  outline-color: var(--brz-yellow);
}
@media (max-width: 480px) {
  .kpi-cell { padding: 12px 14px; }
  .sources-block a { padding: 9px 14px; }
}
footer.site a {
  color: var(--accent); text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color .25s ease, border-color .25s ease;
}
footer.site a:hover { color: var(--text); border-bottom-color: var(--brz-yellow); }
[data-theme="dark"] footer.site a:hover { color: var(--brz-yellow); border-bottom-color: var(--brz-yellow); }
"""


def _head(title: str, description: str, path: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{kit.seo_head(title=title, description=description, path=path)}
<link rel="icon" href="__FAVICON_DATA_URI__">
<script>__SHARED_JS_BOOT__</script>
<style>
__SHARED_THEME_CSS__
{SHARED_PAGE_CSS}
</style>
</head>
"""


def _hub_controls(wiki_href: str, about_href: str) -> str:
    return f"""<div class="hub-controls">
      <div class="nav-trail">
        <a class="navlink" href="{wiki_href}" data-i18n="navWiki">Wiki</a>
        <a class="navlink" href="{about_href}" data-i18n="navAbout">About</a>
      </div>
      <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
      <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
    </div>"""


def _footer(home_href: str = "./") -> str:
    return f"""<footer class="site">
  &copy; <span id="year"></span> GasBrazil
  &middot; <a href="{home_href}wiki/" data-i18n="navWiki">Wiki</a>
  &middot; <a href="{home_href}about/" data-i18n="footerAbout">About &amp; methodology</a>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
<script>
__SHARED_JS_DECODE__
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
document.getElementById("year").textContent = new Date().getFullYear();
initThemeToggle("theme-toggle");
initLangToggle("lang-toggle");
</script>
""" + kit._PRODUCTS_DROPDOWN_JS + """
</body>
</html>
"""


HOME_TEMPLATE = """__HEAD__
<body>
<a class="skip-link" href="#main" data-i18n="skip">Skip to content</a>
<main class="hub" id="main">
  <div class="hub-header">
    __BRAND_MENU__
    __HUB_CONTROLS__
  </div>
  <p class="tagline" data-i18n="tagline">Analytical Firepower for Brazil's Energy Markets</p>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="kpi-strip">
    <a class="kpi-cell" href="desk/" data-slug="desk">
      <div class="kpi-label" data-i18n="cardDesk">The Desk</div>
      <div class="kpi-role">Cross-product snapshot</div>
      <div class="kpi-val" data-en="__DESK_KPI__" data-pt="__DESK_KPI_PT__">__DESK_KPI__</div>
      <div class="kpi-when" data-refresh="__DESK_WHEN__"></div>
    </a>
    <a class="kpi-cell" href="ons/" data-slug="ons">
      <div class="kpi-label" data-i18n="cardOns">ONS Balances</div>
      <div class="kpi-role">Grid &amp; gas dispatch</div>
      <div class="kpi-val" data-en="__ONS_KPI__" data-pt="__ONS_KPI_PT__">__ONS_KPI__</div>
      <div class="kpi-when" data-refresh="__ONS_WHEN__"></div>
    </a>
    <a class="kpi-cell" href="pld/" data-slug="pld">
      <div class="kpi-label" data-i18n="cardPld">PLD Prices</div>
      <div class="kpi-role">Power settlement</div>
      <div class="kpi-val" data-en="__PLD_KPI__" data-pt="__PLD_KPI_PT__">__PLD_KPI__</div>
      <div class="kpi-when" data-refresh="__PLD_WHEN__"></div>
      __PLD_SPARK__
    </a>
    <a class="kpi-cell" href="poc/" data-slug="poc">
      <div class="kpi-label" data-i18n="cardPoc">POC Results</div>
      <div class="kpi-role">Capacity auctions</div>
      <div class="kpi-val" data-en="__POC_KPI__" data-pt="__POC_KPI_PT__">__POC_KPI__</div>
      <div class="kpi-when" data-refresh="__POC_WHEN__"></div>
      __POC_SPARK__
    </a>
    <a class="kpi-cell" href="contratos/" data-slug="contratos">
      <div class="kpi-label" data-i18n="cardContratos">POC Contracts</div>
      <div class="kpi-role">Firm transport</div>
      <div class="kpi-val" data-en="__CON_KPI__" data-pt="__CON_KPI_PT__">__CON_KPI__</div>
      <div class="kpi-when" data-refresh="__CON_WHEN__"></div>
    </a>
    <a class="kpi-cell" href="flows/" data-slug="flows">
      <div class="kpi-label" data-i18n="cardFlows">Pipeline Flows</div>
      <div class="kpi-role">Physical movement</div>
      <div class="kpi-val" data-en="__FLOWS_KPI__" data-pt="__FLOWS_KPI_PT__">__FLOWS_KPI__</div>
      <div class="kpi-when" data-refresh="__FLOWS_WHEN__"></div>
    </a>
    <a class="kpi-cell" href="supply/" data-slug="supply">
      <div class="kpi-label" data-i18n="cardSupply">Gas Supply</div>
      <div class="kpi-role">National balance</div>
      <div class="kpi-val" data-en="__SUPPLY_KPI__" data-pt="__SUPPLY_KPI_PT__">__SUPPLY_KPI__</div>
      <div class="kpi-when" data-refresh="__SUPPLY_WHEN__"></div>
      __SUPPLY_SPARK__
    </a>
    <a class="kpi-cell" href="precos/" data-slug="precos">
      <div class="kpi-label" data-i18n="cardPrecos">ANP Prices</div>
      <div class="kpi-role">Disclosed R$/MMBtu</div>
      <div class="kpi-val" data-en="__PRECOS_KPI__" data-pt="__PRECOS_KPI_PT__">__PRECOS_KPI__</div>
      <div class="kpi-when" data-refresh="__PRECOS_WHEN__"></div>
    </a>
  </div>
  <div class="sources-block">
    <div class="label" data-i18n="sources">Sources</div>
    <div class="row">
      <a href="https://dados.ons.org.br" target="_blank" rel="noopener">ONS<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
      <a href="https://www.ofertadecapacidade.com.br/PEG/resultado" target="_blank" rel="noopener">POC<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
      <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/dados-consolidados-movimentacao-de-gas-natural-em-gasodutos-de-transporte" target="_blank" rel="noopener">ANP<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
      <a href="https://dadosabertos.ccee.org.br/dataset/pld_media_diaria" target="_blank" rel="noopener">CCEE<svg class="ext-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>
    </div>
  </div>
</main>
__FOOTER__
<script>
const TEASERS_URL = "__TEASERS_URL__";
function paintRefreshLabels() {
  document.querySelectorAll(".kpi-when[data-refresh]").forEach(el => {
    const when = el.getAttribute("data-refresh");
    el.textContent = when ? when : "";
  });
  document.querySelectorAll(".kpi-val[data-en]").forEach(el => {
    const en = el.getAttribute("data-en");
    const pt = el.getAttribute("data-pt");
    const val = currentLang() === "pt" ? (pt || en) : en;
    el.textContent = val || "";
    el.hidden = !val;
  });
}
async function loadLiveTeasers() {
  if (!TEASERS_URL || TEASERS_URL.indexOf("teasers") < 0) return;
  try {
    const raw = await inflateGzipUrl(TEASERS_URL);
    const data = JSON.parse(raw);
    const items = (data && data.items) || data || {};
    document.querySelectorAll(".kpi-cell[data-slug]").forEach(cell => {
      const slug = cell.getAttribute("data-slug");
      const t = items[slug];
      if (!t) return;
      const val = cell.querySelector(".kpi-val");
      const when = cell.querySelector(".kpi-when");
      if (val && (t.kpi || t.kpiEn)) {
        const en = t.kpiEn || t.kpi || "";
        const pt = t.kpiPt || en;
        val.setAttribute("data-en", en);
        val.setAttribute("data-pt", pt);
      }
      if (when && t.when) when.setAttribute("data-refresh", t.when);
    });
    paintRefreshLabels();
  } catch (e) {
    /* Build-time markers remain the fallback. */
  }
}
const _apply = applyI18n;
applyI18n = function() { _apply(); paintRefreshLabels(); };
paintRefreshLabels();
loadLiveTeasers();
</script>
"""


ABOUT_TEMPLATE = """__HEAD__
<body>
<a class="skip-link" href="#main" data-i18n="skip">Skip to content</a>
<main class="hub" id="main">
  <div class="hub-header">
    __BRAND_MENU__
    __HUB_CONTROLS__
  </div>
  <h1 class="hub-page-title" data-i18n="aboutH1">About GasBrazil</h1>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="prose">
    <h2 data-i18n="aboutWho">What this is</h2>
    <p data-i18n="aboutWhoBody">A small independent site that republishes public Brazilian natural-gas and power-system data as filterable dashboards. It is not affiliated with ONS, ANP, CCEE, TBG, TAG, or NTS.</p>
    <h2 data-i18n="aboutHow">How the data is built</h2>
    <p data-i18n="aboutHowBody">Each dashboard is a static page on GitHub Pages. GitHub Actions fetch the source, transform it, and publish an HTML shell (plus a gzip data artifact for the larger dashboards). There is no live API behind the published site.</p>
    <h2 data-i18n="aboutGloss">Glossary</h2>
    <ul>
      <li data-i18n="glossGus">GUS — gas acquired by a transportadora for system use.</li>
      <li data-i18n="glossLinepack">Linepack — inventory held inside the pipeline, traded to balance the network.</li>
      <li data-i18n="glossBal">Residual / operational balancing — short-term PEG processes that clear imbalances.</li>
      <li data-i18n="glossCmo">CMO — ONS marginal operating cost (R$/MWh). Not the same as CCEE's PLD settlement price.</li>
      <li data-i18n="glossMaster">Master transport contract — framework that enables later transport nominations; not itself a firm capacity booking.</li>
    </ul>
    <h2 data-i18n="aboutCover">Coverage limits</h2>
    <p data-i18n="aboutCoverBody">POC Contracts currently include Transport Contract and Master Contract rows. Legacy transport contracts and access connections are on the official portal but are not in this feed yet.</p>
    <p data-i18n="aboutCoverFlows">Pipeline Flows has no published ANP data for 2022, and each month is typically released with a lag of several weeks. Average pressure and shipper-level detail are collected but not shown on the dashboard; both are available in the underlying data files in the repository.</p>
    <p data-i18n="aboutCoverSupply">Gas Supply uses ANP PPGN-EL national monthly series plus national natural-gas imports. The open import CSV does not split Bolivia pipeline vs LNG cargoes.</p>
    <p data-i18n="aboutCoverPrecos">ANP Prices are Resolution 52/2011 monthly disclosures (tax-inclusive R$/MMBtu), not assessed spot benchmarks. Some thermal and Other Basins months are suppressed when too few counterparties report.</p>
    <p data-i18n="aboutCoverPld">PLD: CCEE daily averages and hourly prices by submarket; peak is hours 18–20 on weekdays. Optional ONS CMO and median gas CVU when lake data is present.</p>
    <p data-i18n="aboutCoverDesk">The Desk: cross-product headline series. Full history and filters live on each product page.</p>
    <p>
      <a href="../ons/">ONS</a> · <a href="../poc/">POC</a> · <a href="../contratos/">Contratos</a> · <a href="../flows/">Flows</a> · <a href="../supply/">Supply</a> · <a href="../precos/">ANP Prices</a> · <a href="../pld/">PLD</a> · <a href="../desk/">The Desk</a> ·
      <a href="../ons/wiki-html/">ONS wiki</a>
    </p>
  </div>
</main>
__FOOTER__
"""


NOTFOUND_TEMPLATE = """__HEAD__
<body>
<a class="skip-link" href="#main" data-i18n="skip">Skip to content</a>
<main class="hub" id="main">
  <div class="hub-header">
    __BRAND_MENU__
    __HUB_CONTROLS__
  </div>
  <h1 class="hub-page-title" data-i18n="notFound">This page is not here.</h1>
  <p class="tagline" data-i18n="notFoundBody">The hub and dashboards are linked below.</p>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="cards">
    <a class="card" href="./" style="grid-column: 1 / -1"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="backHome">Back to GasBrazil.com</span></div></a>
    <a class="card" href="ons/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardOns">ONS Balances</span></div></a>
    <a class="card" href="poc/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardPoc">POC Results</span></div></a>
    <a class="card" href="contratos/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardContratos">POC Contracts</span></div></a>
    <a class="card" href="flows/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardFlows">Pipeline Flows</span></div></a>
    <a class="card" href="supply/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardSupply">Gas Supply</span></div></a>
    <a class="card" href="precos/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardPrecos">ANP Prices</span></div></a>
    <a class="card" href="pld/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardPld">PLD Prices</span></div></a>
    <a class="card" href="desk/"><div class="name"><span class="dot" aria-hidden="true"></span><span data-i18n="cardDesk">The Desk</span></div></a>
  </div>
</main>
__FOOTER__
"""


def _kit_render(template: str, **extra: str) -> str:
    return kit.render(
        template,
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        SHARED_JS_I18N=kit.JS_I18N,
        SHARED_JS_BOOT=kit.JS_BOOT,
        SHARED_JS_DECODE=kit.JS_DECODE,
        FAVICON_DATA_URI=kit.embed_favicon(),
        **extra,
    )


def write_home(out_path: Path | str = DEFAULT_OUT) -> Path:
    st = collect_status()
    html = HOME_TEMPLATE
    html = html.replace("__HEAD__", _head(
        "GasBrazil.com",
        "Independent data tools for Brazil's natural gas market: ONS grid balances, POC capacity results, transport contracts, pipeline flows, and CCEE PLD prices.",
        "/",
    ))
    html = html.replace("__FOOTER__", _footer("./"))
    html = html.replace("__ONS_KPI__", st["ons_kpi"] or "")
    html = html.replace("__ONS_KPI_PT__", st["ons_kpi_pt"] or st["ons_kpi"] or "")
    html = html.replace("__ONS_WHEN__", st["ons_when"] or "")
    html = html.replace("__POC_KPI__", st["poc_kpi"] or "")
    html = html.replace("__POC_KPI_PT__", st["poc_kpi_pt"] or st["poc_kpi"] or "")
    html = html.replace("__POC_WHEN__", st["poc_when"] or "")
    html = html.replace("__CON_KPI__", st["contratos_kpi"] or "")
    html = html.replace("__CON_KPI_PT__", st["contratos_kpi_pt"] or st["contratos_kpi"] or "")
    html = html.replace("__CON_WHEN__", st["contratos_when"] or "")
    html = html.replace("__FLOWS_KPI__", st["flows_kpi"] or "")
    html = html.replace("__FLOWS_KPI_PT__", st["flows_kpi_pt"] or st["flows_kpi"] or "")
    html = html.replace("__FLOWS_WHEN__", st["flows_when"] or "")
    html = html.replace("__SUPPLY_KPI__", st["supply_kpi"] or "")
    html = html.replace("__SUPPLY_KPI_PT__", st["supply_kpi_pt"] or st["supply_kpi"] or "")
    html = html.replace("__SUPPLY_WHEN__", st["supply_when"] or "")
    html = html.replace("__PLD_KPI__", st["pld_kpi"] or "")
    html = html.replace("__PLD_KPI_PT__", st["pld_kpi_pt"] or st["pld_kpi"] or "")
    html = html.replace("__PLD_WHEN__", st["pld_when"] or "")
    html = html.replace("__PRECOS_KPI__", st.get("precos_kpi") or "")
    html = html.replace("__PRECOS_KPI_PT__", st.get("precos_kpi_pt") or st.get("precos_kpi") or "")
    html = html.replace("__PRECOS_WHEN__", st.get("precos_when") or "")
    html = html.replace("__DESK_KPI__", st.get("desk_kpi") or "")
    html = html.replace("__DESK_KPI_PT__", st.get("desk_kpi_pt") or st.get("desk_kpi") or "")
    html = html.replace("__DESK_WHEN__", st.get("desk_when") or "")
    html = html.replace("__POC_SPARK__", st.get("poc_spark") or "")
    html = html.replace("__SUPPLY_SPARK__", st.get("supply_spark") or "")
    html = html.replace("__PLD_SPARK__", st.get("pld_spark") or "")
    html = html.replace("__TEASERS_URL__", st.get("teasers_url") or "")
    html = html.replace("__HUB_CONTROLS__", _hub_controls("wiki/", "about/"))
    html = html.replace(
        "__BRAND_MENU__",
        kit.products_dropdown_html("home", '<div class="wordmark">GasBrazil</div>'),
    )
    html = _kit_render(html)
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote home page ({len(html):,} bytes) to {out_path}")
    return out_path


def write_about(out_path: Path | None = None) -> Path:
    out_path = out_path or (ROOT / "about" / "index.html")
    html = ABOUT_TEMPLATE
    html = html.replace("__HEAD__", _head(
        "About — GasBrazil.com",
        "How GasBrazil.com is built, what the data covers, and a short glossary of PEG and ONS terms.",
        "/about/",
    ))
    html = html.replace("__FOOTER__", _footer("../"))
    html = html.replace("__HUB_CONTROLS__", _hub_controls("../wiki/", "./"))
    html = html.replace(
        "__BRAND_MENU__",
        kit.products_dropdown_html("home", '<div class="wordmark"><a href="../">GasBrazil</a></div>'),
    )
    # About lives in /about/, so home-relative links in the footer need ../
    html = html.replace('href="./about/"', 'href="./"')
    html = _kit_render(html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote about page ({len(html):,} bytes) to {out_path}")
    return out_path


def write_404(out_path: Path | None = None) -> Path:
    out_path = out_path or (ROOT / "404.html")
    html = NOTFOUND_TEMPLATE
    html = html.replace("__HEAD__", _head(
        "Not found — GasBrazil.com",
        "This page is not on GasBrazil.com.",
        "/",
    ))
    html = html.replace("__FOOTER__", _footer("./"))
    html = html.replace("__HUB_CONTROLS__", _hub_controls("wiki/", "about/"))
    html = html.replace(
        "__BRAND_MENU__",
        kit.products_dropdown_html("home", '<div class="wordmark"><a href="./">GasBrazil</a></div>'),
    )
    html = _kit_render(html)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote 404 page ({len(html):,} bytes) to {out_path}")
    return out_path


def write_robots_and_sitemap() -> None:
    (ROOT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://gasbrazil.com/sitemap.xml\n",
        encoding="utf-8",
    )
    today = dt.date.today().isoformat()
    urls = ["/", "/ons/", "/poc/", "/contratos/", "/flows/", "/supply/", "/precos/", "/pld/", "/desk/", "/wiki/", "/about/"]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>https://gasbrazil.com{u}</loc><lastmod>{today}</lastmod></url>\n"
    body += "</urlset>\n"
    (ROOT / "sitemap.xml").write_text(body, encoding="utf-8")
    print("Wrote robots.txt and sitemap.xml")


def publish_teasers_best_effort() -> None:
    """Write hub/teasers.json.gz when shared/publish_teasers.py is available."""
    try:
        sys.path.insert(0, str(ROOT / "shared"))
        import publish_teasers as pt  # noqa: E402

        payload = pt.collect()
        import data_kit as dk  # noqa: E402

        path, url = dk.write_and_publish_teasers(payload, ROOT / "hub")
        print(f"Wrote teasers ({len(payload.get('items', {}))} items) -> {path} / {url}")
    except Exception as exc:
        print(f"teasers skipped: {exc}")


def write_all() -> None:
    write_home()
    write_about()
    write_404()
    write_robots_and_sitemap()
    publish_teasers_best_effort()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        write_home(sys.argv[1])
        write_about()
        write_404()
        write_robots_and_sitemap()
        publish_teasers_best_effort()
    else:
        write_all()
