# ANP Prices Dashboard

Natural-gas price disclosures under ANP Resolution 52/2011 — producers by
basin, distributors to free consumers (thermal vs non-thermal), and sales
to marketers — as monthly R$/MMBtu series with volumes.

Part of the [gasbrazil.github.io](../README.md) monorepo — served at
`/precos/`, rebuilt on its own schedule, sharing chrome with `ons/`, `poc/`,
`contratos/`, `flows/`, `supply/`, and `pld/` via `../shared/`.

## Source

Landing (humans):
`https://www.gov.br/anp/pt-br/assuntos/movimentacao-estocagem-e-comercializacao-de-gas-natural/acompanhamento-do-mercado-de-gas-natural/precos-do-gas-natural-resolucao-anp-no-52-2011`

Direct CSVs under `…/ppg/`:

| File | Grain |
|------|--------|
| `vendas-entre-produtores.csv` | month × aggregated basin |
| `distribuidoras-consumidores-livres.csv` | month × market type × region |
| `vendas-aos-comercializadores.csv` | month (national) |

Layout: UTF-16LE + BOM, `;` delimiter, comma decimals. Empty price cells
are confidentiality suppressions — kept as nulls (no interpolation).

ANP typically publishes with ~2–3 months of lag.

## Files

- `precos_pipeline.py` — `fetch` / `build` / `all` → `data/anp_prices.parquet`
- `dashboard.py` — single-file `index.html` (gzip payload, shared kit nav/theme)
- `make_mock.py` — synthetic raw CSVs for offline builds
- `../.github/workflows/precos.yml` — monthly schedule + push/dispatch

## Local dev

```bash
cd precos
pip install -r requirements.txt
python make_mock.py             # or: python precos_pipeline.py fetch
python precos_pipeline.py build
python dashboard.py
```
