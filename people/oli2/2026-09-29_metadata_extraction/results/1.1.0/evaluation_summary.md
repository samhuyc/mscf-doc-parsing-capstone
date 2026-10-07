# O6 evaluation summary — ruleset 1.1.0

Generated from [evaluation.json](evaluation.json) and [summary.csv](summary.csv),
with version changes from [comparison.json](comparison.json). The JSON evaluation
remains the machine-readable audit artifact. This report does not rerun extraction.

## Headline results

On the six-document prototype set, ruleset 1.1.0 matched all provisional reference
labels while abstaining on fields that were not explicitly supported. These are
development-set findings, not held-out benchmark accuracy.

- Documents evaluated: **6/6**; missing: **0**.
- Resolved, non-null fields: **18/24 (75%)**.
- Abstentions: **6/24 (25%)**; **6 expected**.
- Differences from provisional labels: **0**.
- Evidence spans valid: **473/473**.
- Recorded extraction time: **0.2604 seconds total**, **0.0434 seconds per document** on average.

| Field | Exact match, including expected nulls | Match where a non-null value is expected | Resolved coverage | Abstentions |
|---|---:|---:|---:|---:|
| Document type | 6/6 | 6/6 | 6/6 | 0/6 |
| Reference period | 6/6 | 6/6 | 6/6 | 0/6 |
| Reference date | 6/6 | 4/4 | 4/6 | 2/6 |
| Document date | 6/6 | 2/2 | 2/6 | 4/6 |

Exact match includes correct null decisions. Coverage counts only resolved, non-null
values; the supported-value column separates extracted dates from correct abstentions.

## Per-document decisions

Reference date means reporting-period end. Document date means publication,
announcement or presentation-event date. Every populated value below is resolved;
`null` denotes a `not_found` abstention in this run.

| Document | Document type | Reference period | Reference date | Document date | Recorded time (ms) |
|---|---|---|---|---|---:|
| CVS (Q2 2025) | earnings presentation | 2025 Q2 | null | 2025-07-31 | 20.9 |
| EDF (2024) | consolidated segmental statement | Year 2024 | 2024-12-31 | null | 7.3 |
| Hippodrome (2025) | annual financial statements | Year 2025 | 2025-12-31 | null | 55.6 |
| Peterborough (2025) | unaudited financial statements | Year 2025 | 2025-03-31 | null | 15.9 |
| Rolls-Royce presentation (H1 2026) | results presentation | 2026 H1 | null | null | 10.9 |
| Rolls-Royce release (H1 2026) | results press release | 2026 H1 | 2026-06-30 | 2026-07-30 | 149.8 |

The document-level `not_found` status in the CSV means at least one field is missing;
it does not invalidate that document's resolved fields. [Full decisions](metadata.jsonl)
retain rule IDs, exact quotations, physical pages and competing candidates.

## Expected abstentions

| Document | Field | Status | Interpretation |
|---|---|---|---|
| CVS (Q2 2025) | Reference date | not_found | Reporting period is known; an exact period-end date is not explicitly supported. |
| Rolls-Royce presentation (H1 2026) | Reference date | not_found | Reporting period is known; an exact period-end date is not explicitly supported. |
| EDF (2024) | Document date | not_found | No supported publication, announcement or presentation-event date under the experiment policy. |
| Hippodrome (2025) | Document date | not_found | No supported publication, announcement or presentation-event date under the experiment policy. |
| Peterborough (2025) | Document date | not_found | No supported publication, announcement or presentation-event date under the experiment policy. |
| Rolls-Royce presentation (H1 2026) | Document date | not_found | No supported publication, announcement or presentation-event date under the experiment policy. |

Quarter and half-year labels are not converted into assumed calendar end dates.
PDF creation dates, filing stamps, approval/signature dates and body as-of dates
are outside the document-date definition. Hippodrome retains warnings about an
excluded Companies House stamp and ambiguous numeric date mentions; its explicit
reporting end remains resolved. `not_found` means the rules found no eligible value,
not proof that a date is absent from the original PDF.

## Changed decisions: 1.0.0 → 1.1.0

| Document | Field | 1.0.0 | 1.1.0 |
|---|---|---|---|
| Rolls-Royce release (H1 2026) | Reference period | null / ambiguous | 2026 H1 / resolved |
| Rolls-Royce release (H1 2026) | Reference date | null / ambiguous | 2026-06-30 / resolved |

**2 field decisions changed; the other 22/24 are unchanged.**

The structural ranking is heading/title > narrative > table. The release's
document-level period outranks comparative table headers. Once the reporting
scope resolves, incompatible comparative reporting dates are excluded. This
uses neither a document-specific exception nor a latest-year rule. Table-only
conflicts remain ambiguous in the adversarial tests.

See the [preserved 1.0.0 baseline](../../baseline/1.0.0/results/evaluation.json)
and [failure analysis and test documentation](../../README.md).

## Limitations

- **Labels:** Assistant-authored review of fixed parsed text and embedded PDF titles before running extraction; date policy agreed in the user request. Provisional; pending independent human review. Not source-PDF gold or held-out evaluation.
- **Small development set:** these six documents informed the rules. Matching these labels does not establish generalization.
- **Fixed parser inputs:** canonical parser choices were made after inspection; parser selection and routing are outside O6.
- **Evidence validity:** Exact quotation, offsets, allowed input and physical page only; this does not establish semantic correctness or OCR accuracy.
- **Structural heuristics:** parser headings and fully bold lines are not verified semantic titles. Malformed table markup and unmarked titles can defeat the ranking.
- **Scope:** the rules target English financial documents and preserve uncertainty; they do not provide a general fiscal-calendar or multilingual date engine.
- **Timing:** One local sequential run: file reads, validation, text adaptation and rules; excludes OCR, models, output serialization and evaluation. Not a controlled benchmark. This report reuses the recorded runtime rather than measuring a new run.
- **Next step:** evaluate on a larger independently labeled corpus before considering an LLM fallback.

## Generation sources

SHA-256 hashes below identify the exact input bytes used for this report.

| Source | SHA-256 |
|---|---|
| [evaluation.json](evaluation.json) | `b4a08281197f2caff3f573ac05204c8109667ce564890822c74ddf5f0388a72e` |
| [summary.csv](summary.csv) | `8ef4bd4b9ac9691fe2be7d6b7c5a57a5a793a09e89b285c3531e19e90a5ae955` |
| [comparison.json](comparison.json) | `7c9d270b9872e0e50a64d613b63cb6ce29c1962ca72f753281c9c7959fb83a24` |
