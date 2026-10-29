# Measured PaddleOCR comparison

Same 54 preliminary references, unchanged scoring logic. Six hash-identical PDFs / 140 source pages; selected labels on 18 pages.

PaddleOCR retains 46/140 processed physical pages, including all 18 labeled pages. The run prioritizes the unchanged 54-label accuracy evaluation. Full-document coverage, native-text diagnostics and end-to-end timing are incomplete.

| Metric | MinerU OCR | MinerU VLM | PyMuPDF4LLM + Tesseract | PyMuPDF4LLM + VLM | PaddleOCR PP-StructureV3 (CPU) |
|---|---|---|---|---|---|
| Correct value in the correct cell | 54/133 (40.6%) | 95/133 (71.4%) | 115/133 (86.5%) | 109/133 (82.0%) | 71/133 (53.4%) |
| Expected table number appears on the page | 126/128 (98.4%) | 127/128 (99.2%) | 128/128 (100.0%) | 128/128 (100.0%) | 121/128 (94.5%) |
| Negative values correct in their cells | 8/18 (44.4%) | 16/18 (88.9%) | 14/18 (77.8%) | 14/18 (77.8%) | 8/18 (44.4%) |
| Selected text passages retained | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) |
| Footnote wording retained | 4/5 (80.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 4/5 (80.0%) | 3/5 (60.0%) |
| Selected text pairs in the right order | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |

[Visual comparison](review/comparison.html) · [Saved outputs](review/outputs.html) · [Detailed JSON](results/preliminary.json) · [CSV](results/metrics.csv).

Paddle configuration: PP-StructureV3 with PP-OCRv5 mobile detection/recognition and standard layout/table models; CPU, four Paddle math threads, 300 DPI renders, 1,280-pixel detector limit for macOS compatibility. Notes, headers and footers are retained. This is a measurement of this specific configuration, not the server-OCR preset.

Historical runtimes are from different hardware. Selected-page processing is not a full-document speed comparison. Reference labels are assistant-authored drafts, and no overall parser ranking is claimed.
