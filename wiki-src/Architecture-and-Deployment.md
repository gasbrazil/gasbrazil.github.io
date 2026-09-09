# Architecture and Deployment

## The pattern every dashboard follows

```
fetch  →  build  →  dashboard  →  (health gate, on most)  →  commit  →  deploy
```

Each dashboard is its own folder (`ons/`, `poc/`, `contratos/`, `flows/`,
`supply/`, `pld/`, `precos/`, `desk/`) with the same shape: a `<slug>_pipeline.py`
CLI that fetches a public data source and aggregates it into a Parquet
store (`fetch` / `build` / sometimes `all`), and a `dashboard.py` (imported
by the CLI, or run standalone) that reads the store and writes one
self-contained `index.html` plus a sibling `payload.json.gz`. Nothing here
needs a database or a running server — the output is static files served by
GitHub Pages.

The browser fetches `payload.json.gz` and inflates it client-side via
`DecompressionStream` (Chrome/Edge 80+, Firefox 113+, Safari 16.4+; older
browsers get a message instead of a blank page) rather than the payload
being base64-embedded directly in the HTML — this keeps the HTML shell
small and the data cacheable separately from it.

## Shared kit

`shared/dashboard_kit.py` and `shared/theme.css` are the single source of
truth for everything that used to be pasted into each dashboard by hand:
CSS custom properties for the light/dark palette, the Pacaembu font
embedding, the cross-dashboard nav bar (`nav_links_html()` — every
dashboard, the Wiki, and About, always in the same order, from one `_SITES`
dict), the theme toggle, i18n (`GB_I18N`, English/Portuguese), and shared
JS helpers (table sort, CSV/XLSX export, chart palette). A color, font, or
nav change is a one-line edit in one file that reaches every dashboard on
its next scheduled rebuild — see the site's [ADR-001](https://github.com/gasbrazil/gasbrazil.github.io/blob/main/README.md)
for why this exists.

## Deployment

Each dashboard has its own GitHub Actions workflow (`.github/workflows/<slug>.yml`)
on its own schedule — daily, every few hours, or monthly, matched to how
often that dashboard's source actually publishes new data — plus
`workflow_dispatch` for a manual run and a `push` trigger scoped to that
dashboard's own folder and `shared/**` (so a shared-kit change rebuilds
every dashboard, but a change to one dashboard's own code only rebuilds
that one). Dashboards run a **health gate before lake publish** — a sanity
check on row counts, data age, and series coverage — so a broken or stale
fetch doesn't overwrite a working deploy or the R2 lake; the previous
build stays live if the gate fails. Push retries rebase on a race, then
fail the job if the push never lands.

Every workflow commits straight to its own subfolder on `main` and retries
with `git pull --rebase origin main` on a push race, rather than using a
single repo-wide Pages-deploy API — that's what lets several dashboards'
workflows run and redeploy concurrently without stepping on each other.

## Data architecture

Two tracks, by dashboard:

- **Gitignored stores with a private lake mirror** (ons, flows, supply,
  pld, precos, poc, contratos): `raw/` and `data/` are gitignored (too large
  or fully rebuildable from source) and instead mirrored to a private
  Cloudflare R2 bucket via `shared/data_kit.py`, so a CI run that doesn't
  have local history can still `ensure_lake()` a copy when it needs one —
  this is how **The Desk** (which reads across several dashboards' data at
  once) gets its inputs without vendoring every sibling's Parquet file
  into its own workflow.

Health gates run **before** lake publish. ONS has a dedicated `health`
command in CI. Flows, supply, precos, poc, contratos, and pld fail the
build on empty/stale/incomplete data, then publish. The Desk fails in CI
when PLD SE is missing. A failed gate leaves the previous HTML live and
does not overwrite lake parquet.

Every dashboard's public `payload.json.gz` is also published to a public R2
artifacts bucket, independent of the committed `index.html` — this is what
lets a dashboard's data refresh on its own schedule (a new payload) without
necessarily needing a full HTML rebuild.

## The wiki you're reading

This wiki is markdown source (`wiki-src/`) rendered to static HTML (`wiki/`)
by `build_wiki.py`, deployed by its own workflow on any push to
`wiki-src/**` or `build_wiki.py`. It draws its palette from
`shared/theme.css` like every dashboard, but is otherwise independent —
pure documentation, no data pipeline behind it.
