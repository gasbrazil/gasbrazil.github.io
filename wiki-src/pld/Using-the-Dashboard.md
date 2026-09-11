# Using the Dashboard

PLD Prices shows CCEE's settlement price (PLD) by submarket — North,
Northeast, Southeast, and South — as a daily average, as an hourly series,
and as peak vs off-peak.

## KPI row

One tile per submarket. On the daily view this is the latest daily
average; on hourly it is the latest hour; on peak / off-peak it is the
latest weekday peak average, with off-peak shown in the subtitle.

## Series toggle

**Daily average**, **Hourly**, and **Peak / off-peak** switch the main
chart, the table, and the CSV/Excel export. Hourly embeds roughly the last
31 days (window presets 1 / 3 / 7 / 14 / 30 days). Daily and peak /
off-peak use the same longer window presets as before (3 / 6 / 12 / 24
months, or all embedded history — about 24 months).

Per-submarket toggles still show or hide a line. On peak / off-peak, each
visible submarket draws two lines: peak (solid) and off-peak (dashed).

## PLD vs CMO vs gas CVU

A second chart, shown only when comparison data was available at build
time: daily PLD alongside ONS's CMO (marginal operating cost) and an
implied gas CVU, for a submarket you pick (defaults to SE). This chart is
built from a join across this dashboard's own daily PLD data and ONS's CMO
series — if that join has no CMO data to work with at build time, the card
doesn't render at all rather than showing a partial or broken chart.

## Table and exports

The table follows the active series view. **Download CSV** and **Export all
data (Excel)** export that same window.

## What "PLD" is (and isn't)

PLD is CCEE's settlement price — not ONS's CMO, which is a different figure
from a different source. Peak / off-peak is a GasBrazil convention on top
of hourly PLD, not a CCEE-published flag. See
[Known Limitations](Known-Limitations).
