"""
Shared build-time helpers + reusable JS snippets for the GasBrazil.com
dashboard family (ons-dashboard, poc-dashboard, poc-contratos).

See ADR-001, Decision 2 Option C. Each project's own dashboard.py still owns
its own data model, TEMPLATE and layout -- this module only centralizes the
mechanical/cosmetic pieces that were previously pasted into all three:

  - font/favicon embedding (embed_font_face, embed_favicon)
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

# Pacaembu is a heavy geometric face -- site default is Light (300); mid
# emphasis is Regular (400); wordmark only uses SemiBold (600). Never Bold.
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
    """Return base64-embedded @font-face rules for the Pacaembu weight stack,
    or "" if no weight files are present (degrade to the system font stack).

    font_path is accepted for call-site compatibility; when it points at the
    shared fonts dir (or the Light file), all available weights are embedded.
    A one-off alternate path still embeds that single file at weight 300."""
    font_path = Path(font_path)
    faces: list[tuple[int, Path]] = []
    if font_path == DEFAULT_FONT_PATH or font_path == FONTS_DIR:
        for weight, name in PACAEMBU_FACES:
            p = FONTS_DIR / name
            if p.exists():
                faces.append((weight, p))
    elif font_path.exists():
        faces.append((300, font_path))
    if not faces:
        return ""
    rules = []
    for weight, path in faces:
        font_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            "@font-face{font-family:'Pacaembu';font-weight:" + str(weight) +
            ";font-style:normal;font-display:swap;src:url(data:font/ttf;base64," +
            font_b64 + ") format('truetype');}"
        )
    return "".join(rules)


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
    """Title, description, canonical, Open Graph, and hreflang tags.
    path is the site-relative path including a leading slash."""
    if not path.startswith("/"):
        path = "/" + path
    canonical = "https://gasbrazil.com" + path
    alt = "https://gasbrazil.github.io" + ("" if path == "/" else path.rstrip("/"))
    if path != "/" and not alt.endswith("/"):
        alt = alt + "/"
    desc = description.replace('"', "&quot;")
    return (
        f"<title>{title}</title>\n"
        f'<meta name="description" content="{desc}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
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
    navAbout: "About",
    navWiki: "Wiki",
    contact: "Contact",
    tagline: "Data tools for Brazil's natural gas market — grid balances, pipeline capacity, contracted transport, physical flows, supply balance, and power prices, refreshed regularly.",
    aboutLead: "Independent, public-data dashboards. Nothing here is an official ONS, ANP, CCEE, or transportadora product.",
    aboutBody: "GasBrazil.com consolidates open Brazilian gas and power data into self-contained tools you can filter, chart, and export. Numbers come from public APIs and open-data portals; caveats live on each dashboard and on the About page.",
    cardOns: "ONS Balances",
    cardOnsDesc: "Daily grid balances, thermal generation by plant, and gas-fired dispatch across Brazil's interconnected power system.",
    cardPoc: "POC Results",
    cardPocDesc: "Pipeline capacity offer results — balancing, GUS acquisition, and linepack trades across TBG, TAG, and NTS.",
    cardContratos: "POC Contracts",
    cardContratosDesc: "Active transport and master transport contracts across TBG, TAG, and NTS. Legacy and access-connection contracts are not yet included.",
    cardFlows: "Pipeline Flows",
    cardFlowsDesc: "Daily physical gas flow at every receipt and delivery point on Brazil's transport pipelines, plus system-use gas, losses, imbalance, and linepack.",
    cardSupply: "Gas Supply",
    cardSupplyDesc: "National monthly natural gas supply balance from ANP — production, available gas, flare and loss, own use, reinjection, LGN, and imports.",
    cardPld: "PLD Prices",
    cardPldDesc: "CCEE daily-average PLD (settlement price) by electricity submarket — Southeast, South, Northeast, and North. Not the same as ONS CMO.",
    kpiRefresh: "Last refreshed",
    sources: "Official sources",
    sourceOns: "ONS open data",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceAnp: "ANP gas transport movement",
    sourceFlows: "ANP open data — pipeline movement",
    sourceSupply: "ANP PPGN-EL — production by state",
    sourcePld: "CCEE open data — PLD média diária",
    pldSubtitle: "CCEE daily-average settlement price (PLD) by electricity submarket, in R$/MWh.",
    pldThrough: "Data through",
    pldNote: "PLD is CCEE's settlement price. It is related to, but not the same as, ONS CMO (marginal operating cost) — see",
    pldNoteLink: "ONS Balances",
    pldChartTitle: "Daily PLD by submarket",
    pldChartNote: "Last 24 months embedded. Toggle submarkets and date window below.",
    pldWindow: "Window",
    pldCsv: "Download CSV",
    pldXlsx: "Export all data (Excel)",
    pldFooter: "Data: CCEE (PLD média diária). Not an official CCEE product.",
    footerAbout: "About & methodology",
    aboutH1: "About GasBrazil",
    aboutWho: "What this is",
    aboutWhoBody: "A small independent site that republishes public Brazilian natural-gas and power-system data as filterable dashboards. It is not affiliated with ONS, ANP, CCEE, TBG, TAG, or NTS.",
    aboutHow: "How the data is built",
    aboutHowBody: "Each dashboard is a single static HTML file. GitHub Actions fetch the source, transform it, and embed a compressed payload in the page. There is no live API behind the published site.",
    aboutGloss: "Glossary",
    glossGus: "GUS — gas acquired by a transportadora for system use.",
    glossLinepack: "Linepack — inventory held inside the pipeline, traded to balance the network.",
    glossBal: "Residual / operational balancing — short-term PEG processes that clear imbalances.",
    glossCmo: "CMO — ONS marginal operating cost (R$/MWh). Not the same as CCEE's PLD settlement price.",
    glossMaster: "Master transport contract — framework that enables later transport nominations; not itself a firm capacity booking.",
    aboutCover: "Coverage limits",
    aboutCoverBody: "POC Contracts currently include Transport Contract and Master Contract rows. Legacy transport contracts and access connections appear on the official portal UI but are not served by the public GraphQL API (re-verified September 2026: no legado/conexão fields in the schema). They will be added when that endpoint is identified.",
    aboutCoverFlows: "Pipeline Flows has no published ANP data for 2022, and each month is typically released with a lag of several weeks. Average pressure is available in the dashboard variable list. Shipper-level flow detail is not embedded (capacity by shipper lives on POC Contracts). TSB and GOM can be included via a toggle.",
    aboutCoverSupply: "Gas Supply uses ANP PPGN-EL national monthly series plus national natural-gas imports. The open import CSV does not split Bolivia pipeline vs LNG cargoes.",
    aboutCoverPld: "PLD Prices shows CCEE daily-average PLD by submarket. It is not ONS CMO — see ONS Balances for marginal operating cost.",
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
    navAbout: "Sobre",
    navWiki: "Wiki",
    contact: "Contato",
    tagline: "Ferramentas de dados para o mercado de gás natural do Brasil — balanços do SIN, capacidade de gasodutos, contratos de transporte, fluxos físicos e preços de energia, atualizados diariamente.",
    aboutLead: "Painéis independentes com dados públicos. Isto não é um produto oficial da ONS, da ANP, da CCEE ou das transportadoras.",
    aboutBody: "O GasBrazil.com reúne dados abertos de gás e energia do Brasil em ferramentas que você pode filtrar, graficar e exportar. Os números vêm de APIs e portais públicos; as ressalvas estão em cada painel e na página Sobre.",
    cardOns: "Balanços ONS",
    cardOnsDesc: "Balanços diários do SIN, geração térmica por usina e despacho a gás no sistema interligado.",
    cardPoc: "Resultados POC",
    cardPocDesc: "Resultados da oferta de capacidade — balanceamento, aquisição de GUS e linepack em TBG, TAG e NTS.",
    cardContratos: "Contratos POC",
    cardContratosDesc: "Contratos de transporte e contratos master ativos em TBG, TAG e NTS. Contratos legados e conexões de acesso ainda não entram.",
    cardFlows: "Fluxos de Gasodutos",
    cardFlowsDesc: "Fluxo físico diário em cada ponto de recebimento e entrega dos gasodutos de transporte do Brasil, além de gás de uso do sistema, perdas, desequilíbrio e linepack.",
    cardSupply: "Oferta de Gás",
    cardSupplyDesc: "Balanço mensal nacional de gás natural da ANP — produção, disponível, queima e perda, consumo próprio, reinjeção, LGN e importações.",
    cardPld: "Preços PLD",
    cardPldDesc: "PLD médio diário da CCEE por submercado — Sudeste, Sul, Nordeste e Norte. Não é o CMO da ONS.",
    kpiRefresh: "Última atualização",
    sources: "Fontes oficiais",
    sourceOns: "Dados abertos da ONS",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceAnp: "Movimentação de gás da ANP",
    sourceFlows: "Dados abertos da ANP — movimentação em gasodutos",
    sourceSupply: "ANP PPGN-EL — produção por estado",
    sourcePld: "Dados abertos da CCEE — PLD média diária",
    pldSubtitle: "Preço médio diário de liquidação (PLD) da CCEE por submercado, em R$/MWh.",
    pldThrough: "Dados até",
    pldNote: "O PLD é o preço de liquidação da CCEE. Relaciona-se ao CMO da ONS (custo marginal de operação), mas não é a mesma série — veja",
    pldNoteLink: "Balanços ONS",
    pldChartTitle: "PLD diário por submercado",
    pldChartNote: "Últimos 24 meses embutidos. Alterne submercados e a janela abaixo.",
    pldWindow: "Janela",
    pldCsv: "Baixar CSV",
    pldXlsx: "Exportar tudo (Excel)",
    pldFooter: "Dados: CCEE (PLD média diária). Não é um produto oficial da CCEE.",
    footerAbout: "Sobre e metodologia",
    aboutH1: "Sobre o GasBrazil",
    aboutWho: "O que é isto",
    aboutWhoBody: "Um site independente que republica dados públicos de gás natural e do sistema elétrico brasileiro em painéis filtráveis. Não tem vínculo com ONS, ANP, CCEE, TBG, TAG ou NTS.",
    aboutHow: "Como os dados são montados",
    aboutHowBody: "Cada painel é um único arquivo HTML estático. O GitHub Actions busca a fonte, transforma e embute o payload compactado na página. O site publicado não tem API ao vivo.",
    aboutGloss: "Glossário",
    glossGus: "GUS — gás adquirido pela transportadora para uso do sistema.",
    glossLinepack: "Linepack — estoque dentro do gasoduto, negociado para balancear a rede.",
    glossBal: "Balanceamento residual / operacional — processos de curto prazo da PEG que zeram desequilíbrios.",
    glossCmo: "CMO — custo marginal de operação da ONS (R$/MWh). Não é o PLD da CCEE.",
    glossMaster: "Contrato master de transporte — quadro que habilita nomeações posteriores; não é, por si, uma reserva firme de capacidade.",
    aboutCover: "Limites de cobertura",
    aboutCoverBody: "Contratos POC incluem hoje Contrato de Transporte e Contrato Master. Contratos de transporte legado e conexões de acesso aparecem na UI do portal oficial, mas não são servidos pela API GraphQL pública (reconfirmado em setembro de 2026: sem campos legado/conexão no schema). Serão adicionados quando esse endpoint for identificado.",
    aboutCoverFlows: "Fluxos de Gasodutos não tem dados publicados pela ANP para 2022, e cada mês costuma ser divulgado com semanas de atraso. A pressão média está na lista de variáveis do painel. O detalhe por carregador não é embutido (capacidade por carregador fica em Contratos POC). TSB e GOM podem ser incluídos por um seletor.",
    aboutCoverSupply: "Oferta de Gás usa as séries mensais nacionais PPGN-EL da ANP mais importações nacionais de gás natural. O CSV aberto de importação não separa Gasbol (Bolívia) de GNL.",
    aboutCoverPld: "Preços PLD mostra o PLD médio diário da CCEE por submercado. Não é o CMO da ONS — veja Balanços ONS para o custo marginal de operação.",
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
    (home, ons, poc, contratos, flows, supply, pld), with the current page
    marked aria-current=page / is-active (not a link). Then any page-specific
    extras (e.g. ONS Wiki), then About. href defaults to each site's
    custom-domain URL; initCrossLinks() rewrites sibling hrefs at view
    time for hostname/flavor.

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
