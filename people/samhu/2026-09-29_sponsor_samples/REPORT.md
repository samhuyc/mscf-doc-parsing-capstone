# Sponsor PDF parsing — September 30, 2026 meeting

Six sponsor PDFs, 140 physical pages, three parser configurations. Full-document results are organized by document, then parser. Start with the [visual comparison](evaluation/REVIEW.html), [concrete source-level examples](OBSERVATIONS.md), [per-document CSV](evaluation/metrics.csv), or [complete metrics and failed-row evidence](evaluation/metrics.json).

## What each pipeline actually does

OCR means recognizing text from page images. A VLM (vision-language model) reads images and generates text or structured output. These runs use three different extraction approaches:

| Pipeline tested | How it reads a PDF | Exact setup |
|---|---|---|
| **MinerU OCR** | Separate layout, text-recognition and table models process page images. OCR is forced even when the PDF already contains selectable text. | MinerU **3.4.5**, `pipeline` backend, local **PDF-Extract-Kit-1.0** models, CPU. Table recognition on; formula recognition off. |
| **MinerU local VLM** | A vision-language model reads page regions and produces text and tables, including from scans. | MinerU **3.4.5**, `vlm-engine` backend, local **MinerU2.5-Pro-2605-1.2B** model, MLX runtime on Apple Silicon. Table recognition on; formula recognition and optional figure descriptions off. |
| **PyMuPDF4LLM — native text** | Reads the PDF's existing text, positions, fonts and drawing lines; uses rules to arrange text and tables into Markdown. **No OCR, VLM or LLM runs in this configuration.** | PyMuPDF4LLM **0.2.9** + PyMuPDF **1.28.2**, `to_markdown(page_chunks=True)`, default `lines_strict` table detection, image crops saved at 100 DPI. No optional layout extension. |

**Does PyMuPDF support OCR?** Yes: PyMuPDF offers [Tesseract-based OCR](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html), and the [current PyMuPDF4LLM documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) describes additional layout/OCR support. Those paths were **not enabled or evaluated here**. “4LLM” means the output is suitable for a downstream LLM; this tested pipeline does not call one. The two scanned filings therefore yield image crops without searchable text. Saving an image is not the same as reading its contents.

**VLM setting clarification:** `--image-analysis false` disables optional descriptions of figures/charts; the VLM still reads page images to extract text and tables. The shared command includes `-m ocr`, but that switch does not select a separate OCR stage for the `vlm-engine` backend.

All three run locally, followed by a common export step that creates Markdown with HTML tables, page JSON and metadata. This standardizes the files without repairing predictions. Each output folder's `run.json` records its command, settings and model snapshot. This is a comparison of these specific configurations; it does not measure every feature available in each package.

## Runtime and coverage

These are single-run local wall times on an Apple M1 Pro with 16 GiB RAM, including process startup and model loading, excluding source downloads, common-format export and evaluation. MinerU weights were already cached. The parser configurations ran sequentially; ordinary development, output checks and diagnostic scoring overlapped parts of the batches, so these are observed end-to-end costs, not isolated latency measurements or a controlled throughput benchmark. No hosted inference API was used.

| Configuration | Completed documents | Pages with transcribed text | Total seconds | Minutes | Pages/sec |
|---|---:|---:|---:|---:|---:|
| MinerU OCR | 6/6 | 140/140 | 654.6 | 10.91 | 0.21 |
| MinerU local VLM | 6/6 | 140/140 | 3545.9 | 59.10 | 0.04 |
| PyMuPDF4LLM (no OCR) | 6/6 | 88/140 | 24.1 | 0.40 | 5.80 |

Completion means the process returned a valid page export, not that its text is correct. PyMuPDF4LLM can complete an image-only document with no transcribed text. Its overall throughput therefore cannot be read as OCR throughput.

| Document | Pages | MinerU OCR seconds | MinerU VLM seconds | PyMuPDF4LLM seconds |
|---|---:|---:|---:|---:|
| [CVS Health 2025 Q2 Earnings Presentation](https://s206.q4cdn.com/752775519/files/doc_financials/2025/q2/2Q-2025-Earnings-Presentation.pdf) | 12 | 46.0 | 234.2 | 1.5 |
| [EDF Consolidated Segmental Statement 2024](https://www.edfenergy.com/sites/default/files/2025-12/CSS-2024-Submission-Final.pdf) | 6 | 30.8 | 124.8 | 1.0 |
| [Hippodrome Casino Limited 2025 Full Accounts](https://find-and-update.company-information.service.gov.uk/company/05497987/filing-history/MzUyNzI0MTgyOGFkaXF6a2N4/document?format=pdf&download=0) | 39 | 179.9 | 983.7 | 4.1 |
| [Peterborough Care Limited Unaudited Financial Statements 2025](https://find-and-update.company-information.service.gov.uk/company/01814662/filing-history/MzQ5NTc4NzAxMWFkaXF6a2N4/document?format=pdf&download=0) | 12 | 48.1 | 241.4 | 0.8 |
| [Rolls-Royce Holdings plc 2026 Half Year Results Presentation](https://www.rolls-royce.com/~/media/Files/R/Rolls-Royce/documents/investors/rr-holdings-plc-2026-half-year-results-presentation.pdf) | 19 | 58.3 | 335.6 | 2.8 |
| [Rolls-Royce Holdings plc 2026 Half Year Results Press Release](https://www.rolls-royce.com/~/media/Files/R/Rolls-Royce/documents/investors/rr-holdings-plc-2026-half-year-results-press-release.pdf) | 52 | 291.5 | 1626.1 | 13.9 |

## Initial quality checks

The assistant visually transcribed three financial rows per document from the original rendered pages before inspecting parser predictions: **18 rows / 50 values**. The exact checks are in [checks.json](checks.json). This is a small, deliberately selected diagnostic set, not independent expert gold or an unbiased model ranking.

- **Selected-value recall:** how many expected numeric tokens occur on the correct source page, preserving currency, signs, grouping, decimals and percentages; whitespace is ignored. Duplicates within a check count as a multiset. This can pass when a number appears in the wrong row.
- **Exact row-cell rate:** whether a corresponding HTML table row has the expected complete ordered value-cell sequence. A leading note column is ignored. Missing tables, concatenated labels/cells and reversed value order fail. Repeated identical rows may match any occurrence. Headers, units, unrelated extra rows and global precision are not scored.
- **Coverage:** pages with any transcribed text, separately from process completion. A nonempty page can still have major omissions.

| Configuration | Selected values retained | Exact financial rows |
|---|---:|---:|
| MinerU OCR | 49/50 (98%) | 12/18 (67%) |
| MinerU local VLM | 50/50 (100%) | 18/18 (100%) |
| PyMuPDF4LLM (no OCR) | 21/50 (42%) | 0/18 (0%) |

| Document | OCR values / rows | VLM values / rows | PyMuPDF4LLM values / rows |
|---|---|---|---|
| cvs_2025q2 | 6/6 values; 3/3 rows | 6/6 values; 3/3 rows | 6/6 values; 0/3 rows |
| edf_2024 | 15/15 values; 0/3 rows | 15/15 values; 3/3 rows | 15/15 values; 0/3 rows |
| hippodrome_2025 | 6/6 values; 3/3 rows | 6/6 values; 3/3 rows | 0/6 values; 0/3 rows |
| peterborough_2025 | 5/6 values; 0/3 rows | 6/6 values; 3/3 rows | 0/6 values; 0/3 rows |
| rolls_royce_2026h1_presentation | 11/11 values; 3/3 rows | 11/11 values; 3/3 rows | 0/11 values; 0/3 rows |
| rolls_royce_2026h1_release | 6/6 values; 3/3 rows | 6/6 values; 3/3 rows | 0/6 values; 0/3 rows |

Keep scan and digital-PDF results separate:

| Input type | Configuration | Text pages | Selected values | Exact rows |
|---|---|---:|---:|---:|
| Image-only | MinerU OCR | 51/51 | 11/12 | 3/6 |
| Image-only | MinerU local VLM | 51/51 | 12/12 | 6/6 |
| Image-only | PyMuPDF4LLM (no OCR) | 0/51 | 0/12 | 0/6 |
| Digital PDF | MinerU OCR | 89/89 | 38/38 | 9/12 |
| Digital PDF | MinerU local VLM | 89/89 | 38/38 | 12/12 |
| Digital PDF | PyMuPDF4LLM (no OCR) | 88/89 | 21/38 | 0/12 |

## Text-layer diagnostics, not accuracy

For the four digital PDFs only, `metrics.csv` includes page-matched multiset word recall and numeric-token F1 against direct PDF text extraction. These help flag missing content. They do not verify reading order, table associations or source truth and inherently favor native-text extraction. The two image-only filings have no such reference; their diagnostics are `null`, not zero or perfect. HTML-table counts are descriptive, not a score.

## Output index

Each link opens the common `document.md`. Adjacent `pages.json` retains 1-based physical page provenance; `metadata.json` retains PDF metadata, embedded bookmarks and a separately labeled heading index. `run.json` records settings, versions, hashes, timestamps and timings. Raw predictions are retained without manual correction.

| Document | MinerU OCR | MinerU VLM | PyMuPDF4LLM |
|---|---|---|---|
| cvs_2025q2 | [mineru_ocr](results/cvs_2025q2/mineru_ocr/document.md) | [mineru_vlm](results/cvs_2025q2/mineru_vlm/document.md) | [pymupdf4llm](results/cvs_2025q2/pymupdf4llm/document.md) |
| edf_2024 | [mineru_ocr](results/edf_2024/mineru_ocr/document.md) | [mineru_vlm](results/edf_2024/mineru_vlm/document.md) | [pymupdf4llm](results/edf_2024/pymupdf4llm/document.md) |
| hippodrome_2025 | [mineru_ocr](results/hippodrome_2025/mineru_ocr/document.md) | [mineru_vlm](results/hippodrome_2025/mineru_vlm/document.md) | [pymupdf4llm](results/hippodrome_2025/pymupdf4llm/document.md) |
| peterborough_2025 | [mineru_ocr](results/peterborough_2025/mineru_ocr/document.md) | [mineru_vlm](results/peterborough_2025/mineru_vlm/document.md) | [pymupdf4llm](results/peterborough_2025/pymupdf4llm/document.md) |
| rolls_royce_2026h1_presentation | [mineru_ocr](results/rolls_royce_2026h1_presentation/mineru_ocr/document.md) | [mineru_vlm](results/rolls_royce_2026h1_presentation/mineru_vlm/document.md) | [pymupdf4llm](results/rolls_royce_2026h1_presentation/pymupdf4llm/document.md) |
| rolls_royce_2026h1_release | [mineru_ocr](results/rolls_royce_2026h1_release/mineru_ocr/document.md) | [mineru_vlm](results/rolls_royce_2026h1_release/mineru_vlm/document.md) | [pymupdf4llm](results/rolls_royce_2026h1_release/pymupdf4llm/document.md) |

## Meeting discussion

1. **Metadata and table of contents:** CVS has 12 embedded outline entries and the Rolls-Royce presentation has 25; the other four files have none. EDF and both Companies House scans have blank PDF title fields. File metadata alone is therefore incomplete. A separately labeled parser-heading index is also exported; it does not prove a correct document hierarchy. Preserve the distinction between embedded outlines, extracted contents pages and generated headings.
2. **Chunking:** use the exported physical page chunks as an auditable baseline. Next compare heading/paragraph chunks while keeping tables intact and carrying page, entity, period, unit and source hashes. Evaluate retrieval separately from transcription.
3. **Financial statements:** table cells must preserve row labels, year/segment columns, signs and units. The selected-row checks expose association errors that page-level number recall misses. A future labeled sample should score cell positions and header paths, with no automatic numerical repair before evaluation.
4. **Excel:** no spreadsheets were supplied, so no Excel results are claimed. A separate workbook sample should preserve sheets, ranges, formulas versus cached values, merged cells and units instead of treating Excel as a PDF.
5. **Confidence:** common `confidence` is deliberately `null`. A model's OCR probability is not calibrated document accuracy and is not comparable to a rule-based parser. Begin with visible flags (empty text, missing table rows, numeric mismatches, inconsistent totals); calibrate any confidence estimate on held-out documents before publishing a percentage.
6. **Benchmark aggregation:** keep text, table structure, numeric associations and runtime separate. For a larger labeled set, report per-document macro averages and totals, retain failures in denominators, stratify digital/scanned inputs and split by issuer/document. Bootstrap documents, not individual rows, for uncertainty.

## Connection to previous benchmarks

The earlier [OmniDocBench/FinCriticalED pilot](../2026-09-20_evaluation/REPORT.md) already separates text, numeric-token, table and critical-field diagnostics. The team's [TAT-QA experiment](../../mc8/2026-09-21_tatqa%20parsers%20evaluation/REPORT.md) motivates checking financial evidence retention. Those labeled-dataset scores have **not** been rerun or mixed into these sponsor-PDF results. No official TEDS, OmniDocBench aggregate, FinCriticalED semantic score or TAT-QA answer score is claimed.

## Reproduction and limitations

See [README](README.md), [pinned dependencies](requirements-lock.txt), [source manifest](source_manifest.json) and [validation](evaluation/validation.json). MinerU 3.4.5 uses the existing local PDF-Extract-Kit and MinerU2.5-Pro-2605-1.2B snapshots recorded in each run. OCR is forced on CPU; VLM uses local MLX. Formula recognition and generative image analysis are disabled. PyMuPDF4LLM 0.2.9 / PyMuPDF 1.28.2 uses native text, `lines_strict` tables and no OCR/layout extension, matching the teammate's version baseline; this is not a test of newer OCR-enabled PyMuPDF4LLM configurations.

Small sample, one run per configuration, no independent annotation adjudication, no complete document gold and no calibrated confidence. High selected-value retention alone cannot establish correct financial extraction. Full raw MinerU intermediates and source PDFs remain local and are reproducible from the manifest; portable Markdown/JSON, linked image assets and the six review-page images are tracked.
