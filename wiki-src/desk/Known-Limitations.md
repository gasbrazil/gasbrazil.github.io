# Known Limitations and Assumptions

## Every number here is only as fresh as its source dashboard's last build

The Desk doesn't fetch anything live — at build time it pulls each source
dashboard's own latest published data (via a private mirror of each
dashboard's data store, `data_kit.ensure_lake()`), so a KPI here is exactly
as current as that source dashboard's own most recent successful rebuild,
not "as of right now." If a source dashboard's own last refresh failed or
is running behind schedule, the Desk's figure for it will lag until that
dashboard catches up — the Desk itself doesn't know it's showing a stale
figure and won't visibly flag it as such.

## SIN gas generation is a sum, not a published figure

Same as [ONS Balances](/wiki/ons/known-limitations.html): there is no
published national "SIN" gas-generation series. This KPI sums ONS's four
published subsystems, exactly as the ONS dashboard's own SIN figures do.

## PLD ≠ CMO

Shown side by side here for comparison, but they're different figures from
different sources — see [PLD Prices](/wiki/pld/known-limitations.html) for
the distinction.

## The spark calculator's assumptions

- **9,400 kcal/m³** for natural gas heat content is Brazil's standard
  calorific value, not a plant- or region-specific figure — same constant
  [ONS Balances](/wiki/ons/known-limitations.html) uses for its own
  estimated-gas-consumption figures.
- **1,800 / 2,500 kcal/kWh** heat-rate presets are typical CCGT/OCGT
  industry figures, not specific to any real plant.
- **The default gas price is whichever figure is available first**, in this
  order: the latest GUS trade price, then POC's 7-day average price, then
  an illustrative 1.2 R$/m³ so the calculator never loads with an empty
  field. Whichever one populated the field is worth checking before reading
  too much into the default — it's a starting point for your own number,
  not a recommendation.
- The calculator computes an *implied* CVU from whatever gas price and heat
  rate you enter — it isn't a published CVU for any specific plant, and
  doesn't claim to be one. The CVU override field is there specifically so
  you can substitute a real plant's own published CVU instead.
