#!/usr/bin/env python3
"""Renders Wiki/*.md into a small static HTML site, styled to match
dashboard.py's own light/dark palette, so it can be deployed alongside
index.html at <site>/ons/wiki-html/ and linked from the dashboard's own
"Wiki" nav button.

Output dir is named wiki-html/ (not wiki/) deliberately: on a
case-insensitive filesystem (Windows, default macOS), a lowercase wiki/
next to the source Wiki/ folder collide into one directory and silently
merge their contents -- git and GitHub Pages are case-sensitive, so that
only surfaces when someone works from a checkout on one of those.

Usage: python3 build_wiki_site.py <src_dir_with_md> <out_dir>
  e.g. python3 build_wiki_site.py Wiki wiki-html
"""
import sys, re, pathlib
import markdown as md

SRC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("Home.md", "index.html", "Home"),
    ("Using-the-Dashboard.md", "using-the-dashboard.html", "Using the Dashboard"),
    ("Architecture-and-Deployment.md", "architecture-and-deployment.html", "Architecture & Deployment"),
    ("Known-Limitations-and-Assumptions.md", "known-limitations.html", "Known Limitations"),
]

# Map internal wiki cross-links like (Using-the-Dashboard) or (Home) to their
# rendered .html filenames, so links keep working once rendered to HTML.
SLUG_TO_FILE = {stem.rsplit(".", 1)[0]: html for stem, html, _ in PAGES}
SLUG_TO_FILE["Home"] = "index.html"

def fix_internal_links(text: str) -> str:
    def repl(m):
        label, target = m.group(1), m.group(2)
        if target in SLUG_TO_FILE:
            return f"[{label}]({SLUG_TO_FILE[target]})"
        return m.group(0)
    return re.sub(r"\[([^\]]+)\]\(([A-Za-z0-9_-]+)\)", repl, text)

# The wiki now draws its palette from shared/theme.css like every other page
# in the family, instead of carrying its own copy of the tokens. Only the
# wiki-specific layout (sidebar shell, prose typography) lives below.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "shared"))
import dashboard_kit as kit

CSS = kit.render_theme_css() + """
:root{ color-scheme: light; }
:root[data-theme="dark"]{ color-scheme: dark; }
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 var(--font);}
/* .wrap's width/centering come from shared/theme.css; the wiki only adds the
   sidebar-plus-prose layout on top of it. */
.wrap{display:flex;gap:28px}
aside{width:190px;flex:0 0 190px;position:sticky;top:16px;align-self:flex-start}
main{min-width:0;flex:1}
header.top{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
  justify-content:space-between;margin:0 auto 4px;padding:12px 0;
  border-bottom:1px solid var(--ring);width:var(--content-w);max-width:var(--content-max)}
header.top .brand{display:flex;align-items:baseline;gap:10px}
header.top h1{font-size:18px;margin:0;font-weight:700}
header.top .tag{color:var(--muted2);font-size:12.5px}
header.top .row{display:flex;gap:8px;align-items:center}
.flagbar{width:var(--content-w);max-width:var(--content-max);margin:0 auto 10px}
a{color:var(--accent)}
.navlink,button.iconBtn{border:1px solid var(--ring);background:var(--panel);
  color:var(--accent);border-radius:8px;padding:5px 10px;font-size:12.5px;
  font-weight:600;text-decoration:none;cursor:pointer;font-family:var(--font)}
.navlink:hover,button.iconBtn:hover{background:var(--accent-soft)}
button.iconBtn{padding:5px 8px;color:var(--text)}
button.iconBtn svg{width:14px;height:14px;display:block}
aside nav{background:var(--panel);border:1px solid var(--border);border-radius:10px;
  padding:10px 12px}
aside nav .label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted);margin-bottom:6px}
aside nav a{display:block;padding:5px 4px;font-size:13px;color:var(--text);
  text-decoration:none;border-radius:6px}
aside nav a:hover{background:var(--accent-soft);color:var(--accent)}
aside nav a.active{color:var(--accent);font-weight:700}
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
main th{background:var(--accent-soft);font-weight:700}
main hr{border:0;border-top:1px solid var(--ring);margin:18px 0}
footer.site{width:var(--content-w);max-width:var(--content-max);margin:20px auto 0;
  color:var(--muted);font-size:12px;line-height:1.6}
footer.site a{color:var(--muted)}
@media (max-width:900px){
  header.top,.flagbar,footer.site{width:auto;max-width:none;padding-left:12px;padding-right:12px}
}
@media (max-width:720px){
  .wrap{flex-direction:column}
  aside{position:static;width:auto;flex:none}
}
"""

THEME_JS = """
(function(){
  var b=document.getElementById('themeBtn');
  var sun='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var moon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function paint(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    b.innerHTML = dark ? sun : moon;
    b.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
  }
  var saved=null;
  try{ saved=localStorage.getItem('ons-wiki-theme'); }catch(e){}
  if(saved==='dark') document.documentElement.setAttribute('data-theme','dark');
  paint();
  b.addEventListener('click', function(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    if(dark){ document.documentElement.removeAttribute('data-theme'); }
    else{ document.documentElement.setAttribute('data-theme','dark'); }
    try{ localStorage.setItem('ons-wiki-theme', dark ? 'light' : 'dark'); }catch(e){}
    paint();
  });
})();
"""

nav_items = [(html, title) for _, html, title in PAGES]

def render_nav(current_html):
    items = []
    for html, title in nav_items:
        cls = ' class="active"' if html == current_html else ''
        items.append(f'<a href="{html}"{cls}>{title}</a>')
    return "\n".join(items)

def page_template(title, body_html, current_html):
    nav = render_nav(current_html)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — ONS Balances Wiki</title>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <h1>ONS Balances — Wiki</h1>
    <span class="tag">gas-first ONS grid data dashboard</span>
  </div>
  <div class="row">
    <a class="navlink" href="../index.html">&larr; Back to dashboard</a>
    <button id="themeBtn" class="iconBtn" title="Toggle light/dark" aria-label="Toggle light/dark"></button>
  </div>
</header>
<div class="flagbar" aria-hidden="true"></div>
<div class="wrap">
  <aside>
    <nav>
      <div class="label">Pages</div>
      {nav}
      <a class="back" href="https://github.com/caissonpoint/ons-dashboard/blob/main/README.md" target="_blank" rel="noopener">README (GitHub) &#8599;</a>
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
    Source: <a href="https://github.com/caissonpoint/ons-dashboard" target="_blank" rel="noopener">caissonpoint/ons-dashboard</a> on GitHub.
    Data via <a href="https://dados.ons.org.br" target="_blank" rel="noopener">ONS Dados Abertos</a> (CC-BY).
    Questions or feedback: <a href="mailto:eb@gasbrazil.com">eb@gasbrazil.com</a>.
  </div>
</footer>
<script>{THEME_JS}</script>
</body>
</html>
"""

extensions = ["tables", "fenced_code", "sane_lists"]

for src_name, out_name, title in PAGES:
    src_path = SRC / src_name
    text = src_path.read_text(encoding="utf-8")
    text = fix_internal_links(text)
    body = md.markdown(text, extensions=extensions)
    html = page_template(title, body, out_name)
    (OUT / out_name).write_text(html, encoding="utf-8")
    print("wrote", OUT / out_name)

print("done")
