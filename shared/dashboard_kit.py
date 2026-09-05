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
DEFAULT_FONT_PATH = HERE / "fonts" / "Degular.ttf"
DEFAULT_FAVICON_PATH = HERE / "favicon.png"

# Raw theme.css text, __FONT_FACE__ placeholder still unresolved -- callers
# combine this with embed_font_face() (see render_theme_css below) and their
# own per-project accent block before dropping it into their TEMPLATE.
THEME_CSS = THEME_CSS_PATH.read_text(encoding="utf-8")


def embed_font_face(font_path: Path | str = DEFAULT_FONT_PATH) -> str:
    """Return a base64-embedded @font-face rule for Degular, or "" if the
    font file isn't present in this checkout (degrade to the system font
    stack rather than ship a broken @font-face rule)."""
    font_path = Path(font_path)
    if not font_path.exists():
        return ""
    font_b64 = base64.b64encode(font_path.read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'Degular';font-weight:400;font-style:normal;"
        "font-display:swap;src:url(data:font/ttf;base64," + font_b64 +
        ") format('truetype');}"
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
    navAbout: "About",
    navWiki: "Wiki",
    contact: "Contact",
    tagline: "Data tools for Brazil's natural gas market — grid balances, pipeline capacity, and contracted transport activity, refreshed daily.",
    aboutLead: "Independent, public-data dashboards. Nothing here is an official ONS, ANP, CCEE, or transportadora product.",
    aboutBody: "GasBrazil.com consolidates open Brazilian gas and power data into three self-contained tools you can filter, chart, and export. Numbers come from public APIs and open-data portals; caveats live on each dashboard and on the About page.",
    cardOns: "ONS Balances",
    cardOnsDesc: "Daily grid balances, thermal generation by plant, and gas-fired dispatch across Brazil's interconnected power system.",
    cardPoc: "POC Results",
    cardPocDesc: "Pipeline capacity offer results — balancing, GUS acquisition, and linepack trades across TBG, TAG, and NTS.",
    cardContratos: "POC Contracts",
    cardContratosDesc: "Active transport and master transport contracts across TBG, TAG, and NTS. Legacy and access-connection contracts are not yet included.",
    kpiRefresh: "Last refreshed",
    sources: "Official sources",
    sourceOns: "ONS open data",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceAnp: "ANP gas transport movement",
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
    aboutCoverBody: "POC Contracts currently include Transport Contract and Master Contract rows. Legacy transport contracts and access connections are on the official portal but are not in this feed yet.",
    notFound: "This page is not here.",
    notFoundBody: "The hub and three dashboards are linked below.",
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
    navAbout: "Sobre",
    navWiki: "Wiki",
    contact: "Contato",
    tagline: "Ferramentas de dados para o mercado de gás natural do Brasil — balanços do SIN, capacidade de gasodutos e contratos de transporte, atualizados diariamente.",
    aboutLead: "Painéis independentes com dados públicos. Isto não é um produto oficial da ONS, da ANP, da CCEE ou das transportadoras.",
    aboutBody: "O GasBrazil.com reúne dados abertos de gás e energia do Brasil em três ferramentas que você pode filtrar, graficar e exportar. Os números vêm de APIs e portais públicos; as ressalvas estão em cada painel e na página Sobre.",
    cardOns: "Balanços ONS",
    cardOnsDesc: "Balanços diários do SIN, geração térmica por usina e despacho a gás no sistema interligado.",
    cardPoc: "Resultados POC",
    cardPocDesc: "Resultados da oferta de capacidade — balanceamento, aquisição de GUS e linepack em TBG, TAG e NTS.",
    cardContratos: "Contratos POC",
    cardContratosDesc: "Contratos de transporte e contratos master ativos em TBG, TAG e NTS. Contratos legados e conexões de acesso ainda não entram.",
    kpiRefresh: "Última atualização",
    sources: "Fontes oficiais",
    sourceOns: "Dados abertos da ONS",
    sourcePoc: "Portal de Oferta de Capacidade",
    sourceAnp: "Movimentação de gás da ANP",
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
    aboutCoverBody: "Contratos POC incluem hoje Contrato de Transporte e Contrato Master. Contratos de transporte legado e conexões de acesso estão no portal oficial, mas ainda não neste feed.",
    notFound: "Esta página não existe.",
    notFoundBody: "O hub e os três painéis estão nos links abaixo.",
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
        "label": "ONS Balances Dashboard",
        "custom": "https://gasbrazil.com/ons/",
        "caissonpoint": "https://caissonpoint.github.io/ons-dashboard/",
        "hub": "https://gasbrazil.github.io/ons/",
    },
    "poc": {
        "label": "POC Results Dashboard",
        "custom": "https://gasbrazil.com/poc/",
        "caissonpoint": "https://caissonpoint.github.io/poc-dashboard/",
        "hub": "https://gasbrazil.github.io/poc/",
    },
    "contratos": {
        "label": "POC Contracts Dashboard",
        "custom": "https://gasbrazil.com/contratos/",
        "caissonpoint": "https://caissonpoint.github.io/poc-contratos/",
        "hub": "https://gasbrazil.github.io/contratos/",
    },
}


def site_links_js(self_id: str) -> str:
    """JS block defining SITE_LINKS (every site except self_id), siteFlavor()
    and initCrossLinks(), which sets `#link-<id>` anchors' href from
    location.hostname at view time (so one build can be published to more
    than one hostname -- custom domain, caissonpoint Pages, gasbrazil hub
    mirror -- and each copy still links to its own equivalent siblings)."""
    others = {k: v for k, v in _SITES.items() if k != self_id}
    links_obj = {k: {kk: vv for kk, vv in v.items() if kk != "label"} for k, v in others.items()}
    set_lines = "\n  ".join(
        f'document.getElementById("link-{k}").href = SITE_LINKS.{k}[flavor];'
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
