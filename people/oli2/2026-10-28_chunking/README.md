# Source-preserving chunking for RAG

**Convert the project's saved PyMuPDF4LLM outputs into section chunks with exact
source references, measured token sizes, and a working retrieval/context interface.**
All six sponsor samples have been processed. No OCR rerun, API key, GPU, embedding
service or LLM call is required.

Start with the [interactive comparison](results/final/preview.html),
[results report](REPORT.md), and [RAG handoff](HANDOFF.md).
Open the HTML locally; GitHub displays its source. EDF page 4 demonstrates two
topics on one page, page 3 an intact table, and page 6 linked reconciliation notes.
Click a source reference to highlight its exact original Markdown slice.

## Where this fits

```text
PDF -> existing PyMuPDF4LLM + Tesseract exports -> section chunking
                                                    |
         prior extracted document metadata ---------+  (optional, hash checked)
                                                    v
                                     BM25 or future vector retrieval
                                                    |
                                    cited, token-bounded context -> LLM
```

MinerU is another upstream document parser. PyMuPDF is a PDF processing library;
the saved PyMuPDF4LLM export already provides page Markdown and tables. A
page-level export is useful input and a retrieval baseline, but it does not
replace this section-aware retrieval step. This implementation does **not** split
PDF files before OCR. It takes the existing successful parser output as input.

Chunking chooses the passages that retrieval can find and send to a model. A
focused passage can reduce irrelevant context and prompt size. Source references
make passages traceable; provenance is one benefit, not the only reason to chunk.
Smaller chunks can also separate useful evidence, so both page and section
strategies are retained and compared.

## Inputs and dependencies

Input directory, relative to the repository root:

`people/samhu/2026-09-29_sponsor_samples/results/<document>/pymupdf4llm/`

- `pages.json`: unchanged page Markdown and physical PDF page numbers.
- `metadata.json`: source identity and existing outline.
- `run.json`: successful parser status, page counts and parser versions.

Issuer/type/period predictions optionally come from
`people/oli2/2026-10-06_metadata_rule_llm/results/predictions/pymupdf4llm/hybrid.jsonl`.
The join checks document ID, parser, source hash and LF-normalized page-file hash.
Unresolved fields remain unresolved. Full inherited decisions and evidence are
retained in `documents.json`; these predictions are not independently verified
facts. Use `--without-metadata` to omit this dependency.

Python 3.10+; tested with Python 3.13.7 on Windows. Runtime packages are pinned in
`requirements.txt`: `markdown-it-py==4.0.0` and `tiktoken==0.12.0`. The first use of
`cl100k_base` may download its tokenizer encoding; subsequent uses are cached.
Document content is processed locally. Source PDFs are not downloaded or rerun.

## Reproduce the complete run

From this experiment directory in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -B -m unittest discover -s tests -v
.venv/Scripts/python.exe -B complete.py --output results/reproduce
```

Use a fresh output directory. `complete.py` loads all six saved exports, validates
source integrity, creates both chunk strategies, runs the 32 development queries,
and writes the preview, index, cited example and provenance manifest. Optional
settings are `--max-tokens 1024`, `--context-budget 3072`, and `--without-metadata`.
`run.py` / `evaluate.py` retain the earlier character-budget v1 experiment;
**use `complete.py` for the final implementation**.

For an existing index:

```powershell
.venv/Scripts/python.exe -B retrieval.py --results results/final --document edf_2024 --question "Which accounting standard was used to prepare EDF financial statements?" --output artifacts/edf-answer-context.json
```

Omit `--document` for corpus-wide retrieval. The command writes evidence and a
ready-to-use prompt, not a generated answer. See [HANDOFF.md](HANDOFF.md) for the
Python interface and integration contract.

## Chunking rules

1. Parse source Markdown into blocks with exact Unicode offsets. Keep tables and
   fenced code intact. Malformed/unclosed HTML tables fail visibly.
2. Normalize candidate section labels while retaining original headings. Repeated
   company names, dates, numeric displays and registration details do not create
   independent semantic sections. Recover conservative standalone report titles
   exported as prose and repeated numbered titles exported as lists.
3. Use report-title rules and numbered notes to stabilize the heading hierarchy.
   Keep headings with their following body. A repeated title on a new page stays
   with that page's body; other sections may continue across pages.
4. Pack blocks within a section toward **1,024 `cl100k_base` tokens**, including
   inherited metadata and heading context. Split long prose/lists at sentence or
   whitespace boundaries without decoding tokens back into altered source text.
5. Preserve complete tables even when they exceed that target; flag every
   exception. Keep tiny page footers with neighboring content where possible.
6. Attach bounded adjacent source text to table chunks when it fits. A nearby
   Notes/Source/Units/Basis heading may bring following text with it. These are
   explicit adjacency links, not verified semantic footnote relationships.

Primary `source_spans` do not overlap. Headings and additional `context_spans`
are separate, so repeated context does not invalidate lossless primary coverage.
No financial number is rewritten, corrected or summarized in `content`.

## Outputs

- `section_chunks.jsonl`: final chunks; `page_chunks.jsonl`: unchanged-page baseline.
- `index.json`: strategy paths and hashes, checked by the retrieval loader.
- `documents.json`: input identity, original outline and inherited metadata evidence.
- `heading_decisions.json`: original/normalized labels, locations and reasons.
- `boundary_audit.json`: dispositions of the v1 small chunks and remaining small chunks.
- `summary.json`: source coverage, table integrity, sizes and token exceptions.
- `retrieval.json`: all 32 development references, 128 strategy/scope trials and aggregates.
- `rag_example.json` / `.txt`: EDF example with selected evidence and a cited prompt.
- `manifest.json`: code, test, requirement, probe and input hashes plus run parameters.
- `preview.html`: offline source/chunk comparison, with sanitized rendering.
- `validation.json`: checks recorded for the delivered final run.

`results/v1/` preserves the initial experiment. `baseline/v1/` is its read-only
source/document snapshot for inspection; its old relative paths are not an
independent entry point. Ignored `artifacts/` contains local QA runs/screenshots.

## Verification and limits

The delivered run passes 36 unit/integration tests, exact source/table validation,
repeat-build checks and headless Chromium preview checks. Optional browser QA
requires Playwright and a Chromium browser installation:

```powershell
python -B tests/check_preview.py results/final/preview.html
```

The tokenizer budget applies to `cl100k_base`, not every model. Re-tokenize before
connecting a different embedding/generation model. The context builder's 3,072
token limit includes its instructions, question, citations and complete passages;
it excludes any extra caller messages and generation allowance.

Heading hierarchy is heuristic, cross-page tables are not stitched, and image
content is not re-recognized. Exact preservation is relative to saved parser text,
not original-PDF accuracy. The benchmark is English lexical retrieval on six
development documents; it does not establish final RAG accuracy or generalization.
Read the [report](REPORT.md) before choosing a production retrieval strategy.
