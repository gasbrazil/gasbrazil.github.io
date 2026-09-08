# Using the Dashboard

POC Results tracks accepted bids from Brazil's "Oferta de Capacidade" (PEG)
portal — pipeline balancing, GUS acquisition, and congestion-process auction
results across TBG, TAG, and NTS. There's no tabbed layout here: one page,
one chart, one table, filtered together.

## Pipeline chips

The row of TSO chips (TBG / TAG / NTS, plus a blank/unspecified chip if any
rows carry no pipeline) filters everything below — chart, quick filters, and
table — to the selected pipeline(s). Click a chip to toggle it; none
selected means no pipeline filter is applied.

## Price Trend chart

Pick any Pipeline + Transaction Type combination from the chart picker and
it becomes its own colored line — multiple combinations chart side by side.
The chart has two Y axes: the left is R$/MMBtu (the source unit as
published); the right mirrors the same gridlines rescaled to R$/m³, using
the same fixed PCR conversion factor as the table's own R$/m³ column (see
[Known Limitations](Known-Limitations)), so a value read off either axis is
consistent with the other.

## Quick filters

Chips above the toolbar for the filters people reach for most: Last 7 Days,
Last 30 Days, GUS + Residual Balancing (transaction type), and one chip per
pipeline. These combine with the toolbar and per-column filters below, not
instead of them — a quick filter is a shortcut into the same filter state
the column menus set.

## Toolbar and table

- **Trade timing** dropdown and a free-text **search** box (matches process
  code / delivery point) sit above the table.
- **Reset filters** clears every filter — quick filters, toolbar, and every
  column's own filter menu — back to showing everything.
- **Columns** shows/hides table columns; a few low-signal columns (process
  code, Flow Days, Service Type, Avg Process Price, Total Value, Volume
  Offered, Total Volume) are hidden by default but always available.
- Every column has its own Excel-style filter menu (click the small filter
  icon in its header): a date-range picker for date columns, checkbox
  value-lists for everything else. Columns can be dragged to reorder,
  resized, and sorted (click a header: first click sorts high→low, second
  low→high).
- **Price (R$/MMBtu)** is the trade price as published; **R$/m³** is this
  site's own conversion of it (see [Known Limitations](Known-Limitations)
  for the exact factor and convention).

## Exports and refresh

- **Download CSV** / **Export all data (Excel)** — CSV follows the table's
  current filters; the Excel export includes everything.
- **Reload latest** re-fetches whatever build is currently published — it
  does not trigger a new pull from the source API. The underlying data
  refreshes automatically on its own schedule (see
  [Architecture and Deployment](Architecture-and-Deployment)); this
  button is for picking up a build that already finished, not forcing a new
  one.
