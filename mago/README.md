# TAG Mago operational data

Hourly JSON snapshots from [TAG Mago](https://mago.ntag.com.br/) (line pack,
consumption forecasts by balancing zone). Both Mago tools read the same S3
objects via `https://api-mago-prod-lb.ntag.com.br/api/s3/*`.

## Pipeline

```bash
/workspace/.venv/bin/python mago_pipeline.py fetch   # last 14 UTC days
/workspace/.venv/bin/python mago_pipeline.py build   # → data/tag_mago_series.parquet
/workspace/.venv/bin/python mago_pipeline.py all
```

Offline:

```bash
/workspace/.venv/bin/python make_mock.py
```

## Dashboard

```bash
/workspace/.venv/bin/python dashboard.py
```

Output: `index.html` with embedded payload (line pack + 7-day zone forecasts).
