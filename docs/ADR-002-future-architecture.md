# ADR-002: Future architecture tracks (data models, artifacts, API)

**Status:** Accepted (Tracks A–C implemented as progressive layers)  
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
| `shared/data_kit.py` | `validate` + `publish()` into `lake/` |
| `shared/transforms.py` | Versioned assumptions (heat rates, submarket maps) |
| `shared/joins.py` | First-class cross-product joins (e.g. PLD vs CMO) |
| `lake/` | Gitignored parquet mirrors (rebuildable) |

Upstream fetch URLs and CI schedules stay the same. Dashboards may still embed small payloads; large series use Track B.

### Track B — Data leaves HTML

The page shell stays on Pages. Large series are separate gzip artifacts the browser fetches (`flows/payload.json.gz`, `ons/payload.json.gz`). HTML keeps only chrome + hub teaser markers. Smaller dashboards (POC, contratos, supply, PLD) may remain embed until they hurt.

### Track C — Read-only `/v1` API

FastAPI under `api/` queries the lake (or per-project parquet). Ingest remains CI-side; the API does **not** proxy ANP/ONS/CCEE live. Public read-only by default. Host separately (Fly/Railway/VM); Pages keeps the UI.

## Consequences

| Stage | Outcome |
|-------|---------|
| A | Cross-product joins and hub teasers stop inventing column names |
| B | First-load and git diffs shrink for Flows and ONS |
| C | Selective history + third-party consumers; ops cost begins |

**Stay on pure embed while** a page stays small after filters and hub joins remain teaser-only.

## References

- Today’s deploy model: [README.md](../README.md)
- ONS notes: [ons/Wiki/Architecture-and-Deployment.md](../ons/Wiki/Architecture-and-Deployment.md)
- API: [api/README.md](../api/README.md)
- Implementation: `shared/{data_kit,schemas,transforms,joins}.py`, `lake/`, `flows|ons/payload.json.gz`, `api/`
