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
    navDesk: "The Desk",
    navProducts: "Products", // retained for previously deployed pages cached in browsers
    navMenu: "Menu",
    navAbout: "About",
    navWiki: "Wiki",
    filterPlaceholder: "Filter…",
    contact: "Contact",
    copyLink: "Copy link",
    linkCopied: "Copied",
    tagline: "Analytical Firepower for Brazil's Energy Markets",
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
    methodAssump_pld: "Daily averages by submarket; SIN has no PLD (join map v1).",
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
    backHome: "Back to GasBrazil"
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
    navDesk: "The Desk",
    navProducts: "Produtos", // retained for previously deployed pages cached in browsers
    navMenu: "Menu",
    navAbout: "Sobre",
    navWiki: "Wiki",
    filterPlaceholder: "Filtrar…",
    contact: "Contato",
    copyLink: "Copiar link",
    linkCopied: "Copiado",
    tagline: "Potência analítica para os mercados de energia do Brasil",
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
    methodAssump_pld: "Médias diárias por submercado; SIN não tem PLD (mapa de junção v1).",
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
    backHome: "Voltar ao GasBrazil"
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
  filterInput.addEventListener("input", () => {
    filters[col.key] = filterInput.value.toLowerCase();
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
    "pld": "Daily averages by submarket; SIN has no PLD (join map v1).",
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
    "aboutCoverPld": "PLD: CCEE daily averages by submarket; optional ONS CMO and median gas CVU when lake data is present.",
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


def masthead_html(
    self_id: str,
    about_href: str = "../about/",
    wiki_href: str = "../wiki/",
) -> str:
    """Single-row dashboard masthead: brand · title … Wiki/About/☰.

    One in-flow row: the GasBrazil wordmark links home, a quiet rule leads
    into the page <h1> (each name appears exactly once), and Wiki / About /
    the products menu sit on the right with the page's PT and theme
    toggles. The menu trigger is icon-only (aria-label Menu) so the title
    line is not a breadcrumb-plus-hamburger. The current page is marked
    inside the menu with aria-current=page. href defaults to each site's
    custom-domain URL; initCrossLinks() rewrites sibling hrefs at view time
    for hostname/flavor -- the #link-<id> anchors getElementById-looked-up,
    so nesting inside the dropdown needs no site_links_js() changes.
    wiki_href/about_href are plain relative paths (not run through
    initCrossLinks) since the wiki and about page only exist at one
    location, not mirrored per-flavor.

    Single source of truth so every dashboard's header stays in the same
    order with the same labels, and a newly-added site lands everywhere
    from one edit."""
    home = _SITES["home"]
    brand = (
        f'<a class="masthead-brand" id="link-home" href="{home["custom"]}" data-i18n="navHome">'
        f'{html.escape(home["label"])}</a>'
    )
    # Icon-only trigger: data-i18n-aria (not data-i18n) so applyI18n() never
    # wipes the hamburger glyph when the language toggles.
    menu = (
        '<div class="products-dd">'
        '<button type="button" class="dd-trigger" aria-haspopup="menu" '
        'aria-expanded="false" aria-controls="gb-products-menu" '
        'id="gb-products-trigger" data-i18n-aria="navMenu" aria-label="Menu">'
        '<span class="dd-icon" aria-hidden="true">☰</span></button>'
        '<div class="dd-menu" id="gb-products-menu" role="menu" aria-labelledby="gb-products-trigger">'
        + _menu_items_html(self_id) + "</div>"
        "</div>"
    )
    wiki_href_esc = html.escape(wiki_href, quote=True)
    about_href_esc = html.escape(about_href, quote=True)
    # Wiki / About / products sit in .nav-trail; theme.css places that group
    # on the same in-flow row as the PT / theme toggles (no position:fixed).
    trail = (
        '<div class="nav-trail">'
        f'<a class="navlink" href="{wiki_href_esc}" data-i18n="navWiki">Wiki</a>'
        f'<a class="navlink" href="{about_href_esc}" data-i18n="navAbout">About</a>'
        + menu
        + "</div>"
    )
    return (
        '<div class="masthead">\n      '
        '<div class="masthead-ident">\n      '
        + brand
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
function placeChartTooltip(tt, clientX, clientY) {
  if (!tt) return;
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
