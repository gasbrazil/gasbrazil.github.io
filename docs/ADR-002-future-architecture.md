# ADR-002: Future architecture tracks (data models, artifacts, API)

**Status:** Accepted (Track A foundation + Flows artifact pilot + API scaffold landed)  
**Date:** 2026-09-07  
**Context:** GasBrazil ships as static GitHub Pages: CI fetches upstream data, builds parquet, gzip+base64-embeds a payload into committed `*/index.html`. That model is offline-capable, cheap, and CORS-free. Pressure comes from multi‑MB Flows/ONS pages, six independent schemas, and no selective queries.

## Decision

Pursue three progressive tracks. **Do not start with a live API.** Normalize data first, then stop stuffing megabytes into HTML, then add a query layer.

```
Track A (data models) → Track B (artifact delivery) → Track C (live API)
```

### Track A — Canonical data models

Introduce a shared intermediate layer (`shared/data_kit.py`, `shared/schemas/`) with:

- Stable column names, UTC dates, domain IDs (TSO, submarket, point)
- Validation on pipeline `build`
- Optional publish into a `lake/` tree (gitignored; CI/local rebuild)

Dashboards may still embed payloads, but they read **one** naming convention.

### Track B — Data leaves HTML

The page shell stays on Pages. Large series are separate gzip artifacts the browser fetches (e.g. `flows/payload.json.gz`). HTML keeps only chrome + hub teaser markers.

### Track C — Read-only `/v1` API

A FastAPI app under `api/` queries the lake (or per-project parquet). Ingest remains CI-side; the API does **not** proxy ANP/ONS/CCEE live. Public read-only by default.

## Consequences

| Stage | Outcome |
|-------|---------|
| A | Cross-product joins and hub teasers stop inventing column names |
| B | First-load and git diffs shrink for Flows (pilot); pattern extends to ONS |
| C | Selective history + third-party consumers; ops cost (uptime, deploy) begins |

**Stay on pure embed while** Flows stays manageable after filters and hub joins remain teaser-only.

## References

- Today’s deploy model: [README.md](../README.md)
- ONS pipeline notes: [ons/Wiki/Architecture-and-Deployment.md](../ons/Wiki/Architecture-and-Deployment.md)
- Implementation: `shared/data_kit.py`, `shared/schemas/`, `lake/README.md`, `flows/payload.json.gz` (built), `api/`
