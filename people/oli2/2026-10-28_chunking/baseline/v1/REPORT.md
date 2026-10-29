# Chunking v1 — October 28, 2026

**Implemented page-baseline and section chunking over existing PyMuPDF4LLM
outputs, preserving original page numbers and text offsets for every chunk.**
Open [the comparison](results/v1/preview.html) locally. Start with EDF page 4,
then page 3 for a financial table and page 6 for reconciliation notes.

## Scope and outcome

Six saved PyMuPDF4LLM + Tesseract document exports, 140 physical PDF pages.
No OCR/parser reruns, source-PDF downloads, embedding calls or LLM calls.
The previous Hybrid metadata decisions are joined by matching source/parser and
input-page hashes; unresolved fields remain unresolved.

- Page baseline: **140 chunks**.
- Section / block-size strategy: **360 chunks**.
- Both strategies preserve all **398,559 source Markdown characters** exactly
  once in primary content, in physical page order.
- All **117 exported table blocks** remain intact. This is preservation of
  existing parser structure, not proof that all source-PDF tables were extracted.
- **6 section chunks** exceed the 4,000-character soft budget; the largest is
  5,448 characters. Full tables, lists and heading/content groups are retained.
- **33 section chunks** contain fewer than 100 raw Markdown characters and
  should be reviewed for over-fragmentation before production retrieval.

Per-document page/section counts: EDF 6/10; Rolls-Royce release 52/154;
Hippodrome 39/111; CVS 12/15; Peterborough 12/41; Rolls-Royce presentation 19/29.
More chunks are not automatically better. The page baseline has 43 chunks over
the same size threshold; it is deliberately not resized.

Machine-readable sizes and integrity checks: [summary.json](results/v1/summary.json).

## What the source evidence shows

EDF physical page 4 contains accounting standards followed by definitions and
methodology. Section chunking separates those topics; the latter section
continues onto page 5 before the hedging-policy heading. Its source spans retain
both pages, so logical sections need not equal PDF pages.

EDF page 6 has a reconciliation table and a separate notes heading. The table
chunk links to nearby note text through `context_spans`; the notes also remain in
their own primary section. These links record adjacency, not verified semantic
footnote relationships.

Repeated corporate headings, period headings and numeric displays are retained
as content but do not necessarily create section boundaries. Heading levels are
still parser-dependent heuristics. No validated semantic document hierarchy is
claimed. [All candidate decisions](results/v1/heading_decisions.json) are inspectable.

## Initial retrieval diagnostic

Eight assistant-authored English development questions use exact source spans
from the saved parser text. The same BM25 configuration searches within the
specified document, separately for each chunking strategy. No expected values or
labels are read during chunk generation or ranking.

- **First-result evidence hit:** page 5/8; section 6/8.
- **Top-three evidence hit:** page 7/8; section 6/8.
- **Mean text size in the first three results:** page 6,232.6 characters;
  section 4,606.8 characters, including the derived search context.

The section strategy returns less text on average in this pilot, but misses more
designated evidence spans in the top three. **These results do not establish an
overall retrieval improvement.** The sample is small, selected during development,
and not independently verified against original PDFs. It is not a held-out RAG
benchmark or a final-answer accuracy measurement. Alternative valid evidence
elsewhere in the document is not annotated.

Specific cases are retained without tuning to make the results look better:

- CVS revenue: the section strategy retrieves the labeled table first; the page
  baseline's first three results miss the designated page-6 table.
- Rolls-Royce free cash flow: the page strategy includes the designated page-1
  evidence among its first three; section retrieval returns other cash-flow
  passages on pages 6, 44 and 47 instead.
- Peterborough assets: the page strategy includes the designated balance-sheet
  evidence on page 2; section retrieval favors related notes on other pages.

The latter cases require inspecting retrieval ranking and alternative evidence,
not assuming the chunker lost the original text. Exact coverage already passes.
Full records: [retrieval.json](results/v1/retrieval.json).

## Verification and practical limits

18 unit/integration tests cover original-text integrity on all six inputs,
Unicode offsets, stale metadata, missing pages, code fences, nested/oversized
tables, repeated headings, notes context, deterministic IDs, and safe HTML export.
Headless Chromium checks the six-document selector, strategy toggles, table spans,
keyword filtering, source highlighting, Unicode positions, desktop/mobile layout,
and absence of external requests or JavaScript errors.

This is a usable first chunking experiment, not a finished RAG system. It does
not join cross-page tables, interpret images, validate the parser's financial
facts, establish true title hierarchy, or enforce a particular model's token
limit. Next, review boundaries and over-fragmentation, label fresh questions,
then evaluate with a fixed embedding/retrieval configuration and token budget.
