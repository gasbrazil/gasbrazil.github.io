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
the same fixed conversion as the table's own R$/m³ column (R$/MMBtu ÷
26.8081 m³ per MMBtu; see
[Known Limitations](Known-Limitations)), so a value read off either axis is
consistent with the other.

## Quick filters

Chips above the toolbar for the filters people reach for most: Last 7 Days,
Last 30 Days, GUS, GUS + Residual Balancing (transaction type), and one chip
per pipeline. These combine with the toolbar and per-column filters below, not
instead of them — a quick filter is a shortcut into the same filter state
the column menus set. Rows with Trade Timing **No Trade** (null-bid) are
hidden by default; a dashed **Show No Trade** chip brings them back (`notrade=1`
in the URL). The Trade Timing dropdown can still select No Trade directly.

## Toolbar and table

- **Trade timing** dropdown and a free-text **search** box (matches process
  code / delivery point) sit above the table.
- **Reset filters** clears every filter — quick filters, toolbar, Show No
  Trade, and every column's own filter menu — back to the default view
  (No Trade rows stay hidden).
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
