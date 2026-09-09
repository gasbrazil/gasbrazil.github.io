# gasbrazil.github.io

Data tools for Brazil's natural gas market, consolidated into one repo, one
GitHub Pages deployment, one custom domain. See
[ADR-001](../../claude/ADR-001-gasbrazil-dashboards-consolidation.md) (kept
in the project's Claude workspace, not this repo) for the full reasoning;
this README covers what actually lives here and how to change it.

## Why this repo exists

Three dashboards (`ons/`, `poc/`, `contratos/`) used to be three separate
repos under a personal account, each with its own copy of the same CSS,
fonts, and JS utility functions. A color or font change meant three edits,
verified three times, and the copies drifted (different accent colors,
different function names, one dashboard had Excel export and the other two
didn't). This repo fixes that two ways:

1. **One repo, one Pages site, path-based URLs.** `ons/`, `poc/`,
   `contratos/`, `flows/`, `supply/`, and `pld/` each build to their own
   `index.html`, committed straight into this repo, served at path URLs
   under one domain — no more one-subdomain-per-repo.
2. **A shared front-end kit.** `shared/theme.css` and
   `shared/dashboard_kit.py` hold the cosmetic and mechanical pieces every
   dashboard needs (palette, font embedding, the theme toggle, CSV/XLSX
   export, cross-dashboard nav links). Each `dashboard.py` imports from
   `shared/` instead of inlining its own copy. **Change a color in
   `shared/theme.css` and every dashboard picks it up on its next rebuild —
   one edit instead of three.**

The Python data pipelines (`ons_pipeline.py`, `poc_pipeline.py`,
`contratos_pipeline.py`, `flows_pipeline.py`, `supply_pipeline.py`,
`pld_pipeline.py`) are untouched by the shared-kit consolidation — each
dashboard still owns its own data model, layout, and business logic;
`shared/` only centralizes what was genuinely identical across all of them.

## Architecture

See [docs/ADR-002-future-architecture.md](docs/ADR-002-future-architecture.md)
for the progressive tracks beyond static HTML embeds:

1. **Canonical lake + schemas** (`shared/data_kit.py`, `shared/schemas/`, `shared/transforms.py`, `shared/joins.py`, `lake/`)
2. **Artifact delivery** — thin Pages shells fetch `payload.json.gz` from **Cloudflare R2** (all six dashboards)
3. **Read-only API** (`api/` FastAPI over the lake, including `/v1/power/pld-cmo`)

CI mirrors lake parquet to a private R2 bucket and uploads public artifacts
when the `R2_*` / `GASBRAZIL_*` repository secrets are set. Local builds
without those env vars still write sibling `payload.json.gz` for offline use.

## Structure

```
shared/                 theme.css + dashboard_kit.py + data_kit / schemas / transforms / joins
  fonts/…                 Pacaembu ExtraLight / Light / Regular / SemiBold
  favicon.png
lake/                   canonical parquet mirrors (gitignored except README)
docs/ADR-002-…          future architecture tracks
api/                    FastAPI read-only /v1 query layer (Track C)
ons/                    ONS grid-balances (thin HTML shell; data on R2)
poc/                    POC capacity-offer-results dashboard -- see poc/README.md
contratos/              POC transport-contracts dashboard -- see contratos/README.md
flows/                  ANP pipeline-flows (thin HTML shell; data on R2)
supply/                 ANP national gas supply balance -- see supply/README.md
precos/                 ANP Resolution 52/2011 gas price disclosures
pld/                    CCEE daily-average PLD prices -- see pld/README.md
desk/                   Cross-product market desk + spark calculator
build_home.py           builds the landing page (this file) from shared/theme.css
index.html              built landing page (committed -- served at /)
.github/workflows/
  home.yml                rebuilds index.html when shared/ or build_home.py changes
  ons.yml                 ons/'s own fetch -> build -> health-gate -> deploy
  poc.yml                 poc/'s own fetch -> build -> deploy
  contratos.yml           contratos/'s own fetch -> build -> deploy
  flows.yml               flows/'s own fetch -> build -> health-gate -> deploy
  supply.yml              supply/'s own fetch -> build -> deploy
  precos.yml              precos/'s own fetch -> build -> deploy
  pld.yml                 pld/'s own fetch -> build -> deploy
  desk.yml                desk rebuild from lake/sibling parquet
```

## Local Python

Install [uv](https://docs.astral.sh/uv/), then per app (or `api/`):

```bash
uv venv                  # creates .venv/ (gitignored)
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
uv pip install -r requirements.txt
```

CI uses the same `requirements.txt` files via `astral-sh/setup-uv` and
`uv pip install --system -c shared/constraints.txt`.

Unit tests (no network, no secrets):

```bash
uv pip install -r tests/requirements.txt -c shared/constraints.txt
python -m pytest -q
```

## Making a visual change

Edit `shared/theme.css` (a color, the font, the `.flagbar` gradient) or
`shared/dashboard_kit.py` (shared JS behavior — the theme toggle, CSV/XLSX
export, nav-link resolution) and push to `main`. Because each workflow
triggers on `paths: [<project>/**, shared/**]`, that one push rebuilds
**every dashboard and the landing page**, no per-project edits needed.
To change just one dashboard's own layout or data logic, edit that
project's own `dashboard.py` — nothing else needs to change.

## Deploy model

GitHub Pages is configured **Deploy from a branch → `main` / `(root)`**, not
the Actions-artifact deployment (`actions/deploy-pages`). That's a
deliberate choice: artifact-based deployment publishes one artifact as the
*entire* site per repo, which would make ons/poc/contratos/flows/home's
five independent workflows race to overwrite each other's deploy. Branch
deployment just serves whatever is currently committed, so each workflow
committing straight into its own subfolder (or root, for the landing
page) coexists without stepping on the others.

Each workflow ends with a commit-and-push step that retries with
`git pull --rebase` if the push is rejected (i.e. another workflow pushed
first). If the push still fails after five attempts the job fails — a
successful rebase after a rejected push is not treated as success.

## URL scheme

Path-based under one domain, per ADR-001 Decision 1 Option C:

| Path | Dashboard |
|---|---|
| `/` | Landing page (this repo's `index.html`) |
| `/ons/` | ONS grid balances |
| `/poc/` | POC capacity offer results |
| `/contratos/` | POC transport contracts |
| `/flows/` | ANP pipeline flows |
| `/supply/` | ANP national gas supply balance |
| `/precos/` | ANP Resolution 52/2011 gas price disclosures |
| `/pld/` | CCEE daily-average PLD prices |
| `/desk/` | Cross-product market desk + spark calculator |

Before the `gasbrazil.com` domain is cut over to this repo, the same
structure is reachable at `gasbrazil.github.io/...` for verification.
Cutover is a separate, deliberate step (removing the custom domain from the
old per-project repos' Pages settings, then adding `gasbrazil.com` as this
repo's custom domain) — not done as part of assembling this repo.

## What replaced the old per-repo mirror steps

The old `ons-dashboard`/`poc-dashboard`/`poc-contratos` repos each had a
conditional CI step that mirrored their built page to `gasbrazil/ons`,
`gasbrazil/poc`, `gasbrazil/contratos` (inert — the deploy-key secrets were
never set). This repo **is** that consolidation target now, so those mirror
steps aren't carried over: `ons/`, `poc/`, and `contratos/` build directly
into their own subfolders here instead of into separate repos.

`ons-dashboard`'s second fallback mirror (a firewall-friendly copy at
`ons-dashboard.github.io`, for visitors whose corporate DNS filter flags a
brand-new custom domain) also isn't carried over — revisit that if the same
issue shows up for `gasbrazil.com` after cutover.
