# Known Limitations and Assumptions

## LGN is NGL, not LNG

"LGN" on this dashboard is ANP's own label, Líquido de Gás Natural — natural
gas liquids (LPG plus C5+ condensate-like liquids stripped out at
processing plants) — the inverse concept from GNL (Gás Natural Liquefeito,
liquefied natural gas / LNG). Checked directly against ANP's own metadata
document for this exact file and against the raw CSV's own `PRODUTO`
column, both of which read LGN, not GNL — this is ANP's own terminology,
not a translation choice made here.

## Imports: one national total, no origin split

The imports file gives a single national monthly import total; it does not
split Bolivia-sourced pipeline imports from LNG. That total is what's shown
here — an origin breakdown is not invented from other sources. If ANP's
imports file isn't reachable when the dashboard rebuilds, an explicit
"import data unavailable" notice is shown instead of silently charting a
zero.

## Publication lag

ANP typically publishes with roughly 2 months of lag.

## The balance identity is a check, not a guarantee

Available ≈ Production − Flare/loss − Own use − Reinjection is a useful
sanity check on this data (it reconciles to within a fraction of a percent
in practice), but each series is independently published by ANP rather than
derived by summing the others — small month-to-month discrepancies between
the identity and the published Available figure reflect ANP's own data, not
an error in this pipeline's arithmetic.
