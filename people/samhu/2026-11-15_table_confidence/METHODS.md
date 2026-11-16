# Methods and reproduction

## Inputs and layout

Six sponsor PDFs, 140 pages, 103 retained table candidates; 15 nested detections suppressed. `sponsor_all.json` fixes the pages. Render at 200 DPI; use pinned PP-DocLayout_plus-L with threshold 0.5, 95% containment suppression and 2% padding. Keep source coordinates, settings and hashes. Detections do not establish financial relevance.

Known layout issues (`layout_review.json`): a missed reconciliation on Hippodrome p36, grouped subtables on Rolls-Royce presentation p9, and excluded shared headers on Rolls-Royce release p25. These are assistant observations. Layout recall and crop completeness remain unmeasured.

## Recognition and confidence

All engines receive the same source crops, with their own internal image processing. Weights are unchanged; no training, quantization or calibration.

- PP-OCRv5: native CTC character probabilities. Tesseract: word certainty divided by 100.
- VLMs: native emitted-token probabilities, normalized in FP32; greedy decoding, maximum 4,096 tokens. EOS/lookahead excluded. Primary scores include formatting.
- Primary aggregation: geometric mean. Secondary: arithmetic mean, p10, fraction below 0.90 and conservative content-only subsets. Zero stays zero; missing evidence stays null. GLM decoding revisions sometimes prevent content alignment, without invalidating its primary score.
- Score collection preserves logits. Additional VLM adapters passed first-crop output/token/stop equivalence against an uninstrumented control; this does not establish publisher-backend parity.

Shared crops and table prompts replace publisher layout pipelines. MinerU uses its recognition component (`Text Recognition:`, maximum side 1536), not its full pipeline. Monkey uses checkpoint processor limits and disables the publisher's 1.05 repetition penalty; no automatic table-closing repair. Paddle retains OTSL output verbatim. GLM's adapter removes a verified redundant configuration field from a temporary copy; its auxiliary prediction layer is unused. MLX/CUDA parity is untested.

Checkpoint sizes: PaddleOCR-VL-1.6 1.930 GB; GLM-OCR 2.657 GB; MonkeyOCR-pro-1.2B 3.825 GB; MinerU weights 2.312 GB. Runtime memory can exceed file size. DeepSeek-OCR-2 was excluded at 6.789 GB. See `model_candidates.json` and download provenance for revisions.

## Evaluation

`accuracy_selection.json` selects 20 development crops; the clipped fragment on Rolls-Royce release p17 is descriptive-only. The primary cohort is exactly 19 crops across five issuers for every engine. References in `accuracy_references.json` were source-checked by the assistant, not independently human-verified. This is not a held-out benchmark.

Numeric multiset F1 retains duplicate counts, signs and percentage/point/magnitude suffixes; it normalizes grouping commas, equivalent decimals, compact dates and markup. Years and note numbers count. Secondary financial-value recall excludes annotated metadata but does not penalize extra values. Neither checks cell associations, labels, units or missing regions.

Within each model: Spearman correlation, error-detection AUROC, 2,000 issuer-cluster bootstrap samples, fixed confidence thresholds and rejection of the lowest-confidence 20% (ties together). Constant accuracy makes correlation undefined. Secondary summaries use their own available sample counts.

The final audit verifies 618 outputs/scores, crop hashes, recomputed confidence and 243 embedded images. Thirty focused tests passed. Two MinerU crops reached the token limit (release p28/t01 and p36/t03); successful execution does not imply complete transcription. Audit: `results/sponsor_all/final_audit.json`.

## Run locally

Keep the real checkout, weights and environments outside iCloud. Use Python 3.12 and separate environments pinned by `environment.lock.txt`, `environment-extra.lock.txt` and `environment-mineru.lock.txt`. MLX requires Apple Silicon GPU access. Plotting additionally needs `matplotlib==3.10.8`.

Inputs: `../2026-09-29_sponsor_samples/inputs/`. Native weights/baselines: `../2026-11-10_native_confidence/`. Raw inputs, weights, environments and full run evidence stay outside Git.

From this directory, after installing the environments and downloading the checkpoints:

```sh
.venv/bin/python download_layout.py
work/extra-env/bin/python download_extra_models.py paddle_vl glm monkey
.venv/bin/python run_tables.py --selection sponsor_all.json --output runs/sponsor_all
.venv/bin/python run_sponsor_batch.py
.venv/bin/python evaluate_table_accuracy.py --require-complete
.venv/bin/python plot_table_accuracy.py
.venv/bin/python verify.py runs/sponsor_all
```

Successful records resume only when hashes/settings match. Changed settings require a new output directory. `finish_local_comparison.py` resumes the saved MinerU run and finalizes the matched comparison. Reports retain reviews. Full local review: `runs/sponsor_all/report.html`; compact published evidence: `results/sponsor_all/`.

## Human review

`review_panel.py` serves the same 19 primary crops locally. MonkeyOCR supplies editable drafts, explicitly unverified; model-assisted annotation may bias comparison. Expanded merged headers retain column context. Confirm values, row/column associations, units and completeness against the source. Flag incomplete crops instead of approving them.

Reviews and revision history save under `runs/sponsor_all/review/`. Only explicit confirmation sets `human_verified`; any edit revokes approval. Source/draft hashes prevent stale reuse. Existing numeric metrics remain unchanged until the new structure-aware evaluation is implemented. No human reviews are fabricated.
