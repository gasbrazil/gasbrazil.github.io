# PLD Prices Dashboard

Daily-average **PLD** (Preço de Liquidação das Diferenças) by CCEE submarket
— North, Northeast, Southeast, and South — from Brazil's electricity
clearinghouse open data.

Part of the [gasbrazil.github.io](../README.md) monorepo — served at `/pld/`,
rebuilt on its own schedule, sharing colors/fonts/chrome with `ons/`, `poc/`,
`contratos/`, and `flows/` via `../shared/`. Same architecture: gzip+base64
JSON payload inflated client-side into a single static HTML file.

## Source

- CKAN package: [pld_media_diaria](https://dadosabertos.ccee.org.br/dataset/pld_media_diaria)
- Discover download URLs each fetch via
  `package_show?id=pld_media_diaria` (tokens rotate); fall back to known
  2021–2026 URLs if the API is unavailable.
- One CSV per year: `MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA`
  (semicolon, ISO-8859-2 / latin-1). Example:
  `202609;NORDESTE;06/09/2026;118.04`
- **PLD ≠ CMO.** CMO is ONS's marginal operating cost (shown on `/ons/`);
  PLD is CCEE's settlement price. They track related fundamentals but are
  not the same series.

## Files

- `pld_pipeline.py` — `fetch` / `build` / `all`
- `dashboard.py` — builds `index.html` (embeds ~last 24 months of daily data)
- `make_mock.py` — synthetic raw CSV + parquet for offline rebuilds
- `../.github/workflows/pld.yml` — scheduled refresh; caches `raw/`; commits
  `index.html` and `data/pld_daily.parquet`

## Local dev

```bash
uv pip install -r requirements.txt
python make_mock.py             # or: python pld_pipeline.py all
python pld_pipeline.py build    # if you only fetched / used mock raw
python dashboard.py
```
