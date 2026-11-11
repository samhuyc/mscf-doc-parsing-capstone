# Native confidence v2: methods and reproduction

Current outputs are in `results/v2/`; the original complete v1 run remains in `results/`. The sponsor brief is generated from saved evidence, not hand-entered statistics.

## Score extraction

**PaddleOCR.** PP-OCRv5 mobile uses a CTC decoder. `score_probes.py` intercepts its probability tensor before averaging. It removes decoder blanks and repeated adjacent predictions exactly as the existing decoder does, retaining the chosen character, timestep, probability, log probability and three alternatives. Repeated letters separated by a blank remain distinct. Text and native line scores pair batch-sorted crops back to page order. Raw pre-softmax logits are unavailable in this export; log probabilities are not relabeled as logits. These are selected-path character scores, not exact marginal final-character correctness probabilities. Probability sums are checked to tolerance 0.001; the maximum observed deviation is recorded in the precision audit.

**MinerU.** The local MinerU2.5-Pro-2605-1.2B model uses the same full-page image, prompt, greedy decoding and token limit as v1. The installed MLX-VLM decoder normalizes BF16 logits in model precision. A process-local, source-guarded hook replaces only that normalization expression. Original logits are promoted to FP32, centered at their maximum, then normalized using `log1p(sum(exp(other logits)))`. This retains tiny competing mass without adding it to 1 first. Every emitted token stores its original logit, corrected log probability, five alternatives, original backend log probability, and the v1 post-hoc correction evaluated on the same logits. EOS and duplicate final streaming events are excluded. No weights or installed packages are overwritten.

The optional FP32 forward check casts the BF16 checkpoint weights to FP32 and reruns CVS page 1. It checks computation precision, not recovery of information already absent from checkpoint weights. Mean probabilities are 0.97289772 native versus 0.97387256 in FP32, with identical text and token IDs. One page cannot establish behavior across the corpus.

## Aggregation and references

Character-weighted mean pools emitted units across pages. Geometric mean gives each unit equal weight and penalizes low probabilities more. Spaces are retained in both Paddle character and MinerU token summaries. The weighted arithmetic mean over Paddle characters is approximately equivalent to character-weighting native line means; retaining characters chiefly enables finer diagnostics and different nonlinear summaries. A true zero makes the geometric mean zero. Neither statistic measures missing text or calibrates correctness.

The existing 13 draft snippets are unchanged. Best-window matching normalizes case/whitespace and can overlook repeated copies elsewhere. All snippets and all three matched outputs are in `snippet_examples.json`. Document correlations exclude incomplete rerun documents.

`evaluate_pages.py` extracts sorted embedded text from every source PDF without consulting OCR output. There are 89 eligible pages and 51 scanned pages with no text layer. The deadline comparison uses the same 23 completed pages for all engines. CER is full-page character edit distance divided by reference length; agreement is `max(0, 1-CER)`. It penalizes extra/missing text but also reading-order and serialization differences. PDF text layers are unreviewed weak references, not gold truth. The selected pages cluster in four PDFs from three issuers and include a deliberately targeted failure. No generalization or calibrated accuracy claim follows.

Current coverage is 80 Paddle and 74 MinerU pages. Output text is unchanged from v1 on every completed page. Only CVS and EDF currently have both complete rerun coverage and complete embedded-text references. Four documents have complete rerun coverage for the snippet comparison. Remaining pages are pending because presentation examples took priority at the user's deadline.

## Reproduce or resume

Use the existing environment or the pinned dependencies in `environment.lock.txt`. From this directory:

```sh
python run_paddle.py
python run_mineru.py --model work/mineru-model
python run_mineru.py --model work/mineru-model --model-dtype float32 --output runs/mineru_fp32_check --documents cvs_2025q2 --pages 1
python finalize_v2.py
python -m unittest -q test_native test_score_probes
```

The new default outputs are `runs/paddle_v2` and `runs/mineru_v2`. Completed pages resume without regeneration. Use only one MinerU GPU worker at a time. `finalize_v2.py` audits saved units, consolidates partial runs, evaluates identical available pages, exports evidence and rebuilds the offline HTML. It never fills missing new scores with old ones. Raw model files and page records stay ignored locally; compact evidence and summaries are tracked. Source PDF hashes and settings accompany the outputs.

The 29 tests cover CTC blank/duplicate handling, crop-order association, whitespace preservation, stable normalization including tied logits and tiny tails, stream alignment, full-page repetition penalties and the original evaluation logic. Saved-output audits also verify line-score reconstruction and original-logit/token associations.
