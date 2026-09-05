#!/usr/bin/env python3
"""
Builds the GasBrazil.com landing page, About page, and branded 404.

Static chrome -- no live fetch -- but it still runs through
shared/dashboard_kit.py so colors and font come from the same theme as
ons/, poc/, and contratos/. KPI teasers are read from the committed
parquet stores (and a light parse of ons/index.html) at build time.
"""
from __future__ import annotations

import datetime as dt
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


def collect_status() -> dict:
    """Headline numbers for the hub cards. Missing stores degrade to None."""
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
    }

    ons_html = ROOT / "ons" / "index.html"
    if ons_html.exists():
        text = ons_html.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"Last refreshed\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC)", text)
        if m:
            status["ons_when"] = m.group(1)
        # Prefer a gas-generation figure if the current HTML still has one.
        g = re.search(r"Gas verified generation.*?([0-9][0-9,]*)\s*MWmed", text, re.S)
        if g:
            status["ons_kpi"] = f"{g.group(1)} MWmed gas"
            status["ons_kpi_pt"] = f"{g.group(1)} MWmed a gás"

    flows_html = ROOT / "flows" / "index.html"
    if flows_html.exists():
        text = flows_html.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"generated:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC)", text)
        if m:
            status["flows_when"] = m.group(1)
        kpi = re.search(r"kpi_total_7d:\s*([0-9.]+)", text)
        npts = re.search(r"n_points:\s*(\d+)", text)
        if kpi and kpi.group(1):
            total = float(kpi.group(1))
            vol_label = f"{total / 1000:.1f}M" if total >= 1000 else f"{total:.0f}"
            n_label = f" · {npts.group(1)} points" if npts and npts.group(1) else ""
            status["flows_kpi"] = f"{vol_label} m³ realized (7d){n_label}"
            status["flows_kpi_pt"] = f"{vol_label} m³ realizados (7d){n_label}"

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
    except Exception:
        pass
    return status


SHARED_PAGE_CSS = """
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--text); font-family: var(--font);
  display: flex; flex-direction: column; min-height: 100vh;
}
.topbar {
  position: fixed; top: 16px; right: 16px; z-index: 20;
  display: flex; gap: 6px;
}
#theme-toggle {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 6px; width: 34px; height: 34px; cursor: pointer; color: var(--muted2);
  display: flex; align-items: center; justify-content: center;
}
#theme-toggle svg { width: 17px; height: 17px; }
main.hub { flex: 1; width: var(--content-w); max-width: 820px; margin: 0 auto;
  padding: 72px 0 40px; }
@media (max-width: 900px) { main.hub { width: auto; padding: 72px 16px 40px; } }
.wordmark { font-size: 30px; font-weight: 700; letter-spacing: -.01em; }
.wordmark .dot { color: var(--accent); }
.wordmark a { color: inherit; text-decoration: none; }
.tagline { color: var(--muted); font-size: 15px; margin-top: 8px; max-width: 40em; line-height: 1.5; }
.flagbar { width: 120px; margin: 22px 0 0; }
.lead { margin-top: 22px; font-size: 14.5px; line-height: 1.55; max-width: 42em; }
.lead strong { font-weight: 650; }
.lead .muted { color: var(--muted2); display: block; margin-top: 8px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 12px; margin-top: 26px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px;
  text-align: left; text-decoration: none; color: var(--text);
  transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
  display: flex; flex-direction: column;
}
.card:hover { box-shadow: 0 8px 24px var(--ring); transform: translateY(-2px); border-color: var(--accent); }
.card .name { font-size: 16px; font-weight: 700; display: flex; align-items: center;
  justify-content: space-between; gap: 8px; }
.card .name .arrow { color: var(--accent); font-weight: 400; transition: transform .15s ease; }
.card:hover .name .arrow { transform: translateX(3px); }
.card .desc { color: var(--muted); font-size: 13px; margin-top: 8px; line-height: 1.5; flex: 1; }
.card .kpi { margin-top: 12px; font-size: 13px; font-weight: 650; color: var(--text); }
.card .when { color: var(--muted); font-size: 11.5px; margin-top: 4px; }
.sources-block { margin-top: 28px; }
.sources-block .label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); font-weight: 600; margin-bottom: 8px; }
.sources-block .row { display: flex; flex-wrap: wrap; gap: 6px; }
.sources-block a {
  font-size: 12px; color: var(--muted2); text-decoration: none;
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px;
}
.sources-block a:hover { background: var(--accent-soft); color: var(--text); border-color: var(--border-strong); }
.prose { margin-top: 8px; max-width: 42em; }
.prose h2 { font-size: 16px; margin: 22px 0 6px; }
.prose p, .prose li { font-size: 14px; line-height: 1.6; color: var(--muted2); }
.prose ul { padding-left: 1.2em; }
footer.site { padding: 14px 24px; color: var(--muted); font-size: 11.5px; text-align: center; }
footer.site a { color: var(--muted); }
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


def _topbar() -> str:
    return """<a class="skip-link" href="#main" data-i18n="skip">Skip to content</a>
<div class="topbar chrome-tools">
  <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
  <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
</div>
"""


def _footer(home_href: str = "./") -> str:
    return f"""<footer class="site">
  &copy; <span id="year"></span> GasBrazil.com
  &middot; <a href="{home_href}about/" data-i18n="footerAbout">About &amp; methodology</a>
  &middot; <span data-i18n="contact">Contact</span>: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
<script>
__SHARED_JS_THEME_TOGGLE__
__SHARED_JS_I18N__
document.getElementById("year").textContent = new Date().getFullYear();
initThemeToggle("theme-toggle");
initLangToggle("lang-toggle");
</script>
</body>
</html>
"""


HOME_TEMPLATE = """__HEAD__
<body>
__TOPBAR__
<main class="hub" id="main">
  <div class="wordmark">GasBrazil<span class="dot">.</span>com</div>
  <p class="tagline" data-i18n="tagline">Data tools for Brazil's natural gas market &mdash; grid balances, pipeline flows and capacity, and contracted transport activity, refreshed daily.</p>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="lead">
    <strong data-i18n="aboutLead">Independent, public-data dashboards. Nothing here is an official ONS, ANP, CCEE, or transportadora product.</strong>
    <span class="muted" data-i18n="aboutBody">GasBrazil.com consolidates open Brazilian gas and power data into self-contained tools you can filter, chart, and export. Numbers come from public APIs and open-data portals; caveats live on each dashboard and on the About page.</span>
  </div>
  <div class="cards">
    <a class="card" href="ons/">
      <div class="name"><span data-i18n="cardOns">ONS Balances</span><span class="arrow">&rarr;</span></div>
      <div class="desc" data-i18n="cardOnsDesc">Daily grid balances, thermal generation by plant, and gas-fired dispatch across Brazil's interconnected power system.</div>
      <div class="kpi" data-en="__ONS_KPI__" data-pt="__ONS_KPI_PT__">__ONS_KPI__</div>
      <div class="when" data-refresh="__ONS_WHEN__"></div>
    </a>
    <a class="card" href="poc/">
      <div class="name"><span data-i18n="cardPoc">POC Results</span><span class="arrow">&rarr;</span></div>
      <div class="desc" data-i18n="cardPocDesc">Pipeline capacity offer results — balancing, GUS acquisition, and linepack trades across TBG, TAG, and NTS.</div>
      <div class="kpi" data-en="__POC_KPI__" data-pt="__POC_KPI_PT__">__POC_KPI__</div>
      <div class="when" data-refresh="__POC_WHEN__"></div>
    </a>
    <a class="card" href="contratos/">
      <div class="name"><span data-i18n="cardContratos">POC Contracts</span><span class="arrow">&rarr;</span></div>
      <div class="desc" data-i18n="cardContratosDesc">Active transport and master transport contracts across TBG, TAG, and NTS. Legacy and access-connection contracts are not yet included.</div>
      <div class="kpi" data-en="__CON_KPI__" data-pt="__CON_KPI_PT__">__CON_KPI__</div>
      <div class="when" data-refresh="__CON_WHEN__"></div>
    </a>
    <a class="card" href="flows/">
      <div class="name"><span data-i18n="cardFlows">Pipeline Flows</span><span class="arrow">&rarr;</span></div>
      <div class="desc" data-i18n="cardFlowsDesc">Daily physical gas flow at every receipt and delivery point on Brazil's transport pipelines, plus system-use gas, losses, imbalance, and linepack.</div>
      <div class="kpi" data-en="__FLOWS_KPI__" data-pt="__FLOWS_KPI_PT__">__FLOWS_KPI__</div>
      <div class="when" data-refresh="__FLOWS_WHEN__"></div>
    </a>
  </div>
  <div class="sources-block">
    <div class="label" data-i18n="sources">Official sources</div>
    <div class="row">
      <a href="https://dados.ons.org.br" target="_blank" rel="noopener" data-i18n="sourceOns">ONS open data</a>
      <a href="https://www.ofertadecapacidade.com.br/PEG/resultado" target="_blank" rel="noopener" data-i18n="sourcePoc">Portal de Oferta de Capacidade</a>
      <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/paineis-dinamicos-da-anp/painel-dinamico-de-movimentacao-de-gas-natural-em-gasodutos-de-transporte" target="_blank" rel="noopener" data-i18n="sourceAnp">ANP gas transport movement</a>
      <a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/dados-consolidados-movimentacao-de-gas-natural-em-gasodutos-de-transporte" target="_blank" rel="noopener" data-i18n="sourceFlows">ANP open data — pipeline movement</a>
    </div>
  </div>
</main>
__FOOTER__
<script>
function paintRefreshLabels() {
  const prefix = t("kpiRefresh");
  document.querySelectorAll(".when[data-refresh]").forEach(el => {
    const when = el.getAttribute("data-refresh");
    el.textContent = when ? prefix + " " + when : "";
  });
  document.querySelectorAll(".kpi[data-en]").forEach(el => {
    const en = el.getAttribute("data-en");
    const pt = el.getAttribute("data-pt");
    const val = currentLang() === "pt" ? (pt || en) : en;
    el.textContent = val || "";
    el.hidden = !val;
  });
}
const _apply = applyI18n;
applyI18n = function() { _apply(); paintRefreshLabels(); };
paintRefreshLabels();
</script>
"""


ABOUT_TEMPLATE = """__HEAD__
<body>
__TOPBAR__
<main class="hub" id="main">
  <div class="wordmark"><a href="../">GasBrazil<span class="dot">.</span>com</a></div>
  <h1 style="font-size:22px;margin:18px 0 0" data-i18n="aboutH1">About GasBrazil</h1>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="prose">
    <h2 data-i18n="aboutWho">What this is</h2>
    <p data-i18n="aboutWhoBody">A small independent site that republishes public Brazilian natural-gas and power-system data as filterable dashboards. It is not affiliated with ONS, ANP, CCEE, TBG, TAG, or NTS.</p>
    <h2 data-i18n="aboutHow">How the data is built</h2>
    <p data-i18n="aboutHowBody">Each dashboard is a single static HTML file. GitHub Actions fetch the source, transform it, and embed a compressed payload in the page. There is no live API behind the published site.</p>
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
    <p>
      <a href="../ons/">ONS</a> · <a href="../poc/">POC</a> · <a href="../contratos/">Contratos</a> · <a href="../flows/">Flows</a> ·
      <a href="../ons/wiki-html/">ONS wiki</a>
    </p>
  </div>
</main>
__FOOTER__
"""


NOTFOUND_TEMPLATE = """__HEAD__
<body>
__TOPBAR__
<main class="hub" id="main">
  <div class="wordmark"><a href="./">GasBrazil<span class="dot">.</span>com</a></div>
  <h1 style="font-size:22px;margin:18px 0 0" data-i18n="notFound">This page is not here.</h1>
  <p class="tagline" data-i18n="notFoundBody">The hub and dashboards are linked below.</p>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="cards" style="margin-top:22px">
    <a class="card" href="./"><div class="name"><span data-i18n="backHome">Back to GasBrazil.com</span><span class="arrow">&rarr;</span></div></a>
    <a class="card" href="ons/"><div class="name"><span data-i18n="cardOns">ONS Balances</span><span class="arrow">&rarr;</span></div></a>
    <a class="card" href="poc/"><div class="name"><span data-i18n="cardPoc">POC Results</span><span class="arrow">&rarr;</span></div></a>
    <a class="card" href="contratos/"><div class="name"><span data-i18n="cardContratos">POC Contracts</span><span class="arrow">&rarr;</span></div></a>
    <a class="card" href="flows/"><div class="name"><span data-i18n="cardFlows">Pipeline Flows</span><span class="arrow">&rarr;</span></div></a>
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
        FAVICON_DATA_URI=kit.embed_favicon(),
        **extra,
    )


def write_home(out_path: Path | str = DEFAULT_OUT) -> Path:
    st = collect_status()
    html = HOME_TEMPLATE
    html = html.replace("__HEAD__", _head(
        "GasBrazil.com",
        "Independent data tools for Brazil's natural gas market: ONS grid balances, POC capacity results, and transport contracts.",
        "/",
    ))
    html = html.replace("__TOPBAR__", _topbar())
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
    html = html.replace("__TOPBAR__", _topbar())
    html = html.replace("__FOOTER__", _footer("../"))
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
    html = html.replace("__TOPBAR__", _topbar())
    html = html.replace("__FOOTER__", _footer("./"))
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
    urls = ["/", "/ons/", "/poc/", "/contratos/", "/flows/", "/about/"]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>https://gasbrazil.com{u}</loc><lastmod>{today}</lastmod></url>\n"
    body += "</urlset>\n"
    (ROOT / "sitemap.xml").write_text(body, encoding="utf-8")
    print("Wrote robots.txt and sitemap.xml")


def write_all() -> None:
    write_home()
    write_about()
    write_404()
    write_robots_and_sitemap()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        write_home(sys.argv[1])
        write_about()
        write_404()
        write_robots_and_sitemap()
    else:
        write_all()
