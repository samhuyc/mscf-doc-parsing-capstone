# pdfplumber Findings

## Test Setup

- **Document:** Apple Inc. Q3 2026 Form 10-Q
- **Input:** `data/10Q.pdf`
- **Parser:** `pdfplumber`
- **Output files:** `output/pdfplumber/10Q.md` and `output/pdfplumber/10Q.json`
- **Pages processed:** 32
- **Command:**

  ```bash
  python3 pdfplumber_parser.py data/10Q.pdf --output-dir output/pdfplumber
  ```

## Strengths

### Transparent extraction

The parser exposes page-level text, words, coordinates, page dimensions, table cells, and table bounding boxes. This makes it possible to inspect exactly what was extracted and diagnose layout errors.

### Strong text coverage on this document

Text was extracted from all 32 pages of the Apple 10-Q. The output preserved narrative sections such as management discussion, risk factors, legal proceedings, and accounting notes.

### Table detection

The parser detected 30 tables across 18 pages. Financial statement pages, revenue tables, segment tables, and share-repurchase tables were recognized as table regions.

### Structured output

The JSON output is useful for downstream processing because each page contains separate fields for text, words, tables, dimensions, and table locations. The Markdown output is easy for people and language models to read.

### No intentional table duplication

The parser removes text inside detected table bounding boxes from the narrative text. Tables are then emitted separately as Markdown tables and JSON cells, avoiding the same table being intentionally represented as both prose and a table.

### Lightweight baseline

`pdfplumber` is relatively simple to install and run. It is useful as a fast, controllable baseline against higher-level document-understanding systems.

## Weaknesses

### No OCR

`pdfplumber` does not read text from scanned or image-only pages. It should not be treated as a complete solution for scanned SEC filings without a separate OCR pipeline.

### Table formatting is imperfect

Although table regions were detected, some extracted tables contain extra empty columns. Currency symbols can also be separated from their numeric values. For example, a value may appear as separate cells such as `$` and `39,544` instead of one cell containing `$39,544`.

### Complex layouts require tuning

Multi-level headers, merged cells, footnotes, continuation tables, and tables with irregular ruling lines may need custom `table_settings` or page-specific handling.

### Reading order can require review

The extracted text generally follows the page layout, but columns, headers, footers, and table-adjacent text may not always appear in ideal reading order.

### Table extraction is not semantic

The parser extracts cells and text but does not inherently understand that a row represents revenue, operating income, or a particular accounting period. Additional post-processing is needed for schema inference and reliable financial querying.

## Recommended Evaluation Result

| Category | Result |
|---|---|
| Text extraction | Good on digitally generated text pages |
| OCR/scanned pages | Not supported by pdfplumber alone |
| Table detection | Good coverage in this 10-Q run |
| Table structure preservation | Partial; requires review and tuning |
| Numeric fidelity | Generally readable, but currency and column alignment need checking |
| Layout and reading order | Usable baseline; complex pages need inspection |
| Coordinates and diagnostics | Strong |
| Markdown output | Readable, with some table-formatting issues |
| JSON/queryable output | Strong foundation for downstream processing |
| Runtime | Approximately 10 seconds in this local run |

## Overall Conclusion

`pdfplumber` is a valuable transparent baseline for the financial-document comparison. It provides broad text coverage, detects many financial tables, and exposes enough page geometry to investigate failures. Its main limitations are the lack of OCR and imperfect preservation of complex table structure. It is best used for digitally generated PDFs, diagnostics, and controllable extraction, potentially followed by custom table cleanup or an OCR/parser fallback for scanned and difficult pages.

## Short Version for the Team

> pdfplumber processed all 32 pages of the Apple Q3 2026 Form 10-Q, extracted text from every page, and detected 30 tables across 18 pages. Its main strengths are transparency, coordinate access, lightweight execution, and useful Markdown/JSON outputs. Its main weaknesses are no built-in OCR and imperfect formatting of complex financial tables, including extra empty columns and separated currency symbols. It is a strong low-level baseline, but not a complete standalone financial document parser.
