# Using the Dashboard

Gas Supply shows Brazil's national monthly natural-gas supply balance from
ANP's PPGN-EL open data, plus ANP's natural-gas imports when that source is
reachable.

## KPI row

Headline figure: latest national monthly production.

## Series picker and chart

Seven series, most in thousand m³/month: Production, Available, Flare &
loss, Own use, Reinjection, Imports, and LGN (NGL) — LGN alone is in plain
m³, a different scale from the rest, which is why it starts off the chart
by default (Production / Available / Flare & loss / Own use are on by
default; toggle any series via the picker). Every table column and export
header spells out its own unit so you don't have to hold LGN's different
scale in your head while reading the table.

## Table and exports

The table lists the full monthly series. **Download CSV** and **Export
Excel** follow it, with the same per-column units in the header.

## Import data gap notice

If ANP's imports file isn't reachable at build time, the dashboard shows an
explicit notice rather than silently charting imports as zero — see
[Known Limitations](Known-Limitations).
