# Known Limitations and Assumptions

## PLD ≠ CMO

PLD (Preço de Liquidação das Diferenças) is CCEE's settlement price. CMO
(Custo Marginal de Operação), shown on [ONS Balances](/wiki/ons/using-the-dashboard.html),
is ONS's marginal operating cost. The two track related fundamentals —
CMO feeds into how PLD is set — but they are published by different bodies
from different processes and are not interchangeable figures. Don't quote
one as if it were the other.

## The compare chart depends on data this dashboard doesn't own

"PLD vs CMO vs gas CVU" joins this dashboard's own PLD series against ONS's
CMO series (via a shared join, `shared/joins.py`), which in turn depends on
ONS's data being reachable from the private data lake at build time. When
it isn't, the join finds no CMO data and the card simply doesn't render —
this is a build-time availability question, not a data-quality issue with
either dashboard's own numbers.

## Source discovery

Download URLs are discovered dynamically each fetch (CCEE's CKAN API
tokens rotate), with a fallback to known URLs by year if that lookup fails
— this affects how reliably a scheduled refresh picks up a brand-new year's
file on day one, not the correctness of any published PLD value once
fetched.
