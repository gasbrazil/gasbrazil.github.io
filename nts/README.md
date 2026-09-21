# NTS OnTime — Pipeline Line Pack Telemetry

Real-time and historical line pack telemetry from Nova Transportadora do Sudeste (NTS) [OnTime Tool](https://www.ntsbrasil.com/ontime).

Data is fetched via WordPress REST endpoints (`https://www.ntsbrasil.com/wp-json/ontime/v1/estoque`), canonicalized into tidy Parquet series, validated against repository schemas, and rendered into an interactive dashboard at `/nts/`.

## Pipeline

```bash
python nts_pipeline.py fetch   # fetches recent days into raw/snapshots/
python nts_pipeline.py build   # compiles to data/nts_linepack_series.parquet and lake/
python nts_pipeline.py all     # fetch + build
```

## Dashboard

```bash
python dashboard.py            # builds nts/index.html with interactive SVG chart and data table
```

Output: `index.html` with self-contained payload (KPIs, time-series points, reverse-chronological table, and export helpers).
