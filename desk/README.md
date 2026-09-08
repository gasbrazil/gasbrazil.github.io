# Desk

Cross-product snapshot at `/desk/`: SIN gas generation, PLD–CMO–CVU (SE),
ANP / POC prices, pipeline utilization, and a client-side thermal spark
calculator.

## Build

```bash
pip install -r requirements.txt
python dashboard.py          # writes index.html + payload.json.gz
python build_payload.py      # print KPI / source summary only
```

At build time `build_payload.py` calls `data_kit.ensure_lake(...)` so CI can
pull sibling parquet mirrors from the private R2 lake bucket when local
`*/data/*.parquet` trees are absent (they are gitignored).

## Spark formula

Implied CVU (R$/MWh) =
`gas (R$/MMBtu) × heat rate (kcal/kWh) × 1000 / (natgas_kcal_per_m3 × mmbtu_per_1000_m3)`

Defaults come from ANP Santos when available, else POC 7-day average, else
an illustrative 12 R$/MMBtu so the form never loads blank.
