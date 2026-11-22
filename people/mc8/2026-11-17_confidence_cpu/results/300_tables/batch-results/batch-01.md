# Cumulative confidence experiment results

**Tables completed:** 100 / 2,000  
**Batches completed:** 1 / 20  
**Scored outputs:** 700

Updated: 2026-11-18 00:02:34 EST (America/New_York).

## Accuracy by configuration

| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 100 | 100 | 0 | 0 | 0 | N/A | 4.63% | 0 |
| PP-OCRv5 | 100 | 100 | 0 | 0 | 0 | N/A | 81.75% | 0 |
| MinerU (text) | 100 | 100 | 0 | 0 | 0 | N/A | 81.67% | 0 |
| PaddleOCR-VL-1.6 | 100 | 100 | 0 | 0 | 93 | 0.9006 | 98.98% | 0 |
| GLM-OCR | 100 | 100 | 0 | 0 | 93 | 0.5983 | 86.59% | 0 |
| MonkeyOCR-pro-1.2B | 100 | 100 | 0 | 0 | 93 | 0.4251 | 75.13% | 0 |
| MinerU (table) | 100 | 100 | 0 | 0 | 93 | 0.7728 | 96.78% | 0 |

Fact F1 measures associated financial facts on a 0–1 scale. Number recall measures the share of reference numbers recovered. Higher values are better for both. Text-only configurations have no fact F1; N/A is not zero.

## Development

Tables scored: 100 / 1,600.

| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 100 | 100 | 0 | 0 | 0 | N/A | 4.63% | 0 |
| PP-OCRv5 | 100 | 100 | 0 | 0 | 0 | N/A | 81.75% | 0 |
| MinerU (text) | 100 | 100 | 0 | 0 | 0 | N/A | 81.67% | 0 |
| PaddleOCR-VL-1.6 | 100 | 100 | 0 | 0 | 93 | 0.9006 | 98.98% | 0 |
| GLM-OCR | 100 | 100 | 0 | 0 | 93 | 0.5983 | 86.59% | 0 |
| MonkeyOCR-pro-1.2B | 100 | 100 | 0 | 0 | 93 | 0.4251 | 75.13% | 0 |
| MinerU (table) | 100 | 100 | 0 | 0 | 93 | 0.7728 | 96.78% | 0 |

## Cohort in this report

| Metric | Count |
| --- | --- |
| Unique crops | 100 |
| Scored outputs | 700 |
| Crops with financial reference facts | 93 |
| Crops without financial reference facts | 7 |
| Source reports | 20 |
| Issuers | 3 |
| Issuers with financial facts | 3 |
| Held-out test crops | 0 |
| Held-out test issuers | 0 |
| Configurations | 7 |
| Models | 6 |

Source reports count distinct manifest document names. These are cropped table images. MinerU text/table share one model.

## Additional accuracy, confidence and runtime metrics

| Configuration | GriTS content F1 | GriTS tables | Number recall tables | Native numeric coverage | Mean native numeric | Native range | Median recognition (s) | Timed outputs | Truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tesseract | N/A | 0 | 93 | 67 / 100 | 0.3072 | [0.0000, 0.7576] | 0.2435 | 100 | 0 |
| PP-OCRv5 | N/A | 0 | 93 | 100 / 100 | 0.9551 | [0.6698, 0.9981] | 7.9700 | 100 | 0 |
| MinerU (text) | N/A | 0 | 93 | 97 / 100 | 0.9768 | [0.8126, 1.0000] | 9.7400 | 100 | 3 |
| PaddleOCR-VL-1.6 | 0.9419 | 100 | 93 | 100 / 100 | 0.9965 | [0.9657, 1.0000] | 9.3330 | 100 | 0 |
| GLM-OCR | 0.8845 | 100 | 93 | 100 / 100 | 0.9834 | [0.8240, 1.0000] | 13.0645 | 100 | 0 |
| MonkeyOCR-pro-1.2B | 0.8300 | 100 | 93 | 100 / 100 | 0.9276 | [0.6439, 0.9999] | 27.8575 | 100 | 0 |
| MinerU (table) | 0.9325 | 100 | 93 | 100 / 100 | 0.9908 | [0.8733, 1.0000] | 12.7530 | 100 | 0 |

GriTS measures cell-content similarity and is averaged over its available saved scores. Its denominator can differ from financial fact F1. Native numeric coverage counts non-null native numeric confidence, including valid zero values; confidence is not correctness probability. Recognition times use saved per-output seconds within this prefix, including first-output setup, and exclude separate scoring/calibration. Sam’s pasted runtime medians instead pool all his cohorts.

## Financial F1 outcome counts

| Configuration | Eligible F1 tables | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 93 | 23 | 63 |
| GLM-OCR | 93 | 59 | 31 |
| MonkeyOCR-pro-1.2B | 93 | 83 | 9 |
| MinerU (table) | 93 | 43 | 48 |

Exact means F1 ≥ 1 − 1e−9 under the saved scorer; it does not certify the whole table.

## Native numeric confidence ranking — development

Within-model association between native numeric confidence and financial fact F1. These are descriptive development results, not held-out validation. Sam’s ranking definitions and 1,000 issuer-bootstrap resamples are reused. Only rows with both confidence and F1 enter this table; missing confidence is excluded here, while the accuracy table retains all eligible F1 rows. No confidence feature is selected here.

| Configuration | Rows | Issuers | Mean F1 | Mean native | Native range | Spearman | Spearman 95% issuer CI | Error AUC (F1 < 0.95) | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 93 | 3 | 0.9006 | 0.9968 | [0.9657, 1.0000] | 0.2971 | [0.0778, 0.5249] | 0.6186 | 23 | 63 |
| GLM-OCR | 93 | 3 | 0.5983 | 0.9822 | [0.8240, 1.0000] | 0.6793 | [0.1671, 0.7225] | 0.8415 | 59 | 31 |
| MonkeyOCR-pro-1.2B | 93 | 3 | 0.4251 | 0.9233 | [0.6439, 0.9999] | 0.4727 | [-0.2272, 0.8208] | 0.9506 | 83 | 9 |
| MinerU (table) | 93 | 3 | 0.7728 | 0.9901 | [0.8733, 1.0000] | 0.5589 | [0.1585, 0.6017] | 0.8209 | 43 | 48 |

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
