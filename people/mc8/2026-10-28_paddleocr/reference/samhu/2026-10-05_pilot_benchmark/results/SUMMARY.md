# Four-pipeline results — October 6 addition

Start with [page comparisons](../review/comparison.html) or [all full parsed results](../review/outputs.html).

The original three parser exports and all 54 October 5 labels are unchanged. These are preliminary assistant-authored references, not independently verified gold. Six PDFs / 140 pages per pipeline; 18 pages have selected labels. No overall ranking.

| Metric | MinerU OCR | MinerU VLM | PyMuPDF4LLM + Tesseract | PyMuPDF4LLM + VLM |
|---|---|---|---|---|
| Correct value in the correct cell | 54/133 (40.6%) | 95/133 (71.4%) | 115/133 (86.5%) | 109/133 (82.0%) |
| Expected table number appears on the page | 126/128 (98.4%) | 127/128 (99.2%) | 128/128 (100.0%) | 128/128 (100.0%) |
| Negative values correct in their cells | 8/18 (44.4%) | 16/18 (88.9%) | 14/18 (77.8%) | 14/18 (77.8%) |
| Selected text passages retained | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) |
| Footnote wording retained | 4/5 (80.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 4/5 (80.0%) |
| Selected text pairs in the right order | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |

The VLM-backed PyMuPDF pipeline resolves **109/133** selected cells correctly, versus **115/133** with Tesseract. Selected-number retention is **128/128**, versus **128/128**. These compare the saved configurations, not an isolated recognition-model ablation.

The six-cell association gap comes entirely from Hippodrome PDF page 21: the new pipeline exports the table as a picture with flat text, while Tesseract produces an explicit table. The amounts survive, but their table structure does not. The 4/5 footnote result is triggered by a missing final period in the Peterborough page 3 note; its words are retained.

Concrete example: on Peterborough PDF page 2, both PyMuPDF variants retain 12/12 labeled amounts but associate only 8/12 with the expected year. Separate detail/total columns remain a layout issue. The new VLM also misreads note 7 as a mathematical symbol; see the unedited comparison.

Counts are selected checks, not whole-document accuracy. Exact row/header matching and explicit table structure are required for cell association. Presence can pass even when association fails.

## What changed

The new pipeline calls PyMuPDF4LLM 1.28.2 with `ocr_function`. Its standard OCR helper removes good native text from the rendered image, calls PP-OCRv6 **detection only**, uses the local MinerU2.5-Pro-2605-1.2B VLM to recognize each detected crop, and inserts the result at the detected coordinates. PyMuPDF Layout then performs layout/table extraction and Markdown export. No Paddle text recognizer, Tesseract recognition, prior MinerU outputs or reference labels supply its recognized text.

This is a custom crop-recognition configuration, not MinerU’s default page parsing pipeline. Its quality depends on detection boxes, crop recognition and PyMuPDF’s text placement/layout. Automatic OCR (`force_ocr=False`, 300 DPI) matches the existing Tesseract routing policy; native-text pages may bypass OCR.

| Document | Pages | Tesseract callback pages | VLM recognition pages | VLM recognized regions |
|---|---:|---:|---:|---:|
| CVS Health 2025 Q2 Earnings Presentation | 12 | 11 | 11 | 27 |
| EDF Consolidated Segmental Statement 2024 | 6 | 6 | 6 | 7 |
| Hippodrome Casino Limited 2025 Full Accounts | 39 | 39 | 39 | 1966 |
| Peterborough Care Limited Unaudited Financial Statements 2025 | 12 | 12 | 12 | 436 |
| Rolls-Royce Holdings plc 2026 Half Year Results Presentation | 19 | 4 | 4 | 13 |
| Rolls-Royce Holdings plc 2026 Half Year Results Press Release | 52 | 0 | 0 | 0 |

## Files and reproduction

- [Full parsed document index](../review/outputs.html): all 24 complete document exports.
- [Same-page examples](../review/comparison.html): six source pages with all four predictions and selected checks.
- [Detailed scores](preliminary.json) and [individual checks](preliminary_checks.jsonl).
- [Original October 5 summary](baseline_2026-10-05.json) preserves the three-pipeline snapshot.
- New raw crop predictions: `parsed/<document>/pymupdf4llm_vlm/ocr/page_NNN.json`.
- [Method and commands](../VLM_ADDITION.md).

Historical timings are not a controlled speed comparison. New runs include local model loading; scoring/report generation uses saved predictions only. No hosted inference is used.
