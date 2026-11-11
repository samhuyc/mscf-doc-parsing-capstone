# Separate correctness models

Individual-feature logistic models are implemented and fitted for exploratory diagnostics. Numeric transcription and row/column association are separate targets. No validated per-cell probability is available yet.

| Target | Correct / total | Error families | Independent reviews | Out-of-family coverage | Errors in scored folds |
|---|---:|---:|---:|---:|---:|
| numeric | 45/50 | 1 | 0 | 80% | 0/5 |
| association | 30/50 | 2 | 0 | 100% | 20/20 |

## Actual out-of-family diagnostic results

| Target | Held family | Status | Brier loss | Training-rate baseline loss |
|---|---|---|---:|---:|
| numeric | cvs_2025q2 | experimental only | 0.0000 | 0.0156 |
| numeric | edf_2024 | training_partition_has_only_one_class | — | — |
| numeric | hippodrome_2025 | experimental only | 0.0001 | 0.0156 |
| numeric | rolls_royce_2026h1 | experimental only | 0.0000 | 0.0278 |
| association | cvs_2025q2 | experimental only | 0.0012 | 0.2500 |
| association | edf_2024 | experimental only | 0.0001 | 0.5625 |
| association | hippodrome_2025 | experimental only | 0.0012 | 0.2500 |
| association | rolls_royce_2026h1 | experimental only | 0.3906 | 0.2778 |

Lower loss is better, but partial coverage and draft labels prevent calibration claims. The association model struggles on the Rolls-Royce family: merged period headers are absent from its training documents. Numeric scored folds contain zero errors, so their small losses do not establish numeric-error detection.

## Why a probability is still withheld

The numeric errors in the current sample all come from EDF. Holding EDF out leaves training with no numeric errors, so that fold cannot fit a binary correctness model. The other numeric folds test only correct examples. A low loss on those folds would not validate error detection.

Association labels describe correct row and column bindings, independently of numeric content. Only EDF and the Rolls-Royce family contain association failures, so errors cannot appear in three disjoint training/calibration/test family partitions. Units remain a separate review target; no unit probability is inferred.

All existing labels are assistant-reviewed drafts. No synthetic errors, duplicated rows, other-parser labels or benchmark F1 scores are used as extra training truth.

## Implementation

- Numeric model: syntax, numeric/text agreement, comparison availability, token/decimal/digit counts, sign, currency and percentage markers.
- Association model: distinct row/value cells, unique comparison row, bound header, header availability/agreement/similarity.
- Fixed regularized logistic regression with fold-local scaling. No class balancing, oversampling or hyperparameter search against this sample.
- Four document-family folds; the two Rolls-Royce documents always stay together. Failed folds remain missing rather than receiving in-sample substitutes.
- Explicit verified-data workflow fits a base model on training families, a regularized sigmoid on calibration families, then reports raw/calibrated/baseline losses and reliability bins on test families. Successful execution does not automatically approve deployment.

## Files

- `data_audit.json`: exact data limitations per target.
- `diagnostics.json`: folds, coverage, losses and reliability bins. Diagnostic probabilities are uncalibrated experimental model outputs, not confidence scores.
- `exploratory_models.json`: fitted coefficients; deliberately not a deployed predictor.
- `feature_rows.json`: label-free numeric and association feature vectors.
- `review_queue.csv`: proposed labels plus blank human decision fields. Fill decisions only after reviewing the source.
- `split_template.json`: illustrates explicit family assignments; the current draft data will fail eligibility checks.

Source/render and annotation limitations remain in the parent README. More numerical variety does not establish that a probability is meaningful.
