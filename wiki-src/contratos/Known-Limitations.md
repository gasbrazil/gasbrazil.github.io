# Known Limitations and Assumptions

## Two of four contract categories aren't covered yet

The source site's UI shows four contract categories; this pipeline covers
two of them — **Contrato de Transporte** and **Contrato Master**. **Contrato
de Transporte Legado** ("Legacy Transport") and **Conexão de Acesso**
("Access Connection") are not served by the same GraphQL field this pipeline
queries — confirmed by exhaustively querying every value the API's own
`StatusContrato` enum accepts (only three exist, all consumed by the two
categories above) and by introspecting the GraphQL schema directly (nothing
named legado/conexão/acesso anywhere in it). That data lives behind a
different, unidentified endpoint and will be added once it's found — it
isn't a gap in what this pipeline processes from the source it reads, it's
a source this pipeline doesn't reach yet.

## Concluded contracts are excluded from the page, not from the data

Concluded ("Concluído") transport contracts are filtered out of the shipped
`index.html` to keep the client-side payload smaller — the footer's coverage
note shows the excluded count. The full history, concluded contracts
included, stays in the repo's committed Parquet store for anyone who needs
it; it just isn't in what your browser downloads.

## TSO identity

Pipeline id → name mapping (`1 = TBG`, `2 = TAG`, `3 = NTS`) is confirmed
directly against the source, not inferred.

## What this page doesn't cover

Auction/bid results (what cleared, at what price) are
[POC Results](/wiki/poc/using-the-dashboard.html)' scope, not this page's —
this page is *held positions* (who has how much capacity, on what terms),
POC Results is *what happened at auction*.
