# October 6 addition — PyMuPDF4LLM with VLM OCR

Added to the October 5 pilot, using the same six complete sponsor PDFs, source hashes, labels and scoring rules. The three existing exports remain unchanged. The fourth configuration is **PyMuPDF4LLM + a local MinerU VLM OCR callback**.

- [Concise results](results/SUMMARY.md)
- [Original page and four predictions](review/comparison.html)
- [All complete parsed documents](review/outputs.html)
- [Original October 5 score snapshot](results/baseline_2026-10-05.json)

## Exactly what runs

1. PyMuPDF4LLM 1.28.2 decides whether each page needs OCR (`force_ocr=False`).
2. Its standard OCR helper renders the page at 300 DPI, excluding readable native text.
3. PP-OCRv6 small **detects text boxes only**. Its text recognizer is not loaded.
4. The cached `opendatalab/MinerU2.5-Pro-2605-1.2B` VLM reads each cropped region locally with MLX. The prompt is `Text Recognition:`; decoding/settings are recorded in each run.
5. The helper inserts recognized text at the detected coordinates. PyMuPDF Layout then performs page organization/table extraction and PyMuPDF4LLM exports HTML tables within Markdown.

This follows PyMuPDF4LLM's [custom OCR callback contract](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/ocr-plugins.html): the callback must add text to the page, not return a Markdown document. The same official `exec_ocr_full` helper used by its OCR plugins handles text placement. The VLM is accessed through the installed [MinerU VL utilities](https://github.com/opendatalab/mineru-vl-utils).

**This is not a copy of the MinerU VLM pipeline output.** The fourth pipeline reads only source PDF pixels for recognition; it never reads saved parser predictions, labels or expected values. The default MinerU VLM pipeline has its own page layout and table recognition; this configuration recognizes detected text crops and leaves layout/tables to PyMuPDF. Detection quality, crop context and text placement can all affect the result.

## Reproduce locally

Run from this October 5 folder. Reuse the existing two environments (PyMuPDF4LLM 1.28.2 in the sponsor-samples environment, MinerU 3.4.5 and MLX in the toy environment). This avoids changing either earlier experiment's dependencies. Requires the cached model weights and Apple Metal GPU access on this tested Mac.

```sh
PY=../2026-09-29_sponsor_samples/.venv/bin/python
TOY=../../../../pdf_parsing_toy
"$PY" run_pymupdf_vlm.py \
  --mineru-python "$TOY/.venv/bin/python" \
  --model-config "$TOY/cache/mineru.json" \
  --skip-existing
"$PY" export_vlm.py
"$PY" benchmark.py validate
"$PY" -m unittest -v
"$PY" benchmark.py score
"$PY" benchmark.py score --include-drafts
"$PY" report.py
"$PY" verify_addition.py
```

Use `--document peterborough_2025` to run one complete PDF. Runs are sequential. Existing output folders are never silently overwritten; archive a failed or changed-configuration folder before retrying. No downloads, API keys or hosted inference are needed with the recorded local caches. Missing weights/backend failures raise an error; there is no fallback to Tesseract or another parser.

The export step rewrites image links to portable document-relative paths without changing recognized content. For score/report reproduction only, omit the parser and export commands; no models or source PDFs are needed. The default scorer resolves the fourth pipeline under `results/parsed/<document>/pymupdf4llm_vlm/` and the original three under `../2026-09-29_sponsor_samples/results/`. `--output-root` still overrides all four using the common `<document>/<parser>/pages.json` contract.

## Audit files

Each new document folder includes:

- `document.md`, `pages.json`: complete canonical document and every physical page.
- `raw.md`, `raw_chunks.json`: direct PyMuPDF4LLM exports before canonical conversion.
- `metadata.json`, `images/`: source metadata, parser headings and linked crops.
- `run.json`: versions, settings, source/code/model identity, time, page coverage and actual VLM-use counts.
- `ocr_pages.json`: every callback invocation, recognized-region counts and text counts.
- `ocr/page_NNN.json`: detector coordinates and unedited VLM text for every recognized crop, with rendered-image hash and dimensions. Temporary rendered page images are removed after recognition; original PDFs remain unchanged.

## Interpretation

Use the unchanged 54 preliminary assistant-authored labels on 18 selected pages. They are not independent human gold. There is no composite score or overall model ranking. A missing table association can reflect strict matching or text placement even if the value is present. No financial value is filled in or repaired.

Native-text pages can bypass OCR in both PyMuPDF variants. The comparison page explicitly identifies actual OCR use; identical digital-page output does not demonstrate equivalent OCR quality. Historical run timings and the new run occurred separately and are not a controlled speed benchmark. No peak-memory claim is made.
