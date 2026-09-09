# Gas Supply Dashboard

National monthly natural-gas supply balance from ANP's PPGN-EL open data
(production, available gas, flare/loss, own consumption, reinjection, LGN)
plus ANP natural-gas imports when the stable CSV is reachable.

Part of the [gasbrazil.github.io](../README.md) monorepo — served at
`/supply/`, rebuilt on its own schedule, sharing chrome with `ons/`, `poc/`,
`contratos/`, and `flows/` via `../shared/`.

## Source

### PPGN-EL (production / availability)

- Base URL:
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/ppgn-el/`
- Landing:
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-estado-e-localizacao`
- Files (direct CSVs, not well-level zips):
  - `producao-gas-natural-1000m3.csv`
  - `gn-disponivel-1000m3.csv`
  - `queima-e-perda-gn-1000m3.csv`
  - `consumo-proprio-gn1000m3.csv`
  - `producao-lgn-m3.csv`
  - `reinjecao-gn-1000m3` (no `.csv` extension on the server; 404 with `.csv`)
- Layout: `;` delimiter, `utf-8-sig`, Portuguese month codes (`JAN`…`DEZ`),
  comma decimals, one row per year × month × UF × location (terra/mar).
- `build` sums to a single national total per calendar month.

### Imports (Bolivia / LNG)

- Landing:
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/importacoes-e-exportacoes`
- Stable CSV:
  `…/arquivos/ie/gn/importacao-gas-natural-2000-<YYYY>.csv`
  (end-year in the filename drifts; `fetch` probes current year ± a few).
- Columns: `ANO;MÊS;PRODUTO;OPERAÇÃO COMERCIAL;IMPORTADO;DISPÊNDIO`.
- **No Bolivia vs LNG split** in this file — only a national monthly import
  total (`OPERAÇÃO COMERCIAL = IMPORTAÇÃO`). That total is included on the
  dashboard; origin breakdown is not invented from PDFs.

ANP typically publishes with ~2 months of lag.

## Files

- `supply_pipeline.py` — `fetch` / `build` / `all` → `data/supply_monthly.parquet`
- `dashboard.py` — single-file `index.html` (gzip payload, shared kit nav/theme)
- `make_mock.py` — synthetic raw CSVs for offline builds
- `../.github/workflows/supply.yml` — monthly schedule + push/dispatch

## Local dev

```bash
cd supply
uv pip install -r requirements.txt
python make_mock.py             # or: python supply_pipeline.py fetch
python supply_pipeline.py build
python dashboard.py
```
