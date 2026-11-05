# Chunking deliverable — October 28

Completed post-parsing chunking over the saved PyMuPDF4LLM + Tesseract exports,
with a working offline retrieval/context interface for downstream RAG.
Prior metadata predictions are optionally attached after source/parser/page-hash
checks; unresolved fields and original evidence remain available.

- Six documents / 140 pages: **333 section chunks**, 330 indexable, and a retained
  **140-chunk page baseline**.
- All **398,559 source Markdown characters** and **117 exported table blocks**
  are preserved. Of 33 small v1 chunks, 32 now belong to larger passages.
- Actual `cl100k_base` counts replace the character proxy: 1,024-token target;
  18 explicit full-table exceptions, maximum 2,017 tokens. The context builder
  enforces a separate 3,072-token prompt limit without truncating tables.
- **36 tests**, repeat-build validation and desktop/mobile browser checks pass.
  English preview, report, code, command examples and RAG handoff are included.
- Across 32 development questions, within-document top-three evidence coverage
  is **29/32 for pages vs 30/32 for sections**. Corpus-wide it is **31/32 vs 28/32**.
  Section prompts use about 24% fewer tokens; overall retrieval improvement is
  not established. These are saved-text evidence checks, not held-out PDF gold
  or generated-answer accuracy.
- Next RAG stage: connect the selected retriever/model, retain both baselines,
  and evaluate fresh independently annotated questions and generated citations.

[Methods and commands](../../people/oli2/2026-10-28_chunking/README.md) ·
[Findings](../../people/oli2/2026-10-28_chunking/REPORT.md) ·
[RAG handoff](../../people/oli2/2026-10-28_chunking/HANDOFF.md) ·
[Preview — open locally](../../people/oli2/2026-10-28_chunking/results/final/preview.html)
