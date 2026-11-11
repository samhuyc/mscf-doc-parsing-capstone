# Parsing confidence prototype — November 10, 2026

This experiment adds **field correctness prediction**, separate from the team's
accuracy benchmarks. It replays five saved parser pipelines, extracts a fixed
parser-agreement signal without reference values, and evaluates a small sigmoid
calibrator on held-out issuer groups. It does not modify teammates' code or outputs.

Start with [the measured replay](results/exploratory/SUMMARY.md) and
[the research and repository review](RESEARCH.md).

## What works now

- `confidence.py`: dependency-free signal helpers, a serializable calibrator,
  fit/score/evaluate commands, Brier/log-loss/ECE/AUROC, reliability bins,
  tie-aware risk/coverage curves, and document summaries.
- PaddleOCR 3 / PP-StructureV3 native JSON adapter: retained **line** recognition
  scores remain raw. It rejects text/score misalignment instead of truncating.
- Selected-token log-probability summaries: count, sum, mean, geometric mean;
  these do not become text-correctness probabilities automatically.
- Field support from normalized peer outputs; unresolved values remain `null`.
- Separate calibration per parser, configuration, signal kind and correctness
  target; incompatible models are rejected. Draft labels require explicit opt-in.
- `benchmark_pilot.py`: read-only replay of the existing gold-blind table adapter
  and cached exports from commit `0baababc2652757982ae5898500a1c72409c4848`.
  It reads Git objects so local files and old reports are not changed. Input and
  implementation hashes, model fits, parser configurations and predictions are saved.

## Reproduce

From this directory, use the existing sponsor environment:

```sh
PY=../2026-09-29_sponsor_samples/.venv/bin/python
"$PY" -m unittest -v
"$PY" benchmark_pilot.py --output results/reviewed
"$PY" benchmark_pilot.py --include-drafts --output results/exploratory
```

On a fresh checkout, create a Python 3.12 environment and install
`requirements.txt`. The calibration core and `test_confidence.py` need only the
standard library; the pilot adapter needs the three pinned packages. Git history
must include the source commit. No PDFs, model downloads, GPU, or API keys are needed.

The default reviewed-only replay is **empty**: there are currently no verified
pilot table labels. The explicit exploratory replay contains 133 requested fields
× 5 pipelines = 665 records, across six documents and five issuer groups. The two
Rolls-Royce documents stay in the same group, across every page and parser.

## Meaning of the numbers

The fixed raw signal is `(1 + matching peers) / (1 + configured peers)`, only when
the candidate is resolved and at least one peer is configured. The one represents
the candidate itself; missing peers remain in the denominator. This is an
arbitrary support statistic, **not an independently justified probability**.
The five-pipeline roster is part of the configuration. Changing peers requires
new calibration. No reference value is supplied to signal construction.

For each held-out issuer and parser, fit `sigmoid(a * raw_score + b)` on resolved
fields from the other issuers. Fixed L2 penalties are 0.01 for the slope and 0.001
for the intercept; fixed-step gradient descent uses at most 2,500 updates.
One-class folds use a Beta(1,1)-smoothed constant rate. The comparison baseline
uses that training-only constant rate in every fold. This is calibration of a
fixed signal; no separately trained feature model is involved. A learned
multi-feature predictor would require separate training and calibration sets.

`p_correct` estimates this narrow event: **the declared row/header resolves to a
cell whose normalized amount/sign/suffix matches the pilot reference**. It uses
the existing `amount_key`, which ignores inline currency symbols and does not
infer scale. It does not certify currency, units inherited from headers, semantic
footnote attachment, undiscovered rows, or the whole page. Row/header names and
physical page IDs are taken from the pilot's requested schema; this retrospective
exercise is not blind schema discovery.

Missing/ambiguous cells have no `p_correct` and count as failures for requested-field
accuracy. Brier, log loss, ECE and AUROC are conditional on scored fields. Review
curves use the scored-field denominator; multiply their coverage by overall score
coverage for coverage of requested fields. Tied scores enter together. Empty
metrics and one-class AUROC are unavailable. ECE uses ten equal-width bins and
depends on binning/sample size. Pooled cross-fold AUROC compares different fitted
models; the report also includes within-fold metrics.

Document summaries report mean scored-field probability and, when every unscored
field is an explicit unresolved failure, expected accuracy over requested fields.
Linearity of expectation does not require independent fields. The probability
that **all** fields or the entire document are correct stays `null`; neither an
average nor a product is justified for that event here.

## Measured outcome and decision

All 16 tests pass. The replay exactly reproduces the saved associated-value
counts: MinerU OCR 54/133, MinerU VLM 95/133, PaddleOCR 71/133, PyMuPDF4LLM 115/133,
and PyMuPDF4LLM + VLM 109/133. These are diagnostics of the selected sample and
strict adapter, not population parser rankings.

The calibrator is **not uniformly better** than raw support or the base-rate
baseline. PaddleOCR Brier increases from 0.0628 to 0.0866 versus raw support,
although it beats the constant baseline's 0.1491. MinerU OCR also worsens versus
raw support. PyMuPDF variants beat their constant baselines only slightly and
have poor pooled error-ranking AUROC. All 95 resolved MinerU VLM fields pass the
draft check, so its near-zero Brier and undefined AUROC cannot demonstrate error
detection. Missing cells still reduce its requested-field accuracy to 71.4%.

Native Paddle line-score means on the ten table pages range from 0.8941 to 0.9855.
Those scores describe recognition of retained lines; they are not comparable
directly to field-association accuracy. We do not copy a page average onto each
field. Native-score-to-field alignment remains future work.

**Decision:** retain this as an offline experimental interface and benchmark.
Do not deploy an auto-accept threshold from these data. No production model is
published; each cross-validation fit is inspectable in `summary.json` and marked
`deployment_validated: false`.

## Use the generic interface

Input is a JSON array. A calibration record looks like this (illustrative only):

```json
{
  "id": "document-17/total", "document": "document-17", "group": "issuer-4",
  "source_sha256": "actual-source-sha256", "parser": "paddleocr",
  "configuration_id": "actual-model-settings-and-peer-roster-hash",
  "score_kind": "paddle_rec_score", "target": "exact_total_including_currency_v1",
  "raw_score": 0.98, "correct": 1, "review_status": "human_verified"
}
```

Supply real source identity, configuration identity and adjudicated labels.
Inference records omit `correct` and do not need review status. Never invent
scores for native PyMuPDF, a missing MinerU confidence field, or missing output.

```sh
python3 confidence.py evaluate labeled_records.json --output held_out.json
python3 confidence.py fit calibration_records.json --output model.json
python3 confidence.py score new_records.json --model model.json --output scored.json
```

`fit` supports one parser/configuration/signal/target per file. `evaluate` supports
multiple such groups. Use issuer/template groups that prevent related sources
from crossing folds. Source-hash checks catch the same file assigned to different
groups, but cannot discover unrecorded near-duplicates or shared templates.
The core intentionally leaves deployment validation to a separate held-out study.

## Tests and limits

Tests cover invalid/NaN scores, empty and zero scores, token-logprob underflow,
Paddle alignment, blanks versus omissions, unanimous wrong peers, known synthetic
overconfidence, one-class fits, model serialization/configuration mismatch,
draft-label gates, duplicated records, source-group leakage, held-out-label
perturbation, independently calculated metric values, tied thresholds, document
aggregation, reference-value isolation and ambiguous tables.

No sponsor-specific private material was uploaded. There were zero hosted calls
and zero parser reruns. Cached run metadata identifies MinerU package 3.4.5 and
MinerU2.5-Pro-2605-1.2B VLM weights; this is not a newly controlled model comparison.
The April MinerU2.5-Pro paper concerns the 2604 release, so its claims must not be
silently substituted for the cached 2605 configuration.

Next: independently review existing labels; obtain fresh documents, including
error-rich scans and cross-page tables; align native OCR evidence to actual fields;
then compare native-score, agreement, validation-rule and Jev/Clef verifier
features with the same issuer-disjoint protocol. Select review thresholds on a
validation set and audit risk/coverage on untouched test issuers.
