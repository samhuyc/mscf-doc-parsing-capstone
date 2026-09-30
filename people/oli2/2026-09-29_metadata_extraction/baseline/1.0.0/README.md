# O6: Document metadata extraction

An initial deterministic experiment on six sponsor documents. It extracts document
type and semantic dates from existing page exports, retaining exact evidence and
abstaining when rules cannot resolve a value. No PDF downloads, OCR, model calls,
or external APIs are needed. All inputs under Sam's folder remain read-only.

## Scope and methodology

**Metadata extraction is evaluated on fixed canonical parsed representations.
Parser selection and routing are outside this experiment.** The choices in
`input_manifest.json` were made after inspecting the outputs. They are not an
automatic ranking or an independent comparison of parsers.

Source revision: `159a4731f1d2320816c65976c79f1f4ed636294b`.
See the existing [sponsor experiment](../../samhu/2026-09-29_sponsor_samples/README.md).

| Document ID | Fixed parser | Reason |
|---|---|---|
| cvs_2025q2 | pymupdf4llm | Cover retains quarter and event date; text identifies a presentation. |
| edf_2024 | pymupdf4llm | Cover retains statement type and explicit year-end. |
| hippodrome_2025 | mineru_ocr | Cover retains title and reporting date; PyMuPDF cover contains only `j rua`. |
| peterborough_2025 | pymupdf4llm | OCR cover retains unaudited statements and explicit year-end. |
| rolls_royce_2026h1_presentation | pymupdf4llm | Cover retains period; embedded PDF title identifies presentation. |
| rolls_royce_2026h1_release | pymupdf4llm | Cover retains announcement date; financial statements state period-end. |

PyMuPDF's existing outputs include automatic OCR. A source is labeled scanned
when all recorded native-text counts are zero; running OCR alone does not imply
an image-only source. This diagnostic does not change parser selection or rules.

## Run

Tested with Python 3.13.7 on Windows. Python 3.10+ is required by the source syntax.
From this folder:

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B extract.py
python -B evaluate.py
```

The evaluation dependency is `jsonschema`; extraction uses only the standard
library. Commands work from other directories when the script path is supplied.
Default input and output locations are relative to the scripts, not the shell.

`extract.py` validates all six inputs before writing results. It fails explicitly
on missing, changed, incomplete, or inconsistent exports. It never silently
skips a document or chooses another parser. Re-running replaces only this
experiment's result files; archive results under this folder before changing
rules if a before/after comparison is needed. Neither command commits changes.

## Files and data flow

```text
input_manifest.json -> inputs.py -> rules.py -> extract.py -> results/metadata.jsonl
                                                          -> results/summary.csv
reference_labels.json -----------------------> evaluate.py -> results/evaluation.json
metadata.schema.json ------------------------> evaluate.py
```

- `inputs.py`: pins four export hashes, validates source identity, successful run
  status, page counts, physical page order, and reconstructed document text.
- `rules.py`: document-type patterns, period/date candidates, priority rules,
  evidence collection, and explicit abstention.
- `extract.py`: sequential CLI runner, provenance, timing, JSONL and CSV outputs.
- `evaluate.py`: evaluation-only reference labels, JSON Schema validation,
  quotation/page verification, metrics, mistakes, and abstentions.
- `tests/test_extraction.py`: 26 tests, mostly synthetic adversarial examples,
  plus read-only validation of the six fixed inputs.

No extraction module imports the evaluator or reads reference labels.

## Output contract

See [metadata.schema.json](metadata.schema.json) for the machine-readable schema.
Each document has four decisions:

| Field | Meaning |
|---|---|
| `document_type` | One of six explicit types, or `null` when unresolved. |
| `reference_period` | `{year, kind, number}`; kind is `year`, `half`, or `quarter`. Number is null when not stated or inapplicable. |
| `reference_date` | An explicitly supported reporting-period end, ISO `YYYY-MM-DD`. |
| `document_date` | Publication/announcement or presentation-event date. Filing stamps, approval/signature dates, PDF timestamps and body as-of dates are outside this definition. |

Types are `earnings_presentation`, `results_presentation`,
`results_press_release`, `annual_financial_statements`,
`unaudited_financial_statements`, and `consolidated_segmental_statement`.

Each decision contains `value`, `role`, `status`, `rule_id`, `evidence_ids`, and
`candidates`. Status is:

- `resolved`: one value survives the highest applicable priority.
- `ambiguous`: equally ranked evidence conflicts or a relevant date is ambiguous.
- `not_found`: no eligible value is supported by the implemented rules.

Abstentions have null values. `not_found` does not prove absence in the PDF.
The document-level status is `ambiguous` if any field is ambiguous, otherwise
`not_found` if any field is missing, otherwise `resolved`. Use individual field
statuses when assessing coverage: an incomplete document can have correct fields.

Candidates retain rule IDs, priorities, evidence and exclusion reasons. Priorities
are ordering rules, not confidence probabilities. The initial rules use:

- Explicit cover type phrases (priorities 80-100); embedded PDF title phrases
  receive 20 less. An earnings-call cover plus "this presentation" on either of
  the first two pages supports `earnings_presentation` at priority 100.
- Cover period labels and cover reporting-end phrases receive priority 100;
  reporting-end phrases on later pages receive 50. Explicit H1/H2 text can
  supply a missing half number for the cover's year. No exact calendar end is
  inferred from quarter or half-year labels.
- Reference dates require a contextual reporting-end phrase. A resolved period
  excludes dates with a different year or period kind. Otherwise conflicting
  candidates remain visible and cause abstention.
- Document dates must be on the cover. Explicit publication labels receive 100;
  unlabeled dates in the first 500 normalized characters of a recognized
  presentation/release receive 80, and remaining cover dates receive 20.
  Reporting-end phrases, nearby Companies House stamps and recognized
  administrative/as-of prefixes are excluded.

Named English months, ISO dates and unambiguous slash dates are supported. An
ambiguous numeric date such as `03/04/2022` stays unresolved. Invalid dates are
flagged and never repaired. This is a small English-language ruleset, not a
general fiscal-calendar or multilingual date engine.

## Evidence and leakage controls

`pages[].markdown` is the canonical text. A character map connects normalized
search text back to the exact original JSON string, including Markdown and HTML.
Evidence stores a repository-relative file path, JSON pointer, 1-based physical
page, exact quotation, and Python Unicode string offsets `[start, end)`.

The only metadata field made available to semantic rules is the **embedded PDF
title**, `/source/metadata/title`. Such evidence has `page: null` because PDF
properties are not physical-page text. This is distinct from the human-supplied
manifest title `/source/title`, which is never searched. Generated headings and
manifest descriptions are also not prediction inputs.

IDs and file paths identify records and evidence; rules do not branch on them.
PDF creation/modification dates are excluded from the semantic rule interface.
Image filenames are stripped from searchable Markdown. Tests vary IDs, supplied
titles and timestamps to check that they cannot change the decisions.

Provenance retains parser versions, source PDF hash, source revision, manifest
hash, extraction-code hashes, and observed input hashes. Source PDFs are not
opened or rehashed. Git can convert LF to CRLF on Windows: validation explicitly
normalizes CRLF to LF for the pinned export hashes, and records both checkout
and normalized hashes plus affected filenames. No source file is rewritten.

## First-run results — ruleset 1.0.0

All 26 tests passed. All six records passed schema and evidence validation.
The first experiment is preserved without tuning against its errors.

| Metric | Result |
|---|---:|
| Document-type exact match | 6/6 |
| Reference-period exact match | 5/6 |
| Reference-date exact match, including null | 5/6 |
| Reference-date match where a date is expected | 3/4 |
| Document-date exact match, including null | 6/6 |
| Document-date match where a date is expected | 2/2 |
| Non-null resolved field coverage | 16/24 (66.7%) |
| Field abstention rate | 8/24 (33.3%) |
| Exact evidence spans valid | 473/473 |

Exact match includes correct null decisions; the separate supported-value metric
prevents nulls from hiding missed dates. Period accuracy compares the complete
year/kind/number object. Coverage is resolved non-null fields divided by all
four fields across six documents. Missing predictions remain in denominators.
Evidence validity checks quotations, offsets, allowed sources and page numbers;
it does not prove semantic correctness or OCR accuracy.

| Document | Reference period | Reference date | Document date | Runtime (ms) |
|---|---|---|---|---:|
| CVS | 2025 Q2 | null / not_found | 2025-07-31 | 18.8 |
| EDF | Year 2024 | 2024-12-31 | null / not_found | 11.5 |
| Hippodrome | Year 2025 | 2025-12-31 | null / not_found | 62.9 |
| Peterborough | Year 2025 | 2025-03-31 | null / not_found | 15.5 |
| Rolls-Royce presentation | 2026 H1 | null / not_found | null / not_found | 14.3 |
| Rolls-Royce release | null / ambiguous | null / ambiguous | 2026-07-30 | 168.3 |

Total measured extraction time: **0.2915 seconds**, mean **0.0486 seconds**.
These are one local run's file reads, validation, adaptation and rules, excluding
OCR, model runtime, serialization and evaluation. They are not controlled
benchmark latency estimates.

### Error analysis before tuning

There are **two unexpected abstentions in one document**: the Rolls-Royce release
should resolve `2026 H1` and `2026-06-30` according to the provisional labels.

The period rule currently treats every matching label on the first physical page
as equally authoritative. That page contains the title's `2026 Half Year` and
table comparisons `H1 2026` / `H1 2025`. Both years receive priority 100, producing
an ambiguous period. With no resolved scope, the reference-date rule retains
both the current statement's `half-year ended 30 June 2026` (page 13) and prior
comparative dates such as `Half-year to<br/>30 June 2025`. It abstains again.

This is a candidate-ranking limitation, not missing OCR text or an incorrect
reference label. A possible later change is to distinguish document titles from
comparative table headers, with synthetic comparison-table tests and evaluation
on additional documents. The current code does **not** implement that change,
select the latest year as a shortcut, or contain a Rolls-Royce-specific exception.

The other six abstentions are expected: exact reference dates for CVS and the
Rolls-Royce presentation, and document dates for EDF, Hippodrome, Peterborough
and the Rolls-Royce presentation. Hippodrome's filing stamp remains an excluded
candidate. Its `ambiguous_numeric_date` warning also records uncertain numeric
date mentions elsewhere, without changing the explicitly supported year-end.

### Limits

Reference labels are assistant-authored from inspected parser outputs and the
agreed date policy, pending independent human review. They are not source-PDF
gold labels or a held-out benchmark. The six documents informed the design;
these results do not establish generalization. Embedded titles can be stale,
and all parser text can contain transcription errors. Cover location and regex
context alone cannot resolve every date role or financial reporting period.

Inspect [the evaluation](results/evaluation.json), [the summary](results/summary.csv),
and [the full decisions and evidence](results/metadata.jsonl) before changing rules.
