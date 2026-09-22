"""
Shared build-time helpers + reusable JS snippets for the GasBrazil.com
dashboard family (ons-dashboard, poc-dashboard, poc-contratos).

See ADR-001, Decision 2 Option C. Each project's own dashboard.py still owns
its own data model, TEMPLATE and layout -- this module only centralizes the
mechanical/cosmetic pieces that were previously pasted into all three:

  - font loading via /shared/fonts/ (@font-face + optional preload)
  - favicon embedding (embed_favicon)
  - the gzip+base64 payload encoding (encode_payload_b64)
  - shared/theme.css loading + template rendering (THEME_CSS, render)
  - reusable JS: gzip inflate, theme-toggle icons, CSV escaping/download,
    and a dependency-free XLSX writer (originally built for ons-dashboard;
    offered here so poc-dashboard/poc-contratos can pick up "Export all
    data (Excel)" too without reimplementing it).

Each dashboard.py should add this file's directory to sys.path (it lives at
<repo-root>/shared/, a sibling of ons/, poc/, contratos/), e.g.:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
    import dashboard_kit as kit
"""
from __future__ import annotations

import base64
import gzip
import html
import json
import re
from collections.abc import Iterable
from pathlib import Path

HERE = Path(__file__).parent
THEME_CSS_PATH = HERE / "theme.css"
FONTS_DIR = HERE / "fonts"
DEFAULT_FONT_PATH = FONTS_DIR / "Pacaembu-Light.ttf"
DEFAULT_FAVICON_PATH = HERE / "favicon.png"

# Site-root path for self-hosted fonts (GitHub Pages + custom domain).
FONTS_URL_PREFIX = "/shared/fonts"

# Pacaembu is a heavy geometric face -- site default is Light (300); mid
# emphasis is Regular (400); wordmark + page titles use SemiBold (600). Never Bold.
# ExtraLight (200) is for muted metadata. File names on disk:
#   Pacaembu-ExtraLight.ttf, Pacaembu-Light.ttf, Pacaembu-Regular.ttf
#   (from Adobe "Pacaembu.ttf", true usWeightClass=400), Pacaembu-SemiBold.ttf
# Do NOT use Adobe's "Pacaembu Regular.ttf" -- that file is Bold 700.
PACAEMBU_FACES = (
    (200, "Pacaembu-ExtraLight.ttf"),
    (300, "Pacaembu-Light.ttf"),
    (400, "Pacaembu-Regular.ttf"),
    (600, "Pacaembu-SemiBold.ttf"),
)

# UI body type (data tables, controls, chart chrome). Self-hosted from the
# Google Fonts download bundle (static/*.ttf).
PLEX_SANS_FACES = (
    (300, "IBMPlexSans-Light.ttf"),
    (400, "IBMPlexSans-Regular.ttf"),
    (500, "IBMPlexSans-Medium.ttf"),
    (600, "IBMPlexSans-SemiBold.ttf"),
)
PLEX_FAMILY = "IBM Plex Sans"

# Raw theme.css text, __FONT_FACE__ placeholder still unresolved -- callers
# combine this with embed_font_face() (see render_theme_css below) and their
# own per-project accent block before dropping it into their TEMPLATE.
THEME_CSS = THEME_CSS_PATH.read_text(encoding="utf-8")


def _font_face_rules(family: str, faces: Iterable[tuple[int, str]]) -> list[str]:
    rules: list[str] = []
    for weight, name in faces:
        stem = Path(name).stem
        woff2_name = f"{stem}.woff2"
        ttf_name = f"{stem}.ttf"
        has_woff2 = (FONTS_DIR / woff2_name).exists()
        has_ttf = (FONTS_DIR / ttf_name).exists()
        if not has_woff2 and not has_ttf:
            continue
        sources = []
        if has_woff2:
            sources.append(f"url('{FONTS_URL_PREFIX}/{woff2_name}') format('woff2')")
        if has_ttf:
            sources.append(f"url('{FONTS_URL_PREFIX}/{ttf_name}') format('truetype')")
        src_clause = ", ".join(sources)
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"font-style:normal;font-display:swap;src:{src_clause};}}"
        )
    return rules


def embed_font_face(font_path: Path | str = DEFAULT_FONT_PATH) -> str:
    """Return @font-face rules for Pacaembu (display) + IBM Plex Sans (UI).

    font_path is kept for call-site compatibility; all bundled weights are
    linked when it points at the shared fonts dir or the default Light file."""
    font_path = Path(font_path)
    if font_path != DEFAULT_FONT_PATH and font_path != FONTS_DIR and font_path.exists():
        return "".join(_font_face_rules("Pacaembu", [(300, font_path.name)]))
    rules = _font_face_rules("Pacaembu", PACAEMBU_FACES)
    rules.extend(_font_face_rules(PLEX_FAMILY, PLEX_SANS_FACES))
    return "".join(rules)


def font_preload_html(*, weight: int = 300) -> str:
    """Preload default UI + display faces (Plex Regular, Pacaembu SemiBold in WOFF2)."""
    links: list[str] = []
    for stem in ("IBMPlexSans-Regular", "Pacaembu-SemiBold"):
        woff2_path = FONTS_DIR / f"{stem}.woff2"
        ttf_path = FONTS_DIR / f"{stem}.ttf"
        if woff2_path.exists():
            href = f"{FONTS_URL_PREFIX}/{stem}.woff2"
            links.append(
                f'<link rel="preload" href="{href}" as="font" type="font/woff2" crossorigin>'
            )
        elif ttf_path.exists():
            href = f"{FONTS_URL_PREFIX}/{stem}.ttf"
            links.append(
                f'<link rel="preload" href="{href}" as="font" type="font/ttf" crossorigin>'
            )
    if links:
        return "\n".join(links)
    # Fallback when Plex bundle not extracted yet.
    name = next((n for w, n in PACAEMBU_FACES if w == weight), None)
    if not name:
        return ""
    stem = Path(name).stem
    if (FONTS_DIR / f"{stem}.woff2").exists():
        href = f"{FONTS_URL_PREFIX}/{stem}.woff2"
        return f'<link rel="preload" href="{href}" as="font" type="font/woff2" crossorigin>'
    if (FONTS_DIR / f"{stem}.ttf").exists():
        href = f"{FONTS_URL_PREFIX}/{stem}.ttf"
        return f'<link rel="preload" href="{href}" as="font" type="font/ttf" crossorigin>'
    return ""


def embed_favicon(favicon_path: Path | str = DEFAULT_FAVICON_PATH,
                   fallback_hex: str = "#03183D",
                   as_data_uri: bool = False) -> str:
    """Return a URL path for the cached favicon asset, or a data: URI if requested
    or if a custom path / fallback SVG square is needed."""
    favicon_path = Path(favicon_path)
    if favicon_path.exists():
        if not as_data_uri and favicon_path.resolve() == DEFAULT_FAVICON_PATH.resolve():
            return "/shared/favicon.png"
        favicon_b64 = base64.b64encode(favicon_path.read_bytes()).decode("ascii")
        return "data:image/png;base64," + favicon_b64
    hex_color = fallback_hex.lstrip("#").upper()
    return (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' "
        f"fill='%23{hex_color}'%3E%3C/rect%3E%3C/svg%3E"
    )


def encode_payload_b64(payload: dict, *, compresslevel: int = 9) -> str:
    """Standard gzip+base64 encoding for the embedded JSON payload every
    dashboard ships. mtime=0 keeps the gzip header byte-for-byte
    reproducible across rebuilds of identical data (nice for diffing build
    output; makes no difference to the browser, which only reads the
    deflate stream via DecompressionStream)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=compresslevel, mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def render_theme_css(font_path: Path | str = DEFAULT_FONT_PATH) -> str:
    """THEME_CSS with __FONT_FACE__ resolved. Callers append their own
    per-project accent/override block after this string."""
    return THEME_CSS.replace("__FONT_FACE__", embed_font_face(font_path))


def typo_weight_css() -> str:
    """Appended after each page's local CSS so titles/labels stay semibold on Plex."""
    return TYPO_WEIGHT_CSS


TYPO_WEIGHT_CSS = """
/* Shared header/label typography — last in cascade (Pacaembu SemiBold on chrome labels). */
.wrap h1,
.wrap h2,
.wrap h3,
header.dash-head h1,
.panel-title,
.kpi-title,
.kpi-label,
.kpi-header,
.kpi-header .kpi-title,
.sources-label,
.sources-block .label,
.filter-label,
.asof-strip .asof-label,
.band-label,
.level-btn,
.view-toggle,
.view-toggle .level-btn,
.tab,
.tabs,
.tabs > button,
.tabs button,
.chip,
.pill,
.pick h3,
.tile .nm,
.tile .cap,
.tile .lbl,
button[aria-pressed],
[role="tab"],
.tool-row label,
.controls label,
.chart-toolbar label,
.hub-section-title,
.tagline,
.prose h2,
.prose h3,
aside nav a,
aside nav .label,
.hub-page-title,
.card .name,
.navlink,
.masthead h1,
header.top h1,
main h1,
main h2,
main h3,
.nav-trail a {
  font-family: var(--font-display);
  font-weight: 600;
}
"""


def render(template: str, **replacements: str) -> str:
    """Single-pass placeholder substitution.

    Keys match both __KEY__ and {{KEY}} spellings. Values are substituted
    in one pass so a payload that happens to contain another placeholder
    marker is not mutated by a later replacement.
    """
    if not replacements:
        return template
    keys = {str(k): str(v) for k, v in replacements.items()}
    pattern = re.compile(
        r"__(?P<a>" + "|".join(re.escape(k) for k in keys) + r")__"
        r"|\{\{(?P<b>" + "|".join(re.escape(k) for k in keys) + r")\}\}"
    )

    def _sub(match: re.Match[str]) -> str:
        key = match.group("a") or match.group("b")
        return keys[key]

    return pattern.sub(_sub, template)


def seo_head(*, title: str, description: str, path: str = "/") -> str:
    """Title, description, canonical, Open Graph, hreflang, and font preload.
    path is the site-relative path including a leading slash."""
    if not path.startswith("/"):
        path = "/" + path
    canonical = "https://gasbrazil.com" + path
    alt = "https://gasbrazil.github.io" + ("" if path == "/" else path.rstrip("/"))
    if path != "/" and not alt.endswith("/"):
        alt = alt + "/"
    title_esc = html.escape(title, quote=True)
    desc = html.escape(description, quote=True)
    canonical_esc = html.escape(canonical, quote=True)
    alt_esc = html.escape(alt, quote=True)
    preload = font_preload_html()
    preload_line = (preload + "\n") if preload else ""
    # Language is client-side (localStorage); hreflang points at the same
    # URL with x-default rather than inventing locale-specific paths.
    return (
        f"<title>{title_esc}</title>\n"
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{canonical_esc}">\n'
        '<link rel="preconnect" href="https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev" crossorigin>\n'
        '<link rel="dns-prefetch" href="https://pub-c07957ad735e48b796eae989fa9e678d.r2.dev">\n'
        '<meta name="theme-color" content="#06080c">\n'
        f'{preload_line}'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:site_name" content="GasBrazil.com">\n'
        f'<meta property="og:title" content="{title_esc}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:url" content="{canonical_esc}">\n'
        f'<meta property="og:locale" content="en_US">\n'
        f'<meta property="og:locale:alternate" content="pt_BR">\n'
        f'<link rel="alternate" hreflang="x-default" href="{canonical_esc}">\n'
        f'<link rel="alternate" href="{alt_esc}">'
    )


# ---------------------------------------------------------------------------
# Reusable JS. Plain strings, not a bundler: each dashboard's TEMPLATE splices
# these into its own <script> block at a place of its choosing (typically
# right after PAYLOAD_B64/DATA is declared). This keeps every dashboard a
# single self-contained HTML file with zero runtime dependencies, which is
# the property Decision 2 explicitly preserves.
# ---------------------------------------------------------------------------

# Inflate the gzip+base64 payload. Identical in spirit to what all three
# dashboards already do; only the exact variable/function names are
# standardized here.
JS_DECODE = r"""
function b64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}
async function inflateGzipB64(b64) {
  if (typeof DecompressionStream !== "function") {
    throw new Error("This browser lacks DecompressionStream (needs Chrome/Edge 80+, Firefox 113+, or Safari 16.4+).");
  }
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([b64ToBytes(b64)]).stream().pipeThrough(ds);
  return new TextDecoder().decode(await new Response(stream).arrayBuffer());
}
async function inflateGzipUrl(url, maxRetries = 1, delayMs = 600) {
  if (typeof DecompressionStream !== "function") {
    throw new Error("This browser lacks DecompressionStream (needs Chrome/Edge 80+, Firefox 113+, or Safari 16.4+).");
  }
  let lastErr;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await fetch(url, { cache: "no-cache" });
      if (!res.ok) throw new Error("Failed to load " + url + " (" + res.status + ")");
      const ds = new DecompressionStream("gzip");
      const stream = res.body.pipeThrough(ds);
      return new TextDecoder().decode(await new Response(stream).arrayBuffer());
    } catch (err) {
      lastErr = err;
      if (attempt < maxRetries) {
        await new Promise(r => setTimeout(r, delayMs * (attempt + 1)));
      }
    }
  }
  throw lastErr;
}
function parseDashboardJson(text) {
  // Legacy gzip payloads were built with Python json.dumps NaN tokens, which
  // JSON.parse rejects. New publishes sanitize to null; normalize on read too.
  const safe = String(text)
    .replace(/:\s*NaN\b/g, ":null")
    .replace(/,\s*NaN\b/g, ",null");
  return JSON.parse(safe);
}
function showBootError(err, retryFn, containerSelector) {
  const container = (typeof containerSelector === "string" ? document.querySelector(containerSelector) : containerSelector)
    || document.querySelector(".wrap") || document.querySelector("main") || document.body;
  if (!container) return;
  const existing = document.getElementById("gb-boot-error");
  if (existing) existing.remove();
  const errorBox = document.createElement("div");
  errorBox.id = "gb-boot-error";
  errorBox.className = "boot-error-boundary";
  errorBox.setAttribute("role", "alert");
  errorBox.setAttribute("aria-live", "assertive");

  const esc = typeof escapeHtml === "function"
    ? escapeHtml
    : s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const title = (typeof t === "function") ? t("bootErrorTitle") : "Unable to load dashboard data";
  const msg = (typeof t === "function") ? t("bootErrorBody") : "A network issue prevented the latest data from loading. Please check your connection and try again.";
  const retryText = (typeof t === "function") ? t("bootRetry") : "Retry";
  const detailsTitle = (typeof t === "function") ? t("bootErrorDetails") : "Technical details";
  const errDetails = esc(err && err.message ? err.message : String(err));

  errorBox.innerHTML =
    '<div class="boot-error-card">' +
      '<h3 class="boot-error-title"><span aria-hidden="true">&#x26A0;&#xFE0F;</span> ' + esc(title) + '</h3>' +
      '<p class="boot-error-desc">' + esc(msg) + '</p>' +
      '<details class="boot-error-details">' +
        '<summary>' + esc(detailsTitle) + '</summary>' +
        '<code>' + errDetails + '</code>' +
      '</details>' +
      (retryFn ? '<button type="button" class="btn-retry" id="gb-boot-retry-btn">' + esc(retryText) + '</button>' : '') +
    '</div>';
  container.prepend(errorBox);
  if (retryFn) {
    const btn = document.getElementById("gb-boot-retry-btn");
    if (btn) {
      btn.addEventListener("click", () => {
        errorBox.remove();
        retryFn();
      });
    }
  }
}
"""

JS_ESCAPE_HTML = r"""
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
"""

# Same sun/moon icon convention on every dashboard: the icon shown is the
# mode a click switches TO. initThemeToggle wires a button to toggle
# document.documentElement's data-theme attribute and calls onChange (if
# given) after each toggle so callers can repaint charts/colors.
JS_BOOT = r"""
(function(){
  try {
    /* Dark is the site default; only "light" opts out. */
    var theme = localStorage.getItem("gasbrazil-theme");
    if (theme !== "light")
      document.documentElement.setAttribute("data-theme", "dark");
    var lang = localStorage.getItem("gasbrazil-lang");
    if (!lang)
      lang = ((navigator.language || "en").toLowerCase().indexOf("pt") === 0) ? "pt" : "en";
    document.documentElement.setAttribute("data-lang", lang);
    document.documentElement.setAttribute("lang", lang === "pt" ? "pt-BR" : "en");
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.setAttribute("data-lang", "en");
    document.documentElement.setAttribute("lang", "en");
  }
  function bindFlagbarHeaderGlow() {
    var bar = document.querySelector(".flagbar");
    if (!bar) return;
    var heads = document.querySelectorAll(
      "header.dash-head, header.top, .site-header, .hub-header"
    );
    if (!heads.length) return;
    var io = new IntersectionObserver(function(entries) {
      var vis = entries[0] && entries[0].isIntersecting;
      heads.forEach(function(h) { h.classList.toggle("flag-glow", !vis); });
    }, { threshold: 0, rootMargin: "0px 0px -2px 0px" });
    io.observe(bar);
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", bindFlagbarHeaderGlow);
  else
    bindFlagbarHeaderGlow();
})();
"""

JS_THEME_TOGGLE = r"""
const SUN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
const MOON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const THEME_KEY = "gasbrazil-theme";
function isDarkTheme() { return document.documentElement.getAttribute("data-theme") === "dark"; }
function initThemeToggle(buttonId, onChange) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  function paint() {
    const dark = isDarkTheme();
    btn.innerHTML = dark ? SUN_SVG : MOON_SVG;
    let label = dark ? "Switch to light mode" : "Switch to dark mode";
    try {
      if (typeof t === "function") label = t(dark ? "themeLight" : "themeDark");
    } catch (e) { /* t is declared later in this script */ }
    btn.title = label; btn.setAttribute("aria-label", label);
  }
  paint();
  if (typeof onChange === "function") btn._onThemeChange = onChange;
  if (btn.dataset.themeWired === "1") return;
  btn.dataset.themeWired = "1";
  btn.addEventListener("click", () => {
    const nextDark = !isDarkTheme();
    if (nextDark) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem(THEME_KEY, nextDark ? "dark" : "light"); } catch (e) {}
    paint();
    const cb = btn._onThemeChange;
    if (typeof cb === "function") cb(nextDark);
  });
}
if (document.getElementById("theme-toggle")) initThemeToggle("theme-toggle");
"""

JS_I18N = r"""
const LANG_KEY = "gasbrazil-lang";
const GB_I18N = {
  en: {
    themeDark: "Switch to dark mode",
    themeLight: "Switch to light mode",
    langSwitch: "Português",
    skip: "Skip to content",
    navHome: "GasBrazil",
    navOns: "ONS Balances",
    navPoc: "POC Results",
    navContratos: "POC Contracts",
    navFlows: "Pipeline Flows",
    navSupply: "Gas Supply",
    navPld: "PLD Prices",
    navPrecos: "ANP Prices",
    navMago: "TAG Mago",
    navNts: "NTS OnTime",
    navMonitor: "Pipeline Monitor",
    navDesk: "The Desk",
    navProducts: "Products", // retained for previously deployed pages cached in browsers
    navMenu: "Menu",
    navAbout: "About",
    navWiki: "Wiki",
    filterPlaceholder: "Filter…",
    contact: "Contact",
    copyLink: "Copy link",
    linkCopied: "Copied",
    clearAllSelections: "Clear all",
    tagline: "Analytical Firepower for Brazil's Energy Markets",
    hubDashboards: "Live dashboards",
    hubHint: "Every card below opens a live dashboard — pick a product to explore.",
    aboutLead: "Independent public-data dashboards. Not an official ONS, ANP, CCEE, or transportadora product.",
    aboutBody: "GasBrazil republishes open Brazilian gas and power data as filterable dashboards. Caveats are on each page and on About.",
    cardOns: "ONS Balances",
    cardOnsDesc: "Daily SIN balances and gas-fired dispatch.",
    cardPoc: "POC Results",
    cardPocDesc: "Capacity offer results — balancing, GUS, and linepack.",
    cardContratos: "POC Contracts",
    cardContratosDesc: "Active transport and master contracts (TBG, TAG, NTS).",
    cardFlows: "Pipeline Flows",
    cardFlowsDesc: "Daily receipt and delivery flows on the transport network.",
    cardSupply: "Gas Supply",
    cardSupplyDesc: "ANP national monthly supply balance.",
    cardPld: "PLD Prices",
    cardPldDesc: "CCEE daily-average and hourly PLD by submarket.",
    cardPrecos: "ANP Prices",
    cardPrecosDesc: "ANP Resolution 52/2011 disclosed gas prices.",
    cardDesk: "The Desk",
    cardDeskDesc: "Cross-product snapshot across gas and power.",
    cardMonitor: "Pipeline Monitor",
    cardMonitorDesc: "TAG Mago & NTS OnTime real-time line pack, forecasts & packing rates.",
    monitorTabTag: "TAG Mago",
    monitorTabNts: "NTS OnTime",
    monitorFooter: "Pipeline Monitor: Real-time and operational linepack telemetry across Brazilian gas transmission systems.",
    deskLinkOns: "ONS",
    deskLinkPld: "CCEE PLD",
    deskLinkPrecos: "ANP prices",
    deskLinkPoc: "POC",
    deskLinkFlows: "ANP flows",
    kpiRefresh: "Last refreshed",
    dataThrough: "Data through",
    staleBadge: "Data may be stale",
    methodTitle: "How this is built",
    methodSources: "Sources",
    methodAssump: "Key assumption",
    methodLimits: "Limits",
    methodAssump_ons: "Gas burn is estimated from verified generation (9,400 kcal/m³; CCGT 1,800 / OCGT 2,500 kcal/kWh; assumptions v1).",
    methodAssump_poc: "R$/m³ is R$/MMBtu divided by 26.8081 m³ per MMBtu (assumptions v2).",
    methodAssump_contratos: "Master rows enable later nominations; they are not firm capacity bookings.",
    methodAssump_flows: "Where ANP and TSO overlap, TSO Actual/Scheduled volumes win.",
    methodAssump_supply: "Monthly aggregation of ANP PPGN-EL national series plus imports.",
    methodAssump_precos: "Tax-inclusive R$/MMBtu monthly disclosures, not spot benchmarks.",
    methodAssump_pld: "Peak = hours 18–20 on weekdays (ANEEL-style ponta, TOU v1); SIN has no PLD (join map v1).",
    methodAssump_desk: "Cross-product headlines; full history and filters live on each product page.",
    methodLimits_ons: "Thermal dispatch updates intraday; subsystem balances finalize in the evening (UTC).",
    methodLimits_poc: "A few hundred records total; full-history rebuild each run.",
    sources: "Sources",
    sourceOns: "ONS",
    sourcePoc: "POC",
    sourceFlows: "ANP",
    sourceSupply: "ANP",
    sourcePrecos: "ANP",
    sourcePld: "CCEE",
    sourceMago: "TAG Mago",
    sourceNts: "NTS OnTime",
    sourceMonitor: "Pipeline Monitor",
    methodAssump_mago: "One EMPACOTAMENTOS snapshot feeds both line pack and zone forecasts; values are stored as published (m³ line pack, Mm³/d zones).",
    methodAssump_nts: "NTS SCADA telemetry snapshot; values are stored as published (m³ line pack and calculated packing rate).",
    methodAssump_monitor: "TAG and NTS operational telemetry snapshots; values are stored as published by each TSO.",
    aboutCoverMonitor: "Pipeline Monitor: TAG Mago line pack and 7-day zone forecasts combined with NTS OnTime real-time SCADA telemetry.",
    magoKpiLinepack: "Integrated line pack",
    ntsKpiLinepack: "NTS Line pack",
    ntsKpiRate: "Packing Rate",
    ntsKpiPacking: "Packing",
    ntsKpiUnpacking: "Unpacking",
    ntsLinepackTitle: "NTS Line pack — Southeast transmission mesh",
    ntsLinepackSub: "Real-time pipeline line pack inventory and hourly packing/unpacking rate.",
    magoKpiZone: "Operating Zone",
    magoKpiSnapshot: "Snapshot (UTC)",
    magoLinepackTitle: "Line pack — integrated mesh",
    magoLinepackSub: "Hourly actual (solid) and short-horizon forecast (dashed) with TAG commercial tolerance risk bands.",
    magoLegendActual: "Actual",
    magoLegendForecast: "Forecast",
    magoLegendSev: "Severe",
    magoLegendAlt: "High Alert",
    magoLegendMarg: "Target",
    magoAxisSevere: "Severe",
    magoAxisHigh: "High",
    magoAxisMild: "Mild",
    magoAxisTarget: "Target",
    magoAxisLow: "Low",
    magoFaixasTitle: "Operating Risk & Imbalance Tolerance Bands",
    magoFaixasSub: "Commercial balancing tolerance thresholds established for TAG's integrated pipeline system. Exceeding marginal thresholds incurs imbalance penalties or triggers operational balancing actions.",
    magoHeatmapTitle: "Operating Risk & Imbalance Breach Heatmap",
    magoHeatmapSub: "Daily historical tracking of TAG integrated inventory across commercial tolerance tiers and correlation with transport balancing actions.",
    magoHmAll: "All Days",
    magoHmAlerts: "Alerts & Breaches",
    magoHmCritical: "Critical Only",
    magoHmCompliance: "Envelope Compliance",
    magoHmAlertHours: "Alert Hours",
    magoHmCriticalHours: "Critical Hours",
    magoHmDaysMonitored: "Days Monitored",
    magoHmViewPoc: "View TAG Balancing on POC",
    magoHmClickHint: "Click day to inspect hourly line pack history",
    magoHmPeakZone: "Peak Operating Zone",
    magoHmRange: "Inventory Range",
    magoHmAvg: "Daily Mean",
    magoHmBalancingPoc: "POC Balancing Auction",
    magoLinepackHistTitle: "Line pack history",
    magoLinepackHistSub: "Hourly integrated inventory from cached snapshots (newest wins on overlap).",
    magoLpCsv: "Download line pack CSV",
    magoHistAll: "All Hours",
    magoHistAlerts: "Alerts & Breaches Only",
    magoColObserved: "Observed (UTC)",
    magoColMm3: "Mm³",
    magoColM3: "m³",
    magoColZone: "Operating Zone",
    magoColSnapshot: "Source snapshot",
    magoZonesTitle: "Consumption forecast",
    magoZonesSub: "7-day daily TAG estimates (Mm³/d). Chart updates from the compact filters below.",
    magoByState: "States",
    magoByZone: "Zones",
    magoChartLine: "Lines",
    magoChartStack: "Stack",
    magoSelectAll: "Select all",
    pldSubtitle: "CCEE daily-average and hourly PLD by submarket (R$/MWh).",
    pldNote: "PLD (CCEE) is not the same series as ONS CMO. See",
    pldNoteLink: "ONS Balances",
    pldChartTitle: "Daily PLD by submarket",
    pldChartTitleHourly: "Hourly PLD by submarket",
    pldChartTitlePeak: "Peak vs off-peak PLD",
    pldChartNote: "",
    pldHourlyNote: "Last ~31 days of hourly PLD (hour beginning, Brazil local). CCEE publishes the next day’s 24 hours each day.",
    pldPeakNote: "Peak (ponta) is hours 18:00–21:00 on Monday–Friday. All other hours, including weekends, are off-peak. CCEE does not publish a ponta flag.",
    pldViewDaily: "Daily average",
    pldViewHourly: "Hourly",
    pldViewPeak: "Peak / off-peak",
    pldKpiPeak: "Peak",
    pldKpiOffPeak: "Off-peak",
    pldCompareTitle: "PLD vs CMO vs gas CVU",
    pldCompareNote: "",
    pldWindow: "Window",
    pldCsv: "Download CSV",
    pldXlsx: "Export all data (Excel)",
    pldFooter: "Data: CCEE (daily-average and hourly PLD). Not an official CCEE product.",
    footerAbout: "About",
    aboutH1: "About GasBrazil",
    aboutWho: "What this is",
    aboutWhoBody: "Independent public-data dashboards for Brazilian gas and power. Not affiliated with ONS, ANP, CCEE, TBG, TAG, or NTS.",
    aboutHow: "How the data is built",
    aboutHowBody: "Static pages on GitHub Pages. Actions fetch sources, transform, and publish HTML plus gzip artifacts on Cloudflare R2.",
    aboutGloss: "Glossary",
    glossGus: "GUS — gas acquired by a transportadora for system use.",
    glossLinepack: "Linepack — inventory held inside the pipeline.",
    glossBal: "Residual / operational balancing — short-term PEG imbalance clearing.",
    glossCmo: "CMO — ONS marginal operating cost (R$/MWh). Not CCEE PLD.",
    glossMaster: "Master transport contract — framework for later nominations; not firm capacity itself.",
    aboutCover: "Coverage limits",
    aboutCoverBody: "POC Contracts include Transport and Master rows. Legacy and access-connection contracts are not in the public GraphQL feed yet.",
    aboutCoverFlows: "Pipeline Flows merges ANP open data with TAG/TBG/NTS Portaria 1/2003 Actual/Scheduled volumes (TSO preferred when both exist). ANP still has no 2022 files and lags several weeks; TSO pubs often close that gap. TSB/GOM can be toggled.",
    aboutCoverSupply: "Gas Supply: ANP PPGN-EL national monthly series plus national imports (no Bolivia vs LNG split in the open CSV).",
    aboutCoverPrecos: "ANP Prices: Resolution 52/2011 monthly disclosures (R$/MMBtu, tax-inclusive). Some months are suppressed for confidentiality.",
    aboutCoverPld: "PLD: CCEE daily averages and hourly prices by submarket; peak is hours 18–20 on weekdays. Optional ONS CMO and median gas CVU when lake data is present.",
    aboutCoverMago: "TAG Mago: hourly line pack and 7-day balancing-zone consumption forecasts from EMPACOTAMENTOS API snapshots.",
    cardMago: "TAG Mago",
    cardMagoDesc: "TAG operational line pack and zone consumption forecasts.",
    cardNts: "NTS OnTime",
    cardNtsDesc: "NTS operational line pack and network packing/unpacking rate.",
    aboutCoverNts: "NTS OnTime: real-time line pack telemetry and hourly network packing/unpacking rate for the NTS pipeline grid.",
    aboutCoverDesk: "The Desk: cross-product headline series. Full history and filters live on each product page.",
    notFound: "This page is not here.",
    notFoundBody: "The hub and dashboards are linked below.",
    backHome: "Back to GasBrazil",
    bootLoading: "Loading dashboard data…",
    bootErrorTitle: "Unable to load dashboard data",
    bootErrorBody: "A network issue prevented the latest data from loading. Please check your connection and try again.",
    bootErrorDetails: "Technical details",
    bootRetry: "Retry",
    copyTable: "Copy table (TSV)",
    tableCopied: "Copied {n} rows to clipboard (TSV for Excel)",
    shortcutsTitle: "Keyboard Shortcuts",
    shortcutsGeneral: "General",
    shortcutsGoTo: "Go To (press \"g\" then key)",
    shortcutHelp: "Show keyboard shortcuts",
    shortcutPalette: "Command search palette",
    shortcutFilter: "Focus search or table filter",
    shortcutTheme: "Toggle dark / light theme",
    shortcutLang: "Toggle EN / PT language",
    shortcutEsc: "Clear filter or close menu",
    shortcutsBtn: "Shortcuts (?)",
    searchBtn: "Search",
    searchPlaceholder: "Search dashboards, transport points, contracts, topics… (Ctrl+K)",
    paletteDashboards: "Dashboards",
    palettePoints: "Transport Hubs & Points",
    paletteActions: "Actions & Settings",
    paletteTopics: "Market & Regulatory Topics",
    paletteNoResults: "No results matching \"{q}\"",
    exportPng: "PNG",
    exportPngTitle: "Download chart as high-resolution PNG (2x)",
    chartCopied: "Chart image copied to clipboard & downloaded",
    chartDownloaded: "Chart image downloaded (PNG)",
    freshLive: "Live & fresh",
    freshDelayed: "Awaiting update",
    freshScheduled: "Scheduled monthly"
  },
  pt: {
    themeDark: "Mudar para o modo escuro",
    themeLight: "Mudar para o modo claro",
    langSwitch: "English",
    skip: "Ir para o conteúdo",
    navHome: "GasBrazil",
    navOns: "Balanços ONS",
    navPoc: "Resultados POC",
    navContratos: "Contratos POC",
    navFlows: "Fluxos de Gasodutos",
    navSupply: "Oferta de Gás",
    navPld: "Preços PLD",
    navPrecos: "Preços ANP",
    navMago: "TAG Mago",
    navNts: "NTS OnTime",
    navMonitor: "Monitor de Gasodutos",
    navDesk: "The Desk",
    navProducts: "Produtos", // retained for previously deployed pages cached in browsers
    navMenu: "Menu",
    navAbout: "Sobre",
    navWiki: "Wiki",
    filterPlaceholder: "Filtrar…",
    contact: "Contato",
    copyLink: "Copiar link",
    linkCopied: "Copiado",
    clearAllSelections: "Limpar tudo",
    tagline: "Potência analítica para os mercados de energia do Brasil",
    hubDashboards: "Painéis ao vivo",
    hubHint: "Cada cartão abaixo abre um painel ao vivo — escolha um produto para explorar.",
    aboutLead: "Painéis independentes com dados públicos. Não é produto oficial da ONS, ANP, CCEE ou transportadoras.",
    aboutBody: "O GasBrazil republica dados abertos de gás e energia em painéis filtráveis. Ressalvas em cada página e em Sobre.",
    cardOns: "Balanços ONS",
    cardOnsDesc: "Balanços diários do SIN e despacho a gás.",
    cardPoc: "Resultados POC",
    cardPocDesc: "Resultados da oferta de capacidade — balanceamento, GUS e linepack.",
    cardContratos: "Contratos POC",
    cardContratosDesc: "Contratos de transporte e master ativos (TBG, TAG, NTS).",
    cardFlows: "Fluxos de Gasodutos",
    cardFlowsDesc: "Fluxos diários de recebimento e entrega na malha de transporte.",
    cardSupply: "Oferta de Gás",
    cardSupplyDesc: "Balanço mensal nacional de gás da ANP.",
    cardPld: "Preços PLD",
    cardPldDesc: "PLD médio diário e horário da CCEE por submercado.",
    cardPrecos: "Preços ANP",
    cardPrecosDesc: "Preços divulgados pela ANP (Resolução 52/2011).",
    cardDesk: "The Desk",
    cardDeskDesc: "Retrato cruzado de gás e energia.",
    cardMonitor: "Monitor de Gasodutos",
    cardMonitorDesc: "Empacotamento e previsões da TAG Mago e taxas de empacotamento em tempo real do NTS OnTime.",
    monitorTabTag: "TAG Mago",
    monitorTabNts: "NTS OnTime",
    monitorFooter: "Monitor de Gasodutos: Telemetria de empacotamento em tempo real nos sistemas de transporte de gás do Brasil.",
    deskLinkOns: "ONS",
    deskLinkPld: "PLD CCEE",
    deskLinkPrecos: "Preços ANP",
    deskLinkPoc: "POC",
    deskLinkFlows: "Fluxos ANP",
    kpiRefresh: "Última atualização",
    dataThrough: "Dados até",
    staleBadge: "Dados possivelmente desatualizados",
    methodTitle: "Como isto é montado",
    methodSources: "Fontes",
    methodAssump: "Premissa-chave",
    methodLimits: "Limites",
    methodAssump_ons: "Queima de gás estimada da geração verificada (9.400 kcal/m³; CC 1.800 / CA 2.500 kcal/kWh; premissas v1).",
    methodAssump_poc: "R$/m³ é R$/MMBtu dividido por 26,8081 m³ por MMBtu (premissas v2).",
    methodAssump_contratos: "Linhas master viabilizam nomeações futuras; não são reservas firmes.",
    methodAssump_flows: "Onde ANP e TSO se sobrepõem, valem os volumes Programado/Realizado das TSO.",
    methodAssump_supply: "Agregação mensal das séries nacionais PPGN-EL da ANP mais importações.",
    methodAssump_precos: "Divulgações mensais em R$/MMBtu com impostos, não benchmarks spot.",
    methodAssump_pld: "Ponta = horas 18–20 em dias úteis (convenção ANEEL, TOU v1); SIN não tem PLD (mapa de junção v1).",
    methodAssump_desk: "Resumo entre produtos; histórico e filtros ficam em cada painel.",
    methodLimits_ons: "Despacho térmico atualiza ao longo do dia; balanços por subsistema fecham à noite (UTC).",
    methodLimits_poc: "Poucas centenas de registros; rebuild completo a cada rodada.",
    sources: "Fontes",
    sourceOns: "ONS",
    sourcePoc: "POC",
    sourceFlows: "ANP",
    sourceSupply: "ANP",
    sourcePrecos: "ANP",
    sourcePld: "CCEE",
    sourceMago: "TAG Mago",
    sourceNts: "NTS OnTime",
    sourceMonitor: "Monitor de Gasodutos",
    methodAssump_mago: "Um snapshot EMPACOTAMENTOS alimenta empacotamento e previsão por zona; valores como publicados (m³ e Mm³/d).",
    methodAssump_nts: "Telemetria de empacotamento em tempo real publicada pelo sistema SCADA da NTS (m³ e Mm³).",
    methodAssump_monitor: "Snapshots de telemetria operacional da TAG e NTS; valores armazenados conforme publicados por cada transportadora.",
    aboutCoverMonitor: "Monitor de Gasodutos: empacotamento e previsões zonais da TAG Mago combinados com a telemetria SCADA do NTS OnTime.",
    magoKpiLinepack: "Empacotamento integrado",
    ntsKpiLinepack: "Empacotamento NTS",
    ntsKpiRate: "Taxa de Variação",
    ntsKpiPacking: "Empacotando",
    ntsKpiUnpacking: "Desempacotando",
    ntsLinepackTitle: "Empacotamento NTS — Malha Sudeste",
    ntsLinepackSub: "Estoque de gás em tempo real na malha de transporte e taxa horária de empacotamento/desempacotamento.",
    magoKpiZone: "Faixa Operacional",
    magoKpiSnapshot: "Snapshot (UTC)",
    magoLinepackTitle: "Empacotamento — malha integrada",
    magoLinepackSub: "Realizado horário (sólido) e previsão de curto prazo (tracejado) com faixas de tolerância comercial da TAG.",
    magoLegendActual: "Realizado",
    magoLegendForecast: "Previsão",
    magoLegendSev: "Severo",
    magoLegendAlt: "Alto (Alerta)",
    magoLegendMarg: "Marginal (Ideal)",
    magoAxisSevere: "Severo",
    magoAxisHigh: "Alto",
    magoAxisMild: "Baixo",
    magoAxisTarget: "Marginal",
    magoAxisLow: "Alerta",
    magoFaixasTitle: "Faixas de Tolerância Operacional e Desbalanço",
    magoFaixasSub: "Limites comerciais de tolerância de balanceamento estabelecidos para a malha integrada da TAG. Desvios além da faixa marginal geram penalidades ou ações de balanceamento operacional.",
    magoHeatmapTitle: "Mapa de Risco Operacional e Violações de Desbalanço",
    magoHeatmapSub: "Acompanhamento diário do empacotamento integrado da TAG nas faixas de tolerância comercial e correlação com ações de balanceamento.",
    magoHmAll: "Todos os Dias",
    magoHmAlerts: "Alertas e Violações",
    magoHmCritical: "Apenas Crítico",
    magoHmCompliance: "Conformidade Operacional",
    magoHmAlertHours: "Horas em Alerta (Alto)",
    magoHmCriticalHours: "Horas Críticas (Severo)",
    magoHmDaysMonitored: "Dias Monitorados",
    magoHmViewPoc: "Ver Balanceamento da TAG no POC",
    magoHmClickHint: "Clique no dia para inspecionar histórico horário",
    magoHmPeakZone: "Faixa Operacional Máxima",
    magoHmRange: "Faixa de Inventário",
    magoHmAvg: "Média Diária",
    magoHmBalancingPoc: "Leilão de Balanceamento POC",
    magoLinepackHistTitle: "Histórico de empacotamento",
    magoLinepackHistSub: "Inventário horário integrado de snapshots armazenados (o mais recente prevalece em sobreposições).",
    magoLpCsv: "Baixar CSV de empacotamento",
    magoHistAll: "Todas as Horas",
    magoHistAlerts: "Apenas Alertas e Violações (Alto e Severo)",
    magoColObserved: "Observado (UTC)",
    magoColMm3: "Mm³",
    magoColM3: "m³",
    magoColZone: "Faixa Operacional",
    magoColSnapshot: "Snapshot de origem",
    magoZonesTitle: "Previsão de consumo",
    magoZonesSub: "Estimativas diárias TAG em 7 dias (Mm³/d). O gráfico atualiza pelos filtros abaixo.",
    magoByState: "Estados",
    magoByZone: "Zonas",
    magoChartLine: "Linhas",
    magoChartStack: "Empilhado",
    magoSelectAll: "Selecionar todos",
    pldSubtitle: "PLD médio diário e horário da CCEE por submercado (R$/MWh).",
    pldNote: "O PLD (CCEE) não é a mesma série do CMO da ONS. Veja",
    pldNoteLink: "Balanços ONS",
    pldChartTitle: "PLD diário por submercado",
    pldChartTitleHourly: "PLD horário por submercado",
    pldChartTitlePeak: "PLD ponta vs fora ponta",
    pldChartNote: "",
    pldHourlyNote: "Últimos ~31 dias de PLD horário (hora inicial, horário de Brasília). A CCEE publica as 24 horas do dia seguinte a cada dia.",
    pldPeakNote: "Ponta são as horas 18:00–21:00 de segunda a sexta. As demais horas, inclusive fins de semana, são fora ponta. A CCEE não publica um flag de ponta.",
    pldViewDaily: "Média diária",
    pldViewHourly: "Horário",
    pldViewPeak: "Ponta / fora ponta",
    pldKpiPeak: "Ponta",
    pldKpiOffPeak: "Fora ponta",
    pldCompareTitle: "PLD vs CMO vs CVU a gás",
    pldCompareNote: "",
    pldWindow: "Janela",
    pldCsv: "Baixar CSV",
    pldXlsx: "Exportar tudo (Excel)",
    pldFooter: "Dados: CCEE (PLD médio diário e horário). Não é um produto oficial da CCEE.",
    footerAbout: "Sobre",
    aboutH1: "Sobre o GasBrazil",
    aboutWho: "O que é isto",
    aboutWhoBody: "Painéis independentes com dados públicos de gás e energia no Brasil. Sem vínculo com ONS, ANP, CCEE, TBG, TAG ou NTS.",
    aboutHow: "Como os dados são montados",
    aboutHowBody: "Páginas estáticas no GitHub Pages. O Actions busca, transforma e publica HTML mais artefatos gzip no Cloudflare R2.",
    aboutGloss: "Glossário",
    glossGus: "GUS — gás adquirido pela transportadora para uso do sistema.",
    glossLinepack: "Linepack — estoque dentro do gasoduto.",
    glossBal: "Balanceamento residual / operacional — processos de curto prazo da PEG.",
    glossCmo: "CMO — custo marginal de operação da ONS (R$/MWh). Não é o PLD da CCEE.",
    glossMaster: "Contrato master de transporte — quadro para nomeações posteriores; não é capacidade firme.",
    aboutCover: "Limites de cobertura",
    aboutCoverBody: "Contratos POC incluem Transporte e Master. Legado e conexões de acesso ainda não estão no feed GraphQL público.",
    aboutCoverFlows: "Fluxos une dados abertos da ANP com volumes Programado/Realizado da Portaria 1/2003 da TAG/TBG/NTS (TSO tem preferência quando ambos existem). A ANP ainda não tem 2022 e atrasa semanas; as publicações das TSO costumam fechar essa lacuna. TSB/GOM podem ser ligados.",
    aboutCoverSupply: "Oferta: séries mensais PPGN-EL da ANP mais importações nacionais (CSV aberto sem split Bolívia vs GNL).",
    aboutCoverPrecos: "Preços ANP: divulgações mensais da Resolução 52/2011 (R$/MMBtu com impostos). Alguns meses são omitidos por confidencialidade.",
    aboutCoverPld: "PLD: médias diárias e preços horários da CCEE por submercado; ponta = horas 18–20 em dias úteis. CMO e CVU a gás da ONS quando disponíveis no lake.",
    aboutCoverMago: "TAG Mago: empacotamento horário e previsões de consumo por zona de balanceamento (snapshots EMPACOTAMENTOS).",
    cardMago: "TAG Mago",
    cardMagoDesc: "Empacotamento operacional TAG e previsões de consumo por zona.",
    cardNts: "NTS OnTime",
    cardNtsDesc: "Empacotamento operacional da malha NTS e taxa horária de empacotamento.",
    aboutCoverNts: "NTS OnTime: telemetria de estoque de empacotamento (linepack) e taxa de variação da malha NTS.",
    aboutCoverDesk: "The Desk: séries-resumo entre produtos. Histórico e filtros ficam em cada painel.",
    notFound: "Esta página não existe.",
    notFoundBody: "O hub e os painéis estão nos links abaixo.",
    backHome: "Voltar ao GasBrazil",
    bootLoading: "Carregando dados do painel…",
    bootErrorTitle: "Não foi possível carregar os dados do painel",
    bootErrorBody: "Ocorreu uma falha de rede ao carregar os dados mais recentes. Verifique sua conexão e tente novamente.",
    bootErrorDetails: "Detalhes técnicos",
    bootRetry: "Tentar novamente",
    copyTable: "Copiar tabela (TSV)",
    tableCopied: "{n} linhas copiadas para a área de transferência (TSV para Excel)",
    shortcutsTitle: "Atalhos de Teclado",
    shortcutsGeneral: "Geral",
    shortcutsGoTo: "Navegação (pressione \"g\" e a tecla)",
    shortcutHelp: "Mostrar atalhos de teclado",
    shortcutPalette: "Busca de comandos",
    shortcutFilter: "Focar busca ou filtro da tabela",
    shortcutTheme: "Alternar modo claro / escuro",
    shortcutLang: "Alternar idioma EN / PT",
    shortcutEsc: "Limpar filtro ou fechar menu",
    shortcutsBtn: "Atalhos (?)",
    searchBtn: "Buscar",
    searchPlaceholder: "Buscar painéis, pontos de transporte, contratos, tópicos… (Ctrl+K)",
    paletteDashboards: "Painéis",
    palettePoints: "Pontos & Hubs de Transporte",
    paletteActions: "Ações & Configurações",
    paletteTopics: "Tópicos de Mercado & Regulatórios",
    paletteNoResults: "Nenhum resultado para \"{q}\"",
    exportPng: "PNG",
    exportPngTitle: "Baixar gráfico em alta resolução PNG (2x)",
    chartCopied: "Gráfico copiado e imagem baixada (PNG)",
    chartDownloaded: "Gráfico baixado (PNG)",
    freshLive: "Ao vivo & atualizado",
    freshDelayed: "Aguardando atualização",
    freshScheduled: "Publicação mensal"
  }
};
function currentLang() {
  return document.documentElement.getAttribute("data-lang") === "pt" ? "pt" : "en";
}
function t(key) {
  const pack = GB_I18N[currentLang()] || GB_I18N.en;
  return pack[key] || GB_I18N.en[key] || key;
}
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach(el => {
    const key = el.getAttribute("data-i18n-aria");
    if (key) el.setAttribute("aria-label", t(key));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.setAttribute("placeholder", t(key));
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.setAttribute("title", t(key));
  });
  const langBtn = document.getElementById("lang-toggle");
  if (langBtn) {
    langBtn.textContent = currentLang() === "pt" ? "EN" : "PT";
    langBtn.title = t("langSwitch");
    langBtn.setAttribute("aria-label", t("langSwitch"));
  }
}
function initLangToggle(buttonId, onChange) {
  const btn = document.getElementById(buttonId || "lang-toggle");
  applyI18n();
  if (!btn) return;
  btn.addEventListener("click", () => {
    const next = currentLang() === "pt" ? "en" : "pt";
    document.documentElement.setAttribute("data-lang", next);
    document.documentElement.setAttribute("lang", next === "pt" ? "pt-BR" : "en");
    try { localStorage.setItem(LANG_KEY, next); } catch (e) {}
    applyI18n();
    if (onChange) onChange(next);
  });
}

// Phase 3: Trader productivity tools (toasts, clipboard copy, shortcuts)
function gbShowToast(msg, durationMs = 2200) {
  let container = document.getElementById("gb-toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "gb-toast-container";
    container.className = "gb-toast-container";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "gb-toast";
  toast.textContent = msg;
  container.appendChild(toast);
  toast.offsetHeight;
  toast.classList.add("is-visible");
  setTimeout(() => {
    toast.classList.remove("is-visible");
    setTimeout(() => toast.remove(), 250);
  }, durationMs);
}

async function gbCopyTableAsTsv(tableOrWrap) {
  const table = (tableOrWrap && tableOrWrap.tagName === "TABLE")
    ? tableOrWrap
    : (tableOrWrap ? tableOrWrap.querySelector("table") : document.querySelector("table"));
  if (!table) return false;

  const rows = [];
  const headers = [];
  const ths = table.querySelectorAll("thead th");
  ths.forEach(th => {
    if (th.classList.contains("no-export") || th.hidden) return;
    const labelEl = th.querySelector(".th-label") || th;
    let text = (labelEl.childNodes[0] ? labelEl.childNodes[0].textContent : labelEl.textContent) || "";
    text = text.replace(/[\t\r\n]/g, " ").trim();
    headers.push(text);
  });
  if (headers.length) rows.push(headers.join("\t"));

  const trs = table.querySelectorAll("tbody tr");
  let rowCount = 0;
  trs.forEach(tr => {
    if (tr.hidden || tr.style.display === "none" || tr.classList.contains("no-export")) return;
    const cells = [];
    tr.querySelectorAll("td").forEach(td => {
      if (td.classList.contains("no-export") || td.hidden) return;
      let text = (td.textContent || "").replace(/[\t\r\n]/g, " ").trim();
      cells.push(text);
    });
    if (cells.length) {
      rows.push(cells.join("\t"));
      rowCount++;
    }
  });

  const tsv = rows.join("\n");
  let ok = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(tsv);
      ok = true;
    }
  } catch (e) {}
  if (!ok) {
    try {
      const ta = document.createElement("textarea");
      ta.value = tsv;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand("copy");
      ta.remove();
    } catch (e) {}
  }
  const tmpl = (typeof t === "function") ? t("tableCopied") : "Copied {n} rows to clipboard (TSV for Excel)";
  const msg = ok ? tmpl.replace("{n}", rowCount) : "Failed to copy table";
  if (typeof gbShowToast === "function") gbShowToast(msg);
  return ok;
}

function gbBindTableCopyButtons() {
  document.querySelectorAll(".table-wrap").forEach(wrap => {
    if (wrap.querySelector(".table-copy-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "table-copy-btn";
    btn.setAttribute("data-i18n-title", "copyTable");
    btn.title = (typeof t === "function") ? t("copyTable") : "Copy table (TSV)";
    btn.innerHTML = '&#x1F4CB; TSV';
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      gbCopyTableAsTsv(wrap);
    });
    wrap.appendChild(btn);
  });
}

function toggleShortcutsModal() {
  let modal = document.getElementById("gb-shortcuts-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "gb-shortcuts-modal";
    modal.className = "shortcuts-modal-backdrop";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "gb-shortcuts-title");

    modal.innerHTML =
      '<div class="shortcuts-modal-card">' +
        '<div class="shortcuts-modal-head">' +
          '<h3 id="gb-shortcuts-title" class="shortcuts-modal-title" data-i18n="shortcutsTitle">Keyboard Shortcuts</h3>' +
          '<button type="button" class="shortcuts-modal-close" aria-label="Close">&times;</button>' +
        '</div>' +
        '<div class="shortcuts-modal-grid">' +
          '<div class="shortcuts-section">' +
            '<h4 class="shortcuts-sec-title" data-i18n="shortcutsGeneral">General</h4>' +
            '<div class="shortcut-row"><kbd>Ctrl</kbd> <kbd>K</kbd> <span data-i18n="shortcutPalette">Command search palette</span></div>' +
            '<div class="shortcut-row"><kbd>?</kbd> <span data-i18n="shortcutHelp">Show this help dialog</span></div>' +
            '<div class="shortcut-row"><kbd>/</kbd> or <kbd>f</kbd> <span data-i18n="shortcutFilter">Focus search / table filter</span></div>' +
            '<div class="shortcut-row"><kbd>t</kbd> <span data-i18n="shortcutTheme">Toggle light / dark theme</span></div>' +
            '<div class="shortcut-row"><kbd>l</kbd> or <kbd>p</kbd> <span data-i18n="shortcutLang">Toggle EN / PT language</span></div>' +
            '<div class="shortcut-row"><kbd>Esc</kbd> <span data-i18n="shortcutEsc">Clear filter or close menu</span></div>' +
          '</div>' +
          '<div class="shortcuts-section">' +
            '<h4 class="shortcuts-sec-title" data-i18n="shortcutsGoTo">Go To (press "g" then key)</h4>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>h</kbd> <span>Home (Hub)</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>d</kbd> <span>The Desk</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>m</kbd> <span>TAG Mago</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>o</kbd> <span>ONS Balances</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>p</kbd> <span>POC Results</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>c</kbd> <span>POC Contracts</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>f</kbd> <span>Pipeline Flows</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>s</kbd> <span>Gas Supply</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>l</kbd> <span>PLD Prices</span></div>' +
            '<div class="shortcut-row"><kbd>g</kbd> <kbd>r</kbd> <span>ANP Prices</span></div>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest(".shortcuts-modal-close")) {
        modal.hidden = true;
      }
    });
    if (typeof applyI18n === "function") applyI18n();
  }
  modal.hidden = !modal.hidden;
}

// -----------------------------------------------------------------------------
// Global Command Palette (Ctrl+K)
// -----------------------------------------------------------------------------
let GB_PALETTE_ITEMS = null;
let gbPaletteActiveIdx = 0;
let gbPaletteVisibleItems = [];

function getPaletteCatalog() {
  if (GB_PALETTE_ITEMS) return GB_PALETTE_ITEMS;
  GB_PALETTE_ITEMS = [
    // Dashboards
    { cat: "dashboards", id: "desk", title: "The Desk", titlePt: "The Desk", desc: "Cross-product snapshot, spark calculator, and market balance", descPt: "Visão integrada mercado de gás e energia, calculadora spark spread", tag: "Live", url: "/desk/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>' },
    { cat: "dashboards", id: "mago", title: "TAG Mago", titlePt: "TAG Mago", desc: "Operational line pack, 7-risk tolerance bands, and zone forecasts", descPt: "Empacotamento operacional, faixas de tolerância e previsão de consumo", tag: "Real-time", url: "/mago/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>' },
    { cat: "dashboards", id: "ons", title: "ONS Balances", titlePt: "Balanços ONS", desc: "SIN electricity grid balance and gas-fired thermal dispatch", descPt: "Balanço do SIN e despacho térmico a gás natural", tag: "Daily", url: "/ons/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' },
    { cat: "dashboards", id: "pld", title: "PLD Prices", titlePt: "Preços PLD", desc: "CCEE spot electricity settlement prices (hourly & peak/off-peak)", descPt: "Preço de Liquidação das Diferenças CCEE (horário e ponta)", tag: "Daily", url: "/pld/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>' },
    { cat: "dashboards", id: "poc", title: "POC Results", titlePt: "Resultados POC", desc: "Capacity auctions, balancing trades, GUS, and linepack tenders", descPt: "Leilões de capacidade de transporte, balanceamento e aquisição GUS", tag: "Daily", url: "/poc/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>' },
    { cat: "dashboards", id: "contratos", title: "POC Contracts", titlePt: "Contratos POC", desc: "Active firm transport and master capacity contracts (TBG, TAG, NTS)", descPt: "Contratos de transporte e contratos master ativos", tag: "Transport", url: "/contratos/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>' },
    { cat: "dashboards", id: "flows", title: "Pipeline Flows", titlePt: "Fluxos de Gasodutos", desc: "Physical receipt and delivery volumes across national gas transport network", descPt: "Movimentação física de gás nos pontos de entrada e saída", tag: "ANP / TSO", url: "/flows/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' },
    { cat: "dashboards", id: "supply", title: "Gas Supply", titlePt: "Oferta de Gás", desc: "National monthly natural gas balance (production, imports, flaring)", descPt: "Balanço nacional de suprimento (produção, importação, queima)", tag: "Monthly", url: "/supply/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>' },
    { cat: "dashboards", id: "precos", title: "ANP Prices", titlePt: "Preços ANP", desc: "ANP Resolution 52/2011 disclosed gas contract prices (R$/MMBtu)", descPt: "Preços de venda de gás natural divulgados sob a Resolução ANP 52/2011", tag: "Monthly", url: "/precos/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>' },
    { cat: "dashboards", id: "wiki", title: "Wiki & Glossary", titlePt: "Wiki & Glossário", desc: "Methodologies, regulatory background, and market definitions", descPt: "Metodologias, contexto regulatório e definições de mercado", tag: "Docs", url: "/wiki/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>' },
    { cat: "dashboards", id: "about", title: "About & Methodology", titlePt: "Sobre & Metodologia", desc: "Data sources, pipelines, and architecture overview", descPt: "Fontes de dados, pipelines e arquitetura técnica", tag: "Info", url: "/about/", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>' },

    // Transport Hubs & Points
    { cat: "points", id: "cabiunas", title: "Cabiúnas (Terminal Cabiúnas / Macaé)", titlePt: "Cabiúnas (Terminal Cabiúnas / Macaé)", desc: "Major offshore pre-salt receipt and processing hub (Rio de Janeiro)", descPt: "Principal hub de recebimento e escoamento do pré-sal (RJ)", tag: "Pre-salt Hub", url: "/flows/?point=Cabi", keywords: ["macae", "upgn", "pre-sal", "rio", "terminal"] },
    { cat: "points", id: "paulinia", title: "Paulínia (REPLAN)", titlePt: "Paulínia (REPLAN)", desc: "Key interconnection between TBG (Gasbol), NTS, and São Paulo demand", descPt: "Interconexão estratégica TBG, NTS e demanda paulista", tag: "SP Hub", url: "/flows/?point=Paulinia", keywords: ["replan", "gasbol", "sp", "tbg", "nts"] },
    { cat: "points", id: "caraguatatuba", title: "Caraguatatuba (UTGCA)", titlePt: "Caraguatatuba (UTGCA)", desc: "Pre-salt Santos basin gas treatment unit and delivery point", descPt: "Unidade de Tratamento de Gás de Caraguatatuba (Bacia de Santos)", tag: "Santos Basin", url: "/flows/?point=Caraguatatuba", keywords: ["utgca", "santos", "mexilhao", "pre-sal"] },
    { cat: "points", id: "guanabara", title: "Terminal Baía de Guanabara (TRBG)", titlePt: "Terminal Baía de Guanabara (TRBG)", desc: "FSRU LNG regasification terminal in Rio de Janeiro", descPt: "Terminal de Regaseificação de GNL da Baía de Guanabara (FSRU)", tag: "LNG Terminal", url: "/flows/?point=Guanabara", keywords: ["gnl", "lng", "fsru", "regas", "rio"] },
    { cat: "points", id: "pecem", title: "Terminal Pecém", titlePt: "Terminal de Pecém", desc: "Ceará LNG import and regasification terminal (Northeast)", descPt: "Terminal de GNL e regaseificação no Ceará (Nordeste)", tag: "LNG Terminal", url: "/flows/?point=Pecem", keywords: ["gnl", "lng", "ceara", "nordeste"] },
    { cat: "points", id: "sergipe", title: "Terminal Sergipe (Barra dos Coqueiros)", titlePt: "Terminal de Sergipe (Barra dos Coqueiros)", desc: "Private LNG import terminal connected to Porto de Sergipe I power plant", descPt: "Terminal privado de GNL conectado à UTE Porto de Sergipe I", tag: "LNG Terminal", url: "/flows/?point=Sergipe", keywords: ["gnl", "lng", "ute", "celse", "aracaju"] },
    { cat: "points", id: "tgs", title: "Terminal Gás Sul (TGS)", titlePt: "Terminal Gás Sul (TGS)", desc: "Offshore LNG regasification terminal in Santa Catarina connected to TBG", descPt: "Terminal de GNL em Santa Catarina conectado à malha da TBG", tag: "LNG Terminal", url: "/flows/?point=TGS", keywords: ["gnl", "lng", "santa catarina", "sul", "tbg"] },
    { cat: "points", id: "mutum", title: "Corumbá / Mutum (Gasbol)", titlePt: "Corumbá / Mutum (Gasbol)", desc: "Bolivia-Brazil international border entry point on TBG pipeline", descPt: "Ponto de entrada na fronteira Bolívia-Brasil no Gasbol (TBG)", tag: "Border Entry", url: "/flows/?point=Mutum", keywords: ["bolivia", "gasbol", "fronteira", "tbg"] },
    { cat: "points", id: "catu", title: "Catu (Bahia)", titlePt: "Catu (Bahia)", desc: "TAG pipeline network balancing hub and junction in Bahia", descPt: "Hub e entroncamento principal da malha TAG na Bahia", tag: "TAG Hub", url: "/mago/?zone=BA1", keywords: ["bahia", "tag", "nordeste", "mago"] },
    { cat: "points", id: "atalaia", title: "Atalaia (Sergipe)", titlePt: "Atalaia (Sergipe)", desc: "TAG coastal pipeline receiving point in Sergipe", descPt: "Ponto de recebimento da TAG em Sergipe", tag: "TAG Point", url: "/mago/?zone=SE", keywords: ["sergipe", "tag", "nordeste"] },

    // Regulatory & Market Topics
    { cat: "topics", id: "linepack", title: "Linepack & Tolerance Bands (Faixas de Tolerância)", titlePt: "Empacotamento & Faixas de Tolerância", desc: "TAG 7-tier balancing risk thresholds (Severe, High, Mild, Target)", descPt: "Faixas comerciais de tolerância da TAG (Severo, Alto, Baixo, Marginal)", tag: "Balancing", url: "/mago/", keywords: ["faixa", "severo", "alto", "marginal", "penalidade", "desequilibrio", "imbalance"] },
    { cat: "topics", id: "spark", title: "Spark Spread Calculator", titlePt: "Calculadora de Spark Spread", desc: "Thermal generation fuel margin (PLD vs Implied CVU)", descPt: "Margem de geração térmica (PLD vs CVU Implícito)", tag: "Power / Gas", url: "/desk/", keywords: ["cvu", "calorifico", "heat rate", "pld", "geracao", "termica"] },
    { cat: "topics", id: "gus", title: "GUS (Gás de Uso do Sistema)", titlePt: "GUS (Gás de Uso do Sistema)", desc: "Fuel gas purchased by transportadoras for pipeline compressor stations", descPt: "Gás de combustível para estações de compressão das transportadoras", tag: "Transport", url: "/poc/?q=GUS", keywords: ["compressao", "combustivel", "leilao", "tso"] },
    { cat: "topics", id: "pld-cmo", title: "PLD vs CMO Spread", titlePt: "Diferencial PLD vs CMO", desc: "CCEE market clearing price compared to ONS marginal operational cost", descPt: "Preço de liquidação CCEE comparado ao custo marginal ONS", tag: "Power", url: "/pld/", keywords: ["ccee", "ons", "cmo", "submercado", "sudeste", "sul"] },
    { cat: "topics", id: "res52", title: "Resolução ANP 52/2011", titlePt: "Resolução ANP 52/2011", desc: "Mandatory public disclosures of natural gas purchase and sale prices", descPt: "Publicação obrigatória de preços de compra e venda de gás natural", tag: "Regulation", url: "/precos/", keywords: ["anp", "resolucao 52", "contrato", "precos"] },

    // Actions & Tools
    { cat: "actions", id: "act-theme", title: "Toggle Theme (Dark / Light)", titlePt: "Alternar Tema (Escuro / Claro)", desc: "Switch between terminal dark desk and paper light theme", descPt: "Alternar entre modo escuro de terminal e modo claro", tag: "Action", action: "theme", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>' },
    { cat: "actions", id: "act-lang", title: "Toggle Language (PT / EN)", titlePt: "Alternar Idioma (PT / EN)", desc: "Switch UI language between English and Portuguese", descPt: "Alternar idioma da interface entre português e inglês", tag: "Action", action: "lang", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>' },
    { cat: "actions", id: "act-shortcuts", title: "Keyboard Shortcuts (?)", titlePt: "Atalhos de Teclado (?)", desc: "View all available keyboard navigation shortcuts", descPt: "Ver todos os atalhos de navegação disponíveis", tag: "Help", action: "shortcuts", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="8" x2="6.01" y2="8"/><line x1="10" y1="8" x2="10.01" y2="8"/><line x1="14" y1="8" x2="14.01" y2="8"/><line x1="18" y1="8" x2="18.01" y2="8"/><line x1="8" y1="12" x2="8.01" y2="12"/><line x1="12" y1="12" x2="12.01" y2="12"/><line x1="16" y1="12" x2="16.01" y2="12"/><line x1="18" y1="16" x2="6" y2="16"/></svg>' },
    { cat: "actions", id: "act-share", title: "Copy Page Link", titlePt: "Copiar Link da Página", desc: "Copy the current page URL with all active filters to clipboard", descPt: "Copiar o endereço da página com todos os filtros ativos", tag: "Tool", action: "share", icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>' }
  ];
  return GB_PALETTE_ITEMS;
}

function executePaletteItem(item) {
  toggleCommandPalette(false);
  if (!item) return;
  if (item.url) {
    window.location.href = item.url;
  } else if (item.action === "theme") {
    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) themeBtn.click();
  } else if (item.action === "lang") {
    const langBtn = document.getElementById("lang-toggle");
    if (langBtn) langBtn.click();
  } else if (item.action === "shortcuts") {
    toggleShortcutsModal();
  } else if (item.action === "share") {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(window.location.href);
      gbShowToast(t("linkCopied") || "Link copied");
    }
  }
}

function renderPaletteResults(query) {
  const container = document.getElementById("gb-palette-results");
  if (!container) return;
  const catalog = getPaletteCatalog();
  const q = (query || "").trim().toLowerCase();
  const isPt = currentLang() === "pt";

  const matches = catalog.filter(item => {
    if (!q) return true;
    const title = (isPt ? item.titlePt : item.title).toLowerCase();
    const desc = (isPt ? item.descPt : item.desc).toLowerCase();
    const tag = (item.tag || "").toLowerCase();
    const kw = (item.keywords || []).map(k => k.toLowerCase()).join(" ");
    return title.includes(q) || desc.includes(q) || tag.includes(q) || kw.includes(q);
  });

  gbPaletteVisibleItems = matches;
  gbPaletteActiveIdx = 0;

  if (matches.length === 0) {
    const noRes = (t("paletteNoResults") || 'No results matching "{q}"').replace("{q}", escapeHtml(q));
    container.innerHTML = '<div class="gb-palette-empty">' + noRes + '</div>';
    return;
  }

  const categoryNames = {
    dashboards: t("paletteDashboards") || "Dashboards",
    points: t("palettePoints") || "Transport Hubs & Points",
    topics: t("paletteTopics") || "Market & Regulatory Topics",
    actions: t("paletteActions") || "Actions & Settings"
  };

  const groups = {};
  matches.forEach(item => {
    const cat = item.cat || "dashboards";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(item);
  });

  let html = "";
  let itemIdx = 0;
  for (const cat of ["dashboards", "points", "topics", "actions"]) {
    const list = groups[cat];
    if (!list || !list.length) continue;
    html += '<div class="gb-palette-group-title">' + escapeHtml(categoryNames[cat] || cat) + '</div>';
    list.forEach(item => {
      const idx = itemIdx++;
      const isSel = idx === gbPaletteActiveIdx;
      const title = isPt ? item.titlePt : item.title;
      const desc = isPt ? item.descPt : item.desc;
      const icon = item.icon || '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/></svg>';
      html +=
        '<div class="gb-palette-item' + (isSel ? ' is-selected' : '') + '" data-idx="' + idx + '" role="option" aria-selected="' + (isSel ? 'true' : 'false') + '">' +
          '<div class="gb-palette-item-icon">' + icon + '</div>' +
          '<div class="gb-palette-item-body">' +
            '<div class="gb-palette-item-title">' + escapeHtml(title) + '</div>' +
            '<div class="gb-palette-item-desc">' + escapeHtml(desc) + '</div>' +
          '</div>' +
          (item.tag ? '<span class="gb-palette-item-tag">' + escapeHtml(item.tag) + '</span>' : '') +
        '</div>';
    });
  }
  container.innerHTML = html;

  container.querySelectorAll(".gb-palette-item").forEach(el => {
    el.addEventListener("mouseenter", () => {
      gbPaletteActiveIdx = parseInt(el.getAttribute("data-idx"), 10);
      updatePaletteSelection();
    });
    el.addEventListener("click", () => {
      const idx = parseInt(el.getAttribute("data-idx"), 10);
      if (gbPaletteVisibleItems[idx]) executePaletteItem(gbPaletteVisibleItems[idx]);
    });
  });
}

function updatePaletteSelection() {
  const container = document.getElementById("gb-palette-results");
  if (!container) return;
  const items = container.querySelectorAll(".gb-palette-item");
  items.forEach((el, idx) => {
    const isSel = idx === gbPaletteActiveIdx;
    el.classList.toggle("is-selected", isSel);
    el.setAttribute("aria-selected", isSel ? "true" : "false");
    if (isSel) {
      el.scrollIntoView({ block: "nearest" });
    }
  });
}

function toggleCommandPalette(forceOpen) {
  let modal = document.getElementById("gb-command-palette");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "gb-command-palette";
    modal.className = "gb-palette-backdrop";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "Command Palette");

    const placeholder = t("searchPlaceholder") || "Search dashboards, transport points, contracts, topics… (Ctrl+K)";
    modal.innerHTML =
      '<div class="gb-palette-card">' +
        '<div class="gb-palette-search-row">' +
          '<svg class="gb-palette-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
          '<input type="text" id="gb-palette-input" class="gb-palette-input" placeholder="' + escapeHtml(placeholder) + '" autocomplete="off" spellcheck="false" aria-autocomplete="list" aria-controls="gb-palette-results">' +
          '<span class="gb-palette-badge">ESC</span>' +
        '</div>' +
        '<div id="gb-palette-results" class="gb-palette-results" role="listbox"></div>' +
        '<div class="gb-palette-footer">' +
          '<span><kbd>&uarr;</kbd><kbd>&darr;</kbd> Navigate</span>' +
          '<span><kbd>&crarr;</kbd> Open</span>' +
          '<span><kbd>Esc</kbd> Close</span>' +
        '</div>' +
      '</div>';

    document.body.appendChild(modal);

    const input = document.getElementById("gb-palette-input");
    input.addEventListener("input", (e) => {
      renderPaletteResults(e.target.value);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (gbPaletteVisibleItems.length > 0) {
          gbPaletteActiveIdx = (gbPaletteActiveIdx + 1) % gbPaletteVisibleItems.length;
          updatePaletteSelection();
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (gbPaletteVisibleItems.length > 0) {
          gbPaletteActiveIdx = (gbPaletteActiveIdx - 1 + gbPaletteVisibleItems.length) % gbPaletteVisibleItems.length;
          updatePaletteSelection();
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (gbPaletteVisibleItems[gbPaletteActiveIdx]) {
          executePaletteItem(gbPaletteVisibleItems[gbPaletteActiveIdx]);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        toggleCommandPalette(false);
      }
    });

    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        toggleCommandPalette(false);
      }
    });
  }

  const shouldOpen = (forceOpen !== undefined) ? forceOpen : modal.hidden;
  modal.hidden = !shouldOpen;
  if (shouldOpen) {
    const input = document.getElementById("gb-palette-input");
    if (input) {
      input.value = "";
      renderPaletteResults("");
      setTimeout(() => input.focus(), 25);
    }
  }
}

// -----------------------------------------------------------------------------
// 1-Click Chart PNG Exporter
// -----------------------------------------------------------------------------
async function gbExportChartPng(svgEl, title, customFilename) {
  if (!svgEl) return;
  try {
    const rect = svgEl.getBoundingClientRect();
    const width = Math.max(svgEl.viewBox?.baseVal?.width || 0, rect.width || 800);
    const height = Math.max(svgEl.viewBox?.baseVal?.height || 0, rect.height || 400);

    const scale = 2;
    const padTop = 64;
    const padBottom = 38;
    const padSide = 24;
    const canvas = document.createElement("canvas");
    canvas.width = (width + padSide * 2) * scale;
    canvas.height = (height + padTop + padBottom) * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);

    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    ctx.fillStyle = isDark ? "#06080c" : "#ffffff";
    ctx.fillRect(0, 0, width + padSide * 2, height + padTop + padBottom);

    // Subtle border
    ctx.strokeStyle = isDark ? "#2a303c" : "#d2d5da";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width + padSide * 2 - 1, height + padTop + padBottom - 1);

    // Header banner: GasBrazil wordmark + flag accent
    ctx.font = "600 16px 'IBM Plex Sans', -apple-system, sans-serif";
    ctx.fillStyle = isDark ? "#ffffff" : "#0b0b0b";
    ctx.fillText("GasBrazil", padSide, 28);

    ctx.font = "400 12px 'IBM Plex Sans', -apple-system, sans-serif";
    ctx.fillStyle = isDark ? "#9aa0ab" : "#6a6e75";
    const chartTitle = title || "Chart Export";
    ctx.fillText(chartTitle, padSide + 85, 28);

    // Brazil Flag accent line
    ctx.fillStyle = "#009C3B"; ctx.fillRect(padSide, 38, 20, 2.5);
    ctx.fillStyle = "#FFDF00"; ctx.fillRect(padSide + 20, 38, 20, 2.5);
    ctx.fillStyle = "#002776"; ctx.fillRect(padSide + 40, 38, 20, 2.5);

    // Footer attribution
    ctx.font = "300 10.5px 'IBM Plex Sans', -apple-system, sans-serif";
    ctx.fillStyle = isDark ? "#9aa0ab" : "#6a6e75";
    const nowUtc = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
    ctx.fillText("Source: GasBrazil.com · Generated " + nowUtc, padSide, height + padTop + padBottom - 14);

    // Clone SVG and inline styles
    const clone = svgEl.cloneNode(true);
    clone.setAttribute("width", width);
    clone.setAttribute("height", height);

    const origElements = svgEl.querySelectorAll("*");
    const cloneElements = clone.querySelectorAll("*");
    for (let i = 0; i < origElements.length; i++) {
      const orig = origElements[i];
      const cl = cloneElements[i];
      if (!orig || !cl) continue;
      const comp = window.getComputedStyle(orig);
      if (comp.fill && comp.fill !== "none") cl.style.fill = comp.fill;
      if (comp.stroke && comp.stroke !== "none") cl.style.stroke = comp.stroke;
      if (comp.strokeWidth) cl.style.strokeWidth = comp.strokeWidth;
      if (comp.strokeDasharray) cl.style.strokeDasharray = comp.strokeDasharray;
      if (comp.opacity) cl.style.opacity = comp.opacity;
      if (comp.fontFamily) cl.style.fontFamily = comp.fontFamily;
      if (comp.fontSize) cl.style.fontSize = comp.fontSize;
      if (comp.fontWeight) cl.style.fontWeight = comp.fontWeight;
    }

    const xml = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    const blobUrl = URL.createObjectURL(svgBlob);

    const img = new Image();
    img.onload = function() {
      ctx.drawImage(img, padSide, padTop, width, height);
      URL.revokeObjectURL(blobUrl);

      canvas.toBlob(async function(blob) {
        if (!blob) return;
        const slug = (chartTitle.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24) || "chart");
        const filename = (customFilename || "gasbrazil_" + slug + "_" + new Date().toISOString().slice(0, 10)) + ".png";

        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);

        let copied = false;
        try {
          if (navigator.clipboard && window.ClipboardItem) {
            await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
            copied = true;
          }
        } catch (e) {}

        const msg = copied ? t("chartCopied") : t("chartDownloaded");
        gbShowToast(msg);
      }, "image/png");
    };
    img.src = blobUrl;
  } catch (err) {
    console.error("Export chart error:", err);
    gbShowToast("Failed to export chart image");
  }
}

function gbBindChartExportButtons() {
  document.querySelectorAll("svg").forEach(svg => {
    if (svg.classList.contains("kpi-spark") || svg.classList.contains("ext-icon") || svg.classList.contains("gb-palette-search-icon")) return;
    const rect = svg.getBoundingClientRect();
    const w = svg.viewBox?.baseVal?.width || rect.width || 0;
    const h = svg.viewBox?.baseVal?.height || rect.height || 0;
    if (w < 200 && h < 100) return;

    const container = svg.closest(".chart-wrap, .chart-card, .analysis-chart-panel, .panel, .stage, .desk-stage, main");
    if (!container) return;
    if (container.querySelector(".chart-export-btn")) return;

    let target = container.querySelector(".chart-toolbar, .chart-toolbar-actions, .panel-title, .chart-title, .infotitle");
    if (!target) {
      target = document.createElement("div");
      target.className = "chart-toolbar-actions";
      container.insertBefore(target, svg);
    }

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chart-export-btn";
    btn.setAttribute("data-i18n-title", "exportPngTitle");
    btn.title = (typeof t === "function") ? t("exportPngTitle") : "Download chart as high-resolution PNG (2x)";
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><span>PNG</span>';

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      let title = "GasBrazil Chart";
      const titleEl = container.querySelector(".panel-title, .chart-title, h2, h3");
      if (titleEl) {
        title = titleEl.childNodes[0]?.textContent?.trim() || titleEl.textContent?.trim() || title;
      }
      gbExportChartPng(svg, title);
    });

    target.appendChild(btn);
  });
}

function initGlobalShortcuts() {
  let gPressed = false;
  let gTimer = null;

  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target && e.target.isContentEditable);

    if (e.key === "Escape") {
      const palette = document.getElementById("gb-command-palette");
      if (palette && !palette.hidden) {
        palette.hidden = true;
        e.preventDefault();
        return;
      }
      const modal = document.getElementById("gb-shortcuts-modal");
      if (modal && !modal.hidden) {
        modal.hidden = true;
        e.preventDefault();
        return;
      }
      if (isInput && e.target.classList && e.target.classList.contains("th-filter")) {
        e.target.value = "";
        e.target.dispatchEvent(new Event("input", { bubbles: true }));
        e.target.blur();
        e.preventDefault();
        return;
      }
    }

    // Ctrl+K or Cmd+K opens Command Palette anywhere (even when focused in input)
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      toggleCommandPalette();
      return;
    }

    if (isInput) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === "?" || (e.shiftKey && e.key === "/")) {
      e.preventDefault();
      toggleShortcutsModal();
      return;
    }

    if (e.key === "/" || e.key === "f") {
      const firstFilter = document.querySelector(".th-filter, input[type='search'], .analysis-filter, #f-search");
      if (firstFilter) {
        e.preventDefault();
        firstFilter.focus();
        firstFilter.select();
      }
      return;
    }

    if (e.key === "t" || e.key === "T") {
      const themeBtn = document.getElementById("theme-toggle");
      if (themeBtn) {
        e.preventDefault();
        themeBtn.click();
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        gbShowToast(isDark ? "Theme: Dark" : "Theme: Light");
      }
      return;
    }

    if (e.key === "l" || e.key === "L" || e.key === "p" || e.key === "P") {
      const langBtn = document.getElementById("lang-toggle");
      if (langBtn) {
        e.preventDefault();
        langBtn.click();
        const lang = document.documentElement.getAttribute("data-lang");
        gbShowToast(lang === "pt" ? "Idioma: Português" : "Language: English");
      }
      return;
    }

    if (e.key === "g" || e.key === "G") {
      gPressed = true;
      clearTimeout(gTimer);
      gTimer = setTimeout(() => { gPressed = false; }, 1200);
      return;
    }

    if (gPressed) {
      gPressed = false;
      clearTimeout(gTimer);
      const routes = {
        "h": "/",
        "d": "/desk/",
        "o": "/ons/",
        "p": "/poc/",
        "c": "/contratos/",
        "f": "/flows/",
        "s": "/supply/",
        "l": "/pld/",
        "r": "/precos/",
        "m": "/mago/",
        "w": "/wiki/",
        "a": "/about/"
      };
      const dest = routes[e.key.toLowerCase()];
      if (dest) {
        e.preventDefault();
        gbShowToast("Navigating…");
        window.location.href = dest;
      }
    }
  });

  const scLink = document.getElementById("link-shortcuts");
  if (scLink) {
    scLink.addEventListener("click", (e) => {
      e.preventDefault();
      toggleShortcutsModal();
    });
  }

  const searchTriggers = document.querySelectorAll("#gb-search-trigger, .gb-search-btn");
  searchTriggers.forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      toggleCommandPalette(true);
    });
  });

  gbBindTableCopyButtons();
  setTimeout(gbBindChartExportButtons, 500);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initGlobalShortcuts);
} else {
  initGlobalShortcuts();
}
/* __GB_I18N_END__ */
"""

# CSV escaping + a generic "download this text as a file" trigger. Column/row
# construction stays project-specific (each dashboard's data model differs).
JS_CSV_HELPERS = r"""
function csvEscape(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function downloadTextFile(text, mime, filename) {
  // UTF-8 BOM so Excel on Windows opens Portuguese characters (Ó, Ç, ³)
  // instead of mojibake (Ã“, Â³). Non-CSV downloads stay unchanged.
  const isCsv = /csv/i.test(String(mime || "")) || /\.csv$/i.test(String(filename || ""));
  const payload = isCsv ? "\uFEFF" + text : text;
  const blob = new Blob([payload], { type: mime || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
"""

# Sortable/filterable <table> headers, shared by every table on every
# dashboard (first built for flows-dashboard's meter picker and chart data
# table -- see ADR-001 -- then lifted here so ONS/POC/Contratos can use the
# exact same behavior instead of a page-specific re-implementation):
#   - naturalDir/cycleSort: a 3-click cycle per column -- click 1 sorts in
#     that column's natural direction (descending for the table's own
#     default column, ascending otherwise), click 2 reverses it, click 3
#     clears back to the table's default column+direction, instead of
#     getting stuck sorted on whatever was last clicked.
#   - withFocusPreserved: rebuilding a table wholesale on every filter
#     keystroke would normally steal focus out of the input being typed
#     in; this remembers which .th-filter (by data-col) had focus and
#     where the caret was, runs the rebuild, then restores both.
#   - buildSortFilterTh: the actual <th> builder -- a clickable label (for
#     sorting) plus a small inline filter box -- so a table only has to
#     supply its column defs, current {col,dir} state, default state, and
#     a filters object.
# Pairs with theme.css's .th-label/.th-filter rules for the look, and
# nothing else -- each table still owns its own sort-value/filter-value
# functions and row rendering, since those are inherently page-specific.
JS_TABLE_SORT = r"""
function naturalDir(col, defaultCol) { return col === defaultCol ? -1 : 1; }
function cycleSort(current, col, def) {
  const nd = naturalDir(col, def.col);
  if (current.col !== col) return { col, dir: nd };
  if (current.dir === nd) return { col, dir: -nd };
  return { col: def.col, dir: def.dir };
}
function withFocusPreserved(host, rebuild) {
  const active = document.activeElement;
  const col = (active && active.classList && active.classList.contains("th-filter") && host.contains(active))
    ? active.dataset.col : null;
  const caret = col ? active.selectionStart : null;
  rebuild();
  if (col) {
    const input = Array.from(host.querySelectorAll(".th-filter")).find(el => el.dataset.col === col);
    if (input) { input.focus(); if (caret != null) input.setSelectionRange(caret, caret); }
  }
}
function buildSortFilterTh(col, sortState, defaultSort, filters, onChange, extraClass) {
  const th = document.createElement("th");
  if (extraClass) th.className = extraClass;
  const labelSpan = document.createElement("span");
  labelSpan.className = "th-label";
  labelSpan.textContent = col.label;
  if (sortState.col === col.key) {
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = sortState.dir === 1 ? "↑" : "↓";
    labelSpan.appendChild(arrow);
  }
  labelSpan.addEventListener("click", () => onChange(cycleSort(sortState, col.key, defaultSort), filters));
  th.appendChild(labelSpan);
  const filterInput = document.createElement("input");
  filterInput.type = "search";
  filterInput.className = "th-filter";
  filterInput.dataset.col = col.key;
  filterInput.setAttribute("data-i18n-placeholder", "filterPlaceholder");
  filterInput.placeholder = (typeof t === "function") ? t("filterPlaceholder") : "Filter…";
  filterInput.value = filters[col.key] || "";
  if (filterInput.value) th.classList.add("has-filter");
  filterInput.addEventListener("input", () => {
    filters[col.key] = filterInput.value.toLowerCase();
    th.classList.toggle("has-filter", !!filterInput.value);
    onChange(sortState, filters);
  });
  th.appendChild(filterInput);
  return th;
}
"""

# Shareable view state in the URL (deep-linking). One mechanism for all
# eight dashboards: each page reads its own toolbar-level params on boot
# (dates, selected series, presets) and rewrites them with
# history.replaceState on every repaint, so a copied URL reopens the same
# view. Header-menu column Sets stay local-only (encoding arbitrary Sets
# gets noisy fast -- the poc/contratos precedent). `refreshed` is a
# cache-bust token and is always stripped so shared links stay clean.
#
# Robustness contract: every reader validates and degrades to defaults --
# unknown or partial params never blank the page. gbValidDate accepts only
# real calendar days (YYYY-MM-DD); gbValidEnum allows only a listed value;
# gbValidList keeps only allow-listed comma entries (unknown entries are
# dropped, and an all-unknown list reads as absent).
JS_QUERY_STATE = r"""
function gbQueryParams() {
  try { return new URLSearchParams(location.search); }
  catch (e) { return new URLSearchParams(); }
}
function gbWriteQuery(pairs) {
  try {
    const u = new URL(location.href);
    const sp = u.searchParams;
    sp.delete("refreshed");
    for (const k of Object.keys(pairs || {})) {
      const v = pairs[k];
      if (v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length)) sp.delete(k);
      else sp.set(k, Array.isArray(v) ? v.join(",") : String(v));
    }
    const qs = sp.toString();
    const next = u.pathname + (qs ? "?" + qs : "") + u.hash;
    if (next !== location.pathname + location.search + location.hash) history.replaceState(null, "", next);
  } catch (e) {}
}
function gbValidDate(s) {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(s + "T00:00:00Z");
  if (isNaN(d.getTime())) return null;
  const parts = s.split("-");
  if (d.getUTCFullYear() !== +parts[0] || d.getUTCMonth() + 1 !== +parts[1] || d.getUTCDate() !== +parts[2]) return null;
  return s;
}
function gbValidEnum(v, allowed) {
  if (!v || !Array.isArray(allowed)) return null;
  return allowed.indexOf(v) >= 0 ? v : null;
}
function gbValidList(raw, allowed) {
  if (!raw || !Array.isArray(allowed)) return null;
  const allow = {};
  allowed.forEach(a => { allow[a] = 1; });
  const seen = {};
  const out = [];
  String(raw).split(",").forEach(s => {
    const t = s.trim();
    if (t && allow[t] && !seen[t]) { seen[t] = 1; out.push(t); }
  });
  return out.length ? out : null;
}
function gbCopyLink(buttonId) {
  const btn = document.getElementById(buttonId || "btn-share");
  if (!btn || btn.dataset.gbShareBound === "1") return;
  btn.dataset.gbShareBound = "1";
  btn.addEventListener("click", async () => {
    const url = location.href;
    let ok = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
        ok = true;
      }
    } catch (e) {}
    if (!ok) {
      try {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand("copy");
        ta.remove();
      } catch (e) {}
    }
    btn.textContent = (typeof t === "function") ? t(ok ? "linkCopied" : "copyLink") : (ok ? "Copied" : "Copy link");
    setTimeout(() => {
      btn.textContent = (typeof t === "function") ? t("copyLink") : "Copy link";
    }, 1600);
  });
}
"""


def clear_selection_button_html(
    button_id: str = "btn-clear-selection", css_class: str = "btn-clear"
) -> str:
    """Clear-all button for multi-select pickers. Uses shared clearAllSelections i18n."""
    safe = html.escape(button_id, quote=True)
    cls = html.escape(css_class, quote=True)
    return (
        f'<button type="button" id="{safe}" class="{cls}" '
        'data-i18n="clearAllSelections">Clear all</button>'
    )


def share_link_button_html(button_id: str = "btn-share", css_class: str = "") -> str:
    """Copy-link button for a dashboard toolbar. Plain toolbar-button look
    (no new CSS, no new prose): the label is the shared copyLink i18n key
    so PT toggles translate it like every other chrome string. css_class
    covers pages with no generic button rule (desk reuses series-btn)."""
    safe = html.escape(button_id, quote=True)
    cls = f' class="{html.escape(css_class, quote=True)}"' if css_class else ""
    return (
        f'<button type="button" id="{safe}"{cls} '
        'data-i18n="copyLink">Copy link</button>'
    )

# Dependency-free XLSX writer (store-only-adjacent ZIP via the browser's
# native CompressionStream("deflate-raw"), plus the minimal OOXML parts Excel
# needs). Originally built for ons-dashboard's "Export all data" button;
# lifted here verbatim so poc-dashboard/poc-contratos can back-port the same
# feature per ADR-001's action items -- each project only needs to supply its
# own buildAllDataSheets()-equivalent returning [{name, rows}, ...] (rows[0]
# is the header row) and call buildWorkbookXlsxBlob(sheets).
JS_XLSX_ENGINE = r"""
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
const zU16 = v => { const b = new Uint8Array(2); b[0] = v & 0xFF; b[1] = (v >>> 8) & 0xFF; return b; };
const zU32 = v => { const b = new Uint8Array(4); b[0] = v & 0xFF; b[1] = (v >>> 8) & 0xFF; b[2] = (v >>> 16) & 0xFF; b[3] = (v >>> 24) & 0xFF; return b; };
function zConcat(arrs) {
  let total = 0; arrs.forEach(a => total += a.length);
  const out = new Uint8Array(total); let o = 0;
  arrs.forEach(a => { out.set(a, o); o += a.length; });
  return out;
}
async function deflateRaw(bytes) {
  const cs = new CompressionStream("deflate-raw");
  const writer = cs.writable.getWriter();
  writer.write(bytes); writer.close();
  return new Uint8Array(await new Response(cs.readable).arrayBuffer());
}
async function makeZip(files) {
  const localParts = [], centralParts = []; let offset = 0;
  const dosTime = 0, dosDate = 0x21;
  for (const f of files) {
    const nameBytes = new TextEncoder().encode(f.name);
    const crc = crc32(f.data), uncompSize = f.data.length;
    const compData = await deflateRaw(f.data);
    const compSize = compData.length;
    const localHeader = zConcat([
      zU32(0x04034b50), zU16(20), zU16(0), zU16(8),
      zU16(dosTime), zU16(dosDate),
      zU32(crc), zU32(compSize), zU32(uncompSize),
      zU16(nameBytes.length), zU16(0),
      nameBytes
    ]);
    localParts.push(localHeader, compData);
    const centralHeader = zConcat([
      zU32(0x02014b50), zU16(20), zU16(20), zU16(0), zU16(8),
      zU16(dosTime), zU16(dosDate),
      zU32(crc), zU32(compSize), zU32(uncompSize),
      zU16(nameBytes.length), zU16(0), zU16(0),
      zU16(0), zU16(0), zU32(0),
      zU32(offset),
      nameBytes
    ]);
    centralParts.push(centralHeader);
    offset += localHeader.length + compData.length;
  }
  const centralDir = zConcat(centralParts), centralOffset = offset;
  const eocd = zConcat([
    zU32(0x06054b50), zU16(0), zU16(0),
    zU16(files.length), zU16(files.length),
    zU32(centralDir.length), zU32(centralOffset),
    zU16(0)
  ]);
  return zConcat([...localParts, centralDir, eocd]);
}
function xmlEsc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}
function xlsxCol(n) {
  let s = ""; while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}
function sheetXml(rows) {
  let body = "<sheetData>";
  rows.forEach((row, ri) => {
    body += '<row r="' + (ri + 1) + '">';
    row.forEach((val, ci) => {
      if (val === null || val === undefined || val === "") return;
      const ref = xlsxCol(ci + 1) + (ri + 1);
      if (typeof val === "number" && isFinite(val))
        body += '<c r="' + ref + '"><v>' + val + '</v></c>';
      else
        body += '<c r="' + ref + '" t="inlineStr"><is><t xml:space="preserve">' + xmlEsc(val) + '</t></is></c>';
    });
    body += "</row>";
  });
  body += "</sheetData>";
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + body + '</worksheet>';
}
async function buildWorkbookXlsxBlob(sheets) {
  const enc = s => new TextEncoder().encode(s);
  const files = [];
  files.push({ name: "[Content_Types].xml", data: enc(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
    sheets.map((s, i) => '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ' +
      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join("") +
    '</Types>'
  )});
  files.push({ name: "_rels/.rels", data: enc(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
    '</Relationships>'
  )});
  files.push({ name: "xl/workbook.xml", data: enc(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<sheets>' + sheets.map((s, i) => '<sheet name="' + xmlEsc(s.name) + '" sheetId="' + (i + 1) +
      '" r:id="rId' + (i + 1) + '"/>').join("") + '</sheets></workbook>'
  )});
  files.push({ name: "xl/_rels/workbook.xml.rels", data: enc(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    sheets.map((s, i) => '<Relationship Id="rId' + (i + 1) + '" ' +
      'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" ' +
      'Target="worksheets/sheet' + (i + 1) + '.xml"/>').join("") +
    '</Relationships>'
  )});
  sheets.forEach((s, i) => {
    files.push({ name: "xl/worksheets/sheet" + (i + 1) + ".xml", data: enc(sheetXml(s.rows)) });
  });
  const zipBytes = await makeZip(files);
  return new Blob([zipBytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}
"""

# Cross-dashboard nav links. Each project calls site_links_js(self_id) at
# BUILD time to get a ready-to-splice <script> block defining SITE_LINKS/
# siteFlavor()/initCrossLinks() -- kept as generated JS (not a runtime fetch)
# so the output stays a single offline-capable file. self_id excludes that
# page from its own link list (a page doesn't link to itself).
_SITES = {
    "home": {
        "label": "GasBrazil",
        "custom": "https://gasbrazil.com",
        "caissonpoint": "https://caissonpoint.github.io/gasbrazil-com/",
        "hub": "https://gasbrazil.github.io/",
    },
    # Product order matches the hub KPI strip (desk → power → POC → supply).
    "desk": {
        "label": "The Desk",
        "custom": "https://gasbrazil.com/desk/",
        "caissonpoint": "https://gasbrazil.com/desk/",
        "hub": "https://gasbrazil.github.io/desk/",
    },
    "ons": {
        "label": "ONS Balances",
        "custom": "https://gasbrazil.com/ons/",
        "caissonpoint": "https://caissonpoint.github.io/ons-dashboard/",
        "hub": "https://gasbrazil.github.io/ons/",
    },
    "pld": {
        "label": "PLD Prices",
        "custom": "https://gasbrazil.com/pld/",
        "caissonpoint": "https://gasbrazil.com/pld/",
        "hub": "https://gasbrazil.github.io/pld/",
    },
    "poc": {
        "label": "POC Results",
        "custom": "https://gasbrazil.com/poc/",
        "caissonpoint": "https://caissonpoint.github.io/poc-dashboard/",
        "hub": "https://gasbrazil.github.io/poc/",
    },
    "contratos": {
        "label": "POC Contracts",
        "custom": "https://gasbrazil.com/contratos/",
        "caissonpoint": "https://caissonpoint.github.io/poc-contratos/",
        "hub": "https://gasbrazil.github.io/contratos/",
    },
    "flows": {
        "label": "Pipeline Flows",
        "custom": "https://gasbrazil.com/flows/",
        "caissonpoint": "https://gasbrazil.com/flows/",
        "hub": "https://gasbrazil.github.io/flows/",
    },
    "mago": {
        "label": "TAG Mago",
        "custom": "https://gasbrazil.com/mago/",
        "caissonpoint": "https://gasbrazil.com/mago/",
        "hub": "https://gasbrazil.github.io/mago/",
    },
    "nts": {
        "label": "NTS OnTime",
        "custom": "https://gasbrazil.com/nts/",
        "caissonpoint": "https://gasbrazil.com/nts/",
        "hub": "https://gasbrazil.github.io/nts/",
    },
    "supply": {
        "label": "Gas Supply",
        "custom": "https://gasbrazil.com/supply/",
        "caissonpoint": "https://gasbrazil.com/supply/",
        "hub": "https://gasbrazil.github.io/supply/",
    },
    "precos": {
        "label": "ANP Prices",
        "custom": "https://gasbrazil.com/precos/",
        "caissonpoint": "https://gasbrazil.com/precos/",
        "hub": "https://gasbrazil.github.io/precos/",
    },
    "monitor": {
        "label": "Pipeline Monitor",
        "custom": "https://gasbrazil.com/monitor/",
        "caissonpoint": "https://gasbrazil.com/monitor/",
        "hub": "https://gasbrazil.github.io/monitor/",
    },
}

# Page-intro trust block: breadcrumb + h1. Maps each dashboard to its
# existing GB_I18N nav key so both languages keep working with no new
# translation burden. Deliberately no visible description paragraph -- the
# pages stay streamlined; the hub cards already describe each product.
_PAGE_INTRO = {
    "desk": "navDesk",
    "ons": "navOns",
    "pld": "navPld",
    "poc": "navPoc",
    "contratos": "navContratos",
    "flows": "navFlows",
    "mago": "navMago",
    "nts": "navNts",
    "monitor": "navMonitor",
    "supply": "navSupply",
    "precos": "navPrecos",
}

# Freshness thresholds (days) for the staleness badge. Tuned to each
# product's publication cadence: daily pipelines (ons/pld/contratos) get a
# week; monthly ANP products get room for their multi-week release lag.
# POC is intentionally absent -- its "data through" is the latest trade
# date (event-driven), not build freshness, so a lag badge would mislead.
STALE_LAG_DAYS = {
    "ons": 7,
    "pld": 7,
    "contratos": 7,
    "flows": 60,
    "mago": 2,
    "nts": 2,
    "monitor": 2,
    "supply": 100,
    "precos": 100,
    "desk": 14,
}


def page_intro_html(self_id: str) -> str:
    """Title fragment for a dashboard masthead.

    Just the <h1> -- the surrounding masthead_html() row already carries
    the brand link and the section menu, so a separate breadcrumb line
    would repeat the page name twice. Raises KeyError on unknown ids so
    a typo fails the build, not the page.
    """
    if self_id not in _PAGE_INTRO:
        raise KeyError(f"Unknown page {self_id!r}; known: {sorted(_PAGE_INTRO)}")
    nav_key = _PAGE_INTRO[self_id]
    title = _SITES[self_id]["label"]
    return f'<h1 data-i18n="{nav_key}">{html.escape(title)}</h1>'


# Methodology disclosure: one collapsed line in each dashboard's footer --
# sources, the single assumption that most changes how numbers read, and
# the coverage limit. Collapsed by default so fresh pages gain zero
# visible prose; limits reuse the About page's aboutCover* strings where
# they exist. Assumption sentences mirror shared/transforms.py (bump the
# version note here when the registry version bumps).
_METHODOLOGY = {
    "ons": (("sourceOns",), "methodAssump_ons", "methodLimits_ons"),
    "poc": (("sourcePoc",), "methodAssump_poc", "methodLimits_poc"),
    "contratos": (("sourcePoc",), "methodAssump_contratos", "aboutCoverBody"),
    "flows": (("sourceFlows",), "methodAssump_flows", "aboutCoverFlows"),
    "supply": (("sourceSupply",), "methodAssump_supply", "aboutCoverSupply"),
    "precos": (("sourcePrecos",), "methodAssump_precos", "aboutCoverPrecos"),
    "pld": (("sourcePld",), "methodAssump_pld", "aboutCoverPld"),
    "mago": (("sourceMago",), "methodAssump_mago", "aboutCoverMago"),
    "nts": (("sourceNts",), "methodAssump_nts", "aboutCoverNts"),
    "monitor": (
        ("sourceMago", "sourceNts"),
        "methodAssump_monitor",
        "aboutCoverMonitor",
    ),
    "desk": (
        ("sourceOns", "sourcePld", "sourcePoc", "sourceFlows"),
        "methodAssump_desk",
        "aboutCoverDesk",
    ),
}

# English defaults for the methodology rows (data-i18n swaps in PT at view
# time). Source defaults reuse the _SITES-adjacent agency names.
_METHOD_SOURCE_LABELS = {
    "sourceOns": "ONS",
    "sourcePoc": "POC",
    "sourceFlows": "ANP",
    "sourceSupply": "ANP",
    "sourcePrecos": "ANP",
    "sourcePld": "CCEE",
    "sourceMago": "TAG Mago",
    "sourceNts": "NTS OnTime",
    "sourceMonitor": "Pipeline Monitor",
}


def methodology_html(self_id: str) -> str:
    """Collapsed footer disclosure for a dashboard. Raises KeyError on
    unknown ids so a typo fails the build, not the page."""
    if self_id not in _METHODOLOGY:
        raise KeyError(f"Unknown page {self_id!r}; known: {sorted(_METHODOLOGY)}")
    source_keys, assump_key, limits_key = _METHODOLOGY[self_id]
    sources = " · ".join(
        f'<span data-i18n="{k}">{html.escape(_METHOD_SOURCE_LABELS[k])}</span>'
        for k in source_keys
    )
    assump_default = _METHOD_ASSUMP_DEFAULTS[self_id]
    limits_default = _METHOD_LIMITS_DEFAULTS[limits_key]
    return (
        '<details class="method">\n'
        '<summary data-i18n="methodTitle">How this is built</summary>\n'
        '<div class="method-row"><span class="method-label" data-i18n="methodSources">Sources</span>'
        f"<span>{sources}</span></div>\n"
        '<div class="method-row"><span class="method-label" data-i18n="methodAssump">Key assumption</span>'
        f'<span data-i18n="{assump_key}">{html.escape(assump_default)}</span></div>\n'
        '<div class="method-row"><span class="method-label" data-i18n="methodLimits">Limits</span>'
        f'<span data-i18n="{limits_key}">{html.escape(limits_default)}</span></div>\n'
        "</details>"
    )


_METHOD_ASSUMP_DEFAULTS = {
    "ons": "Gas burn is estimated from verified generation (9,400 kcal/m³; CCGT 1,800 / OCGT 2,500 kcal/kWh; assumptions v1).",
    "poc": "R$/m³ is R$/MMBtu divided by 26.8081 m³ per MMBtu (assumptions v2).",
    "contratos": "Master rows enable later nominations; they are not firm capacity bookings.",
    "flows": "Where ANP and TSO overlap, TSO Actual/Scheduled volumes win.",
    "supply": "Monthly aggregation of ANP PPGN-EL national series plus imports.",
    "precos": "Tax-inclusive R$/MMBtu monthly disclosures, not spot benchmarks.",
    "pld": "Peak = hours 18–20 on weekdays (ANEEL-style ponta, TOU v1); SIN has no PLD (join map v1).",
    "mago": "One EMPACOTAMENTOS snapshot feeds both line pack and zone forecasts; values are stored as published (m³ line pack, Mm³/d zones).",
    "nts": "NTS SCADA telemetry snapshot; values are stored as published (m³ line pack and calculated packing rate).",
    "monitor": "TAG and NTS operational telemetry snapshots; values are stored as published by each TSO.",
    "desk": "Cross-product headlines; full history and filters live on each product page.",
}

# aboutCover* defaults mirror GB_I18N en (kept here so the builder needs no
# JS parsing); methodLimits_ons/poc are new with this panel.
_METHOD_LIMITS_DEFAULTS = {
    "methodLimits_ons": "Thermal dispatch updates intraday; subsystem balances finalize in the evening (UTC).",
    "methodLimits_poc": "A few hundred records total; full-history rebuild each run.",
    "aboutCoverBody": "POC Contracts include Transport and Master rows. Legacy and access-connection contracts are not in the public GraphQL feed yet.",
    "aboutCoverFlows": "Pipeline Flows merges ANP open data with TAG/TBG/NTS Portaria 1/2003 Actual/Scheduled volumes (TSO preferred when both exist). ANP still has no 2022 files and lags several weeks; TSO pubs often close that gap. TSB/GOM can be toggled.",
    "aboutCoverSupply": "Gas Supply: ANP PPGN-EL national monthly series plus national imports (no Bolivia vs LNG split in the open CSV).",
    "aboutCoverPrecos": "ANP Prices: Resolution 52/2011 monthly disclosures (R$/MMBtu, tax-inclusive). Some months are suppressed for confidentiality.",
    "aboutCoverPld": "PLD: CCEE daily averages and hourly prices by submarket; peak is hours 18–20 on weekdays. Optional ONS CMO and median gas CVU when lake data is present.",
    "aboutCoverMago": "TAG Mago: hourly line pack and 7-day balancing-zone consumption forecasts from EMPACOTAMENTOS API snapshots.",
    "aboutCoverNts": "NTS OnTime: real-time line pack telemetry and hourly network packing/unpacking rate for the NTS pipeline grid.",
    "aboutCoverMonitor": "Pipeline Monitor: TAG Mago line pack and 7-day zone forecasts combined with NTS OnTime real-time SCADA telemetry.",
    "aboutCoverDesk": "The Desk: cross-product headline series. Full history and filters live on each product page.",
}


def site_links_js(self_id: str) -> str:
    """JS block defining SITE_LINKS (every site except self_id), siteFlavor()
    and initCrossLinks(), which sets `#link-<id>` anchors' href from
    location.hostname at view time (so one build can be published to more
    than one hostname -- custom domain, caissonpoint Pages, gasbrazil hub
    mirror -- and each copy still links to its own equivalent siblings).

    Each assignment is null-guarded: a page whose nav markup hasn't been
    updated yet for a newly-added site (missing that #link-<k> anchor)
    should just not get that one link wired up, not throw and abort every
    initCrossLinks() call after it in the page's init sequence -- that's
    exactly how a stale nav once took down the whole ONS dashboard."""
    others = {k: v for k, v in _SITES.items() if k != self_id}
    links_obj = {k: {kk: vv for kk, vv in v.items() if kk != "label"} for k, v in others.items()}
    set_lines = "\n  ".join(
        f'{{ const el = document.getElementById("link-{k}"); if (el) el.href = SITE_LINKS.{k}[flavor]; }}'
        for k in others
    )
    return (
        "const SITE_LINKS = " + json.dumps(links_obj, indent=2) + ";\n"
        "function siteFlavor() {\n"
        '  const h = location.hostname;\n'
        '  if (h === "gasbrazil.github.io") return "hub";\n'
        '  if (h === "caissonpoint.github.io") return "caissonpoint";\n'
        '  return "custom";\n'
        "}\n"
        "function initCrossLinks() {\n"
        "  const flavor = siteFlavor();\n"
        f"  {set_lines}\n"
        "}\n"
    )


# Products dropdown: open on hover (short delay + CSS fade) for pointer
# devices; click still toggles for touch / keyboard. Scoped to .products-dd
# so the gap between trigger and menu doesn't immediately dismiss.
_PRODUCTS_DROPDOWN_JS = r"""<script>
(function () {
  var OPEN_MS = 120;
  var CLOSE_MS = 220;
  var openTimer = null;
  var closeTimer = null;

  function menuLinks(dd) {
    return Array.prototype.slice.call(dd.querySelectorAll(".dd-menu a"));
  }
  function setOpen(dd, open) {
    if (!dd) return;
    var menu = dd.querySelector(".dd-menu");
    var btn = dd.querySelector(".dd-trigger");
    if (!menu || !btn) return;
    menu.classList.toggle("is-open", !!open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  function closeAll(except) {
    document.querySelectorAll(".products-dd").forEach(function (dd) {
      if (dd !== except) setOpen(dd, false);
    });
  }
  function scheduleOpen(dd) {
    clearTimeout(closeTimer);
    clearTimeout(openTimer);
    openTimer = setTimeout(function () {
      closeAll(dd);
      setOpen(dd, true);
    }, OPEN_MS);
  }
  function scheduleClose(dd) {
    clearTimeout(openTimer);
    clearTimeout(closeTimer);
    closeTimer = setTimeout(function () {
      setOpen(dd, false);
    }, CLOSE_MS);
  }
  function focusLink(dd, idx) {
    var items = menuLinks(dd);
    if (!items.length) return;
    var i = ((idx % items.length) + items.length) % items.length;
    items[i].focus();
  }
  function bind(dd) {
    if (dd.getAttribute("data-dd-bound") === "1") return;
    dd.setAttribute("data-dd-bound", "1");
    dd.addEventListener("mouseenter", function () { scheduleOpen(dd); });
    dd.addEventListener("mouseleave", function () { scheduleClose(dd); });
  }
  function bindAll() {
    document.querySelectorAll(".products-dd").forEach(bind);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindAll);
  else bindAll();

  document.addEventListener("click", function (e) {
    var trigger = e.target.closest(".dd-trigger");
    if (trigger) {
      var dd = trigger.closest(".products-dd");
      var menu = dd && dd.querySelector(".dd-menu");
      if (dd && menu) {
        clearTimeout(openTimer);
        clearTimeout(closeTimer);
        var open = !menu.classList.contains("is-open");
        closeAll(open ? dd : null);
        setOpen(dd, open);
      }
      return;
    }
    if (!e.target.closest(".products-dd")) closeAll(null);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var openDd = document.querySelector(".products-dd .dd-menu.is-open");
      var dd = openDd && openDd.closest(".products-dd");
      closeAll(null);
      if (dd) {
        var btn = dd.querySelector(".dd-trigger");
        if (btn) btn.focus();
      }
      return;
    }
    var inTrigger = e.target.closest && e.target.closest(".dd-trigger");
    var inMenu = e.target.closest && e.target.closest(".dd-menu");
    var dd = (inTrigger && inTrigger.closest(".products-dd")) ||
             (inMenu && e.target.closest(".products-dd"));
    if (!dd) return;
    var items = menuLinks(dd);
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setOpen(dd, true);
      var idx = items.indexOf(document.activeElement);
      if (e.key === "Home") focusLink(dd, 0);
      else if (e.key === "End") focusLink(dd, items.length - 1);
      else if (e.key === "ArrowDown") focusLink(dd, idx < 0 ? 0 : idx + 1);
      else focusLink(dd, idx < 0 ? items.length - 1 : idx - 1);
    }
  });
})();
</script>"""


def _menu_items_html(self_id: str) -> str:
    """One menu entry per dashboard site (hub order: desk, ons, pld, poc,
    contratos, flows, supply, precos); the current page renders as a
    non-clickable current item (checkmark) with aria-current=page."""
    i18n_keys = {
        "ons": "navOns",
        "poc": "navPoc",
        "contratos": "navContratos",
        "flows": "navFlows",
        "mago": "navMago",
        "nts": "navNts",
        "monitor": "navMonitor",
        "supply": "navSupply",
        "pld": "navPld",
        "precos": "navPrecos",
        "desk": "navDesk",
    }
    items: list[str] = []
    for k, v in _SITES.items():
        if k == "home":
            continue
        if k == self_id:
            items.append(
                f'<span class="is-current" role="menuitem" aria-current="page" data-i18n="{i18n_keys[k]}">'
                f'<span class="chk">✓</span>{html.escape(v["label"])}</span>'
            )
        else:
            items.append(
                f'<a id="link-{k}" href="{html.escape(v["custom"], quote=True)}" role="menuitem" data-i18n="{i18n_keys[k]}">'
                f'<span class="chk"></span>{html.escape(v["label"])}</a>'
            )
    return "".join(items)


_BRAND_MARK_BUTTON = (
    '<button type="button" class="dd-trigger brand-mark" aria-haspopup="menu" '
    'aria-expanded="false" aria-controls="gb-products-menu" '
    'id="gb-products-trigger" data-i18n-aria="navMenu" aria-label="Menu">'
    '<span class="brand-mark-dot" aria-hidden="true"></span>'
    '<span class="dd-caret" aria-hidden="true"></span></button>'
)


def products_dropdown_html(self_id: str, brand_html: str) -> str:
    """Wordmark + blue-dot menu control + products menu. brand_html is the
    clickable (or static) title without the trailing dot; the dot lives on
    .brand-mark and turns flag-yellow on hover."""
    return (
        '<div class="products-dd">'
        '<span class="brand-lockup">'
        + brand_html
        + _BRAND_MARK_BUTTON
        + "</span>"
        '<div class="dd-menu" id="gb-products-menu" role="menu" aria-labelledby="gb-products-trigger">'
        + _menu_items_html(self_id)
        + "</div></div>"
    )


def masthead_html(
    self_id: str,
    about_href: str = "../about/",
    wiki_href: str = "../wiki/",
) -> str:
    """Single-row dashboard masthead: brand-menu · title … Wiki/About.

    The GasBrazil wordmark is the leftmost control in the frame: hover
    (or the quiet caret, for touch/keyboard) opens the products list
    underneath it; a click on the wordmark still goes home. The page
    <h1> follows a 1px rule. Wiki / About sit on the right with PT and
    theme -- no hamburger wedged into the title or the right chrome.
    The current page is marked inside the menu with aria-current=page.
    href defaults to each site's custom-domain URL; initCrossLinks()
    rewrites sibling hrefs at view time for hostname/flavor -- the
    #link-<id> anchors getElementById-looked-up, so nesting inside the
    dropdown needs no site_links_js() changes. wiki_href/about_href are
    plain relative paths (not run through initCrossLinks) since the wiki
    and about page only exist at one location, not mirrored per-flavor.

    Single source of truth so every dashboard's header stays in the same
    order with the same labels, and a newly-added site lands everywhere
    from one edit."""
    home = _SITES["home"]
    # Caret is a sibling of the home link so applyI18n() on navHome cannot
    # wipe it. Hover is bound on .products-dd, so the wordmark itself opens
    # the menu; the caret is the keyboard/touch target.
    brand_menu = products_dropdown_html(
        self_id,
        f'<a class="masthead-brand" id="link-home" href="{home["custom"]}" data-i18n="navHome">'
        f'{html.escape(home["label"])}</a>',
    )
    wiki_href_esc = html.escape(wiki_href, quote=True)
    about_href_esc = html.escape(about_href, quote=True)
    search_btn = (
        '<button type="button" class="gb-search-btn" id="gb-search-trigger" aria-label="Search (Ctrl+K)" title="Search (Ctrl+K)">'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
        '<span data-i18n="searchBtn">Search</span> <kbd>Ctrl+K</kbd>'
        '</button>'
    )
    trail = (
        '<div class="nav-trail">'
        f'<a class="navlink" href="{wiki_href_esc}" data-i18n="navWiki">Wiki</a>'
        f'<a class="navlink" href="{about_href_esc}" data-i18n="navAbout">About</a>'
        f'{search_btn}'
        "</div>"
    )
    return (
        '<div class="masthead">\n      '
        '<div class="masthead-ident">\n      '
        + brand_menu
        + '\n      <span class="crumb-sep" aria-hidden="true"></span>\n      '
        + page_intro_html(self_id)
        + "\n      </div>\n      "
        + trail
        + "\n      "
        + _PRODUCTS_DROPDOWN_JS
        + "\n    </div>"
    )


def chart_palette_js() -> str:
    """JS helpers: chartPalette() + tsoColorOf() + placeChartTooltip().

    placeChartTooltip keeps hover tips compact and on-screen: prefer to the
    right of the cursor, flip left near the right edge, clamp vertically.

    Tooltips are position:fixed. On mobile, pointerleave often never fires
    after a tap (iOS sticky-hover), so the tip stays glued to the viewport
    while the user scrolls, opens the products menu, or switches tabs.
    hideChartTooltips() dismisses every .tt on scroll, navigation, and
    pointerdown outside the chart SVG.
    """
    return r"""
function chartPalette() {
  const s = getComputedStyle(document.documentElement);
  return [1,2,3,4,5,6,7,8].map(i => (s.getPropertyValue('--chart-' + i) || '').trim()).filter(Boolean);
}
function tsoColorOf(tso, shadeIndex) {
  const s = getComputedStyle(document.documentElement);
  const code = String(tso || '').toLowerCase();
  if (!code) return chartPalette()[0] || 'var(--accent)';
  const shades = [1,2,3,4].map(i => (s.getPropertyValue('--tso-' + code + '-' + i) || '').trim()).filter(Boolean);
  if (shades.length) {
    const idx = Math.max(0, Number(shadeIndex) || 0);
    return shades[idx % shades.length];
  }
  const base = (s.getPropertyValue('--tso-' + code) || '').trim();
  return base || chartPalette()[0] || 'var(--accent)';
}
function tsoFromChartKey(key) {
  const k = String(key || '');
  if (k.indexOf('||') >= 0) return k.split('||')[0];
  if (k.indexOf('AGG:') === 0) {
    const part = k.split(':')[1];
    return (part && part !== 'ALL') ? part : '';
  }
  return '';
}
function hideChartTooltips() {
  document.querySelectorAll(".tt").forEach(function (el) {
    el.style.display = "none";
    if (el._gbIo) { el._gbIo.disconnect(); el._gbIo = null; }
  });
}
var __gbChartTtScrollLock = false;
var __gbChartTtScrollTimer = 0;
function bindChartTooltipDismiss() {
  if (window.__gbChartTtBound) return;
  window.__gbChartTtBound = true;
  function hideFromScroll() {
    __gbChartTtScrollLock = true;
    hideChartTooltips();
    window.clearTimeout(__gbChartTtScrollTimer);
    __gbChartTtScrollTimer = window.setTimeout(function () {
      __gbChartTtScrollLock = false;
    }, 180);
  }
  window.addEventListener("scroll", hideFromScroll, { capture: true, passive: true });
  window.addEventListener("resize", hideChartTooltips, { passive: true });
  window.addEventListener("orientationchange", hideChartTooltips);
  window.addEventListener("pagehide", hideChartTooltips);
  window.addEventListener("pageshow", hideChartTooltips);
  window.addEventListener("hashchange", hideChartTooltips);
  window.addEventListener("popstate", hideChartTooltips);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") hideChartTooltips();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") hideChartTooltips();
  });
  document.addEventListener("pointercancel", hideFromScroll, true);
  document.addEventListener("pointerdown", function (ev) {
    const t = ev.target;
    if (t && t.closest) {
      if (t.closest(".tt")) return;
      if (t.closest("svg")) return;
    }
    hideChartTooltips();
  }, true);
}
bindChartTooltipDismiss();
function watchChartTooltipAnchor(tt, clientX, clientY) {
  if (!tt || typeof IntersectionObserver === "undefined") return;
  if (tt._gbIo) { tt._gbIo.disconnect(); tt._gbIo = null; }
  const node = document.elementFromPoint(clientX, clientY);
  const svg = node && node.closest && node.closest("svg");
  if (!svg) return;
  const io = new IntersectionObserver(function (entries) {
    for (let i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting) {
        hideChartTooltips();
        return;
      }
    }
  }, { threshold: 0 });
  io.observe(svg);
  tt._gbIo = io;
}
function placeChartTooltip(tt, clientX, clientY) {
  if (!tt) return;
  if (__gbChartTtScrollLock) return;
  bindChartTooltipDismiss();
  tt.style.display = "block";
  const pad = 12, gap = 14;
  const tw = tt.offsetWidth, th = tt.offsetHeight;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = clientX + gap;
  if (left + tw > vw - pad) left = clientX - tw - gap;
  if (left < pad) left = pad;
  if (left + tw > vw - pad) left = Math.max(pad, vw - tw - pad);
  let top = clientY - th / 2;
  if (top < pad) top = pad;
  if (top + th > vh - pad) top = Math.max(pad, vh - th - pad);
  tt.style.left = left + "px";
  tt.style.top = top + "px";
  watchChartTooltipAnchor(tt, clientX, clientY);
}
""".lstrip()


def refreshed_local_js() -> str:
    """JS helper: format an ISO timestamp as local time only -- 24-hour
    HH:MM, viewer's IANA timezone name, no UTC. Single source of truth for
    the "Last refreshed" asof-strip value across every dashboard, so a
    format change (like dropping UTC or switching to 24-hour time) only
    has to happen once. Falls back to `fallback` (the server-rendered UTC
    string) if the ISO string can't be parsed. `locale` is optional and
    only affects date-part punctuation / month-day order (e.g. "pt-BR");
    the time part is always 24-hour regardless of locale, since that's the
    whole point -- no AM/PM ambiguity.
    """
    return (
        "function formatRefreshedLocal(iso, fallback, locale) {\n"
        "  try {\n"
        "    const d = new Date(iso);\n"
        "    if (isNaN(d.getTime())) return fallback || \"\u2014\";\n"
        "    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;\n"
        "    const datePart = d.toLocaleDateString(locale, "
        "{ year: 'numeric', month: '2-digit', day: '2-digit' });\n"
        "    const timePart = d.toLocaleTimeString(locale, "
        "{ hour: '2-digit', minute: '2-digit', hour12: false });\n"
        "    return datePart + ' ' + timePart + ' ' + tz;\n"
        "  } catch (e) {\n"
        "    return fallback || \"\u2014\";\n"
        "  }\n"
        "}\n"
        "const STALE_MAX_LAG_DAYS = " + json.dumps(STALE_LAG_DAYS) + ";\n"
        "function initStalenessBadgeFor(site, through) {\n"
        "  try {\n"
        "    var maxLag = STALE_MAX_LAG_DAYS[site];\n"
        "    if (!through || !maxLag) return;\n"
        "    var m = String(through).match(/(\\d{4})-(\\d{2})(?:-(\\d{2}))?/);\n"
        "    if (!m) return;\n"
        "    var d = m[3] ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(+m[1], +m[2], 0);\n"
        "    if (isNaN(d.getTime())) return;\n"
        "    var days = Math.floor((Date.now() - d.getTime()) / 864e5);\n"
        "    if (days <= maxLag) return;\n"
        "    var strip = document.getElementById(\"asof-strip\");\n"
        "    if (!strip || strip.querySelector(\".stale-badge\")) return;\n"
        "    var b = document.createElement(\"span\");\n"
        "    b.className = \"stale-badge\";\n"
        "    b.textContent = (typeof t === \"function\" ? t(\"staleBadge\") : \"Data may be stale\")"
        " + \" \\u00b7 \" + days + \"d\";\n"
        "    strip.appendChild(b);\n"
        "  } catch (e) {}\n"
        "}\n"
    )
