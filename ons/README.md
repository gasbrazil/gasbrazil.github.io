# ONS Balances — scraper + dashboard

Pulls Brazilian grid data from the ONS open-data portal, aggregates it to a daily
store, and generates a single self-contained HTML dashboard (`index.html`) you
open in a browser. Part of the [gasbrazil.github.io](../README.md) monorepo —
see the root README for how this fits with `poc/`, `contratos/`, and `shared/`.

## What it collects

Every series below is the open-data publication of something the Boletim Diário
da Operação also prints, so the dashboard reproduces the bulletin rather than
approximating it. The `check_bulletin.py` script proves that for any given day.

| Dataset | ONS source | Native granularity | Bulletin equivalent |
|---|---|---|---|
| Balanço de Energia nos Subsistemas | `balanco_energia_subsistema_ho` | hourly | **Sheets 03–07, "Dados Diários acumulados"** — production total, hydro, thermal, wind, solar, interchange, load (MWmed) |
| Geração Térmica por Motivo de Despacho | `geracao_termica_despacho_2_ho` | hourly, per plant | **Sheet 09, "Produção Térmica"** — programmed vs verified MWmed per plant, and the source of the thermal-by-fuel splits |
| Dados Hidráulicos por Reservatório | `dados_hidrologicos_di` | daily, per reservoir | **Sheets 23–26, "Sit. Princ. Reservatórios"** — upstream level (m) and usable volume (%) |
| ENA Diário por Subsistema | `ena_subsistema_di` | daily | Sheet 21 — natural inflow energy, MWmês and % of MLT |
| EAR Diário por Subsistema | `ear_subsistema_di` | daily | Sheet 19/20 — reservoir storage, MWmês and % of capacity |
| CMO Semi-Horário | `cmo_tm` | 30-minute | Marginal operating cost, R$/MWh |
| Geração por Usina em Base Horária | `geracao_usina_2_ho` | hourly, per plant | *Optional.* Fuel splits across the full plant universe. Not downloaded by default — it is ~1 GB and `termica` already covers sheet 09's universe. |

Everything is by subsystem (SE/CO, S, NE, N) plus a derived SIN national row.
Hourly and semi-hourly sources are averaged to daily means.

Two things the build reconciles rather than assumes:

- **Net interchange sign.** Sheets 03–07 satisfy `Carga = Produção total −
  Intercâmbio`, so a positive interchange is a net export. The build detects
  which orientation ONS's `val_intercambio` is using and normalizes to the
  bulletin's, printing the residual so you can see the identity holds.
- **Fuel splits vs. balance thermal.** The per-fuel numbers come from the thermal
  dispatch file; `gen_thermal` comes from the balance file. They are separate ONS
  publications, so every build prints the gap between them and flags a median
  above 3%.

The pipeline reads the portal's `.parquet` resources where ONS publishes them
(2021 onward) and falls back to `.csv` with delimiter and decimal-separator
sniffing for older years — ONS has shipped both `;`/decimal-comma and
`,`/decimal-point CSVs over time.

## Use

Run from inside this `ons/` directory (CI does the same — see
`.github/workflows/ons.yml`):

```bash
pip install -r requirements.txt
python ons_pipeline.py verify      # confirm every source URL is reachable — run this first
python ons_pipeline.py refresh     # fetch + build + dashboard (the normal daily run)
open index.html
```

The individual steps, if you want them separately:

```bash
python ons_pipeline.py fetch       # download raw files into ./raw
python ons_pipeline.py build       # aggregate ./raw -> ./data/daily.parquet + daily.csv
python ons_pipeline.py dashboard --html index.html
python ons_pipeline.py health      # is the store fresh and complete? (CI deploy gate)
```

Useful flags: `--years 2019 2026`, `--datasets balanco termica`, `--force`
(re-download even when the local copy matches the remote size), `--raw DIR
--out DIR --html FILE`.

No real data on hand? `python make_mock.py` generates ONS-shaped synthetic
raw/ files so `build`/`dashboard` run without hitting the network.

### Checking against a bulletin

Download any `DIARIO_dd-mm-yyyy.xlsx` from the
[Boletim Diário da Operação](https://sdro.ons.org.br/SDRO/DIARIO/index.htm) and
reconcile it against the store:

```bash
python check_bulletin.py DIARIO_20-08-2026.xlsx
```

It parses sheets 03–07, 09 and 23–26, matches every value to the store by date,
subsystem, plant or reservoir name and series, and reports what is missing and
what differs. Small residuals are normal when ONS has revised one publication and
not the other; large or systematic gaps are not.

### First run vs. daily refresh

The first `fetch` downloads a few hundred MB, mostly the monthly thermal dispatch
files. After that, `fetch` compares `Content-Length` against the local copy and
re-downloads only what changed, and `build` reuses cached per-file aggregates in
`data/_cache/`, so a daily refresh touches only the current month.

### The health gate

Between `build` and `deploy`, CI runs `ons_pipeline.py health`, which fails the
job if the store is stale, has too few rows, or has lost plants or reservoirs.
**A failed gate means no deploy** — yesterday's working dashboard stays up
rather than being replaced by a broken one.

## The dashboard

`index.html` is one file with the data embedded — no server, no CDN, no
network calls. It works from a `file://` path and survives being emailed. The
data is embedded gzipped and inflated in the browser via `DecompressionStream`,
which needs Chrome/Edge 80+, Firefox 113+, or Safari 16.4+; on anything older
the page says so instead of rendering blank.

Three tabs:

- **Subsystems** — the sheet 03–07 balance series, thermal by fuel, hydrology and CMO.
- **Thermal plants** — sheet 09. Every dispatched thermal plant, filterable by
  fuel and searchable by name, charted as verified, programmed, or deviation %.
- **Reservoirs** — sheets 23–26. Every reservoir, filterable by basin, charted as
  usable volume % or upstream level.

Shared controls: date range presets, daily/7-day/30-day smoothing, subsystem
toggles, up to 8 series at once, per-unit chart panels, a data table, CSV
export, and an "Export all data (Excel)" button (dependency-free XLSX writer,
now shared with `poc/` and `contratos/` — see `../shared/dashboard_kit.py`).

Colors, fonts, the theme toggle, and the cross-dashboard nav links at the top
of the page come from `../shared/theme.css` and `../shared/dashboard_kit.py` —
see the root README for how that sharing works.

## Caveats worth knowing

- **ONS revises.** Recent days get restated after publication. The pipeline
  re-downloads changed files, so a refresh picks revisions up, but a figure you
  quoted last week may not match today.
- **CMO is not PLD.** CMO is ONS's DESSEM marginal cost. PLD is CCEE's settlement
  price and comes from a different source; they track each other but are not the
  same number.
- **The SIN row is derived, not published.** Absolute series are summed across
  subsystems. EAR % is rebuilt as summed stored ÷ summed capacity. ENA % of MLT is
  rebuilt by summing each subsystem's implied MLT. CMO for SIN is an unweighted
  mean of the four subsystem CMOs — a reference level, not a traded price.
- **Fuel classification is string matching** on `nom_tipocombustivel`. Natural gas
  captures "Gás Natural", GNL/LNG, and process gas. If ONS introduces a new fuel
  label it lands in "Thermal — other"; the mapping is `classify_fuel()` in
  `ons_pipeline.py`, near the top of the aggregation section.
- **Deviation % is computed, not published.** It is `100 × (verified −
  programmed) / programmed`, from the smoothed components, and is left blank when
  programmed generation is zero. The bulletin prints −100% in that case.
- **Reservoir coverage.** The open-data hydraulic file carries every reservoir ONS
  tracks; the bulletin's sheets 23–26 print the principal ones. The store is a
  superset, so a name in the bulletin should always be present, but not the
  reverse.
- **MWmed vs MWmês.** The balance and generation series are in MWmed (average MW).
  ENA and EAR are in MWmês, which is why they sit in a separate chart panel.

## Files

```
ons_pipeline.py     downloader + aggregator + CLI
dashboard.py        HTML/JS dashboard generator (imported by the CLI; consumes ../shared/)
check_bulletin.py   reconciles the store against a DIARIO_*.xlsx workbook
make_mock.py        generates ONS-shaped fake data for offline testing
build_wiki_site.py  Wiki/*.md -> wiki-html/*.html, linked from the dashboard's Wiki button
tools/stamp.py      writes .state/last_refresh.json after each successful build
Wiki/               source markdown for the in-dashboard Wiki pages
requirements.txt
raw/                downloaded source files (gitignored; CI keeps it in the Actions cache)
data/               daily.parquet, daily.csv, entities.parquet, aggregate cache (gitignored)
index.html          the deliverable (committed — this is what GitHub Pages serves at /ons/)
wiki-html/          built Wiki pages (committed)
```

Source: [ONS Dados Abertos](https://dados.ons.org.br), CC-BY.
