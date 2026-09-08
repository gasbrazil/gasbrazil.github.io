# Using the Dashboard

The Desk is a cross-product snapshot — one page pulling a headline number
from each of the other dashboards, plus an interactive spark-spread
calculator, rather than a dashboard with its own data pipeline.

## KPI row

SIN gas generation, PLD (SE), CMO (SE), latest GUS trade price, ANP Santos
basin price, ANP non-thermal Southeast price, POC 7-day average price, and
Flows 7-day total — one figure pulled from each source dashboard's own
latest data.

## PLD · CMO · CVU

A submarket-selectable (SE/S/NE/N) chart comparing PLD, CMO, and an implied
gas CVU over time, toggle-able via the series picker above the chart.

## Spark

An interactive spark-spread calculator: enter a gas price in **R$/m³**
(defaults to whichever of the following is available first: the latest GUS
trade price, else POC's 7-day average price, else an illustrative 1.2
R$/m³ so the form never loads blank) and a heat rate (CCGT 1800 kcal/kWh,
OCGT 2500 kcal/kWh, or a custom value), and it computes:

```
Implied CVU (R$/MWh) = gas price (R$/m³) × heat rate (kcal/kWh) × 1000 / natural-gas heat content (kcal/m³)
```

against Brazil's standard 9,400 kcal/m³ natural-gas calorific value, then
shows that implied CVU alongside the gap to the current PLD and CMO (SE).
A **CVU override** field lets you substitute your own CVU figure into the
vs-PLD / vs-CMO comparison directly, bypassing the gas-price/heat-rate
calculation.

## POC · ANP — monthly

A monthly comparison of POC's traded price against ANP's published
disclosures, series picker above the chart.

## Capacity vs flows

A table comparing held transport capacity (from
[POC Contracts](/wiki/contratos/using-the-dashboard.html)) against actual
physical flow (from [Pipeline Flows](/wiki/flows/using-the-dashboard.html))
by pipeline.

## Getting to the source dashboards

The row of pills under the header links straight to each source dashboard
— ONS, CCEE (PLD), ANP (Prices), POC, and Flows — for anyone who wants the
full picture behind one of the Desk's headline numbers.
