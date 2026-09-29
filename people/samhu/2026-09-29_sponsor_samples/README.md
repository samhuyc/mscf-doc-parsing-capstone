# Sponsor samples — September 30 meeting

Start with `REPORT.md` after the runs finish. Sources are the six links in the sponsor email. Inputs and large native MinerU intermediates remain local; the source manifest records URLs and hashes.

## Common output

`results/<document>/<parser>/` contains `document.md` (Markdown prose plus HTML tables), `pages.json` (one record per physical source page), `metadata.json` (PDF metadata, embedded outline, and a separate parser-heading index), `run.json`, raw parser Markdown/JSON, and linked images. Logs and full MinerU native intermediates remain local. `confidence: null` is intentional: no calibrated confidence exists for this comparison. Page chunks are the initial retrieval units; no financial values or missing cells are inferred, corrected, or summarized.

The canonical table converter is reused from `../2026-09-20_evaluation/formats.py`. Pipe tables become HTML without inventing spans. MinerU page exports come from its content list; original Markdown is retained as `raw.md`. PyMuPDF4LLM exports retain native chunk metadata. Embedded outlines and heading indexes are distinct from a verified semantic table of contents.

## Reproduce

From the repository root, create `.venv` and install this folder's `requirements.txt`. MinerU 3.4.5 runs in a separate environment (see the September 9 experiment) with cached weights.

```bash
.venv/bin/python people/samhu/2026-09-29_sponsor_samples/prepare.py
.venv/bin/python people/samhu/2026-09-29_sponsor_samples/parse.py --parser pymupdf4llm
.venv/bin/python people/samhu/2026-09-29_sponsor_samples/parse.py --parser mineru_ocr --mineru /path/to/mineru --model-config /path/to/mineru.json
.venv/bin/python people/samhu/2026-09-29_sponsor_samples/parse.py --parser mineru_vlm --mineru /path/to/mineru --model-config /path/to/mineru.json
```

Outputs cannot be silently overwritten. `--skip-existing` resumes completed, hash-matching documents; archive failed folders before retrying. Full PDFs are processed, not selected pages. A single document per subprocess provides comparable process/model startup-inclusive timing; downloads, serialization adapters and evaluation are excluded. Runs should be sequential to avoid resource competition.

## Configurations

- **MinerU OCR**: `pipeline`, forced `ocr`, CPU, tables enabled, formula recognition disabled.
- **MinerU VLM**: `vlm-engine`, local runtime auto-selected (MLX on this Apple Silicon host), tables enabled, image analysis and formula recognition disabled.
- **PyMuPDF4LLM 0.2.9 / PyMuPDF 1.28.2**: native-text/geometry baseline, default `lines_strict` tables, no OCR or layout extension. Pinned to the same versions as the teammate's September 21 TAT-QA experiment. This is not a test of newer PyMuPDF4LLM layout/OCR features. Image-only inputs can produce images but no transcribed text and are explicitly reported as empty/partial.

All inference is local. The adapter reads no benchmark labels. Scanned document failures must remain visible rather than being silently rescued by another parser. Results are a six-document case study, not a representative ranking.
