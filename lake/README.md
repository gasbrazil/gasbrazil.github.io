# GasBrazil canonical data lake (ADR-002 Track A)

Rebuildable parquet mirrors of each dashboard store, with **one** column
contract per dataset (see `shared/schemas/`). Pipelines validate then
`data_kit.publish(...)` here after `build`. When Cloudflare R2 credentials
are set (`R2_*` + `GASBRAZIL_LAKE_BUCKET`), `publish()` also mirrors each
file to the private R2 lake bucket.

```
lake/                          # local (gitignored)
  transport/
    flows_points.parquet
    flows_ledger.parquet
    poc_results.parquet
    contratos.parquet
  power/
    ons_daily.parquet
    ons_entities.parquet
    pld_daily.parquet
    pld_hourly.parquet
  supply/
    supply_monthly.parquet
    anp_prices.parquet
```

Production mirror (private R2): same relative keys under
`GASBRAZIL_LAKE_BUCKET`. Public browser payloads are separate — see
`GASBRAZIL_ARTIFACTS_BUCKET` / `GASBRAZIL_DATA_BASE_URL` (Track B).

Column contracts: `shared/schemas/`. Versioned assumptions (heat rates,
submarket maps): `shared/transforms.py`. Cross-product helpers:
`shared/joins.py` (e.g. PLD vs CMO).

Everything under this tree is **gitignored** except this README — same
rationale as `ons/data/` and `flows/data/` (large, rebuildable). The FastAPI
app in `api/` reads from here when present, else falls back to each
project's `data/*.parquet`.

Rebuild examples:

```bash
python flows/flows_pipeline.py build    # publishes flows_* into lake/ (+ R2)
python pld/pld_pipeline.py build
python supply/supply_pipeline.py build
```
