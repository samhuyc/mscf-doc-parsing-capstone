# Source-page spot checks

These are assistant visual observations of two source pages and their saved
MinerU outputs, not independently human-verified labels or a comprehensive score.
They were recorded after the adapter was frozen and are not used to modify it.

## Scanned invoice: 01_extractbench, page 1

The original main line-item table shows item 2856676, quantity ordered 455,
quantity shipped 455, quantity backordered 0, unit price 26.35, and total
11,989.25. MinerU retains several of these strings but merges quantity text into
the description/header region and does not preserve the complete column
association in the main line-item table. This is a parser table-structure error.

The upper payment summary's subtotal 11,989.25, shipping 0.00, and amount due
11,989.25 are retained and mapped by the deterministic extractor. Invoice number
NF67652 also appears in the parser output but is omitted by the adapter because
its label/value matching finds conflicting candidates in the mixed table.
That omission is an adapter limitation, not evidence that OCR lost the number.

## Holdings filing: 02_extractbench, page 1

The original first holdings row identifies ACCENTURE PLC IRELAND, CUSIP
G1151C101, value 1,609,800, and shares 6,000. MinerU retains those values in the
same HTML row. The adapter maps issuer, CUSIP, and voting fields, but omits
`value_usd` and the shares field because the printed headers do not meet its
conservative schema-header matching rule. This demonstrates why pipeline value
recall cannot be interpreted as MinerU transcription recall.

MinerU also drops some entries in the printed row-number column and compresses
spacing in security-class labels (for example, `SHS CLASS A` becomes
`SHS CLASSA`). These observations are confined to the inspected page.

Source PDFs: `data/01_extractbench/document.pdf` and
`data/02_extractbench/document.pdf`. Original rendered review images are in
`artifacts/review/`; raw parser outputs and hashes are in `runs/mineru_cpu_v2/`.
