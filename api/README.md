# GasBrazil API (ADR-002 Track C)

Read-only FastAPI over the canonical lake (or per-project parquet fallbacks).
Does **not** fetch ANP/ONS/CCEE at request time — rebuild data via each
dashboard's pipeline (or CI), then query here.

```bash
# from repo root, after at least one pipeline build:
pip install -r api/requirements.txt
python pld/pld_pipeline.py build          # example
python supply/supply_pipeline.py build
uvicorn api.main:app --reload --port 8000
```

- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

### Endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/v1/flows/points` | `tso`, `point_code`, `variable`, `source` (`anp`/`tag`/`tbg`/`nts`), `from`, `to`, `limit` |
| GET | `/v1/pld/daily` | `submarket`, `from`, `to`, `limit` |
| GET | `/v1/supply/monthly` | `from`, `to`, `limit` |
| GET | `/v1/ons/balances` | `subsystem`, `series`, `from`, `to`, `limit` |
| GET | `/v1/power/pld-cmo` | PLD vs ONS CMO join; `submarket`, `from`, `to`, `limit` |

`/health` also lists dataset presence and transform registry versions.

Deploy anywhere that runs ASGI (Fly.io, Railway, a small VM). Point
`CORS` allow-list in `api/main.py` at your front-end origins. GitHub Pages
continues to host the static UI; the API is a separate service.
