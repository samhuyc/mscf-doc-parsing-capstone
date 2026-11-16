# Shared table regions and native confidence

Source-linked **table-region** confidence experiment. It does not estimate the probability that a table is correct. No training or calibration is performed.

## Completed sponsor run — November 16, 2026

All six models processed the same 103 detected table crops across 140 pages in six sponsor PDFs: 618 outputs, no failed jobs, and native scores for every crop. MinerU reached the 4,096-token limit on two crops outside the accuracy subset; these are flagged, not counted as complete transcriptions.

The accuracy comparison uses **exactly the same 19 crops for all six models**, spanning five issuers. References were visually checked by the assistant and still require independent human review.

| Model | Mean numeric F1 | Exact numeric inventories | Confidence–F1 Spearman ρ |
|---|---:|---:|---:|
| PP-OCRv5 | 99.25% | 14/19 | +0.27 |
| Tesseract | 96.27% | 10/19 | -0.03 |
| PaddleOCR-VL | 100.00% | 19/19 | No error variation |
| GLM-OCR | 98.98% | 14/19 | +0.17 |
| MonkeyOCR | 99.61% | 15/19 | +0.14 |
| MinerU recognition | 99.57% | 17/19 | -0.07 |

**Finding:** this small development subset does not establish native confidence as a reliable proxy for numeric accuracy. All five measurable correlation intervals include zero; PaddleOCR-VL has constant numeric F1, so its correlation cannot be estimated. Raw confidence scales differ across models.

**Accuracy definition:** within each crop, match numeric occurrences including duplicates. F1 = `2 × matched occurrences / (reference count + output count)`; the reported mean weights crops equally. Missing/extra values and sign errors reduce the score. Years and note numbers count. Row/column associations are ignored: swapping values between years can still score 100%.

**Next evaluation:** human-verify `(row label, period, signed value, currency/unit/scale)` facts, measure layout completeness separately, and evaluate confidence-based review decisions on harder documents held out by issuer. The intended expansion is toward 60 sponsor-like documents; no quality predictor has been trained.

[Confidence–accuracy plot](results/sponsor_all/accuracy/confidence_vs_numeric_accuracy.png) · [Per-crop pairs](results/sponsor_all/accuracy/pairs.csv) · [Full statistics and limitations](results/sponsor_all/accuracy/tracking.json) · [Final evidence audit](results/sponsor_all/final_audit.json)

The evidence audit checks source crop hashes, native score recomputation, all 243 embedded report images, and per-engine coverage. Thirty focused checks pass. This validates provenance and computation, not financial-table correctness. The local interactive summary is `runs/sponsor_all/accuracy/report.html`; raw inputs, model weights, environments and full decoder evidence are kept outside Git.

## Pipeline

1. Render selected sponsor pages at 200 DPI.
2. Run the team's pinned `PP-DocLayout_plus-L` (RT-DETR-L) checkpoint independently of every recognizer. Keep all table detections at the declared 0.5 threshold; financial relevance is not silently inferred. Retain all other layout boxes in raw output.
3. Suppress nearly contained duplicate table boxes (95% containment), preferring the larger context; save suppressed predictions for audit. Add 2% padding, clamped to the page. Adjacent tables remain separate; one region may contain multiple subtables.
4. Run PP-OCRv5 mobile and Tesseract on the same PNG crops. Separately add MinerU recognition using the same source crops and its original maximum-side resize. Engine weights remain unchanged.
5. Pool native confidence per region. Geometric mean is the declared primary summary; arithmetic mean, tenth percentile and fraction below 0.90 remain secondary. A zero score stays zero; missing evidence stays null.

`report.html` is self-contained: crops, transcriptions, confidence and full-page overviews are embedded. `table_scores.csv` and `summary.json` are compact exports. Full decoder evidence stays in ignored `runs/`. Source/model/settings/crop hashes are retained.

## Scope and known limitations

- The initial pilot used seven selected pages and eight retained regions. The completed full run and 19-crop development comparison are summarized above; neither is a held-out benchmark.
- **Layout is not yet adequate for automatic financial extraction.** Assistant visual inspection found a missed reconciliation in Hippodrome page 36, grouped subtables in Rolls-Royce presentation page 9, and shared column headers outside the second crop of Rolls-Royce release page 25. See `layout_review.json`. These observations are not independently verified labels.
- Detected tables are candidates. Headers, units, narrative qualifiers, footnotes and chart/KPI content can fall outside their boxes. Nothing here establishes that all important financial content was found.
- Recognition scores do not validate cell association or completeness. Outputs are table-region transcriptions, not validated cell grids. No automatic acceptance threshold is enabled.
- Existing Paddle v2 page scores can be assigned to regions using line geometry. Characters inherit the line box; these are not exact character positions. Units are assigned to at most one region by greatest overlap, requiring at least 50% overlap. Boundary and ambiguous assignments are recorded.
- Existing Tesseract pages used 300 DPI; shared crops use 200 DPI. Its baseline/crop difference is not a controlled cropping-only experiment. Paddle page and crop inputs are 200 DPI, but cropping changes internal resizing and context. Text changes alone do not establish accuracy changes.
- Existing MinerU page output lacks spatial token mapping, so no per-region page baseline is fabricated. MinerU uses the recognition component with `Text Recognition:` rather than the full original layout/table pipeline; it is explicitly labelled that way.
- MinerU's summary includes every emitted token, including formatting characters where generated (for example the EDF Markdown table). It is not a numeric-content-only score. All eight pilot crops reached EOS without hitting the token limit, but that does not establish complete extraction: the first Rolls-Royce release crop omits visible division headers in its generated text. This is an assistant observation, not an independent correctness label.
- Raw scores remain engine-specific. Current summary provenance records the underlying unit type. New VLM adapters must distinguish formatting tokens from transcription tokens where applicable.

## Reproduce

From this directory, create a Python 3.12 `.venv`, install `environment.lock.txt`, then:

```sh
.venv/bin/python download_layout.py
.venv/bin/python -m unittest -q test_regions
.venv/bin/python run_tables.py
```

The layout downloader uses the existing team revision and file hashes. Native PP-OCRv5 weights and original page baselines are read from `../2026-11-10_native_confidence/`; sponsor inputs are read from `../2026-09-29_sponsor_samples/inputs/`. No teammate files or presentation artifacts are changed.

The default output is `runs/pilot_v2`. Completed table inference resumes only when source/configuration/crop hashes match; changed configurations require a new output directory. `runs/pilot` preserves the initial unsuppressed detector trial. `pilot.json` controls the page selection.

MinerU uses a separate persistent environment to preserve the audited MLX decoder:

Create `work/mineru-env` with Python 3.12 and install `environment-mineru.lock.txt`. On this Mac, MLX requires execution with access to the Metal GPU.

```sh
work/mineru-env/bin/python run_mineru_tables.py
.venv/bin/python report.py runs/pilot_v2
.venv/bin/python verify.py runs/pilot_v2
```

Its separate settings and per-table files live in `runs/pilot_v2/mineru/`. Missing tables remain pending. Generation limits and repetitive outputs remain visible even when native confidence is high. Report rebuilds preserve existing reviewer entries and append newly added engines.

## Additional models under 4 GB

The user clarified that 4 GB limits model files, not running memory. The downloaded recognition checkpoints include tokenizer/configuration files:

| Model | Files, decimal GB | Mode |
|---|---:|---|
| PaddleOCR-VL-1.6 | 1.930 | Table recognition, OTSL structure tokens |
| GLM-OCR | 2.657 | Table recognition |
| MonkeyOCR-pro-1.2B | 3.825 | Table HTML |
| DeepSeek-OCR-2 | 6.789 | Excluded; not downloaded or tested |

Names such as “1.2B” do not necessarily count all vision parameters. Exact revisions, file hashes and byte sizes are in the model download provenance and result settings. `model_candidates.json` links the official sources. `extra_trial_policy.json` records the size constraint.

Create Python 3.12 environment `work/extra-env` and install `environment-extra.lock.txt`. Then:

```sh
work/extra-env/bin/python inspect_models.py
work/extra-env/bin/python download_extra_models.py paddle_vl glm monkey
work/extra-env/bin/python run_extra_models.py paddle_vl
work/extra-env/bin/python run_extra_models.py glm
work/extra-env/bin/python run_extra_models.py monkey
.venv/bin/python report.py runs/pilot_v2
.venv/bin/python verify.py runs/pilot_v2
```

Models run sequentially on the Mac GPU, in a separate environment from the existing probes. No checkpoint quantization, training or calibration is applied. The supported identity logits callback observes the raw model logits and returns the identical object. Reporting normalizes logits in FP32, without changing generation. On the first crop, text, token IDs and stop reason must match an uninstrumented control. EOS and lookahead tokens are excluded from summaries. Twelve focused evidence/geometry tests cover alignment, EOS, truncation, mixed markup and region handling.

The all-token score includes markup. A secondary content-only score excludes tokens wholly inside HTML/OTSL tags, code fences, whitespace and mixed content/markup tokens. Coverage counts remain visible; this is a conservative token subset, not a cell-level correctness probability. Nonmonotonic token decoding makes this subset unavailable rather than guessing alignment.

### Changes from publisher pipelines

- Shared cropped inputs and publisher table prompts replace each publisher's complete layout pipeline. The model-specific MLX image processor still resizes/normalizes each crop. The adapter adds no external crop resize. Monkey's full upstream pipeline caps images at 1600 pixels; this adapter uses its checkpoint processor limits instead.
- Generation is explicitly greedy, maximum 4096 output tokens, with no repetition/presence/frequency penalties. Monkey's upstream vLLM pipeline uses repetition penalty 1.05; this controlled raw-logit trial disables it. Thus it is not an exact reproduction of the publisher's end-to-end system.
- MLX runs the original BF16 weights on Apple Silicon. Backend parity against publisher CUDA inference has not been established. The instrumentation check establishes only that score collection itself preserves output on the tested crop.
- GLM's newer checkpoint adds a vision rotary configuration field unsupported by the pinned MLX config parser. The adapter verifies it specifies axial rotary with theta 10000, matching the backend's hardcoded implementation, then removes only that redundant field from a temporary configuration copy. Original downloaded files remain unchanged. The backend also omits GLM's auxiliary next-token prediction layer, which is unused by ordinary autoregressive inference.
- Paddle uses the runtime's built-in processor, without executing downloaded remote Python. Paddle emits OTSL tokens in table mode; output is retained verbatim, not converted to invented HTML. Monkey output is also retained without the publisher's automatic table-closing repair.
- Instrumented times include score collection. First-crop control time is separate. Peak MLX allocation and process peak resident memory are different overlapping measurements; neither is whole-machine memory, and they must not be added.

The initial eight-region pilot is documented below. Successful completion and high native confidence do not establish table correctness or complete financial coverage.

### Completed pilot

All three additional models completed all eight regions, reached EOS and passed the first-crop instrumentation equivalence check. Together with the three existing engines, the report contains 48 successful outputs. Twelve focused tests and the evidence/export audit pass. Measured peak MLX allocation ranges: PaddleOCR-VL 2.70–2.94 GB, GLM 3.18–3.39 GB, Monkey 4.64–4.81 GB. Instrumented per-crop times: 2.3–12.4 s, 2.8–25.0 s and 5.1–39.5 s respectively. This tiny selected sample does not establish general speed or accuracy rankings.

See `results/extra_trials.json` for exact ranges and content-summary availability. GLM's incremental decoder revises Unicode prefixes on some tables; those content-only summaries are explicitly unavailable, while all-token native confidence remains available. `results/audit.json` records validation; full token evidence and the self-contained report remain in `runs/pilot_v2/`.

## Full sponsor-corpus run

`sponsor_all.json` selects all 140 pages in the six original sponsor PDFs. It uses the same detector, 200 DPI rendering, 0.5 detection threshold, 95% nested-box suppression and 2% padding as the pilot. Every detected table remains a candidate; this does not automatically classify financial relevance. Original PDFs and the eight-region pilot remain separate.

```sh
.venv/bin/python run_tables.py --selection sponsor_all.json --output runs/sponsor_all
.venv/bin/python run_sponsor_batch.py
```

The first command saves page overviews, layout detections, reusable PNG crops, source coordinates/hashes and PP-OCRv5/Tesseract evidence. After it completes, the batch runs PaddleOCR-VL, GLM, Monkey and MinerU sequentially in separate processes. It requires Mac GPU access. Output and progress live under `runs/sponsor_all/`, including `report.html`, `tables.json`, `batch_status.json`, per-engine logs and the final evidence audit. Restarting resumes successful matching records; a process lock prevents concurrent batches targeting the same output.

The report updates after each model's first crop, every ten crops and at stage completion. Completion of recognition is distinct from correctness review. Existing known crop-context and missed-table limitations still apply. No 4 GB-or-larger checkpoint is added.

Full preprocessing completed: 140 pages, 103 retained table candidates, 15 nested duplicate detections suppressed, and 206 successful baseline outputs (PP-OCRv5 and Tesseract). The preprocessing audit verified crop hashes, recomputed native summaries and all 243 embedded report images. Coverage by document is saved in `results/sponsor_all/preprocessing_summary.json`. All remaining recognition stages are now complete; `results/sponsor_all/final_audit.json` records six engines with 103 outputs each.

## Confidence versus accuracy tracking

`accuracy_selection.json` fixes 20 development crops spanning all six sponsor PDFs. `accuracy_references.json` contains original-PDF numeric inventories for digital pages and source-image transcriptions for scanned pages. All 20 were visually checked by the assistant without deriving references from OCR outputs; none is independently human-verified. The clipped narrative fragment in RR release page 17 makes that crop descriptive-only, leaving 19 primary cases across five issuer clusters. These are selected examples, not a random or held-out sample.

The primary correctness proxy is numeric multiset F1: match numeric value occurrences, retaining signs, percentages and percentage-point suffixes, while normalizing commas, equivalent decimal forms, compact month dates and markup. Dates and note markers count in this primary metric. A separate expected-financial-value recall excludes annotated metadata numbers; that secondary measure does not penalize extra numbers. Neither metric catches swapped columns, incorrect associations, omitted table regions, missing nonnumeric labels, or currency/scale mistakes.

For each engine, tracking reports Spearman rank correlation, error-detection AUROC, issuer-cluster bootstrap intervals, fixed confidence thresholds, and error after rejecting the lowest-confidence 20% with ties kept together. No correctness calibration or learned quality model is fitted. Constant correctness outcomes are explicitly labelled as insufficient variation, not missing model confidence. Secondary mean, p10 and content-only confidence comparisons retain their own sample sizes.

Install `matplotlib==3.10.8` in the chosen evaluation environment for plotting; it is separate from the recognition lockfiles.

```sh
.venv/bin/python evaluate_table_accuracy.py
.venv/bin/python plot_table_accuracy.py
.venv/bin/python follow_accuracy_batch.py
```

The finite follower updates `runs/sponsor_all/accuracy/report.html`, `tracking.json`, `pairs.csv`, and the scientific PNG/SVG plot as selected model results arrive. It finishes after the current recognition batch completes, copies compact results into `results/sponsor_all/accuracy/`, and repairs the main report with the current reporting code. `accuracy/progress.json` records its status. It never sends notifications or starts new inference. Existing reviews are retained. `prepare_accuracy_references.py` creates drafts only and refuses to overwrite reviewed reference edits.


### Completing the matched comparison

`evaluate_table_accuracy.py --require-complete` rejects a final comparison unless all six models have exactly the same eligible crop IDs, without duplicates or missing native scores. `tracking.json` records this matched-cohort audit. The additional twentieth crop remains descriptive-only. The fixed primary metric and reviewed references are unchanged.

`resume_sponsor_batch.py` recovers the November 15 run after a report-image read stalled at Monkey crop 100. It preserves successful matching outputs, completes remaining inference sequentially with intermediate report refreshes disabled, then rebuilds and audits the reports. The pre-recovery batch status is retained. This changes scheduling/report frequency, not recognition settings or scores.

Recommended next step: independently review reference cell grids and score financial facts `(row label, period, signed value, currency/unit/scale)`. Report fact precision/recall/F1 and all-critical-facts-correct table rate. Evaluate layout recall and crop completeness separately; use GriTS (https://arxiv.org/abs/2203.12555) for comparable cell-grid outputs. Plain OCR output needs a separately evaluated structure stage. Expand to harder sponsor-like documents toward the planned 60-document corpus, hold out issuers, and measure critical errors remaining at fixed automatic-acceptance coverage before fitting a quality predictor.

Startup delay diagnosis: macOS marked the original MinerU checkpoint and some dependency/source files as `dataless` cloud placeholders. Explicit iCloud download requests restored the unchanged files, after which inference proceeded. The direct MinerU runner used the same settings and shared crops while the original worker was paused. For future work, keep the real checkout, environments, model weights and runs outside Desktop/Documents iCloud folders; a Finder alias on Desktop can point to the local checkout. Virtual-environment launcher paths may need repair or recreation after a move.

### Local execution

Keep the checkout, model weights, Python environments and runs outside iCloud-synced Desktop/Documents folders. `finish_local_comparison.py` resumes saved successful MinerU crops, audits all six engines and requires the identical 19-crop cohort before finalizing the report. The pipeline uses paths relative to this checkout; machine-specific migration receipts are ignored.
