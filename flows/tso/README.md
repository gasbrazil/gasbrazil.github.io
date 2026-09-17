# TSO Portaria ANP nº 1/2003 adapters

TAG, TBG, and NTS publish daily programmed/actual volumes at receipt and
delivery points under the same regulatory item (Art. 2º I-h). This package
normalizes those publications into the lake `flows_points` shape and merges
them over ANP open data for Actual/Scheduled variables.

## Layout notes

### TAG (confirmed)

Cumulative workbooks `Prog-Real_<SUBSYSTEM>_MM-YYYY_a_MM-YYYY.xlsx` from
[ntag.com.br/transparencia](https://ntag.com.br/transparencia/):

| Sheet | Variable |
|-------|----------|
| `*- Prog` | Scheduled Volume |
| `*- Realizado` | Actual Volume |

Header rows (0-based): type → point name (`DATA` col) → sub-pipeline → UF →
daily m³/dia series. Convert to thousand m³ (`/1000`) to match ANP.

Subsystems: GASENE, Malhas NE, Pilar–Ipojuca, Urucu–Manaus.

When the cache holds multiple coverage windows for the same subsystem,
build keeps only the workbook whose `_a_MM-YYYY` end date is newest.

### TBG

Monthly ZIPs under [Informações à ANP](https://www.tbg.com.br/informacoes-a-anp)
(Liferay document library; opaque UUID URLs). `fetch` pulls recent
`ANP <Mês> <Ano>.zip` packs, extracts the Volumes Entregues / Recebidos
Excel workbooks, and melts paired Programado/Realizado columns (already in
Mm³). PDFs on the same page are ignored.

### NTS

[Volumes Programados e Realizados](https://www.ntsbrasil.com/transparencia/)
are listed via the MZIQ catalog API
(`apicatalog.mziq.com/filemanager/...`), not plain HTML hrefs. Year
workbooks expose one sheet per month (`Programado (AGO)` /
`Realizado (AGO)`); values are already mil m³/dia.

## Crosswalk

Optional ANP code mapping in `point_crosswalk.json`. Keys are
`normalize_key("{tso}|{point_name}")`. Without a hit, synthetic codes
`{source}:{subsystem}:{slug}:{hash10}` are used so series remain chartable.
TBG Entregues sheets often embed ANP point codes directly; those are
preferred when present.
