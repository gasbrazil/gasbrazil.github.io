# GasBrazil canonical data lake (ADR-002 Track A)

Rebuildable parquet mirrors of each dashboard store, with **one** column
contract per dataset (see `shared/schemas/`). Pipelines validate then
`data_kit.publish(...)` here after `build`.

```
lake/
  transport/
    flows_points.parquet
    flows_ledger.parquet
    poc_results.parquet
    contratos.parquet
  power/
    ons_daily.parquet
    pld_daily.parquet
  supply/
    supply_monthly.parquet
```

Everything under this tree is **gitignored** except this README — same
rationale as `ons/data/` and `flows/data/` (large, rebuildable). The FastAPI
app in `api/` reads from here when present, else falls back to each
project's `data/*.parquet`.

Rebuild examples:

```bash
python flows/flows_pipeline.py build    # publishes flows_* into lake/
python pld/pld_pipeline.py build
python supply/supply_pipeline.py build
```
