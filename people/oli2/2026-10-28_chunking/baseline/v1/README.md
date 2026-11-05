# Source-preserving chunking for downstream retrieval

**This experiment converts existing `pages.json` exports into searchable chunks
with traceable source locations.** It uses saved parser outputs without rerunning
OCR or calling an LLM. MinerU integration is not required.

Start with [the local preview](results/v1/preview.html) and [the findings](REPORT.md).
Download/open the HTML locally; GitHub displays its source rather than running it.
The preview starts on EDF physical page 4: compare the page baseline with the
separate accounting-standards and methodology sections. Click a chunk's page
button to highlight its exact source Markdown slice. Page 3 shows an intact
financial table; page 6 shows an explicit link to adjacent reconciliation notes.

## Where this fits

```text
PDF -> existing PyMuPDF4LLM + Tesseract exports -> this chunker -> retrieval -> LLM
                    saved pages.json                ^
previous Hybrid metadata predictions ---------------+ (optional, hash checked)
```

MinerU is another upstream document parser, not a prerequisite for this module.
PyMuPDF is the PDF processing library; PyMuPDF4LLM organizes its extracted text
and tables into Markdown. The existing `page_chunks=True` export is a page-level
representation, which becomes our baseline. Section chunking is a later step.
This v1 deliberately accepts only the saved `pymupdf4llm` pipeline. A later
adapter can reuse the contract for MinerU without mixing parser changes with
chunking changes in the same experiment.

Chunking defines the unit searched and supplied to a downstream model. Source
spans provide provenance; neither guarantees the original PDF was recognized
correctly. Smaller chunks may improve focus but can lose needed context.

## Frozen inputs

The six documents / 140 pages come from:

`people/samhu/2026-09-29_sponsor_samples/results/<document>/pymupdf4llm/`

- `pages.json`: primary content; physical page numbers and unchanged Markdown.
- `metadata.json`: source identity, embedded outline and generated heading index.
- `run.json`: successful status, parser identity, original page count and versions.

The implementation reads headings from page Markdown to recover exact offsets;
it does not trust an embedded outline as a complete semantic hierarchy. Existing
`source_outline` entries remain available in `documents.json` for inspection.

By default, issuer, document type and reporting dates/periods come from
`../2026-10-06_metadata_rule_llm/results/predictions/pymupdf4llm/hybrid.jsonl`.
Each record must match document ID, parser, source hash and normalized input-page
hash. Values, methods and unresolved/ambiguous statuses are carried forward;
complete original decisions and evidence are retained once in `documents.json`.
These are provisional extractor outputs, not independently verified truth.
Use `--without-metadata` to run the chunker without this dependency.

No source PDF or dataset is downloaded. PDF identity is inherited from the saved
exports, not independently reverified against PDF bytes. Old exports, notebooks,
baseline rules and labels are not modified.

## Run

Python 3.10+; tested on Windows / Python 3.13.7. The only runtime package is
`markdown-it-py==4.0.0`; no OCR package, API key, GPU or vector database is needed.
From this experiment folder:

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B run.py --output results/reproduce
python -B evaluate.py --results results/reproduce --output results/reproduce/retrieval.json
```

Output paths must be new. This preserves previous runs rather than overwriting
them. A first-document trial is:

```powershell
python -B run.py --documents edf_2024 --without-metadata --output artifacts/edf-trial
```

Use `--max-chars 3000` for a separate size experiment. This is a **soft raw-Markdown
Unicode character budget**, not an embedding model's token limit. Full tables,
long lists, code and paragraphs remain atomic even if they exceed it. Actual model
token limits must be checked before a future embedding/generation integration.

## Rules in v1

1. Parse Markdown block boundaries while preserving every original character,
   including whitespace, repeated page furniture and image references.
2. Treat complete HTML/Markdown tables as atomic. Unclosed HTML tables fail
   explicitly rather than being silently repaired. Fenced code is not a heading.
3. Treat Markdown headings as candidate section boundaries. Suppress boundaries
   for numeric displays, period-only headings and repeated corporate headings.
   Suppressed text is retained; decisions are exported for review.
4. Use heading levels as a heuristic hierarchy. Repeated/continued headings can
   continue the same section across pages. Several sections can share one page.
5. Pack adjacent blocks within the same candidate section until the soft budget
   would be exceeded. Do not strand a heading merely to meet the budget.
6. For a table chunk, attach bounded adjacent text when it lies outside the
   primary chunk. A following same-page `Notes`/`Source`/`Unit`/`Basis` heading
   and nearby text can be linked across a section boundary. These are explicit
   `context_spans`, **not verified semantic footnote attachments**.

Primary source spans have no overlap. Additional context and inherited headings
are deliberately separate, so exact coverage can be checked without pretending
context repetition is new document content. No financial number is corrected,
summarized, inferred, or reformatted in `content`.

## Output contract

- `page_chunks.jsonl`: one baseline record per physical page.
- `section_chunks.jsonl`: section/block-size strategy records.
- `documents.json`: source identity, input hashes, parser versions, complete
  inherited metadata decisions and evidence; original page files remain the source.
- `heading_decisions.json`: every heading candidate, location and accepted/suppressed reason.
- `summary.json`: exact coverage, table integrity, chunk sizes and limitations.
- `manifest.json`: code, input and metadata hashes, dependency version and parameters.
- `preview.html`: offline source/chunk comparison with escaped/sanitized rendering.
- `retrieval.json`: separate optional BM25 development-probe results.

Each chunk has `chunk_id`, `strategy`, `content`, `section_path`,
`source_spans`, `heading_evidence`, `context_spans`, `document_metadata`,
`retrieval_text`, source hashes and parser identity. IDs are deterministic for a
fixed version, configuration, inputs and metadata record. Changed versions or
inputs intentionally produce different IDs.

`source_spans` address the **decoded original page Markdown**, not the PDF's
internal bytes or image coordinates. `page` is 1-based physical PDF numbering;
`start`/`end` are half-open Unicode code-point offsets. `json_pointer` points to
`/pages/<zero-based-index>/markdown` in `source_artifact`. It is not a printed
report page number. JavaScript consumers must account for UTF-16 when applying
these offsets to non-BMP text; the provided preview does so explicitly.

`content` is the exact concatenation of the source slices, in order. Image paths
remain relative to the original export folder recorded in `source_artifact`.
`retrieval_text` is a derived search view: resolved document metadata, inherited
heading path, visible primary text and linked context. Use it for indexing; use
the structured source spans and original `content` when assembling cited answers.
Document reporting-period metadata does not replace comparison-year table headers.

## Evaluation and next work

Unit/integration tests check Unicode offsets, multiple and continued sections,
table preservation, stale metadata, missing/duplicated/changed text, and unsafe
preview content. The complete six-document outputs pass lossless coverage checks.

`probes.json` contains eight assistant-authored **development** questions with
exact evidence locations in saved parser outputs. `evaluate.py` runs BM25 inside
the specified document, uses the same top-3 rule for both strategies, and reports
evidence hit@1, hit@3 and retrieved-text size. Probes are loaded only by evaluation,
never by the chunker. This does not measure cross-document retrieval, Chinese
queries, original-PDF factual accuracy or final RAG answers. Alternative valid
evidence may exist outside the labeled span. The small sample is not held out.

Optional browser QA, with an existing Playwright/Chromium installation:

```powershell
python -B tests/check_preview.py results/v1/preview.html
```

Next, manually review the 33 very small chunks and selected long-document heading
paths, then label fresh evidence questions. Test retrieval with model-token budgets
and a fixed embedding/retrieval configuration before claiming RAG improvement.
Cross-page table stitching and semantic footnote association remain future work.
