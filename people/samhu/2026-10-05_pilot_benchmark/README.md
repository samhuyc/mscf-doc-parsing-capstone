# Sponsor pilot evaluation — October 5, 2026

A small, offline evaluation pipeline for the six sponsor PDFs. **The 54 references are assistant-authored preliminary labels, accepted for this exploratory pilot; they are not independently human-verified gold.** Teammate review is optional follow-up. No composite score or overall parser ranking is claimed.

## Open the demo

Clone or pull this repository, then open `review/index.html` in a browser. No Python, server, model, or API key is needed to read the saved reports. GitHub displays HTML source, so open the downloaded/local file rather than its GitHub preview.

- [Wednesday meeting walkthrough](MEETING.md)
- [Review guide](review/index.html)
- [Table parsing](review/tables.html) — correct values under correct rows and headers
- [Number retention](review/numbers.html) — amounts, signs, units and formatting
- [Text and organization](review/text.html) — wording, footnotes and selected order pairs
- [Source gallery](review/labels.html) — original pages beside references, without parser scores
- [Optional review workspace](review/workspace.html) — approve or flag labels for a later revision

The 18 public source-page previews are included (about 4 MB). Full source PDFs remain outside Git; their public URLs and SHA-256 hashes are recorded in `documents.json`. The demo and cached-output evaluation work without downloading those PDFs.

## What is labeled?

| Source | PDF pages | Annotated PDF pages | Table-cell expectations |
|---|---:|---|---:|
| CVS quarterly presentation | 12 | 1, 6, 12 | 10 |
| EDF segmental statement | 6 | 1, 3, 6 | 25 |
| Hippodrome scanned accounts | 39 | 1, 20, 21 | 28 |
| Peterborough scanned accounts | 12 | 1, 2, 3 | 12 |
| Rolls-Royce presentation | 19 | 1, 5, 9 | 26 |
| Rolls-Royce release | 52 | 1, 13, 17 | 32 |

All **140 pages** are inventoried; selected regions on **18 pages** have labels. The 54 records comprise **11 table references / 133 cells**, 8 text spans, 5 footnotes, 7 order pairs, 18 metadata fields and 5 visual facts. Four table references cover complete designated data matrices; the rest cover selected rows. This is a deliberate development sample, not an exhaustive or random sample.

Review counts overlap: table review covers 11 records; number review covers those tables plus 5 visual cards (16); text/organization covers 43 records including those same cards. There are still only 54 unique records. Approving a table means checking the entire displayed reference, not one cell.

## Files and data contract

| File | Purpose |
|---|---|
| `labels.jsonl` | Authoritative, editable reference labels and review states |
| `documents.json`, `pages.jsonl`, `coverage.json` | Source identity, all-page inventory and label coverage |
| `reference_tables/` | Readable HTML derived from table labels |
| `benchmark.py` | Deterministic adapter, scoring, validation and reference refresh |
| `report.py`, `review_workspace.html` | Generate the reports and optional browser review workspace |
| `import_reviews.py` | Validate/import human review decisions with a backup |
| `results/` | Preliminary and reviewed-only summaries plus individual checks |
| `test_benchmark.py`, `test_reviews.py` | Adversarial scorer and review-import checks |
| `author_labels.py` | Initial transcription provenance; refuses to overwrite existing labels |

Each label has an ID, document, 1-based PDF page, source hash, evidence region, kind, importance and review status. Tables store row labels, ordered column-header paths, string-valued expectations and unit/context evidence. Blanks, dashes and zero remain distinct. References are assertions, not a full Markdown transcription.

Inputs are the checked-in `../2026-09-29_sponsor_samples/results/<document>/<parser>/pages.json` files: `parser`, `source_sha256` and `pages` entries with `page` and `markdown`. Optional `run.json` supplies original timing/settings. Markdown may contain native HTML tables. HTML spans preserve merged headers that Markdown pipe tables cannot express.

The adapter is ordinary Python, **not an LLM**. It reads explicit tables, expands row/column spans and matches reference row/header paths. It never uses expected values to choose a table or repair a prediction. It does not infer tables from flat prose or read the source PDF while scoring. Missing predictions and ambiguous matches fail applicable checks.

## Reproduce without rerunning parsers

From this directory, either reuse the original environment:

```sh
PY=../2026-09-29_sponsor_samples/.venv/bin/python
```

Or create a lightweight environment on a fresh clone (Python 3.12 was used):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PY=.venv/bin/python
```

Then run:

```sh
"$PY" benchmark.py validate
"$PY" benchmark.py refresh
"$PY" -m unittest -v
"$PY" benchmark.py score
"$PY" benchmark.py score --include-drafts
"$PY" report.py
```

Scoring takes roughly one second on the development machine. No parser model installation, hosted call or parser rerun is involved. `refresh` updates references and review counts from the checked-in inventory. Optional `prepare --render` instead requires the original PDFs in the earlier experiment's `inputs/`; it checks their hashes and regenerates page previews. If obtaining sources again, use the URLs in `documents.json` and verify the recorded hashes before replacing the reference sources.

Default scoring admits only `human_verified` or `adjudicated` labels and currently selects zero. An empty reviewed-only result is **not** perfect performance. `--include-drafts` explicitly produces the preliminary results used by the meeting reports. Inputs, labels and scorer hashes are recorded; `--output-root PATH` can select another cached output directory using the same contract.

## Interpret the results

The three report pages explain each metric, denominator, example and limitation. Supporting diagnostics are collapsed. Source-level, pooled, equal-document and importance-stratified summaries are also available in JSON; there are no calibrated importance weights.

- **Presence versus association:** a number anywhere on the labeled page can pass presence while failing its row/year association. Repeated facts can share one matching occurrence.
- **Strict matching:** exact normalized row/header text and explicit table relationships are required. An OCR typo or recoverable layout variation can fail a match. Inspect unresolved cells before attributing every failure to a parser.
- **Selected precision/recall:** only four complete numeric matrices are assessed. A 100% precision result can coexist with missing values; it is not document-wide hallucination precision.
- **Not automatically scored:** footnote attachment, visual semantic relationships and independently extracted metadata fields. Text proximity or manifest-supplied metadata would overstate performance.
- **Small scope:** seven order pairs cannot establish full-document order; selected-span character error is not whole-page OCR accuracy. These documents were previously inspected, so this is not a blind generalization test.
- **Configuration:** comparisons use the existing exported pipelines. PyMuPDF4LLM includes layout analysis and automatic local Tesseract OCR (English, 300 DPI), not just native PDF text extraction. Historical timings are not a new controlled speed benchmark.

## Optional teammate review

In `review/workspace.html`, enter your name, compare each reference with the original page, and approve, flag a correction, exclude with a reason, or leave pending. Decisions autosave in the browser where supported. **Export decisions** saves a portable JSON file; a local webpage does not silently edit repository files. Export before closing if browser storage is unavailable.

Validate an export, then apply it when ready:

```sh
"$PY" import_reviews.py /path/to/pilot-review-decisions.json
"$PY" import_reviews.py /path/to/pilot-review-decisions.json --apply
```

Import checks the exact label version, source hashes, reviewer name and timestamp. It backs up labels locally in ignored `review_history/`, then regenerates references, counts, both result sets and reports without PDFs or parser reruns. Correction notes do not automatically change values; flagged labels remain draft. After correcting a reference in `labels.jsonl`, retain/reset its draft state and review it again. Older exports cannot silently overwrite a revised label version. The CSV is only an optional checklist, not an import format.
