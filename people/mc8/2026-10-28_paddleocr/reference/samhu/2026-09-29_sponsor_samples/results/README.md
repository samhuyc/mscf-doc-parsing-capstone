# Parsed sponsor PDFs

Completed outputs for the September 30 meeting. Each model folder contains `document.md`, `pages.json`, `metadata.json`, raw predictions, linked image assets and `run.json` with measured settings and runtime.

**Status: all 18 runs complete; all three configurations have extracted text on 140/140 pages.** This is coverage, not a claim of correct extraction.

**PyMuPDF4LLM now includes layout analysis and automatic local Tesseract OCR.** All six active PyMuPDF folders have been replaced with this configuration. `ocr_pages.json` records pages routed to OCR. Earlier native-only results remain in Git history at `9cbf66a`.

| Document | MinerU OCR | MinerU VLM | PyMuPDF4LLM + OCR |
|---|---|---|---|
| CVS Health 2025 Q2 Earnings Presentation | [success](cvs_2025q2/mineru_ocr/document.md) | [success](cvs_2025q2/mineru_vlm/document.md) | [success](cvs_2025q2/pymupdf4llm/document.md) |
| EDF Consolidated Segmental Statement 2024 | [success](edf_2024/mineru_ocr/document.md) | [success](edf_2024/mineru_vlm/document.md) | [success](edf_2024/pymupdf4llm/document.md) |
| Hippodrome Casino Limited 2025 Full Accounts | [success](hippodrome_2025/mineru_ocr/document.md) | [success](hippodrome_2025/mineru_vlm/document.md) | [success](hippodrome_2025/pymupdf4llm/document.md) |
| Peterborough Care Limited Unaudited Financial Statements 2025 | [success](peterborough_2025/mineru_ocr/document.md) | [success](peterborough_2025/mineru_vlm/document.md) | [success](peterborough_2025/pymupdf4llm/document.md) |
| Rolls-Royce Holdings plc 2026 Half Year Results Presentation | [success](rolls_royce_2026h1_presentation/mineru_ocr/document.md) | [success](rolls_royce_2026h1_presentation/mineru_vlm/document.md) | [success](rolls_royce_2026h1_presentation/pymupdf4llm/document.md) |
| Rolls-Royce Holdings plc 2026 Half Year Results Press Release | [success](rolls_royce_2026h1_release/mineru_ocr/document.md) | [success](rolls_royce_2026h1_release/mineru_vlm/document.md) | [success](rolls_royce_2026h1_release/pymupdf4llm/document.md) |
