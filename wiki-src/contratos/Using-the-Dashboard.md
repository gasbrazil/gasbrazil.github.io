# Using the Dashboard

POC Contracts tracks held transport capacity — who holds how much, on which
pipeline, under what contract — from the same PEG portal as POC Results, but
positions rather than auction outcomes.

## Pipeline chips

TBG / TAG / NTS chips above the table filter everything (drill-down,
tariff-trend chart, and table) to the selected pipeline. Clicking a chip a
second time clears it.

## Top Shippers by Held Capacity

A ranked drill-down of the largest shippers by contracted capacity — active
contracts, currently within their term, only. Selecting a pipeline chip
scopes it to that pipeline and adds an Entry/Exit capacity split per
pipeline column; with no pipeline selected it shows every pipeline side by
side. Shows the top 10 shippers by default, with a button to expand to the
full list. Clicking a shipper row filters the main table below to that
shipper (click again, or use Reset filters, to clear it).

## Allocated Tariff Trend

Capacity-weighted average allocated tariff (R$/MMBtu), charted by contract
start date — a proxy for how transport tariffs have moved over time, weighted
so a handful of large contracts don't get outvoted by many small ones.

## Table

Columns: Pipeline, Contract Number, Contract Category, Status, Shipper,
Product Type, Point/Zone, Flow, Quality, Start/End Date, Contracted Capacity
(000 m³/d), Allocated Tariff (R$/MMBtu), Tariff Multiplier, Transporter
Ownership %, Amendment. Same Excel-style per-column filters, drag-to-reorder,
resize, and sort as POC Results.

## Coverage note (footer)

The footer's info icon states exactly what's in scope: **Transport
Contract** and **Master Contract** categories only — "Legacy Transport
Contract" and "Access Connection" are smaller, separately-sourced categories
on the source site not yet covered (see
[Known Limitations](Known-Limitations)) — and concluded contracts are
excluded from the shipped view, with the excluded count shown next to the
note.

## Exports

**Download CSV** follows the table's current filters; **Export all data
(Excel)** includes everything currently shipped to the page (concluded
contracts are already excluded upstream — see Known Limitations for where
the full history including those still lives).
