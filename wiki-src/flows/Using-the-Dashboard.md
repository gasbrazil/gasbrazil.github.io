# Using the Dashboard

Pipeline Flows shows daily physical gas movement on Brazil's transport
pipelines — receipt/delivery points and pipeline-wide balancing entries —
from ANP's published data, overlaid with TAG/TBG/NTS's own transparency
reporting where available.

## Level toggle: two different kinds of series

The two buttons at the top switch between genuinely different data:

- **Receipt & Delivery Points** — point-level flow: Volume Solicitado /
  Programado / Realizado, Allocation (%).
- **Pipeline System (GUS, losses, imbalance, linepack)** — pipeline-wide
  balancing entries: Gás de Uso no Sistema, unaccounted-for gas, operational
  and extraordinary losses, daily imbalance (and its accumulated form),
  Empacotamento (linepack).

Switching levels resets pipeline/state/flow-type filters and the chart's
selected series, since the two levels don't share dimensions.

## View toggle

**Totals by transporter** sums the current level's series across every
matching point/pipeline; **Individual meters** (Points level) or
**Individual pipelines** (Pipeline System level) breaks it out instead of
summing it.

## KPI cards

"Receipts & deliveries by transporter" for a selected month (picker at top
right of the card) — one card per transporter, receipts vs. deliveries.

## Chart

Variable and smoothing (Daily / 7-day / 30-day avg) selectors, plus a window
preset (90 days / 12 months / 3 years / all history). Below the chart, an
entity picker lets you select specific points or pipelines to chart
individually instead of the aggregate total — collapsible once you've made a
selection, to reclaim vertical space.

## Filters

- **TSO toggle** — filter to one transporter (or several).
- **Flow type** (Points level only) — All / Receipts / Deliveries.
- **Pipeline / State / search** — narrows the point or pipeline list.
- **Include TSB & GOM** — off by default; these are smaller transporters
  excluded from the default view, included on request.
- **Reset all filters** clears everything above back to the unfiltered view.

## Table and exports

The table mirrors whatever level/view/filters are currently active.
**Download CSV** and **Export table (Excel)** follow the table's current
state, same as the other dashboards.
