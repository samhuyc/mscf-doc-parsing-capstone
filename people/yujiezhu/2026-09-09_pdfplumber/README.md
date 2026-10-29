# Financial PDF Parsing Baseline

This is the `pdfplumber` contribution to the team comparison. `pdfplumber` is intentionally a transparent, lower-level baseline: it exposes extracted text, word coordinates, page dimensions, and table cells so the team can inspect exactly where parsing succeeds or fails. The Markdown narrative excludes characters inside detected table bounding boxes, so table content is not intentionally repeated as both prose and a table.

## What you should do

1. Install the dependency: `python -m pip install -r requirements.txt`
2. Run the parser on the agreed SEC sample:

   ```bash
   python pdfplumber_parser.py path/to/sec_document.pdf --output-dir output/pdfplumber
   ```

3. Review both outputs:
   - `.md`: human-readable text and tables for LLM/RAG experiments.
   - `.json`: page-level text, word bounding boxes, table cells, dimensions, and counts for evaluation.
4. Compare the output with the source-page screenshots. Record reading-order errors, missing or merged text, numeric mistakes, table structure problems, headers/footers, and runtime.
5. Bring the output folder and a short findings summary to the team. Use the same document pages and metrics as the other tools.

## Suggested findings summary

- Text extraction: accurate, incomplete, or incorrectly ordered?
- Tables: detected, missed, or structurally damaged?
- Financial numbers: any lost commas, parentheses, decimals, or column shifts?
- Layout: how well are headings, footnotes, and headers/footers preserved?
- Runtime: command runtime and approximate document size/page count.
- Downstream usefulness: is the Markdown readable and is the JSON queryable?

## Apple 10-Q result

The current run on `data/10Q.pdf` processed 32 pages, extracted text from all 32 pages, and detected 30 tables across 18 pages. Table content is separated from narrative text, but the default table detector can create extra empty columns or separate currency symbols from values. These are important table-fidelity findings to report to the team.

This script does not perform OCR. That is useful in the comparison: scanned pages should be marked as a limitation of the `pdfplumber` baseline rather than silently treated as successful extraction.
