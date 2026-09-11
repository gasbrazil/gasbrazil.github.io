# PLD Prices Dashboard

**PLD** (Preço de Liquidação das Diferenças) by CCEE submarket — North,
Northeast, Southeast, and South — from Brazil's electricity clearinghouse
open data. Daily averages and hourly prices, plus a peak / off-peak view.

Part of the [gasbrazil.github.io](../README.md) monorepo — served at `/pld/`,
rebuilt on its own schedule, sharing colors/fonts/chrome with `ons/`, `poc/`,
`contratos/`, and `flows/` via `../shared/`. Same architecture: gzip+base64
JSON payload inflated client-side into a single static HTML file.

## Source

- Daily CKAN package: [pld_media_diaria](https://dadosabertos.ccee.org.br/dataset/pld_media_diaria)
- Hourly CKAN package: [pld_horario](https://dadosabertos.ccee.org.br/dataset/pld_horario)
- Discover download URLs each fetch via `package_show` (tokens rotate);
  fall back to known yearly URLs if the API is unavailable.
- Daily CSV (one per year): `MES_REFERENCIA;SUBMERCADO;DIA;PLD_MEDIA_DIA`
  (semicolon, ISO-8859-2 / latin-1). Example:
  `202609;NORDESTE;06/09/2026;118.04`
- Hourly CSV (one per year, from 2021; this pipeline keeps ≥ 2024):
  `MES_REFERENCIA;SUBMERCADO;PERIODO_COMERCIALIZACAO;DIA;HORA;PLD_HORA`
  with `DIA` as day-of-month. Example: `202609;NORDESTE;241;11;0;157.31`
- **PLD ≠ CMO.** CMO is ONS's marginal operating cost (shown on `/ons/`);
  PLD is CCEE's settlement price. They track related fundamentals but are
  not the same series.
- **Peak / off-peak** is not a CCEE field. The dashboard treats hours 18–20
  (18:00–21:00) on Monday–Friday as ponta (ANEEL-style TOU v1 in
  `shared/transforms.py`). Weekends are off-peak; holidays are not excluded.

## Files

- `pld_pipeline.py` — `fetch` / `build` / `all` (daily + hourly)
- `dashboard.py` — builds `index.html` (embeds ~last 24 months of daily
  data, ~last 31 days of hourly, and daily peak/off-peak averages)
- `make_mock.py` — synthetic raw CSV + parquet for offline rebuilds
- `../.github/workflows/pld.yml` — scheduled refresh; caches `raw/`; commits
  `index.html` and publishes `data/pld_daily.parquet` + `data/pld_hourly.parquet`

## Local dev

```bash
uv pip install -r requirements.txt
python make_mock.py             # or: python pld_pipeline.py all
python pld_pipeline.py build    # if you only fetched / used mock raw
python dashboard.py
```
