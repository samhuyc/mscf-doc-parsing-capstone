# RAG integration handoff

The ready-to-use dataset is `results/final/section_chunks.jsonl`. The independent
page baseline is `results/final/page_chunks.jsonl`. `index.json` records both paths
and hashes. **Use `retrieval_text` for search and `context_text` for model context;
retain source spans and the original `content` for citations and auditing.**

## Input contract

The current adapter reads the saved PyMuPDF4LLM `pages.json`, `metadata.json` and
`run.json` files together. It requires schema version 1, successful matching
document/parser identities, matching source hashes and contiguous 1-based pages.
`load_document` optionally joins prior metadata after checking input hashes.

To chunk another compatible saved export without running the development benchmark:

```python
from pathlib import Path
from run import load_document, write_jsonl
from structure import chunk_document

document = load_document(Path("path/to/pymupdf4llm"))
page_chunks, section_chunks, heading_decisions = chunk_document(document, max_tokens=1024)
write_jsonl(Path("new_section_chunks.jsonl"), section_chunks)
```

This low-level writer does not create the corpus index or protect an existing
output path. `complete.py` is the reproducible, no-overwrite entry point for the
six-document deliverable. MinerU would need a separate adapter that provides the
same validated page identity and text contract; its output is not interchangeable
without that adapter and validation.

## Chunk fields

- `chunk_id`, `document_id`, `strategy`, `chunker_version`: stable record identity
  for fixed inputs, metadata, configuration and implementation version.
- `content`: exact concatenation of primary source slices, in original order.
- `source_artifact`, `source_sha256`, `pages_sha256`, `parser`: input identity.
  PDF hashes are inherited from exports, not reverified against downloaded PDF bytes.
- `source_spans`: primary locations; `context_spans`: extra linked source text;
  `heading_evidence`: locations supporting the inherited heading path.
- `section_path`: heuristic normalized labels. Prefer physical source references
  over these labels when a distinction matters.
- `document_metadata`: inherited values/status/method; complete evidence is stored
  once in `documents.json`. Do not treat inferred periods as all table column years.
- `retrieval_text`: metadata + section path + visible primary/adjacent text.
- `context_text`: metadata + section path + unchanged primary Markdown + linked
  context. It preserves table markup and is what the prompt builder budgets.
- `content_tokens`, `retrieval_tokens`, `context_tokens`, `tokenizer`, `max_tokens`:
  separate counts and the per-chunk target.
- `indexable`, `element_types`, `flags`: search eligibility and explicit exceptions.

Each source location uses a 1-based **physical PDF page**, a `json_pointer` such as
`/pages/3/markdown`, and half-open `[start, end)` Unicode code-point offsets into
that decoded page Markdown. These are not printed page labels, PDF coordinates,
UTF-8 byte offsets or JavaScript UTF-16 offsets. The preview uses code-point slicing.
Image references remain relative to the original export folder.

Primary spans provide exact coverage with no overlap. Adjacent context may repeat
text whose primary home is another chunk. Do not count that repetition as additional
document content. Never silently drop `over_token_budget` table chunks at ingestion:
retain them and choose an explicit model limit or table-specific strategy.

## Retrieve and construct context

```python
from retrieval import query

result = query(
    "results/final",
    "Which accounting standard was used to prepare EDF financial statements?",
    document_id="edf_2024",  # use None for all documents
    strategy="section",   # also supports "page"
    budget=3072,
    top_k=3,
)
prompt = result["prompt"]
citations = {item["citation"]: item["chunk"] for item in result["selected"]}
```

The loader verifies the index hash before retrieval. `selected` maps `[S1]`, `[S2]`,
etc. to full chunk records and source references. `skipped` explains passages that
do not fit. If nothing fits or matches, `status` is `no_evidence_within_budget`;
do not invent an answer. `evidence_found` means passages were selected, not that
they necessarily answer the question.

The returned prompt treats source passages as data and asks the model to cite
evidence and abstain when unsupported. The caller must check answer support and
citation validity. The 3,072-token limit covers this prompt only, using
`cl100k_base`; budget additional chat/system messages and generated output separately.

For vector retrieval, index eligible chunks' `retrieval_text` and keep the complete
records keyed by `chunk_id`. Validate the embedding model's input limit, especially
for flagged tables. Feed ranked `(score, chunk)` pairs into `build_context` or an
equivalent model-specific budgeter. Re-tokenize if the chosen model uses another
encoding. This repository experiment makes no model/API calls.

## Practical choice for the next stage

Keep both strategies available. In this development set, sections use less prompt
space but pages retrieve more designated evidence in corpus-wide BM25 search.
Use fresh evidence questions and a fixed retriever/model configuration to decide
whether section, page, hybrid or parent-context retrieval works best for the team's
actual RAG task. See [REPORT.md](REPORT.md) for the measured comparison.
