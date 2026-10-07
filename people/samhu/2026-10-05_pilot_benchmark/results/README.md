# Results

- **[SUMMARY.md](SUMMARY.md)** — concise four-pipeline findings and limitations.
- **[Full parsed document index](../review/outputs.html)** — all six PDFs × four pipelines, with Markdown, page JSON, raw output and run records.
- **[Specific-page comparisons](../review/comparison.html)** — source images alongside all four page predictions.
- `preliminary.json` / `preliminary_checks.jsonl` — scores using the unchanged 54 draft labels.
- `reviewed.json` / `reviewed_checks.jsonl` — independently reviewed labels only (currently none).
- `baseline_2026-10-05.json` — preserved original three-pipeline summary.
- `parsed/<document>/pymupdf4llm_vlm/` — new complete parses and OCR audit records. The original three parses stay in the September folder and are linked in the index.
- `verification.json` — coverage, unchanged baseline/labels, provenance and report-link checks.

See [VLM_ADDITION.md](../VLM_ADDITION.md) for the OCR method and reproduction.
