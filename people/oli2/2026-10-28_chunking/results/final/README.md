# Read the chunking output

**Start with one chunk, then compare it with the original parsed page.**
The main output is a collection of text passages. Each passage carries its
document, section and source location so retrieval can find it and cite it.

## A real output, in readable form

This example comes directly from a record in `section_chunks.jsonl`:

- **Document:** EDF 2024.
- **Section:** Accounting Standards.
- **Source:** physical PDF page 4.
- **Content excerpt:**

  > which have been prepared in accordance with accounting standards Financial Reporting Standard 101 Reduced Disclosure Framework (‘FRS 101’).

- **Context size:** 185 tokens, including the inherited document and section context.
- **Available for retrieval:** yes.

The full chunk contains the accounting-standards heading and its complete
paragraph. It is a passage copied from the parser output, not a generated summary
or an answer. A question about EDF's accounting standards should retrieve this
passage as evidence.

On the same PDF page, the next section is **Definitions and Methodology**.
That becomes a separate chunk, with 635 context tokens. It includes text from
page 4 and the continuation on page 5. This shows why a chunk is not necessarily
the same thing as a page.

## See the actual boundaries

Open **[preview.html](preview.html)** in a browser. The entire preview is contained
in this one file; no server or additional assets are needed.

**On GitHub:** download `preview.html` using the file's download/raw action, then
open the downloaded file in a browser. GitHub's file view shows HTML source rather
than running the preview.

**In a local checkout:** open `results/final/preview.html` from this experiment.

The preview starts at **EDF / physical page 4 / Sections and paragraphs**:

1. **Left:** the original saved parser text for page 4.
2. **Right:** the two chunks that contain text from that page: Accounting Standards
   and Definitions and Methodology. Each bordered block is one chunk.
3. Click **Page baseline** to see what keeping the entire page together looks like.
   Click **Sections / paragraphs** to return to the final section chunks.
4. Click a **PDF p4** source button on a chunk to highlight its exact text on the
   left. A chunk with both **PDF p4** and **PDF p5** buttons spans those pages.

Start with the section title, passage and source page. The long ID and character
offsets are technical references; they do not describe the quality of the chunk.
Keep **Show chunks from all pages** unchecked while inspecting one example.

## Which file should I use?

- **To inspect the output visually:** [preview.html](preview.html).
- **To pass chunks into a retrieval system:** [section_chunks.jsonl](section_chunks.jsonl).
  It contains all 333 chunk records, with one JSON record per line. There are not
  333 separate output files. The `indexable` field selects the 330 search records.
- **To see what the model would receive after retrieval:**
  [rag_example.txt](rag_example.txt). This is an example question plus selected
  passages and citation labels, not a generated model answer.
- **To understand the measured results:** [REPORT.md](../../REPORT.md).

## If you open a JSON record

Read these fields first:

- `content`: the actual chunk text, with original Markdown/table markup preserved.
- `section_path`: its inferred section title and parent titles.
- `source_spans`: where that text came from; `page` is the physical PDF page.
- `context_tokens`: the size of the prepared model context, including added context.

`retrieval_text` and `context_text` are two views of the same chunk, so they may
look repetitive. The first is prepared for search; the second preserves source
formatting and adds document/section context for the model. They are not additional
independent chunks. Use [HANDOFF.md](../../HANDOFF.md) when connecting the code.

<details>
<summary>Supporting files for evaluation and reproducibility</summary>

- `page_chunks.jsonl`: the 140-page baseline used for comparison.
- `summary.json`: counts, sizes and source-preservation checks.
- `retrieval.json`: the 32 development questions and retrieval comparisons.
- `rag_example.json`: the structured version of the example prompt and citations.
- `documents.json`: input identity and inherited document metadata evidence.
- `heading_decisions.json`: accepted, normalized and suppressed heading decisions.
- `boundary_audit.json`: the review of small chunks from the first experiment.
- `index.json`: chunk file paths and hashes used by the retrieval loader.
- `manifest.json`: code, dependency, configuration and input provenance.
- `validation.json`: recorded test, browser and repeat-build checks.

These files explain or validate the output. They are not more chunks to read.
The adjacent `results/v1` directory is the earlier experiment; this `final`
directory contains the delivered version.

</details>
