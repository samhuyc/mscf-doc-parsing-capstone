# Parsed sponsor PDFs

Completed outputs for the September 30 meeting. Each model folder contains `document.md`, `pages.json`, `metadata.json`, raw predictions, image assets and `run.json` with measured runtime.

**Status: 17 of 18 runs complete.** The final Rolls-Royce release VLM run is still in progress; its unfinished files are not included in this snapshot.

**PyMuPDF4LLM is the no-OCR native-text configuration.** It returns images but no transcribed text for the two scanned Companies House filings, and has no transcribed text on CVS page 8. These are explicitly recorded as `empty`/`partial`, not extraction successes.

| Document | MinerU OCR | MinerU VLM | PyMuPDF4LLM |
|---|---|---|---|
| CVS Health 2025 Q2 Earnings Presentation | [success](cvs_2025q2/mineru_ocr/document.md) | [success](cvs_2025q2/mineru_vlm/document.md) | [partial](cvs_2025q2/pymupdf4llm/document.md) |
| EDF Consolidated Segmental Statement 2024 | [success](edf_2024/mineru_ocr/document.md) | [success](edf_2024/mineru_vlm/document.md) | [success](edf_2024/pymupdf4llm/document.md) |
| Hippodrome Casino Limited 2025 Full Accounts | [success](hippodrome_2025/mineru_ocr/document.md) | [success](hippodrome_2025/mineru_vlm/document.md) | [empty](hippodrome_2025/pymupdf4llm/document.md) |
| Peterborough Care Limited Unaudited Financial Statements 2025 | [success](peterborough_2025/mineru_ocr/document.md) | [success](peterborough_2025/mineru_vlm/document.md) | [empty](peterborough_2025/pymupdf4llm/document.md) |
| Rolls-Royce Holdings plc 2026 Half Year Results Presentation | [success](rolls_royce_2026h1_presentation/mineru_ocr/document.md) | [success](rolls_royce_2026h1_presentation/mineru_vlm/document.md) | [success](rolls_royce_2026h1_presentation/pymupdf4llm/document.md) |
| Rolls-Royce Holdings plc 2026 Half Year Results Press Release | [success](rolls_royce_2026h1_release/mineru_ocr/document.md) | Running — pending next push | [success](rolls_royce_2026h1_release/pymupdf4llm/document.md) |
