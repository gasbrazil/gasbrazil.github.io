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
import json
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

# Raw theme.css text, __FONT_FACE__ placeholder still unresolved -- callers
# combine this with embed_font_face() (see render_theme_css below) and their
# own per-project accent block before dropping it into their TEMPLATE.
THEME_CSS = THEME_CSS_PATH.read_text(encoding="utf-8")


def embed_font_face(font_path: Path | str = DEFAULT_FONT_PATH) -> str:
    """Return @font-face rules pointing at /shared/fonts/*.ttf, or "" if none.

    Fonts are loaded as separate cacheable files (not base64-inlined). Keep
    font-display:swap so text paints with the system stack first.

    font_path is accepted for call-site compatibility; when it points at the
    shared fonts dir (or the Light file), all available weights are linked.
    A one-off alternate path still emits a single face at weight 300."""
    font_path = Path(font_path)
    faces: list[tuple[int, str]] = []
    if font_path == DEFAULT_FONT_PATH or font_path == FONTS_DIR:
        for weight, name in PACAEMBU_FACES:
            if (FONTS_DIR / name).exists():
                faces.append((weight, name))
    elif font_path.exists():
        faces.append((300, font_path.name))
    if not faces:
        return ""
    rules = []
    for weight, name in faces:
        url = f"{FONTS_URL_PREFIX}/{name}"
        rules.append(
            "@font-face{font-family:'Pacaembu';font-weight:" + str(weight) +
            ";font-style:normal;font-display:swap;src:url('" + url +
            "') format('truetype');}"
        )
    return "".join(rules)


def font_preload_html(*, weight: int = 300) -> str:
    """<link rel=preload> for the default Pacaembu weight (Light = 300)."""
    name = next((n for w, n in PACAEMBU_FACES if w == weight), None)
    if not name or not (FONTS_DIR / name).exists():
        return ""
    href = f"{FONTS_URL_PREFIX}/{name}"
    return (
        f'<link rel="preload" href="{href}" as="font" type="font/ttf" crossorigin>'
    )


def embed_favicon(favicon_path: Path | str = DEFAULT_FAVICON_PATH,
                   fallback_hex: str = "#03183D") -> str:
    """Return a data: URI for the favicon, or a plain flat-color square
    (fallback_hex) if favicon.png isn't present in this checkout."""
    favicon_path = Path(favicon_path)
    if favicon_path.exists():
        favicon_b64 = base64.b64encode(favicon_path.read_bytes()).decode("ascii")
        return "data:image/png;base64," + favicon_b64
    return (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' "
        f"fill='%{fallback_hex.lstrip('#').upper()}'%3E%3C/rect%3E%3C/svg%3E"
        # Note: kept for byte-compatibility with the original three
        # dashboards' fallback marker; a valid data URI regardless of the
        # exact fallback_hex format passed in.
    ).replace("%%", "%")


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


def render(template: str, **replacements: str) -> str:
    """Small .replace() chain helper: render(TEMPLATE, PAYLOAD=b64,
    FAVICON_DATA_URI=uri) does the same thing as chaining
    .replace("__PAYLOAD__", b64).replace("{{FAVICON_DATA_URI}}", uri) but
    without every dashboard.py re-deciding its own placeholder spelling.
    Keys are matched against both __KEY__ and {{KEY}} spellings so existing
    templates don't need to be touched just to adopt this helper.
    """
    out = template
    for key, value in replacements.items():
        out = out.replace(f"__{key}__", value).replace(f"{{{{{key}}}}}", value)
    return out


def seo_head(*, title: str, description: str, path: str = "/") -> str:
    """Title, description, canonical, Open Graph, hreflang, and font preload.
    path is the site-relative path including a leading slash."""
    if not path.startswith("/"):
        path = "/" + path
    canonical = "https://gasbrazil.com" + path
    alt = "https://gasbrazil.github.io" + ("" if path == "/" else path.rstrip("/"))
    if path != "/" and not alt.endswith("/"):
        alt = alt + "/"
    desc = description.replace('"', "&quot;")
    preload = font_preload_html()
    preload_line = (preload + "\n") if preload else ""
    return (
        f"<title>{title}</title>\n"
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'{preload_line}'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:site_name" content="GasBrazil.com">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:locale" content="en_US">\n'
        f'<meta property="og:locale:alternate" content="pt_BR">\n'
        f'<link rel="alternate" hreflang="en" href="{canonical}">\n'
        f'<link rel="alternate" hreflang="pt-BR" href="{canonical}">\n'
        f'<link rel="alternate" hreflang="x-default" href="{canonical}">\n'
        f'<link rel="alternate" href="{alt}">'
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
async function inflateGzipUrl(url) {
  if (typeof DecompressionStream !== "function") {
    throw new Error("This browser lacks DecompressionStream (needs Chrome/Edge 80+, Firefox 113+, or Safari 16.4+).");
  }
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error("Failed to load " + url + " (" + res.status + ")");
  const ds = new DecompressionStream("gzip");
  const stream = res.body.pipeThrough(ds);
  return new TextDecoder().decode(await new Response(stream).arrayBuffer());
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
    if (localStorage.getItem("gasbrazil-theme") === "dark")
      document.documentElement.setAttribute("data-theme", "dark");
    var lang = localStorage.getItem("gasbrazil-lang");
    if (!lang)
      lang = ((navigator.language || "en").toLowerCase().indexOf("pt") === 0) ? "pt" : "en";
    document.documentElement.setAttribute("data-lang", lang);
    document.documentElement.setAttribute("lang", lang === "pt" ? "pt-BR" : "en");
  } catch (e) {}
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
    const label = dark ? (typeof t === "function" ? t("themeLight") : "Switch to light mode")
                       : (typeof t === "function" ? t("themeDark") : "Switch to dark mode");
    btn.title = label; btn.setAttribute("aria-label", label);
  }
  paint();
  btn.addEventListener("click", () => {
    const nextDark = !isDarkTheme();
    if (nextDark) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem(THEME_KEY, nextDark ? "dark" : "light"); } catch (e) {}
    paint();
    if (onChange) onChange(nextDark);
  });
}
"""

JS_I18N = r"""
const LANG_KEY = "gasbrazil-lang";
const GB_I18N = {
  en: {
    themeDark: "Switch to dark mode",
    themeLight: "Switch to light mode",
    langSwitch: "Português",
    skip: "Skip to content",
    navHome: "GasBrazil.com",
    navOns: "ONS Balances",
    navPoc: "POC Results",
    navContratos: "POC Contracts",
    navFlows: "Pipeline Flows",
    navSupply: "Gas Supply",
    navPld: "PLD Prices",
    navPrecos: "ANP Prices",
    navDesk: "The Desk",
    navAbout: "About",
    navWiki: "Wiki",
    contact: "Contact",
    tagline: "Public data for Brazil's natural gas and power markets.",
    aboutLead: "Independent public-data dashboards. Not an official ONS, ANP, CCEE, or transportadora product.",
    aboutBody: "GasBrazil.com republishes open Brazilian gas and power data as filterable dashboards. Caveats are on each page and on About.",
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
    cardPldDesc: "CCEE daily-average PLD by submarket.",
    cardPrecos: "ANP Prices",
    cardPrecosDesc: "ANP Resolution 52/2011 disclosed gas prices.",
    cardDesk: "The Desk",
    cardDeskDesc: "Cross-product snapshot across gas and power.",
    deskLinkOns: "ONS",
    deskLinkPld: "CCEE PLD",
    deskLinkPrecos: "ANP prices",
    deskLinkPoc: "POC",
    deskLinkFlows: "ANP flows",
    kpiRefresh: "Last refreshed",
    dataThrough: "Data through",
    sources: "Sources",
    sourceOns: "ONS open data",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceFlows: "ANP + TAG/TBG/NTS Portaria 1/2003 — pipeline movement",
    sourceSupply: "ANP PPGN-EL — production by state",
    sourcePrecos: "ANP — publicidade dos preços de gás natural",
    sourcePld: "CCEE open data — PLD média diária",
    pldSubtitle: "CCEE daily-average PLD by submarket (R$/MWh).",
    pldNote: "PLD (CCEE) is not the same series as ONS CMO. See",
    pldNoteLink: "ONS Balances",
    pldChartTitle: "Daily PLD by submarket",
    pldChartNote: "",
    pldCompareTitle: "PLD vs CMO vs gas CVU",
    pldCompareNote: "",
    pldWindow: "Window",
    pldCsv: "Download CSV",
    pldXlsx: "Export all data (Excel)",
    pldFooter: "Data: CCEE (PLD média diária). Not an official CCEE product.",
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
    aboutCoverPld: "PLD: CCEE daily averages by submarket; optional ONS CMO and median gas CVU when lake data is present.",
    aboutCoverDesk: "The Desk: cross-product headline series. Full history and filters live on each product page.",
    notFound: "This page is not here.",
    notFoundBody: "The hub and dashboards are linked below.",
    backHome: "Back to GasBrazil.com"
  },
  pt: {
    themeDark: "Mudar para o modo escuro",
    themeLight: "Mudar para o modo claro",
    langSwitch: "English",
    skip: "Ir para o conteúdo",
    navHome: "GasBrazil.com",
    navOns: "Balanços ONS",
    navPoc: "Resultados POC",
    navContratos: "Contratos POC",
    navFlows: "Fluxos de Gasodutos",
    navSupply: "Oferta de Gás",
    navPld: "Preços PLD",
    navPrecos: "Preços ANP",
    navDesk: "The Desk",
    navAbout: "Sobre",
    navWiki: "Wiki",
    contact: "Contato",
    tagline: "Dados públicos do mercado de gás e energia do Brasil.",
    aboutLead: "Painéis independentes com dados públicos. Não é produto oficial da ONS, ANP, CCEE ou transportadoras.",
    aboutBody: "O GasBrazil.com republica dados abertos de gás e energia em painéis filtráveis. Ressalvas em cada página e em Sobre.",
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
    cardPldDesc: "PLD médio diário da CCEE por submercado.",
    cardPrecos: "Preços ANP",
    cardPrecosDesc: "Preços divulgados pela ANP (Resolução 52/2011).",
    cardDesk: "The Desk",
    cardDeskDesc: "Retrato cruzado de gás e energia.",
    deskLinkOns: "ONS",
    deskLinkPld: "PLD CCEE",
    deskLinkPrecos: "Preços ANP",
    deskLinkPoc: "POC",
    deskLinkFlows: "Fluxos ANP",
    kpiRefresh: "Última atualização",
    dataThrough: "Dados até",
    sources: "Fontes",
    sourceOns: "Dados abertos da ONS",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceFlows: "ANP + TAG/TBG/NTS Portaria 1/2003 — movimentação em gasodutos",
    sourceSupply: "ANP PPGN-EL — produção por estado",
    sourcePrecos: "ANP — publicidade dos preços de gás natural",
    sourcePld: "Dados abertos da CCEE — PLD média diária",
    pldSubtitle: "PLD médio diário da CCEE por submercado (R$/MWh).",
    pldNote: "O PLD (CCEE) não é a mesma série do CMO da ONS. Veja",
    pldNoteLink: "Balanços ONS",
    pldChartTitle: "PLD diário por submercado",
    pldChartNote: "",
    pldCompareTitle: "PLD vs CMO vs CVU a gás",
    pldCompareNote: "",
    pldWindow: "Janela",
    pldCsv: "Baixar CSV",
    pldXlsx: "Exportar tudo (Excel)",
    pldFooter: "Dados: CCEE (PLD média diária). Não é um produto oficial da CCEE.",
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
    aboutCoverPld: "PLD: médias diárias da CCEE por submercado; CMO e CVU a gás da ONS quando disponíveis no lake.",
    aboutCoverDesk: "The Desk: séries-resumo entre produtos. Histórico e filtros ficam em cada painel.",
    notFound: "Esta página não existe.",
    notFoundBody: "O hub e os painéis estão nos links abaixo.",
    backHome: "Voltar ao GasBrazil.com"
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
  const blob = new Blob([text], { type: mime });
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
    const input = host.querySelector('.th-filter[data-col="' + col + '"]');
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
  filterInput.placeholder = "Filter…";
  filterInput.value = filters[col.key] || "";
  filterInput.addEventListener("input", () => {
    filters[col.key] = filterInput.value.toLowerCase();
    onChange(sortState, filters);
  });
  th.appendChild(filterInput);
  return th;
}
"""

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
        "label": "GasBrazil.com",
        "custom": "https://gasbrazil.com",
        "caissonpoint": "https://caissonpoint.github.io/gasbrazil-com/",
        "hub": "https://gasbrazil.github.io/",
    },
    "ons": {
        "label": "ONS Balances",
        "custom": "https://gasbrazil.com/ons/",
        "caissonpoint": "https://caissonpoint.github.io/ons-dashboard/",
        "hub": "https://gasbrazil.github.io/ons/",
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
    "supply": {
        "label": "Gas Supply",
        "custom": "https://gasbrazil.com/supply/",
        "caissonpoint": "https://gasbrazil.com/supply/",
        "hub": "https://gasbrazil.github.io/supply/",
    },
    "pld": {
        "label": "PLD Prices",
        "custom": "https://gasbrazil.com/pld/",
        "caissonpoint": "https://gasbrazil.com/pld/",
        "hub": "https://gasbrazil.github.io/pld/",
    },
    "precos": {
        "label": "ANP Prices",
        "custom": "https://gasbrazil.com/precos/",
        "caissonpoint": "https://gasbrazil.com/precos/",
        "hub": "https://gasbrazil.github.io/precos/",
    },
    "desk": {
        "label": "The Desk",
        "custom": "https://gasbrazil.com/desk/",
        "caissonpoint": "https://gasbrazil.com/desk/",
        "hub": "https://gasbrazil.github.io/desk/",
    },
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


def nav_links_html(self_id: str, about_href: str = "../about/", extra_links_html: str = "") -> str:
    """Standard header text nav: every site in _SITES in fixed order
    (home, ons, poc, contratos, flows, supply, pld, precos, …), with the
    current page marked aria-current=page / is-active (not a link). Then any
    page-specific extras (e.g. ONS Wiki), then About. href defaults to each
    site's custom-domain URL; initCrossLinks() rewrites sibling hrefs at
    view time for hostname/flavor.

    Single source of truth so every dashboard's nav stays in the same
    order with the same labels, and a newly-added site lands everywhere
    from one edit."""
    i18n_keys = {
        "home": "navHome",
        "ons": "navOns",
        "poc": "navPoc",
        "contratos": "navContratos",
        "flows": "navFlows",
        "supply": "navSupply",
        "pld": "navPld",
        "precos": "navPrecos",
        "desk": "navDesk",
    }
    parts: list[str] = []
    for k, v in _SITES.items():
        i18n = i18n_keys.get(k)
        i18n_attr = f' data-i18n="{i18n}"' if i18n else ""
        if k == self_id:
            parts.append(
                f'<span class="navlink is-active" aria-current="page"{i18n_attr}>{v["label"]}</span>'
            )
        else:
            parts.append(
                f'<a class="navlink" id="link-{k}" href="{v["custom"]}"{i18n_attr}>{v["label"]}</a>'
            )
    if extra_links_html:
        parts.append(extra_links_html)
    parts.append(f'<a class="navlink" href="{about_href}" data-i18n="navAbout">About</a>')
    return "\n      ".join(parts)


def chart_palette_js() -> str:
    """JS helper: CHART_PALETTE from CSS custom properties (--chart-1..8)."""
    return (
        "function chartPalette() {\n"
        "  const s = getComputedStyle(document.documentElement);\n"
        "  return [1,2,3,4,5,6,7,8].map(i => "
        "(s.getPropertyValue('--chart-' + i) || '').trim()).filter(Boolean);\n"
        "}\n"
    )
