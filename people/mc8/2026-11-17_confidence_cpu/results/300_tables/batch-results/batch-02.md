# Cumulative confidence experiment results

**Tables completed:** 200 / 2,000  
**Batches completed:** 2 / 20  
**Scored outputs:** 1,400

Updated: 2026-11-18 04:35:34 EST (America/New_York).

## Accuracy by configuration

| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 200 | 200 | 0 | 0 | 0 | N/A | 3.06% | 0 |
| PP-OCRv5 | 200 | 200 | 0 | 0 | 0 | N/A | 82.81% | 0 |
| MinerU (text) | 200 | 200 | 0 | 0 | 0 | N/A | 81.99% | 0 |
| PaddleOCR-VL-1.6 | 200 | 200 | 0 | 0 | 190 | 0.8778 | 99.17% | 0 |
| GLM-OCR | 200 | 200 | 0 | 0 | 190 | 0.6017 | 90.43% | 0 |
| MonkeyOCR-pro-1.2B | 200 | 200 | 0 | 0 | 190 | 0.4746 | 81.83% | 0 |
| MinerU (table) | 200 | 200 | 0 | 0 | 190 | 0.7660 | 97.75% | 0 |

Fact F1 measures associated financial facts on a 0–1 scale. Number recall measures the share of reference numbers recovered. Higher values are better for both. Text-only configurations have no fact F1; N/A is not zero.

## Development

Tables scored: 200 / 1,600.

| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 200 | 200 | 0 | 0 | 0 | N/A | 3.06% | 0 |
| PP-OCRv5 | 200 | 200 | 0 | 0 | 0 | N/A | 82.81% | 0 |
| MinerU (text) | 200 | 200 | 0 | 0 | 0 | N/A | 81.99% | 0 |
| PaddleOCR-VL-1.6 | 200 | 200 | 0 | 0 | 190 | 0.8778 | 99.17% | 0 |
| GLM-OCR | 200 | 200 | 0 | 0 | 190 | 0.6017 | 90.43% | 0 |
| MonkeyOCR-pro-1.2B | 200 | 200 | 0 | 0 | 190 | 0.4746 | 81.83% | 0 |
| MinerU (table) | 200 | 200 | 0 | 0 | 190 | 0.7660 | 97.75% | 0 |

## Cohort in this report

| Metric | Count |
| --- | --- |
| Unique crops | 200 |
| Scored outputs | 1400 |
| Crops with financial reference facts | 190 |
| Crops without financial reference facts | 10 |
| Source reports | 36 |
| Issuers | 6 |
| Issuers with financial facts | 6 |
| Held-out test crops | 0 |
| Held-out test issuers | 0 |
| Configurations | 7 |
| Models | 6 |

Source reports count distinct manifest document names. These are cropped table images. MinerU text/table share one model.

## Additional accuracy, confidence and runtime metrics

| Configuration | GriTS content F1 | GriTS tables | Number recall tables | Native numeric coverage | Mean native numeric | Native range | Median recognition (s) | Timed outputs | Truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tesseract | N/A | 0 | 190 | 119 / 200 | 0.3246 | [0.0000, 0.7576] | 0.2465 | 200 | 0 |
| PP-OCRv5 | N/A | 0 | 190 | 200 / 200 | 0.9553 | [0.6698, 0.9982] | 8.8110 | 200 | 0 |
| MinerU (text) | N/A | 0 | 190 | 196 / 200 | 0.9792 | [0.8126, 1.0000] | 11.2940 | 200 | 7 |
| PaddleOCR-VL-1.6 | 0.9634 | 200 | 190 | 199 / 200 | 0.9966 | [0.9657, 1.0000] | 10.3755 | 200 | 0 |
| GLM-OCR | 0.8918 | 200 | 190 | 200 / 200 | 0.9879 | [0.8240, 1.0000] | 16.5365 | 200 | 1 |
| MonkeyOCR-pro-1.2B | 0.8576 | 200 | 190 | 200 / 200 | 0.9411 | [0.6439, 0.9999] | 31.0800 | 200 | 0 |
| MinerU (table) | 0.9352 | 200 | 190 | 200 / 200 | 0.9909 | [0.8733, 1.0000] | 11.7335 | 200 | 0 |

GriTS measures cell-content similarity and is averaged over its available saved scores. Its denominator can differ from financial fact F1. Native numeric coverage counts non-null native numeric confidence, including valid zero values; confidence is not correctness probability. Recognition times use saved per-output seconds within this prefix, including first-output setup, and exclude separate scoring/calibration. Sam’s pasted runtime medians instead pool all his cohorts.

## Financial F1 outcome counts

| Configuration | Eligible F1 tables | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 190 | 52 | 129 |
| GLM-OCR | 190 | 120 | 66 |
| MonkeyOCR-pro-1.2B | 190 | 155 | 32 |
| MinerU (table) | 190 | 85 | 101 |

Exact means F1 ≥ 1 − 1e−9 under the saved scorer; it does not certify the whole table.

## Native numeric confidence ranking — development

Within-model association between native numeric confidence and financial fact F1. These are descriptive development results, not held-out validation. Sam’s ranking definitions and 1,000 issuer-bootstrap resamples are reused. Only rows with both confidence and F1 enter this table; missing confidence is excluded here, while the accuracy table retains all eligible F1 rows. No confidence feature is selected here.

| Configuration | Rows | Issuers | Mean F1 | Mean native | Native range | Spearman | Spearman 95% issuer CI | Error AUC (F1 < 0.95) | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 189 | 6 | 0.8780 | 0.9968 | [0.9657, 1.0000] | 0.3972 | [0.2131, 0.5109] | 0.7111 | 51 | 129 |
| GLM-OCR | 190 | 6 | 0.6017 | 0.9873 | [0.8240, 1.0000] | 0.5779 | [0.3906, 0.6830] | 0.8263 | 120 | 66 |
| MonkeyOCR-pro-1.2B | 190 | 6 | 0.4746 | 0.9389 | [0.6439, 0.9999] | 0.5205 | [0.1375, 0.7343] | 0.9073 | 155 | 32 |
| MinerU (table) | 190 | 6 | 0.7660 | 0.9905 | [0.8733, 1.0000] | 0.5844 | [0.3844, 0.6427] | 0.8487 | 85 | 101 |

Error AUC treats lower confidence as an error signal. N/A includes undefined correlation (constant data), one-class AUC, or insufficient issuer clusters for a confidence interval.

## Measurement flags and audit status

References are public benchmark annotations; independent human audit is pending. Flagged cases remain included. This report does not claim Sam’s audit passes for these new outputs.

No saved measurement flags in this prefix.

Post-inspection exclusion sensitivity: not computed; the original scoring denominator is retained.

## Held-out forecast quality

Pending means calibration and held-out forecasts are not available for this prefix. Calibration freezes after all 1,600 development tables. No fit is performed to fill this report. Text-only configurations have no expected-F1 forecast.

| Configuration | Test rows | Issuers | MAE | Baseline MAE | MSE | Baseline MSE | MSE gain | MSE gain 95% issuer CI | Selected feature (rows) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 0 | 0 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| GLM-OCR | 0 | 0 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| MonkeyOCR-pro-1.2B | 0 | 0 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| MinerU (table) | 0 | 0 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

MAE uses the 0–1 F1 scale; multiply by 100 for percentage points. Positive MSE gain means lower error than the development-mean baseline. These metrics use held-out test rows only.

## Review policy on held-out forecasts

The review cutoff is learned from development confidence. Errors mean F1 < 0.95; kept accuracy is mean F1. No acceptance threshold is selected from the current report prefix.

| Configuration | Reviewed / total | Errors | Caught | Error capture | Kept | Kept coverage | Kept mean F1 | All mean F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| GLM-OCR | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| MonkeyOCR-pro-1.2B | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| MinerU (table) | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

## Interpretation

- Results include the scored prefix only; tables that have not run are excluded.
- Failed or missing outputs within that prefix remain in the scoring denominator.
- Development scores are descriptive. Held-out test results are reported separately.
- Calibration freezes after all 1,600 development tables, before test inference.
- Native confidence features are saved in the per-table `pairs.json` files.
- Expected F1 and native confidence are not the probability that an entire table is correct.
- References are public labels; human audit is pending. Flagged measurements stay visible.

The matching JSON summary retains the original precision and forecast details. Additional metrics and source-score hashes are in the companion `*-metrics.json` file.
