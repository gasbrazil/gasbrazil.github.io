# ADR-002: Future architecture tracks (data models, artifacts, API)

**Status:** Accepted (Tracks A–C as progressive layers; R2 hosts lake + artifacts)  
**Date:** 2026-09-07  
**Context:** GasBrazil ships as static GitHub Pages: CI fetches upstream data, builds parquet, and publishes dashboards. The original model gzip+base64-embedded multi‑MB payloads into committed `*/index.html`. That model is offline-capable, cheap, and CORS-free. Pressure comes from multi‑MB Flows/ONS pages, six independent schemas, and no selective queries.

## Decision

Pursue three progressive tracks. **Do not start with a live API.** Normalize data first, then stop stuffing megabytes into HTML, then add a query layer.

```
Track A (data models) → Track B (artifact delivery) → Track C (live API)
```

### Track A — Canonical data models

Shared intermediate layer:

| Piece | Role |
|-------|------|
| `shared/schemas/` | Stable column contracts (transport / power / supply) |
| `shared/data_kit.py` | `validate` + `publish()` into `lake/` (+ R2 mirror) |
| `shared/transforms.py` | Versioned assumptions (heat rates, submarket maps) |
| `shared/joins.py` | First-class cross-product joins (e.g. PLD vs CMO) |
| `lake/` | Local parquet mirrors (gitignored); **Cloudflare R2** private bucket is production |

Upstream fetch URLs and CI schedules stay the same. Dashboards never embed multi‑MB payloads.

### Track B — Data leaves HTML (R2)

The page shell stays on **GitHub Pages**. All six dashboards fetch `payload.json.gz` from the public **Cloudflare R2** artifacts bucket (`GASBRAZIL_DATA_BASE_URL`). CI uploads lake parquet to the private R2 lake bucket and artifacts to the public bucket; `main` commits only thin `*/index.html` (plus ONS wiki HTML).

Local/dev without R2 env still writes sibling `payload.json.gz` and uses a relative URL.

### Track C — Read-only `/v1` API

FastAPI under `api/` queries the lake (or per-project parquet). Ingest remains CI-side; the API does **not** proxy ANP/ONS/CCEE live. Public read-only by default. Host separately (Fly/Railway/VM); Pages keeps the UI. Future: read the private R2 lake bucket directly.

## Consequences

| Stage | Outcome |
|-------|---------|
| A | Cross-product joins and hub teasers stop inventing column names |
| B | First-load and git diffs shrink; data lives on R2 |
| C | Selective history + third-party consumers; ops cost begins |

## References

- Today’s deploy model: [README.md](../README.md)
- ONS notes: [ons/Wiki/Architecture-and-Deployment.md](../ons/Wiki/Architecture-and-Deployment.md)
- API: [api/README.md](../api/README.md)
- Implementation: `shared/{data_kit,schemas,transforms,joins}.py`, `lake/`, R2 artifacts, `api/`
