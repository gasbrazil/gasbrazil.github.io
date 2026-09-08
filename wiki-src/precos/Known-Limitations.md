# Known Limitations and Assumptions

## A blank cell is a confidentiality suppression, not a zero

ANP withholds a price when publishing it would reveal a single counterparty's
terms (too few participants in that basin/market/month combination). This
pipeline keeps those cells as nulls — no interpolation, no estimate, no
zero — so a gap in the chart or a blank in the table means ANP didn't
publish a figure for that cell, not that gas didn't trade or that this
pipeline failed to fetch it.

## Publication lag

ANP typically publishes with roughly 2–3 months of lag. The most recent 2–3
months on this dashboard should generally be treated as not yet available
rather than as "zero activity."

## Not an official ANP product

This dashboard aggregates and charts ANP's own published disclosures; it
isn't an ANP product itself, and the figures are exactly what ANP
published, in R$/MMBtu with volumes, un-transformed.
