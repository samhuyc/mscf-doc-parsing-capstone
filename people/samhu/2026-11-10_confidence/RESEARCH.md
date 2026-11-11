# Confidence scoring: repository review and research

Research checked November 10, 2026. Jev and Clef identities were confirmed by Sam;
their use here remains a brainstorming hypothesis, not a selected solution.

## Repository changes reviewed

The checkout started clean on `main` at `946e4f2`, with origin
`git@github.com:samhuyc/mscf-doc-parsing-capstone.git`. Fetch found seven new commits
through `0baabab` (November 9). Update policy is fast-forward only, followed by a
feature branch; no reset, stash, rewrite, teammate-file edit, or force-push.

| Contribution | Findings relevant to confidence |
|---|---|
| Yujie, `5bb964d`, October 28 | Added pdfplumber findings, FinTabNet pilot, evaluation framework, and ExtractBench/LongExtract pilot. Detailed review below. |
| Michael, `818c2a1`, October 28 | PP-StructureV3 replication against unchanged sponsor labels. All 18 labeled pages are available, but only 46/140 physical pages were processed. Native JSON preserves OCR evidence; table counts exactly reproduce the prior scorer. |
| Oli, `7e7ad0a` and `0c65bc9` | Source-preserving section chunks, retrieval/context handoff and readable output guide. Confidence should preserve those source references; retrieval usefulness is a separate target. |
| Oscar, `fa15b01`, merged in `0baabab` | Validates positive chunking budgets before loading inputs. No confidence estimator added. |
| Yuyang, October 21 uploads | PyMuPDF/PubTabNet work predates the starting checkout. Cell-count similarity is a limited structural diagnostic, not confidence. |

### Yujie's F1 work: what it actually establishes

The [FinTabNet report](../../yujiezhu/2026-09-20_evaluation/RESULTS.md) reports
24/25 successfully scored table images, numeric F1 0.9355, exact cell accuracy
0.3185 and exact row accuracy 0.1645. Inspection of
`score_fintabnet_pilot.py` shows numeric F1 is a **bag-of-numbers** comparison,
ignoring row/column associations. It scores the first parsed table, uses zip-style
cell/row alignment, does not expand HTML spans, and averages over successes.
Accounting parentheses and contextual units are not fully captured by its number
regex. A high numeric F1 can therefore coexist with wrong structure or misplaced
values. The report discloses one missing-table failure. It is not a calibrated
probability and does not establish 93.55% confidence in a new table.

The newer [confidence-score pilot](../../yujiezhu/confidence%20score/README.md)
is more explicit about this distinction. Its saved report has only 3/9 completed
documents, all from ExtractBench: F1 24.00%, 59.09%, and 13.69%, averaging 32.26%
over completed/scored documents. Zero LongExtract tasks were scored. It used
MinerU 2.1.11 CPU plus a frozen conservative schema mapper, not MinerU Pro VLM.
The mapper omits unsupported fields; no page/box citations are supplied. Results
measure the combined parser and mapper. Unfinished tasks are disclosed and
excluded from that interim average, so it is not an official full-run score.

Yujie's source spot checks separate missing column associations from fields that
were present in parser text but omitted by the mapper. The newer evaluation
framework also addresses several older scorer limitations. Preserve this work:
it supplies useful **outcome definitions and labels**, which confidence prediction
needs. F1 itself is neither the missing confidence estimator nor a bad metric.

## Define the target before the score

| Level | Possible event to predict | Important boundary |
|---|---|---|
| Character/token | Aligned token transcription is correct | Tokenizer units differ from words; deletions have no returned token to score. |
| Field | Value, sign, units, period and source association all match a defined rubric | Requires explicit alignment and labels for that rubric; plausibility is insufficient. |
| Document | No critical field error; or all requested fields correct | These are different events from mean field accuracy and from completeness. |
| Quality/accuracy prediction | Expected fraction of requested fields correct, or predicted task score | A predicted quality statistic is not the probability that the entire document is correct. |

Keep raw model evidence, a fitted probability estimate, measured benchmark
accuracy, and any uncertainty interval as distinct fields. A confidence interval
for aggregate accuracy is not a per-document correctness estimate.

## Evidence available from the parsers

**PaddleOCR.** The official OCR output includes `rec_texts` and `rec_scores`,
filtered by the recognition threshold. PP-StructureV3 keeps OCR and layout/table
outputs separately. The CTC-style decoder removes blank/duplicate selections and
averages selected recognition confidences; decoder choice matters. A retained
line score does not measure missed regions, reading order, table structure or
field association. Preserve scores, threshold, geometry, decoder/model version
and filtering counts; instrument the recognizer if true aligned character/logit
features are needed. The prototype imports actual cached line scores, without
renaming them token probabilities. [Official OCR contract](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md),
[decoder implementation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/postprocess/rec_postprocess.py).

**MinerU2.5-Pro.** The April technical report describes a 1.2B coarse-to-fine
parser, data curation using cross-model consistency, and render-then-verify
annotation refinement. These training methods do not establish an exported
calibrated field-confidence interface. Our cached VLM metadata records package
3.4.5 with `MinerU2.5-Pro-2605-1.2B`, a different checkpoint from the April 2604
paper. Save the exact backend/checkpoint and distinguish detection scores from
recognition scores. If the chosen inference backend exposes selected-token
logprobs, preserve them before Markdown conversion; otherwise mark them missing.
The existing portable exports do not contain usable token-logprob traces.
[MinerU2.5-Pro paper](https://arxiv.org/html/2604.04771v2).
Current [MinerU output documentation](https://opendatalab.github.io/MinerU/reference/output_files/)
describes 4.1 and must not be used as a 2.5/3.4.5 API contract.

**PyMuPDF.** Native text extraction is PDF decoding, not probabilistic OCR.
`TextPage` outputs text, characters, positions and formatting; a successful call
does not prove faithful text, order or tables. Do not assign confidence 1.0.
PyMuPDF4LLM plus Tesseract or a VLM callback is a different pipeline: any OCR
evidence belongs to that OCR engine. Use extraction diagnostics, missing-page
signals, schema checks, independent source verification and parser disagreement
as candidate predictors. [Official TextPage API](https://pymupdf.readthedocs.io/en/latest/textpage.html).

### Are decoded probabilities or a probit model related?

Yes as candidate evidence, with different meanings. Discrete token probabilities
are probability masses, not a probability density over whole parsed documents.
For autoregressive generation, the sum of conditional logprobs is sequence log
likelihood under that model. A length-normalized geometric mean reduces length
effects but is not semantic correctness. CTC alignment paths and blank collapse
need different treatment; multiplying retained Paddle line scores is not a CTC
sequence probability. Logit margins, entropy (requiring distributions, not just
chosen-token scores), minimum/quantile scores and length can be features.
A probit link is an alternative binary regression link; it does not make an
uncalibrated decoder score reliable automatically. The prototype uses a sigmoid
link for simplicity.

## What HYCEDIS contributes

[HYCEDIS](https://arxiv.org/html/2206.02628v2) trains an auxiliary correctness
predictor from OCR activations, recognized text and key/value network logits,
plus a document-image anomaly detector. Its field label requires matching key,
text and location (IoU above 0.3). It evaluates ranking and calibration using AUC
and ECE, including an out-of-distribution dataset. Reported SROIE ECE is 0.1002
and AUC 88.12%; CORD results are weaker. Those are paper-specific measurements,
not transferable sponsor performance.

Despite the name “Multi-modal Conformal Predictor,” the described final estimator
uses supervised binary cross-entropy. The method does not provide the usual
split-conformal quantile construction or a finite-sample coverage guarantee.
Our reading is that its useful lesson is **learn to predict field errors from
multiple signals**, not read one confidence number out of Markdown. Reproducing
the full architecture would need internal features, image training and sufficient
field-level labels; it is beyond this prototype.

## How the proposed benchmarks fit

| Benchmark | Useful role | What it cannot provide alone |
|---|---|---|
| [LlamaIndex ExtractBench](https://github.com/run-llama/ExtractBench) | PDF + schema → structured extraction, value F1 and evidence-grounding checks; aligned outcomes can become correctness labels | A parser's Markdown is not the required schema extraction. F1 is observed performance, not an inference-time confidence signal. Pin schema, scorer and dataset revisions. |
| [LongExtractBench](https://github.com/micro1-research/longextract-bench) | Long-document JSON extraction; missing/repeated rows, leaf correctness and operational completion | Conditional accuracy on completed/matched outputs can hide omissions; retain completion and row-recall denominators. |
| [DocILE](https://github.com/rossumai/docile) | Business-document field localization (KILE), grouping into line items (LIR), and layout-generalization splits | Default localization matching is not exact text correctness. Text is an optional secondary evaluation. Prediction scores rank AP; supplying a score does not demonstrate probability calibration. |

There is also a distinct [Contextual AI paper named ExtractBench](https://arxiv.org/abs/2602.12247).
Yujie's pinned pilot uses **run-llama/ExtractBench**, so do not mix these datasets
or their reported results. For confidence evaluation, reuse the appropriate
official matcher, retain wrong and missing outputs, and add probability metrics.
None of these benchmarks is inherently a confidence estimator.

## Jev / Clef: a testable verifier hypothesis

[TypeSafe's documentation](https://docs.typesafe.ai/confidence) distinguishes
probabilities from the `confidence` statistic. For Choice with n options, the
latter is `(p_max - 1/n) / (1 - 1/n)`; Noul returns a yes probability and no separate
confidence. Therefore a high confidence in **incorrect** must not be mistaken for
a high probability that the extraction is correct. Preserve the probability of
the specifically defined correct/supported option.

[Cloudflare's Clef announcement](https://blog.cloudflare.com/clef-decision-models/)
describes typed decision probabilities, a Jev-compatible interface, open weights,
and calibration-oriented training including Brier loss. That establishes an
interface and training objective, not validated performance on Barclays documents.

Proposed experiment (not run): give a fixed verifier the original page/crop,
candidate field, row/header context, units and a frozen rubric. Ask whether that
specific extraction is supported, contradicted, or unverifiable. Keep source
content separate from instructions, version the prompt/model and retain the full
response. A verifier seeing only the parser's own text cannot reliably find OCR
content that was omitted or misread. Image support and exact API semantics must
be verified for the selected deployed version.

Compare verifier probabilities with native evidence, parser agreement, deterministic
validation rules and a constant base-rate baseline on identical held-out issuers.
Use adjudicated human labels rather than verifier agreement as truth. Measure
latency/cost and errors such as wrong year, wrong sign, missing row and plausible
hallucination separately. Add a second verifier only if it improves held-out
Brier/risk at useful coverage; shared errors and prompt sensitivity can defeat
the approach. No Jev/Clef calls, installations or performance claims are included
in this branch.

## Calibration and accuracy-prediction plan

[Guo et al.](https://proceedings.mlr.press/v70/guo17a.html) demonstrate that accurate
neural classifiers may be poorly calibrated and describe temperature scaling.
Temperature scaling is suitable when the relevant logits and labeled calibration
data are accessible. For scalar scores, sigmoid/Platt-style or isotonic mappings
are alternatives; for several signals, a regularized correctness classifier is
a stronger next experiment. Isotonic fitting can overfit a tiny calibration set.

Use three independent partitions when training a predictor: training, calibration,
and untouched test, grouped by issuer/template/source family. A fixed raw signal
needs only calibration/test separation. Report Brier and log loss (probability
quality), reliability/ECE (calibration), AUROC or error AUPRC (ranking), and
risk/coverage (review policy), alongside extraction accuracy and missing-field
coverage. Confidence intervals should resample issuer/document groups, not treat
hundreds of cells as independent documents. Five groups cannot support a strong
generalization claim.

For document-level all-correct probability, label and fit that event directly;
do not multiply correlated field probabilities. For expected requested-field
accuracy, mean field probabilities is a meaningful separate estimate. Completeness
needs missing-field/row labels and cannot be inferred from confidence on returned
values. Standard conformal sets or risk-control methods can be explored later
with appropriate exchangeability assumptions; they do not guarantee conditional
correctness on every document or under arbitrary distribution shift.

The immediate blocker to sponsor-grade confidence is independently reviewed,
diverse outcome data with enough errors. Additional sponsor reference materials
can refine the target and verifier rubric without blocking this offline prototype.
