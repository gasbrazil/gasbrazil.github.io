# Known Limitations and Assumptions

## PLD ≠ CMO

PLD (Preço de Liquidação das Diferenças) is CCEE's settlement price. CMO
(Custo Marginal de Operação), shown on [ONS Balances](/wiki/ons/using-the-dashboard.html),
is ONS's marginal operating cost. The two track related fundamentals —
CMO feeds into how PLD is set — but they are published by different bodies
from different processes and are not interchangeable figures. Don't quote
one as if it were the other.

## Peak / off-peak is not a CCEE field

Hourly PLD has no ponta flag. The dashboard classifies **peak** as hours
18, 19, and 20 (18:00–21:00, hour beginning) on Monday–Friday, and
**off-peak** as every other hour, including all weekend hours. That matches
the common ANEEL-style three-hour weekday window (TOU assumptions v1 in
`shared/transforms.py`). Distributor-specific ponta windows can differ,
and national holidays are **not** excluded — there is no holiday calendar
in this tree.

## Hourly history is a recent slice

CCEE publishes hourly PLD from 2021. The pipeline keeps a few recent years
(from 2024) rather than the full hourly archive, and the page only embeds
about the last 31 days of hour-by-hour points (peak / off-peak daily
averages still cover the same ~24-month window as daily PLD). The private
lake parquet has the fetched hourly history; the read-only API exposes
`/v1/pld/hourly`.

## The compare chart depends on data this dashboard doesn't own

"PLD vs CMO vs gas CVU" joins this dashboard's own **daily** PLD series
against ONS's CMO series (via a shared join, `shared/joins.py`), which in
turn depends on ONS's data being reachable from the private data lake at
build time. When it isn't, the join finds no CMO data and the card simply
doesn't render — this is a build-time availability question, not a
data-quality issue with either dashboard's own numbers.

## Source discovery

Download URLs are discovered dynamically each fetch (CCEE's CKAN API
tokens rotate), with a fallback to known URLs by year if that lookup fails
— this affects how reliably a scheduled refresh picks up a brand-new year's
file on day one, not the correctness of any published PLD value once
fetched.
