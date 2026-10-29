# Chunking deliverable — October 28, 2026

**Implemented and validated post-parsing chunking for the six saved sponsor
samples, plus an offline retrieval and cited-context handoff for downstream RAG.**
The pipeline preserves source text, measures actual tokenizer sizes, records
exceptions, and keeps the original page strategy for comparison.

Open the [source/chunk preview](results/final/preview.html) locally. Reproduction
commands are in [README.md](README.md); integration details are in
[HANDOFF.md](HANDOFF.md).

## Delivered corpus

- **6 documents, 140 physical PDF pages**.
- **333 section chunks**, of which **330 are indexable**; 140 page-baseline chunks.
- All **398,559 source Markdown characters** occur exactly once in primary spans,
  in source order, under both strategies.
- All **117 exported table blocks** remain intact. Multiple tables can share a
  chunk; this count describes table blocks, not table-containing chunks.
- **18 section chunks** exceed the 1,024-token target to keep tables whole.
  The largest context is **2,017 tokens**. Every exception is explicitly flagged.
- **2 chunks** have fewer than 100 raw Markdown characters: a meaningful 81-character
  Rolls-Royce footnote and a six-character Hippodrome OCR fragment. The latter is
  retained for source coverage but excluded from retrieval.

Page/section counts by document: EDF **6/11**; Rolls-Royce release **52/148**;
Hippodrome **39/104**; CVS **12/14**; Peterborough **12/30**; Rolls-Royce presentation
**19/26**. Three low-information image/OCR passages are preserved but excluded
from the section search index. A document-title-only chunk remains indexable.

The target is measured with `cl100k_base` and includes inherited metadata and
section context. The page baseline is intentionally not resized.
Full metrics: [summary.json](results/final/summary.json).

## Boundary audit and changes from v1

The initial v1 produced 360 sections using a soft 4,000-character budget. Its
33 sub-100-character chunks were inspected through source text and mapped to
their final locations. **32 now belong to larger passages**; one remains a
low-information cover fragment. This structural audit is not independent human
semantic annotation. See [boundary_audit.json](results/final/boundary_audit.json).

The final rules keep parent/child headings with following content, attach short
page footers, handle continued headings at page boundaries, and use token counts
instead of character count as a proxy. Long prose and lists can split; complete
tables remain atomic. The small remaining Rolls-Royce footnote is retained
separately because merging it with the neighboring table would exceed the target.

Peterborough exposed a specific parser inconsistency: some "Notes to the
Financial Statements" titles were plain paragraphs, while others were headings.
The initial hierarchy consequently placed notes under the balance sheet. The
final implementation recovers conservative standalone report titles and uses
numbered-note depth to stabilize that hierarchy. All promotions, original labels
and normalized levels are exported in
[heading_decisions.json](results/final/heading_decisions.json).

The hierarchy is still imperfect. For example, an unnumbered "Employees" title
in Peterborough inherits the preceding numbered policy context. Source text is
unchanged and source spans remain authoritative; `section_path` is a navigation
and retrieval aid, not validated accounting taxonomy.

## Retrieval comparison

The evaluation contains **32 assistant-authored English development questions**:
the original eight and 24 additional questions, four per document. References
are exact spans in saved parser text, including headers/units where designated.
They are loaded only for evaluation, never supplied to the chunker or ranker.
One duplicated finance-total quote was extended with adjacent row text to identify
a unique occurrence before scoring. References are saved with hashes.

Both strategies use the same BM25 parameters and a fixed top-three candidate pool.
Whole passages are packed into a **3,072-token** prompt, including instructions,
question and citation wrappers. Oversized passages are skipped explicitly;
tables are never truncated and lower-ranked candidates do not replace skips.

When the document is already known:

- Page baseline: first-result evidence **24/32**; top-three evidence **29/32**;
  evidence retained within the prompt budget **29/32**.
- Section chunks: first-result evidence **23/32**; top-three evidence **30/32**;
  evidence retained within the prompt budget **30/32**.
- Mean prompt size: **1,987.1 tokens** for pages and **1,505.3** for sections,
  about **24% lower** for sections.

When searching all six documents:

- Page baseline: first-result evidence **24/32**; top-three evidence **31/32**;
  evidence retained within the prompt budget **31/32**.
- Section chunks: first-result evidence **22/32**; top-three evidence **28/32**;
  evidence retained within the prompt budget **28/32**.
- Mean prompt size: **2,016.9 tokens** for pages and **1,538.7** for sections,
  about **24% lower** for sections.

**Sections reduce prompt size here, but do not establish an overall retrieval
improvement.** Corpus-wide retrieval loses designated evidence for some cash-flow
and balance-sheet queries. Both strategies miss the designated statutory
operating-profit evidence in one query. No source loss was observed: these are
ranking/reference-coverage misses. Other valid answer locations may be unlabeled.

Document filtering changes the BM25 candidate set and document frequencies, so
within-document and corpus-wide ranks can differ. The original eight questions
are also reported separately; within-document top-three hits are 7/8 for both
final strategies. Full trial records: [retrieval.json](results/final/retrieval.json).

These six previously inspected documents and development references are **not a
held-out benchmark**. Results measure designated evidence coverage, not generated
answer accuracy, independently verified PDF facts, latency or API cost. No
embedding model, reranker or LLM has been evaluated.

## Validation and handoff

**36 unit/integration tests pass**, including Unicode offsets, lost/duplicate text,
all six real inputs, stale metadata, nested/oversized tables, long prose/lists,
recovered/continued headings, token limits, index tampering, document-aware
evidence checks, deterministic IDs and safe preview rendering.

Headless Chromium verifies the six-document selector, strategy toggles, table
spans, keyword filtering, source highlighting, Unicode positions and desktop/mobile
layout. No external requests or JavaScript errors occur. A repeat build verifies
deterministic data artifacts. [validation.json](results/final/validation.json)
records the delivered checks; [manifest.json](results/final/manifest.json) identifies
the exact code, dependencies, source exports and development references.

`retrieval.py` already produces a cited, token-bounded context using either strategy.
The [EDF example](results/final/rag_example.txt) is ready for a downstream model;
the companion JSON retains the exact chunks and citations. The chunking task and
its retrieval handoff are complete. Connecting the team's chosen embedding/model
stack and evaluating generated answers are the next RAG stage.

No source parser outputs or prior metadata results were changed. Remaining limits
are parser/OCR errors, heuristic headings and note links, separate cross-page
table fragments, and a tokenizer-specific budget. Retain the page baseline and
use fresh independently annotated questions before selecting the final retrieval
strategy or claiming quality gains.
