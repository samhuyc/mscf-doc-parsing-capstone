# Sam Hu — sponsor PDF parsing, September 30

All six sponsor PDFs (140 pages) were processed with MinerU OCR, local MinerU VLM and PyMuPDF4LLM: 18 completed runs. Outputs use the same Markdown + HTML-table format with page-level JSON and source metadata.

- [Parsed output index](../../people/samhu/2026-09-29_sponsor_samples/results/README.md)
- [Runtime, initial metrics and meeting discussion](../../people/samhu/2026-09-29_sponsor_samples/REPORT.md)
- [Concrete source-level findings](../../people/samhu/2026-09-29_sponsor_samples/OBSERVATIONS.md)
- [Source/output visual comparison — download/open locally](../../people/samhu/2026-09-29_sponsor_samples/evaluation/REVIEW.html)

Observed total runtimes: OCR 10.91 minutes; VLM 59.10 minutes; PyMuPDF4LLM 24.1 seconds. On 18 selected financial rows / 50 values, exact row-cell preservation was 12/18, 18/18 and 0/18 respectively. These are small source-row spot checks, not official benchmark scores or whole-document accuracy.

PyMuPDF4LLM is pinned to the team's 0.2.9 native-text baseline without OCR. It produced transcribed text on 88/140 pages, including no transcription for the 51 scanned pages. Its speed is not comparable to OCR throughput, and its zero strict row score does not mean all text or values were lost.

Discuss native/scanned routing, table/header association labels, metadata versus semantic TOC, page/table-preserving chunks, a separate Excel sample, and confidence calibration. The report connects these to the previous OmniDocBench, FinCriticalED and TAT-QA work.
