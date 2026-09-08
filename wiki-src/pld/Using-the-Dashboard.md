# Using the Dashboard

PLD Prices shows CCEE's daily-average settlement price (PLD) by submarket —
North, Northeast, Southeast, and South.

## KPI row

One tile per submarket, latest available PLD.

## Daily PLD by submarket

Window preset (3 / 6 / 12 / 24 months, or all embedded history — the
dashboard embeds roughly the last 24 months) and per-submarket toggles to
show or hide a line.

## PLD vs CMO vs gas CVU

A second chart, shown only when comparison data was available at build
time: PLD alongside ONS's CMO (marginal operating cost) and an implied gas
CVU, for a submarket you pick (defaults to SE). This chart is built from a
join across this dashboard's own PLD data and ONS's CMO series — if that
join has no CMO data to work with at build time, the card doesn't render at
all rather than showing a partial or broken chart.

## Table and exports

The table lists daily PLD by submarket for the current window. **Download
CSV** and **Export all data (Excel)** follow it.

## What "PLD" is (and isn't)

PLD is CCEE's settlement price — not ONS's CMO, which is a different figure
from a different source. See [Known Limitations](Known-Limitations) for the
distinction.
