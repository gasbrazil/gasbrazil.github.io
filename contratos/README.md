# POC Contratos Dashboard

Web dashboard for Brazil's "Oferta de Capacidade" (PEG) portal's gas
transport **contracts** data — transport contracts and master transport
contracts across TBG, TAG, and NTS.

Part of the [gasbrazil.github.io](../README.md) monorepo — served at
`/contratos/`, rebuilt on its own schedule, sharing colors/fonts/chrome with
`ons/` and `poc/` via `../shared/`. Same architecture as those two projects
(gzip+base64 JSON payload inflated client-side into a single static HTML
file — no server, no database).

## Source

- API: `https://www.ofertadecapacidade.com.br/v2/api/graphql` (GraphQL,
  operation `getContratos`, field `contratosCarregador`)
- Site: https://ofertadecapacidade.com.br/home/contratos
- `contratos_pipeline.py` covers two of the four contract categories shown on
  the site's UI:
  - **Contrato de Transporte** (`tipoContrato: PEDIDO` / `PEDIDO_LEILAO`,
    `statusContrato: ATIVO` / `CONCLUIDO`)
  - **Contrato Master** (`tipoContrato: CONTRATO MASTER DE TRANSPORTE`,
    `statusContrato: HABILITADO`)

  **Not yet covered:** "Contrato de Transporte Legado" and "Conexão de
  Acesso". These are not served by `contratosCarregador` — confirmed by
  exhaustively querying every value the `StatusContrato` enum accepts (only
  three: `ATIVO`, `CONCLUIDO`, `HABILITADO`, all consumed by the branches
  above) and by introspecting the full GraphQL schema (33 types, nothing
  named legado/conexão/acesso). That data comes from a different, unidentified
  endpoint.
- TSO id mapping: `1 = TBG`, `2 = TAG`, `3 = NTS` — confirmed.
- The dashboard excludes concluded ("Concluído") transport contracts by
  default to keep the client-side payload smaller — `dashboard.py` filters
  them out of the shipped `index.html` (see `load_payload()`). The full
  history, concluded contracts included, stays in `data/contratos.parquet`
  (checked into git) for anyone who needs it.
- The source API has no CORS headers reachable from a restricted-egress
  sandbox, so live fetching is expected to run from GitHub Actions (matching
  ons/poc) rather than client-side or from a dev machine with restricted
  egress.

## Files

- `contratos_pipeline.py` — `fetch` pulls raw JSON, `build` transforms it
  into `data/contratos.parquet` (tidy store, checked into git for history).
- `dashboard.py` — builds `index.html`, the single-file dashboard. Imports
  `../shared/dashboard_kit.py` for theming, font/favicon embedding, the
  theme toggle, CSV/XLSX export helpers, and cross-dashboard nav links.
- `make_mock.py` — synthetic raw data for local testing without hitting the
  live API.
- `../.github/workflows/contratos.yml` — daily cron (11:00 UTC) + push +
  manual dispatch: fetch → build → commit `data/contratos.parquet` +
  `index.html`.

## Local dev

Run from inside this `contratos/` directory:

```bash
pip install -r requirements.txt
python make_mock.py                  # or: python contratos_pipeline.py fetch (needs network access to the source)
python contratos_pipeline.py build
python dashboard.py
```
