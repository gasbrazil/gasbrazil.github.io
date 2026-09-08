# Known Limitations and Assumptions

## The R$/m³ conversion is derived, not published

The source publishes trade price in R$/MMBtu only. The dashboard's R$/m³
column and the price chart's right-hand axis are computed from it:

```
R$/m3 = R$/MMBtu × 28.8081 / 1000
```

28.8081 is the MMBtu-per-1000-m³ factor implied by the dataset's PCR (poder
calorífico de referência) convention — it's a fixed linear factor applied
uniformly to every row, not a per-trade or per-pipeline heating value. This
is the conversion PEG's own portal and this dashboard use; it isn't a
site-specific assumption about gas quality on any particular contract.

## Coverage

The pipeline is a Python port of the "Resultados (Includes Null)" Power
Query in the original source workbook: one row per accepted bid; a process
with no accepted bids gets a single null-bid row rather than being dropped
silently, so you can see that a process ran and cleared nothing. Portuguese
`finalidadeProcesso` / `formaAtendimento` values are translated to English
where a mapping exists; anything not in the map falls back to its original
Portuguese label rather than being blanked or guessed.

## Refresh cadence

Data refreshes automatically roughly every 6 hours via a scheduled GitHub
Actions run (fetch happens server-side, since the source API has no CORS
headers reachable from a browser). The on-page **Reload latest** button
reloads whatever build is currently published — it does not itself trigger
a new fetch.

## What this page doesn't cover

Contract-level capacity (who holds how much, on what terms) is
[POC Contracts](/wiki/contratos/using-the-dashboard.html)' scope, not this
page's — POC Results is *auction results* (what cleared, at what price),
Contracts is *held positions*.
