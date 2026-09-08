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

### TBG

Monthly files under [Informações à ANP](https://www.tbg.com.br/informacoes-a-anp)
(Liferay document library; opaque URLs). Parser expects the same wide
Prog/Realizado sheet layout when Excel is published. PDFs are discovered but
not parsed. Seed local `.xlsx` under `flows/raw/tso/tbg/` if fetch is empty.

### NTS

[Volumes Programados e Realizados](https://www.ntsbrasil.com/transparencia/)
via MZIQ CDN (`api.mziq.com/mzfilemanager/...`). Same wide-layout parser as
TAG/TBG when the download is Excel. Seed `flows/raw/tso/nts/` as needed.

## Crosswalk

Optional ANP code mapping in `point_crosswalk.json`. Keys are
`normalize_key("{tso}|{point_name}")`. Without a hit, synthetic codes
`{source}:{subsystem}:{slug}:{hash10}` are used so series remain chartable.
