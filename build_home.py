#!/usr/bin/env python3
"""
Builds the GasBrazil.com landing page (repo-root index.html).

Static content -- no data pipeline, no external fetch -- but it still runs
through shared/dashboard_kit.py so its colors and font come from the same
shared/theme.css as ons/, poc/, and contratos/. That's the whole point of
the consolidation: change shared/theme.css once and every page, including
this one, picks it up on its next rebuild (see ADR-001, Decision 2 Option C).

Usage:
    python build_home.py [out_path]   # default: index.html
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import dashboard_kit as kit  # noqa: E402  (must follow sys.path.insert)

DEFAULT_OUT = Path(__file__).resolve().parent / "index.html"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GasBrazil.com</title>
<link rel="icon" href="__FAVICON_DATA_URI__">
<style>
__SHARED_THEME_CSS__
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--text); font-family: var(--font);
  display: flex; flex-direction: column; min-height: 100vh;
}
#theme-toggle {
  position: fixed; top: 20px; right: 20px; background: none; border: 1px solid var(--border);
  border-radius: 8px; width: 34px; height: 34px; cursor: pointer; color: var(--muted2);
  display: flex; align-items: center; justify-content: center;
}
#theme-toggle svg { width: 17px; height: 17px; }
main { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 24px; text-align: center; }
.wordmark { font-size: 30px; font-weight: 700; letter-spacing: -.01em; }
.wordmark .dot { color: var(--accent); }
.tagline { color: var(--muted); font-size: 15px; margin-top: 8px; max-width: 32em; }
.flagbar { width: 120px; margin: 22px auto 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; margin-top: 32px; width: 100%; max-width: 720px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px 20px;
  text-align: left; text-decoration: none; color: var(--text);
  transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
}
.card:hover { box-shadow: 0 8px 24px var(--ring); transform: translateY(-2px); border-color: var(--accent); }
.card .name { font-size: 16px; font-weight: 700; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card .name .arrow { color: var(--accent); font-weight: 400; transition: transform .15s ease; }
.card:hover .name .arrow { transform: translateX(3px); }
.card .desc { color: var(--muted); font-size: 13px; margin-top: 8px; line-height: 1.5; }
.card .url { color: var(--accent); font-size: 11.5px; margin-top: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
footer { padding: 20px 24px; color: var(--muted); font-size: 11.5px; text-align: center; flex: none; }
footer a { color: var(--muted); }
</style>
</head>
<body>
<button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
<main>
  <div class="wordmark">GasBrazil<span class="dot">.</span>com</div>
  <div class="tagline">Data tools for Brazil's natural gas market &mdash; grid balances, pipeline capacity, and contracted transport activity, refreshed daily.</div>
  <div class="flagbar" aria-hidden="true"></div>
  <div class="cards" id="cards"></div>
</main>
<footer>
  &copy; <span id="year"></span> GasBrazil.com &middot; Contact: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>
</footer>
<script>
// Add a future page here and it appears on the hub automatically. Paths are
// relative -- this same file serves gasbrazil.com/ (after cutover) and
// gasbrazil.github.io/ (pre-cutover verification) equally well.
const SITES = [
  {
    name: "ONS Balances Dashboard",
    url: "ons/",
    desc: "Daily grid balances, thermal generation by plant, and gas-fired dispatch across Brazil's interconnected power system.",
  },
  {
    name: "POC Results Dashboard",
    url: "poc/",
    desc: "Pipeline capacity offer results \\u2014 balancing, GUS acquisition, and linepack trades across Brazil's gas transportadoras.",
  },
  {
    name: "POC Contracts",
    url: "contratos/",
    desc: "Transport contracts and master transport contracts across Brazil's gas transportadoras \\u2014 TBG, TAG, and NTS.",
  },
];

function render() {
  const el = document.getElementById("cards");
  el.innerHTML = "";
  for (const site of SITES) {
    const a = document.createElement("a");
    a.className = "card";
    a.href = site.url;
    a.innerHTML = `<div class="name">${site.name}<span class="arrow">&rarr;</span></div><div class="desc">${site.desc}</div><div class="url">${location.host}/${site.url}</div>`;
    el.appendChild(a);
  }
}
render();

document.getElementById("year").textContent = new Date().getFullYear();

__SHARED_JS_THEME_TOGGLE__
initThemeToggle("theme-toggle");
</script>
</body>
</html>
"""


def write_home(out_path: Path | str = DEFAULT_OUT) -> Path:
    html = kit.render(
        TEMPLATE,
        SHARED_THEME_CSS=kit.render_theme_css(),
        SHARED_JS_THEME_TOGGLE=kit.JS_THEME_TOGGLE,
        FAVICON_DATA_URI=kit.embed_favicon(),
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote home page ({len(html):,} bytes) to {out_path}")
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    write_home(out)
