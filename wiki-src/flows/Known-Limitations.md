# Known Limitations and Assumptions

## 2022 is a real gap, not a bug

ANP has no published files at all for 2022 — confirmed by exhaustively
probing every month and both filename-separator conventions ANP has used,
not assumed from a missing download. A hole in the chart for 2022 reflects
a gap in ANP's own publication record, not a failure of this pipeline.

## Two different granularities, one aggregation trap

The source publishes every variable at shipper/contract granularity, but
**not every variable is a genuine per-shipper split**:

- **Volume Solicitado / Programado / Realizado and Allocation (%) are real
  per-shipper figures** and are summed across shippers/contracts to get a
  point's total — this is a correct sum.
- **Average Pressure and every pipeline-system ledger variable (GUS,
  unaccounted-for gas, losses, imbalance, linepack) are a single physical
  or system-wide reading, broadcast identically to every shipper row active
  that day** — confirmed by inspecting raw rows directly (the same value
  repeated across every shipper reporting for a pipeline on a given date).
  Summing these would multiply the true value by however many shippers
  happened to be active that day. Both are aggregated with `median()`
  instead of `sum()` specifically to avoid that.

Shipper- and contract-level detail exists in the source but is deliberately
collapsed at build time to keep the dashboard's payload a reasonable size —
[POC Contracts](/wiki/contratos/using-the-dashboard.html) already covers
shipper/contract-level detail for held capacity; this dashboard is about
physical flow totals. Average Pressure is computed and stored in the
pipeline's own data store but left out of the dashboard's embedded payload
entirely (it was roughly 30% of the payload's size on its own).

## TSO overlay takes priority over ANP when both exist

TAG, TBG, and NTS each publish their own programmed/actual meter volumes,
often sooner than ANP. Where the same point and date exist in both sources,
the TSO's own figure is used in preference to ANP's. Ledger, pressure,
allocation, and requested-volume series stay ANP-only (the TSOs don't
publish those in a comparable form).

## Data lag and revisions

ANP typically publishes files with a lag of several weeks after month-end,
and revises recently-published months in place — a figure for last month
quoted today may not match the same figure quoted next month, once ANP's
own revision settles.
