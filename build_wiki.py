#!/usr/bin/env python3
"""Renders wiki-src/*.md into a static, site-wide wiki at wiki/, styled to
match every dashboard.py's own light/dark palette, so it can be deployed
alongside every other page at <site>/wiki/ and linked from every
dashboard's own nav (see masthead_html()'s wiki_href) and from the home
page / About footer.

Structure:
- wiki-src/Home.md, wiki-src/Architecture-and-Deployment.md -- site-wide
  pages covering the whole repo (all dashboards share one architecture).
- wiki-src/<slug>/Using-the-Dashboard.md, wiki-src/<slug>/Known-Limitations.md
  -- one pair per dashboard in shared/dashboard_kit.py's _SITES (every key
  except "home"), covering what's specific to that page: its controls, its
  KPIs, and where its numbers rest on an assumption rather than a published
  figure.

Output mirrors that shape under wiki/: wiki/index.html,
wiki/architecture-and-deployment.html, wiki/<slug>/using-the-dashboard.html,
wiki/<slug>/known-limitations.html.

Source lives in wiki-src/ (not Wiki/) and output in wiki/ (not Wiki-html/)
deliberately: on a case-insensitive filesystem (Windows, default macOS), a
source and output folder differing only in case collide into one directory
and silently merge their contents -- git and GitHub Pages are
case-sensitive, so that only surfaces when someone works from a checkout on
one of those. All-lowercase names for both sidesteps the problem entirely.

Usage: python3 build_wiki.py   (run from the repo root; no arguments)
"""
import html
import pathlib
import sys

import markdown as md

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "wiki-src"
OUT = ROOT / "wiki"

sys.path.insert(0, str(ROOT / "shared"))
import dashboard_kit as kit  # noqa: E402

# Every dashboard except "home" gets a wiki section, in the same order as
# every dashboard's own nav bar (_SITES is the single source of truth for
# that order and for display labels -- adding a 9th dashboard there and
# dropping its two markdown files into wiki-src/<slug>/ is all a future
# addition needs to pick up a wiki section automatically).
DASHBOARD_SLUGS = [k for k in kit._SITES if k != "home"]

# (output relative path, markdown source relative path, nav label, dashboard
# slug or None for a site-wide page)
PAGES: list[tuple[str, str, str, str | None]] = [
    ("index.html", "Home.md", "Home", None),
    ("architecture-and-deployment.html", "Architecture-and-Deployment.md",
     "Architecture & Deployment", None),
]
for slug in DASHBOARD_SLUGS:
    label = kit._SITES[slug]["label"]
    PAGES.append((f"{slug}/using-the-dashboard.html", f"{slug}/Using-the-Dashboard.md",
                   f"{label}: Using the Dashboard", slug))
    PAGES.append((f"{slug}/known-limitations.html", f"{slug}/Known-Limitations.md",
                   f"{label}: Known Limitations", slug))

# Cross-links inside the markdown source use short slugs in parens, same as
# a GitHub wiki -- (Home), (Architecture-and-Deployment), same-dashboard
# (Using-the-Dashboard) / (Known-Limitations) -- resolved relative to
# whichever page they're rendered on. A link to a *different* dashboard's
# page, or from a site-wide page into a dashboard's page, is written out in
# full as a root-relative path directly in the markdown (e.g.
# "/wiki/ons/known-limitations.html") since that's unambiguous regardless
# of which page it's rendered on and doesn't need resolving here.
import re as _re

def fix_internal_links(text: str, out_name: str) -> str:
    depth_prefix = "../" if "/" in out_name else ""

    def repl(m):
        label, target = m.group(1), m.group(2)
        if target == "Home":
            return f"[{label}]({depth_prefix}index.html)"
        if target == "Architecture-and-Deployment":
            return f"[{label}]({depth_prefix}architecture-and-deployment.html)"
        if target == "Using-the-Dashboard":
            return f"[{label}](using-the-dashboard.html)"
        if target == "Known-Limitations":
            return f"[{label}](known-limitations.html)"
        return m.group(0)

    return _re.sub(r"\[([^\]]+)\]\(([A-Za-z0-9_-]+)\)", repl, text)

# The wiki draws its palette from shared/theme.css like every other page in
# the family, instead of carrying its own copy of the tokens. Only the
# wiki-specific layout (sidebar shell, prose typography) lives below.
CSS = kit.render_theme_css() + """
:root{ color-scheme: light; }
:root[data-theme="dark"]{ color-scheme: dark; }
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 var(--font);}
.wrap{display:flex;gap:28px}
aside{width:220px;flex:0 0 220px;position:sticky;top:16px;align-self:flex-start;
  max-height:calc(100vh - 32px);overflow-y:auto}
main{min-width:0;flex:1}
header.top{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
  justify-content:space-between;margin:0 auto 4px;padding:12px 0;
  border-bottom:1px solid var(--ring);width:var(--content-w);max-width:var(--content-max)}
header.top .masthead-ident{display:flex;align-items:center;gap:10px}
header.top h1{font-size:14px;margin:0;font-weight:400;letter-spacing:-.01em;color:var(--muted2)}
header.top .row{display:flex;gap:8px;align-items:center}
.flagbar{width:var(--content-w);max-width:var(--content-max);margin:0 auto 10px}
a{color:var(--accent)}
button.iconBtn,#theme-toggle{border:1px solid var(--ring);background:var(--panel);
  color:var(--text);border-radius:5px;padding:5px 8px;font-size:12.5px;
  font-weight:400;text-decoration:none;cursor:pointer;font-family:var(--font);
  display:inline-flex;align-items:center;justify-content:center;line-height:0}
button.iconBtn:hover,#theme-toggle:hover{background:var(--accent-soft)}
button.iconBtn svg,#theme-toggle svg{width:14px;height:14px;display:block}
aside nav{background:var(--panel);border:1px solid var(--border);border-radius:10px;
  padding:10px 12px}
aside nav .label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);margin-bottom:6px}
aside nav .group{font-size:11.5px;font-weight:400;color:var(--muted2);
  margin:12px 0 2px;padding:0 4px}
aside nav .group:first-of-type{margin-top:4px}
aside nav a{display:block;padding:5px 4px 5px 12px;font-size:13px;color:var(--text);
  text-decoration:none;border-radius:5px}
aside nav a.toplevel{padding-left:4px}
aside nav a:hover{background:var(--accent-soft);color:var(--accent)}
aside nav a.active{color:var(--accent);font-weight:400}
aside .back{display:block;margin-top:10px;font-size:12.5px}
main .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;
  padding:18px 22px}
main h1{font-size:23px;margin:0 0 6px}
main h2{font-size:17px;margin:22px 0 8px;padding-top:12px;border-top:1px solid var(--ring)}
main h2:first-of-type{border-top:none;padding-top:0}
main h3{font-size:14.5px;margin:16px 0 6px}
main p{margin:0 0 10px;color:var(--text)}
main li{margin-bottom:4px}
main ul,main ol{padding-left:22px;margin:0 0 12px}
main code{background:var(--accent-soft);border-radius:4px;padding:1px 5px;font-size:12.5px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
main pre{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:10px 12px;overflow-x:auto;font-size:12.5px;line-height:1.5}
main pre code{background:none;padding:0}
main table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:13px}
main th,main td{border:1px solid var(--border);padding:4px 8px;text-align:left;
  vertical-align:top}
main th{background:var(--accent-soft);font-weight:400}
main hr{border:0;border-top:1px solid var(--ring);margin:18px 0}
footer.site{width:var(--content-w);max-width:var(--content-max);margin:20px auto 0;
  color:var(--muted);font-size:12px;line-height:1.6}
footer.site a{color:var(--muted)}
@media (max-width:900px){
  header.top,.flagbar,footer.site{width:auto;max-width:none;padding-left:12px;padding-right:12px}
}
@media (max-width:720px){
  .wrap{flex-direction:column}
  aside{position:static;width:auto;flex:none;max-height:none}
}
"""

THEME_JS = """
(function(){
  var b=document.getElementById('theme-toggle');
  var sun='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var moon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  var THEME_KEY='gasbrazil-theme';
  function paint(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    b.innerHTML = dark ? sun : moon;
    b.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
  }
  var saved=null;
  try{ saved=localStorage.getItem(THEME_KEY); }catch(e){}
  if(saved!=='light') document.documentElement.setAttribute('data-theme','dark');
  else document.documentElement.removeAttribute('data-theme');
  paint();
  b.addEventListener('click', function(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    if(dark){ document.documentElement.removeAttribute('data-theme'); }
    else{ document.documentElement.setAttribute('data-theme','dark'); }
    try{ localStorage.setItem(THEME_KEY, dark ? 'light' : 'dark'); }catch(e){}
    paint();
  });
})();
"""


def render_nav(current_out: str) -> str:
    items = []
    for out_name, _src, label, slug in PAGES:
        if slug is None:
            cls = "toplevel" + (" active" if out_name == current_out else "")
            items.append(f'<a class="{cls}" href="/wiki/{out_name}">{label}</a>')
    items.append('<div class="group">Dashboards</div>')
    for slug in DASHBOARD_SLUGS:
        dash_label = kit._SITES[slug]["label"]
        items.append(f'<div class="group">{dash_label}</div>')
        for out_name, _src, label, s in PAGES:
            if s != slug:
                continue
            short = "Using the Dashboard" if "using-the-dashboard" in out_name else "Known Limitations"
            cls = "active" if out_name == current_out else ""
            items.append(f'<a class="{cls}" href="/wiki/{out_name}">{short}</a>')
    return "\n      ".join(items)


def page_template(title: str, body_html: str, current_out: str, slug: str | None) -> str:
    nav = render_nav(current_out)
    if slug is None:
        back_href, back_label = "/", "GasBrazil"
        readme_href = "https://github.com/gasbrazil/gasbrazil.github.io/blob/main/README.md"
    else:
        back_href = f"/{slug}/"
        back_label = kit._SITES[slug]["label"]
        readme_href = f"https://github.com/gasbrazil/gasbrazil.github.io/blob/main/{slug}/README.md"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} &mdash; GasBrazil.com Wiki</title>
{kit.font_preload_html()}
<script>
(function(){{
  try {{
    var theme = localStorage.getItem("gasbrazil-theme");
    if (theme !== "light") document.documentElement.setAttribute("data-theme", "dark");
  }} catch (e) {{
    document.documentElement.setAttribute("data-theme", "dark");
  }}
}})();
</script>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="masthead-ident">
    {kit.products_dropdown_html("home", '<a class="masthead-brand" href="/">GasBrazil</a>')}
    <span class="crumb-sep" aria-hidden="true"></span>
    <h1>Wiki</h1>
  </div>
  <div class="row">
    <a class="navlink" href="{back_href}">&larr; {back_label}</a>
    <button id="theme-toggle" class="iconBtn" title="Toggle light/dark" aria-label="Toggle light/dark"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="wrap">
  <aside>
    <nav>
      <div class="label">Pages</div>
      {nav}
      <a class="back" href="{readme_href}" target="_blank" rel="noopener">README (GitHub) &#8599;</a>
    </nav>
  </aside>
  <main>
    <div class="card">
{body_html}
    </div>
  </main>
</div>
<footer class="site">
  <div style="display:block">
    Source: <a href="https://github.com/gasbrazil/gasbrazil.github.io" target="_blank" rel="noopener">gasbrazil/gasbrazil.github.io</a> on GitHub.
    Every dashboard cites its own data source on its own page &mdash; see each page's Sources row.
    Questions or feedback: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>.
  </div>
</footer>
<script>{THEME_JS}</script>
{kit._PRODUCTS_DROPDOWN_JS}
</body>
</html>
"""


def main() -> None:
    extensions = ["tables", "fenced_code", "sane_lists"]
    for out_name, src_name, title, slug in PAGES:
        src_path = SRC / src_name
        text = src_path.read_text(encoding="utf-8")
        text = fix_internal_links(text, out_name)
        body = md.markdown(text, extensions=extensions)
        html = page_template(title, body, out_name, slug)
        out_path = OUT / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print("wrote", out_path)
    print("done")


if __name__ == "__main__":
    main()
