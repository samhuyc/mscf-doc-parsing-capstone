# Native parsing confidence prototype

This experiment attaches **the engine's own confidence signal to the text it produced in the same inference**, summarizes those signals per page/document, and independently compares them with reference text. It does not use agreement between parsers, ask a model to state its confidence, or train a correctness predictor from sponsor labels.

See [the measured results](results/REPORT.md) and [confidence-versus-accuracy chart](results/confidence_vs_accuracy.png).

## Measured run

All three adapters processed all six PDFs / 140 pages each. They recorded 49,645 Tesseract word scores, 9,602 PaddleOCR line scores, and 107,280 MinerU subword-token probabilities. Eight MinerU pages reached the token limit; processed-page coverage must not be confused with complete generation.

| Engine | Spearman: character-weighted mean | Spearman: geometric mean |
|---|---:|---:|
| Tesseract | 0.880 | 0.108 |
| PaddleOCR | -0.152 | 0.698 |
| MinerU recognition | Undefined | Undefined |

These correlations use only six documents and 13 draft reference snippets. MinerU matches all 13 snippets, making reference accuracy constant, while the references miss its repetition failures. Aggregation choice matters, and these data do not establish a generally calibrated document-quality score. The strict reviewed-reference evaluation has zero eligible labels. All 20 tests and the full saved-output integrity audit passed.

Yujie's latest imported work (`5bb964d`) already separates parsing/extraction evaluation from confidence: her MinerU CPU pilot reports ExtractBench value F1, and her evaluation framework checks transcription, structure and field associations. Those measure correctness against references. This prototype adds native inference signals and checks whether they track correctness; it does not replace that evaluation work.

## What the scores actually mean

| Adapter | Native signal | Important scope |
|---|---|---|
| Tesseract | TSV word `conf`, preserved raw and divided by 100 | PyMuPDF renders pages; standalone Tesseract recognizes them. It uses the existing project's English language data, but this is not the unchanged PyMuPDF integrated OCR wrapper. All pages are forced through OCR, including digital PDFs. |
| PaddleOCR | PP-OCRv5 mobile recognition `rec_scores`, paired with `rec_texts` and polygons | Recognition-line confidence. The CTC postprocessor averages selected character scores after duplicate/blank removal. It does not measure whether detection found all text, nor table/layout correctness. Score filtering is disabled (threshold 0). |
| MinerU | Selected-token log-softmax from the local MinerU2.5-Pro-2605-1.2B decoder through MLX | Subword tokens, not words. Greedy decoding, no repetition penalty/logit bias. The probability distribution is read before sampling; temperature zero does not turn the recorded confidence into 1. This adapter performs full-page text recognition, not MinerU's complete layout/table pipeline. |

PyMuPDF's direct extraction of embedded PDF text has no neural decoder distribution to expose. A Tesseract score belongs to the OCR output that Tesseract produced; it must not be attached to different text from direct PDF extraction.

MinerU's final streaming event may repeat the last token or carry EOS. The adapter avoids double counting and excludes EOS. It retains full emitted text plus selected token IDs/log-probabilities; a token limit is recorded as truncation, never hidden as complete extraction. Whole-page recognition at a maximum image side of 1536 is an explicit experimental configuration, not a replication of the previous crop-based pipeline. Model/config hashes and package versions accompany each run.

MLX's decoder normalization runs at model precision (BF16 here), which can round selected log-probabilities to zero. The adapter re-normalizes the entire exposed distribution in FP32 before reading the selected-token probability, and retains both the original backend value and normalization correction. This changes neither token choice nor temperature and uses no reference labels; it corrects numerical normalization, not statistical calibration. Tests check that the probabilities sum to one and are invariant to a common logit shift.

## From units to a document statistic

For returned units with scores `s_i`, the initial primary summary is `sum(w_i * s_i) / sum(w_i)`, with `w_i` the number of output characters (minimum 1). This prevents a short line from counting as much as a long line. All scored units across pages are pooled; page means are not averaged equally.

The same output also includes unweighted mean, geometric mean `exp(mean(log(s_i)))`, lower tenth percentile, minimum, and fraction below 0.90. For MinerU, mean/geometric mean over subword-token probabilities are particularly natural; character weighting of individually decoded tokens is only a diagnostic because token boundaries and Unicode fragments are imperfect character units. A true zero makes the geometric mean zero; the implementation does not invent a floor to improve results.

None of these is `P(entire document correct)`. Multiplying thousands of scores is length-sensitive and does not model omissions; independence assumptions would be unjustified. Even an exact sequence likelihood is not the probability that the transcription matches the image. Every result explicitly carries `probability_document_correct: null` and `calibrated: false`.

Page coverage, failures, empty pages and truncation are separate from confidence. All requested pages being processed is not proof that all their text was detected. Missing scores stay null. Inference never opens the labels file.

The actual MinerU recognition run produced high-confidence repetition: Hippodrome page 36 repeated underscores at mean token confidence about 0.997, and Rolls-Royce release page 25 repeated “Underlying operating profit/(loss)” at about 0.999. Both reached the 4,096-token cap. Those outputs are retained and flagged, not silently trimmed or assigned an invented confidence penalty. Repetition can dominate an output-length-weighted summary. These observations concern this full-page, greedy recognition configuration; they are not a benchmark claim about the complete MinerU pipeline.

## Evaluation and calibration

The available benchmark contains six PDFs / 140 pages, but only 13 text/footnote reference snippets across those six PDFs. They are existing assistant-authored **drafts**, not independently verified ground truth. The 133 table cells are not treated as transcription labels: evaluating those needs cell/row/column association, beyond this prototype.

The evaluator uses source-hash checks and normalized text (Unicode NFKC, case, whitespace, common quote/minus variants, and escaped punctuation such as `\$` becoming `$` without removing the currency sign). Because snippets lack exact bounding boxes, it aligns the full reference to the minimum-edit output substring on the stated page using semi-global Levenshtein alignment. Missing output receives zero accuracy. This is selected-span accuracy, not whole-document accuracy; repeated phrases and reference-selected windows can make it optimistic. Unit tests compare the alignment against exhaustive search on small examples.

It reports per-engine Spearman rank correlation and Pearson correlation between document confidence and selected-span accuracy, for all five declared summaries. It does not pick the best summary after seeing the results. Six documents, including two from one issuer, are insufficient to establish generalization. Exact permutation p-values in JSON are exploratory and assume exchangeability, which the shared issuer weakens.

For native word-score output, it additionally aligns the selected reference/output words, labels exact matches, and reports confidence-bin accuracy, Brier score and ten-bin ECE. These are diagnostics of the normalized native score as a probability proxy. Deletions have no emitted-word score and are recorded separately. Line and subword scores are not misrepresented as word scores. Most reference words are easy and high-confidence; this selection is not a calibration dataset.

A defensible next calibration experiment would define the target first: word exactness, expected character accuracy, or a document quality threshold. Review and locate a broader reference sample, include omissions and difficult pages, split by document/issuer, fit a simple monotone mapping on a calibration split, and evaluate it on untouched documents. Report raw and calibrated scores together. Calibrating word correctness does not automatically calibrate document correctness.

## Run locally

From this directory, with Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Install Tesseract separately, e.g. brew install tesseract on macOS.
.venv/bin/python run_tesseract.py
.venv/bin/python run_paddle.py
.venv/bin/hf download opendatalab/MinerU2.5-Pro-2605-1.2B --revision bff20d4ae2bf202df9f45284b4d43681555a97ed --local-dir work/mineru-model
.venv/bin/python run_mineru.py --model work/mineru-model
.venv/bin/python evaluate.py runs/tesseract runs/paddle runs/mineru --include-drafts
.venv/bin/python audit.py runs/tesseract runs/paddle runs/mineru
.venv/bin/python plot_results.py
.venv/bin/python -m unittest -v test_native
```

The measured Tesseract run used the pre-existing sponsor environment with PyMuPDF 1.28.2; the new environment uses PyMuPDF 2.1. A different renderer version may change pixels/scores, so `settings.json` records that distinction and prevents silent reuse under a changed configuration. Use a new `--output` directory for different settings.

`environment.lock.txt` records the complete working environment after dependency resolution. Tesseract expects the project's existing `eng.traineddata` in the sponsor sample cache; provide `--tessdata /path/to/tessdata` if it is elsewhere. The measured language-file hash is retained in settings. On this 16 GB Mac, two simultaneous MinerU workers exhausted GPU memory; use one GPU worker. Completed page files survive an interrupted run and are reused on restart.

Each runner accepts `--documents` and `--pages` for smaller runs. Tesseract also accepts `--binary`, `--tessdata`, `--dpi`, `--workers`, and `--timeout`. The existing inputs and manifest are reused with SHA-256 checks. Results are resumable at page boundaries; a recorded failed page must be moved aside before retrying. Do not run two writers on the same page output.

Without `--include-drafts`, only references marked `human_verified` or `adjudicated` are evaluated. The current reviewed-only result has no qualifying references, so accuracy/correlation remains unavailable rather than pretending draft labels were verified.

Use `evaluate.py --labels /path/to/reviewed_labels.jsonl` to evaluate new references for these documents without editing teammates' labels. Each text/footnote record needs `id`, `document`, `page`, `kind`, `source_sha256`, `text`, and `review_status` in the existing pilot format. Inference can be rerun without any reference file; evaluation can be rerun without loading a model.

Raw page outputs and downloaded models stay in ignored `runs/` and `work/`; compact measured summaries, settings and evaluation results are retained in `results/`. No documents are sent to an inference service. Package/model downloads require network access; MinerU inference requires an Apple Silicon GPU for this adapter.

## Evidence and sources

- [PaddleOCR OCR API](https://www.paddleocr.ai/v3.3.0/en/version3.x/pipeline_usage/OCR.html): recognition texts/scores and configuration. The installed PaddleX 3.3.13 `text_recognition/processors.py` was inspected to confirm CTC score aggregation.
- [Tesseract API reference](https://tesseract-ocr.github.io/tessapi/5.x/a02438.html): word confidence and recognition API. TSV output is read directly from Tesseract 5.5.3.
- [MLX-VLM source](https://github.com/ml-explore/mlx-vlm): installed version 0.3.9 `generate.py` exposes `logits - logsumexp(logits)` and streaming token/log-probability results. The installed code was inspected, including final-event behavior.
- [MinerU model](https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B): existing local revision `bff20d4ae2bf202df9f45284b4d43681555a97ed`; the adapter mirrors the existing MinerU MLX tied-embedding compatibility fix in a temporary config without modifying weights.

Jev/Clef and cross-model agreement are not part of this experiment. They are separate hypotheses, not substitutes for measuring a parser's own confidence.
