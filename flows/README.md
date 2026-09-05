# Pipeline Flows Dashboard

Web dashboard for ANP's (Agência Nacional do Petróleo, Gás Natural e
Biocombustíveis) "movimentação de gás natural em gasodutos de transporte"
data — daily physical gas flow at every receipt and delivery point on
Brazil's transport pipelines, plus pipeline-wide balancing entries (system-use
gas, unaccounted-for gas, losses, daily imbalance, linepack).

Part of the [gasbrazil.github.io](../README.md) monorepo — served at
`/flows/`, rebuilt on its own schedule, sharing colors/fonts/chrome with
`ons/`, `poc/`, and `contratos/` via `../shared/`. Same architecture as those
projects (gzip+base64 JSON payload inflated client-side into a single static
HTML file — no server, no database).

## Source

- Files: one CSV per month, wide format (one row per pipeline/point/
  shipper/contract/variable combination, one column per day of that month):
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-movimentacao-de-gas-natural-em-gasodutos-de-transporte/<year>/gn_<month-pt>_<year>.csv`
- Landing page (for humans; file names are generated directly, not scraped):
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/dados-consolidados-movimentacao-de-gas-natural-em-gasodutos-de-transporte`
- Two filename conventions coexist on the server: most months use
  underscores (`gn_junho_2026.csv`), but 2021 and 2023 files were published
  with hyphens (`gn-junho-2023.csv`), and one 2023 file (November) breaks
  that year's own pattern and uses an underscore. `flows_pipeline.py fetch`
  tries both separators for every candidate month and caches which one
  worked in `raw/_manifest.json`.
- **2022 has no published files at all** — confirmed by exhaustive probing
  of every month/separator combination, not assumed. It's a real gap in
  ANP's publication, not a bug in this pipeline.
- Files are typically published with a lag of several weeks after month-end,
  and ANP revises recently-published months in place (confirmed: the
  Jan–Apr 2024 files were revised after a new TBG receiving point was
  added) — `fetch` always re-downloads the last 3 months even if already
  cached.
- Encoding is `latin-1`, delimiter is `;`, decimals use a comma. Some files
  have malformed number formatting (stray whitespace, `- 123,45` with a
  space after the minus sign) that silently breaks pandas' built-in
  `decimal=","` parsing — everything is read as `dtype=str` and cleaned with
  a dedicated regex-validated parser (`_clean_numeric`) instead.
- 2021's files use different column headers and variable names than every
  later year (`"do Gasoduto"` vs `"de Gasoduto"`, `"Nome da variável"` vs
  `"Nome da Variável"`, missing unit suffixes, one accent typo on
  "Desequilíbrio"). Handled with alias maps rather than dropped.

### Two output tables — and the aggregation trap

The source mixes two different granularities of data, split into two tidy
parquet stores at build time:

- **`data/flows_points.parquet`** — point-level flow: Volume Solicitado /
  Programado / Realizado, Alocação (%), and Average Pressure, one row per
  (point, variable, date).
- **`data/flows_ledger.parquet`** — pipeline-wide balancing entries: Gás de
  Uso no Sistema, Gás não contado, Perdas Operacionais/Extraordinárias,
  Desequilíbrio Diário (and its accumulated form), Empacotamento — one row
  per (pipeline, variable, date).

The source publishes every variable at shipper/contract granularity, but
**not every variable is a genuine per-shipper split**. Volume
Solicitado/Programado/Realizado and Alocação (%) are real per-shipper
figures and are summed across shippers/contracts to get the point total.
Average Pressure and every ledger variable are a single physical or
system-wide reading, **broadcast identically to every shipper row** active
that day — confirmed by inspecting raw rows directly (e.g. the same
`Gás de Uso no Sistema` value repeated across all 16 shippers reporting for
a pipeline on a given date). Summing those would multiply the true value by
however many shippers happened to be active. Both aggregators use
`median()` for the broadcast variables instead — see the comments in
`_aggregate_points()` / `_aggregate_ledger()` in `flows_pipeline.py`.

Shipper- and contract-level detail exists in the source but is discarded at
build time (median/sum collapses it) to keep the store and the dashboard's
embedded payload a reasonable size — POC Contracts already covers
shipper/contract-level detail for capacity; this dashboard is about
physical flow. Average Pressure is computed and stored in
`flows_points.parquet` but deliberately left out of the dashboard's
embedded payload (it was ~30% of the points payload on its own); it's in
the repo for anyone who wants it.

## Files

- `flows_pipeline.py` — `fetch` downloads `raw/gn_<month>_<year>.csv` files,
  `build` transforms them into `data/flows_points.parquet` +
  `data/flows_ledger.parquet` (health-gated: exits non-zero on zero rows,
  staleness beyond ~75 days, or missing point codes). `all` runs both.
- `dashboard.py` — builds `index.html`, the single-file dashboard. Imports
  `../shared/dashboard_kit.py` for theming, font/favicon embedding, the
  theme toggle, i18n, CSV/XLSX export helpers, and cross-dashboard nav
  links.
- `make_mock.py` — synthetic raw CSV for local testing without hitting the
  live source; deliberately exercises the broadcast-vs-per-shipper
  aggregation cases above.
- `../.github/workflows/flows.yml` — scheduled + push + manual dispatch:
  fetch → build → dashboard → commit `index.html` only (`raw/` and `data/`
  are gitignored — large and fully rebuildable from the source, same as
  `ons/raw/` and `ons/data/`).

## Local dev

Run from inside this `flows/` directory:

```bash
pip install -r requirements.txt
python make_mock.py             # or: python flows_pipeline.py fetch (needs network access to the source)
python flows_pipeline.py build
python dashboard.py
```
