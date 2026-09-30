# O6: Document metadata extraction

An initial deterministic experiment on six sponsor documents. It extracts document
type and semantic dates from existing page exports, retaining exact evidence and
abstaining when rules cannot resolve a value. No PDF downloads, OCR, model calls,
or external APIs are needed. All inputs under Sam's folder remain read-only.

Current ruleset: **1.1.0**. The [first-run baseline](baseline/1.0.0/results/evaluation.json)
is archived with exact-byte integrity hashes. Its original `results/` files and
the first-run report below remain unchanged. See the final section for the narrow
1.1.0 change and the two changed decisions.

On the six-document prototype set, ruleset 1.1.0 matched all of our provisional
reference labels while abstaining on fields that were not explicitly supported.
These are development-set findings, not held-out benchmark accuracy. The next
step is evaluation on a larger independently labeled corpus.

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
python -B extract.py --output results/reproduce-1.1.0
python -B evaluate.py --predictions results/reproduce-1.1.0/metadata.jsonl --output results/reproduce-1.1.0/evaluation.json
python -B compare.py --after results/reproduce-1.1.0/metadata.jsonl --output results/reproduce-1.1.0/comparison.json
```

The evaluation dependency is `jsonschema`; extraction uses only the standard
library. Commands work from other directories when the script path is supplied.
Default input and output locations are relative to the scripts, not the shell.

`extract.py` validates all six inputs before writing results. It fails explicitly
on missing, changed, incomplete, or inconsistent exports. It never silently
skips a document or chooses another parser. Current commands write to
`results/1.1.0/` and refuse to overwrite existing outputs. To repeat a run, supply
a fresh directory with `extract.py --output`, then explicitly supply the matching
`evaluate.py --predictions` and `--output` paths. Archives under `baseline/` are
read-only to these commands. No command commits changes.

The commands above use a fresh directory because the committed `results/1.1.0/`
already contains the frozen review run. Choose another fresh directory for
subsequent runs. This folder's `.gitattributes` disables Git newline conversion
so archived hashes and frozen artifacts survive checkout with their exact bytes.

## Files and data flow

```text
input_manifest.json -> inputs.py -> rules.py -> extract.py -> results/1.1.0/metadata.jsonl
                                                          -> results/1.1.0/summary.csv
reference_labels.json -----------------------> evaluate.py -> results/1.1.0/evaluation.json
metadata.schema.json ------------------------> evaluate.py
```

- `inputs.py`: pins four export hashes, validates source identity, successful run
  status, page counts, physical page order, and reconstructed document text.
- `rules.py`: document-type patterns, period/date candidates, priority rules,
  evidence collection, and explicit abstention.
- `extract.py`: sequential CLI runner, provenance, timing, JSONL and CSV outputs.
- `evaluate.py`: evaluation-only reference labels, JSON Schema validation,
  quotation/page verification, metrics, mistakes, and abstentions.
- `tests/test_extraction.py`: the original 26 tests plus six adversarial period
  tests and two baseline-preservation tests; 34 total.
- `compare.py`: compares field values, statuses and roles, emitting changed
  decisions only. It verifies baseline integrity before writing its report.

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
are ordering rules, not confidence probabilities. The current rules use:

- Explicit cover type phrases (priorities 80-100); embedded PDF title phrases
  receive 20 less. An earnings-call cover plus "this presentation" on either of
  the first two pages supports `earnings_presentation` at priority 100.
- Cover period labels receive priority 120 in headings, 100 in narrative, and 20
  in tables. Cover reporting-end phrases retain priority 100; reporting-end
  phrases on later pages receive 50. Explicit H1/H2 text can
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

The next section is the preserved historical 1.0.0 record. References to its
"current code" describe that frozen first run; the 1.1.0 improvement follows it.

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

## Ruleset 1.1.0: period evidence ranked by source structure

### Baseline preservation

`baseline/1.0.0/` contains exact copies of all 13 original files: source code,
tests, schema, manifest, provisional labels, README, dependencies and the three
first-run outputs. `integrity.json` pins their raw SHA-256 hashes. These source
copies are a historical snapshot for inspection, not a second installation.
The original three files directly under `results/` also retain their exact bytes,
including recorded runtimes. Baseline tests and the comparison command verify
both sets of output files. The first-run results section above remains the
historical 1.0.0 report.

Current output locations:

```text
baseline/1.0.0/             # Frozen code, documentation, inputs and results
results/metadata.jsonl     # Original 1.0.0 output, retained unchanged
results/summary.csv        # Original 1.0.0 summary, retained unchanged
results/evaluation.json    # Original 1.0.0 evaluation, retained unchanged
results/1.1.0/
  metadata.jsonl
  summary.csv
  evaluation.json
  comparison.json
```

### Narrow rule change

Only the ranking of cover period-label candidates changes. The existing character
map recovers each match's original Markdown/HTML location. Candidate `rule_id`
and `priority` expose its structural source:

| Evidence source | Rule ID | Priority |
|---|---|---:|
| Cover heading/title formatting | `cover_heading_period` | 120 |
| Cover narrative | `cover_narrative_period` | 100 |
| HTML table header or first row | `cover_table_header_period` | 20 |
| Other HTML table content | `cover_table_period` | 20 |

Heading formatting means Markdown `#` headings, HTML `h1`-`h6`, or a standalone
fully bold line. Table containment is checked first, so bold text within a table
cell never receives heading priority. The standardized inputs use HTML tables.
No new document-type, date-parsing, fiscal-calendar or document-date rule was added.
The period-label search remains cover-only. Existing explicit reporting-end
candidates retain their original priorities.

When the authoritative title states a half-year and a year, existing same-year
H1/H2 evidence can supply the half number. Table candidates remain in the output
at lower priority. If only comparative table labels are available, equal-priority
conflicts still yield `ambiguous`; conflicting authoritative headings also remain
ambiguous. Ranking never compares numeric year values to choose a maximum.

`reference_date` is unchanged: once the period resolves, its existing scope check
excludes reporting-end candidates with an incompatible year or period kind using
`different_reporting_period`. This now excludes comparative 2025 dates for the
release while retaining their evidence.

### Tests before implementation

Six synthetic period tests were added while the ruleset was still 1.0.0. They
cover the four requested cases, heading/narrative/table precedence, and conflicting
authoritative headings. Four test methods failed initially (six failed assertions
including title-format subtests), while the table-only and conflicting-heading
ambiguity cases passed. After the change, all six passed, along with all 26
original tests and two additional baseline-preservation checks: **34/34 passed**.

The future-year fixture uses a 2025 title and a 2029 table forecast. It resolves
2025, demonstrating that the rule follows title authority rather than the largest
year. Other fixtures check Markdown, HTML and fully bold headings, including bold
comparative table headers.

### Changed decisions only

The [machine-readable comparison](results/1.1.0/comparison.json) compares semantic
field values, statuses and roles across all six documents. It omits routine
changes in rule IDs, candidate rankings, provenance and timing.

| Document | Field | 1.0.0 | 1.1.0 |
|---|---|---|---|
| rolls_royce_2026h1_release | reference_period | null / ambiguous | 2026 H1 / resolved |
| rolls_royce_2026h1_release | reference_date | null / ambiguous | 2026-06-30 / resolved |

The other 22 field decisions are unchanged. The release's derived document-level
status consequently becomes `resolved`, and its two ambiguity warnings disappear.
The six expected abstentions remain.

All four field metrics are now 6/6 exact matches against the unchanged provisional
labels, including expected nulls. Coverage is 18/24 (75%); abstentions are 6/24
(25%). All six records pass schema validation and all 473 evidence spans validate.
The 1.1.0 run took 0.2604 seconds in total; one run does not establish a speed
improvement. See [the new evaluation](results/1.1.0/evaluation.json).

This addresses one diagnosed structural-ranking error. It is not an independent
generalization result: source selection and provisional labels remain the same
small case study. Fully bold lines and parser-produced headings are structural
heuristics, not verified semantic titles. Unmarked titles retain narrative rank,
and malformed or nonstandard table markup may not be recognized by this MVP.
