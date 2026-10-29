# PaddleOCR replication of Sam's pipeline

All new work lives in this folder. Sam's original folder is never modified. Start with [the pipeline review](PIPELINE_REVIEW.md) for the complete source audit and stage-by-stage mapping.

The experiment uses the **same six sponsor PDFs / 140 source pages**, local PaddleOCR **PP-StructureV3**, and **Sam's byte-identical scorer and 54 unchanged draft reference records**. At the user's request, the current run prioritizes **all 18 labeled pages**, retains every previously completed page, and skips remaining non-evaluation pages. Full-document coverage and timing are therefore incomplete. Earlier public trials are implemented but deferred so they do not delay this accuracy benchmark; FinCriticalED is additionally gated and unavailable.

## Current accuracy-first run

```sh
.venv/bin/python selected_pages.py --plan-only
.venv/bin/python selected_pages.py
.venv/bin/python evaluate.py
.venv/bin/python report.py
.venv/bin/python verify.py
```

`selected_pages.py` derives only document/page IDs from the unchanged labels. Its inference worker reads only PDFs, requested page numbers and model weights. It imports the original worker's unchanged model constructor/settings. Completed full runs and per-page checkpoints are hash-checked and reused without inference. New native predictions are committed one page at a time; a rerun processes only missing requested pages. Native outputs without a committed checkpoint are preserved and cause an explicit error rather than being overwritten.

The saved checkpoint under `checkpoints/before_selected_pages/` preserves the initial run records, original 11-page remainder plan and all 17 completed Hippodrome pages. CVS and EDF's complete exports remain byte-identical. Sparse exports contain only real predictions, with original physical PDF page IDs; no blank page placeholders remain in `pages.json`. `results/selected_plan.json` records the current remainder; `selected_completion.json` and `verification.json` record completion and preservation checks. Verification also reruns only the scorer on an 18-page projection and requires every check and metric to match the larger retained export exactly.

Sam's scorer uses only the pages referenced by its 54 labels, so omitting other pages leaves those accuracy definitions and denominators unchanged. All 18 earlier financial row checks also fall within this selection. Whole-document native-text agreement, coverage and runtime must not be treated as full-run comparisons. These limitations are displayed in the report.

## Install

Python 3.10 is used on the Intel macOS host. All models run locally on CPU; no inference API key is needed. First-time package/model downloads require internet access.

```sh
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

`requirements.txt` provides the direct constraints; `requirements-lock.txt` records the exact installed environment. The PaddlePaddle version is selected for a native Intel macOS wheel.

## Original full-document mode (fresh output directories)

Run from this folder:

```sh
.venv/bin/python prepare.py
.venv/bin/python download_models.py
.venv/bin/python run.py
.venv/bin/python evaluate.py
.venv/bin/python report.py
.venv/bin/python verify.py
```

`prepare.py` checks the original source hashes and PDF page counts. `run.py` executes each full document in a separate subprocess, sequentially. It refuses to overwrite existing output. Its `--skip-existing` option is for prior full-document runs only; use `selected_pages.py` to resume the current selected-page experiment. `run_all.py` detects the selected-page plan and runs only that scope plus evaluation/report/verification, preserving the decision to defer earlier experiments. Do not use the old `run.py` directly over the selected-page exports. `--document edf_2024` selects one complete PDF in a fresh output directory.

The scorer and export adapter are Sam's original Python, without modified matching, expected values, normalization or metric definitions. The wrapper only registers the new parser and routes input/output paths. Evaluation requires exact reproduction of all historical per-document metrics, pooled scores and counts. Equal-document means alone allow `1e-14` floating-point roundoff: Python 3.12 changed float summation, and one saved mean differs from Python 3.10 by `2.22e-16`. Returned scores are never rewritten.

`download_models.py` records the official Paddle repositories, exact model revisions and file hashes before timing starts. `run_all.py` executes all available stages sequentially. `status.py` prints current document/page progress.

## Earlier stages

```sh
.venv/bin/python early_trial.py --prepare-only
.venv/bin/python early_trial.py --skip-existing
.venv/bin/python prepare_benchmarks.py
.venv/bin/python run_benchmarks.py --skip-existing
```

OmniDocBench uses the exact pinned revision, selected IDs and image/annotation hashes. FinCriticalED requires an approved Hugging Face login or an existing approved download:

```sh
.venv/bin/python prepare_benchmarks.py --dataset fin --fin-folder /path/to/FinCriticalED
.venv/bin/python run_benchmarks.py --dataset fin --skip-existing
```

The earlier trial has no committed source gold or quantitative evaluation in Sam's folder; it produces full-document exports, run records and the documented illustrative-page excerpts. A missing/gated input is recorded explicitly, never replaced with another dataset or a synthetic PDF.

## Outputs

- `results/parsed/<document>/paddleocr_ppstructurev3/`: `document.md`, physical `pages.json`, `metadata.json`, `raw.md`, untouched native per-page JSON/Markdown, image crops, OCR audit, timings, versions, code and model hashes.
- `results/preliminary.json`, `preliminary_checks.jsonl`, `metrics.csv`: same 54-label evaluation as Sam, with the new parser added.
- `results/reviewed.json`: reviewed-only scoring; zero selected labels is explicitly an empty evaluation.
- `evaluation/metrics.json`, `metrics.csv`: Sam's original 18-row/50-value sponsor diagnostics and native-text agreement checks.
- `review/index.html`, `comparison.html`, `tables.html`, `numbers.html`, `text.html`, `outputs.html`, `labels.html`: offline review and full-output links.
- `REPORT.md`: compact measured comparison; `results/verification.json`: source, output, scorer, baseline and report-link audit.
- `benchmarks/results/`: earlier page-level predictions and unchanged September scorer results.
- `early/results/`: original September 9 two-PDF trial reproduced with PaddleOCR.
- `reference/samhu/`: frozen upstream code, labels and historical predictions. `upstream.json` identifies the exact commit and every file hash.

Source PDFs, gated dataset files, model caches and the environment stay local and are ignored by Git. Portable predictions, evaluation outputs and reports are saved in this folder.

Verification accepts either Sam's initial workspace snapshot or the complete pinned upstream snapshot. This accounts for Sam's pre-existing report/glossary updates when checking out newer repository commits; it does not permit arbitrary source edits or mixed snapshots. The selected baseline is recorded in `results/verification.json`.

## Interpretation

The 54 references are assistant-authored drafts, not independently verified gold. Selected labels cover 18 pages, not the full 140 pages. Presence and correct row/year association are distinct. No official TEDS, OmniDocBench leaderboard, FinCriticalED semantic or TAT-QA answer score is claimed. Historical Sam timings were measured on different hardware.

PP-StructureV3 handles layout, OCR recognition and table reconstruction. PyMuPDF renders pixels and reads source metadata only. Formula and optional figure/LLM analysis are disabled. Predictions receive no repairs or financial inference. Common confidence is `null`; native scores are retained separately.

The measured CPU preset uses official PP-OCRv5 mobile text models and the standard PP-StructureV3 layout/table models. Its detector's internal image limit is 1,280 pixels because the available Intel macOS PaddlePaddle wheel crashes on larger detector tensors. PDF rendering and recognition crops remain at 300 DPI. The full setting and compatibility fixes are described in [PIPELINE_REVIEW.md](PIPELINE_REVIEW.md) and recorded per run.
