# GasBrazil.com — Wiki

GasBrazil.com is a family of Brazilian natural-gas market dashboards — ONS
grid balances, PEG capacity-offer results and contracts, ANP pipeline
flows, CCEE electricity settlement prices, ANP gas-price disclosures, the
national supply balance, and a cross-product desk view — plus the home page
and this wiki. Every dashboard is a single self-contained HTML file with an
embedded, gzip-compressed data payload: no server, no database, no API call
at view time.

This wiki covers what each dashboard's own README doesn't: how to read the
live page, and where a number on it rests on an assumption rather than a
published figure. It's organized in two layers — this Home page and
[Architecture and Deployment](Architecture-and-Deployment) cover the whole
site, and every dashboard has its own **Using the Dashboard** and **Known
Limitations** pair covering what's specific to it.

## Dashboards

| Dashboard | Live | Using the Dashboard | Known Limitations |
|---|---|---|---|
| ONS Balances | [gasbrazil.com/ons](https://gasbrazil.com/ons/) | [Using the Dashboard](/wiki/ons/using-the-dashboard.html) | [Known Limitations](/wiki/ons/known-limitations.html) |
| POC Results | [gasbrazil.com/poc](https://gasbrazil.com/poc/) | [Using the Dashboard](/wiki/poc/using-the-dashboard.html) | [Known Limitations](/wiki/poc/known-limitations.html) |
| POC Contracts | [gasbrazil.com/contratos](https://gasbrazil.com/contratos/) | [Using the Dashboard](/wiki/contratos/using-the-dashboard.html) | [Known Limitations](/wiki/contratos/known-limitations.html) |
| Pipeline Flows | [gasbrazil.com/flows](https://gasbrazil.com/flows/) | [Using the Dashboard](/wiki/flows/using-the-dashboard.html) | [Known Limitations](/wiki/flows/known-limitations.html) |
| Gas Supply | [gasbrazil.com/supply](https://gasbrazil.com/supply/) | [Using the Dashboard](/wiki/supply/using-the-dashboard.html) | [Known Limitations](/wiki/supply/known-limitations.html) |
| PLD Prices | [gasbrazil.com/pld](https://gasbrazil.com/pld/) | [Using the Dashboard](/wiki/pld/using-the-dashboard.html) | [Known Limitations](/wiki/pld/known-limitations.html) |
| ANP Prices | [gasbrazil.com/precos](https://gasbrazil.com/precos/) | [Using the Dashboard](/wiki/precos/using-the-dashboard.html) | [Known Limitations](/wiki/precos/known-limitations.html) |
| The Desk | [gasbrazil.com/desk](https://gasbrazil.com/desk/) | [Using the Dashboard](/wiki/desk/using-the-dashboard.html) | [Known Limitations](/wiki/desk/known-limitations.html) |

## Repo at a glance

```
shared/dashboard_kit.py   theming, i18n, nav, fonts, CSV/XLSX/theme-toggle JS -- single source of truth
shared/theme.css          CSS design tokens (light + dark), header/nav/table styling
<slug>/<slug>_pipeline.py fetch + build for that dashboard's data source
<slug>/dashboard.py       builds that dashboard's index.html (imports shared/dashboard_kit.py)
<slug>/README.md          that dashboard's own data-source and pipeline notes
wiki-src/, build_wiki.py  this wiki's markdown source and build script
build_home.py             builds the home page, /about/, and the branded 404
.github/workflows/*.yml   one workflow per dashboard, plus home and wiki
```

Full setup and local-dev instructions are in each dashboard's own README —
this wiki assumes the site is already live and focuses on how to read it.
