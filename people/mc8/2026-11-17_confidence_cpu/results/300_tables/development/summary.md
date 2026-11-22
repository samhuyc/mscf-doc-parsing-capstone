# Development results

**Tables scored:** 300 / 1,600

## Accuracy by configuration

| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 300 | 300 | 0 | 0 | 0 | N/A | 3.59% | 1 |
| PP-OCRv5 | 300 | 300 | 0 | 0 | 0 | N/A | 83.81% | 1 |
| MinerU (text) | 300 | 300 | 0 | 0 | 0 | N/A | 84.40% | 1 |
| PaddleOCR-VL-1.6 | 300 | 300 | 0 | 0 | 283 | 0.8877 | 99.18% | 1 |
| GLM-OCR | 300 | 300 | 0 | 0 | 283 | 0.6316 | 91.60% | 1 |
| MonkeyOCR-pro-1.2B | 300 | 300 | 0 | 0 | 283 | 0.4500 | 82.72% | 1 |
| MinerU (table) | 300 | 300 | 0 | 0 | 283 | 0.7939 | 97.63% | 1 |

Fact F1 measures associated financial facts on a 0–1 scale. Number recall measures the share of reference numbers recovered. Higher values are better for both. Text-only configurations have no fact F1; N/A is not zero.

## Cohort in this report

| Metric | Count |
| --- | --- |
| Unique crops | 300 |
| Scored outputs | 2100 |
| Crops with financial reference facts | 283 |
| Crops without financial reference facts | 17 |
| Source reports | 55 |
| Issuers | 9 |
| Issuers with financial facts | 9 |
| Held-out test crops | 0 |
| Held-out test issuers | 0 |
| Configurations | 7 |
| Models | 6 |

Source reports count distinct manifest document names. These are cropped table images. MinerU text/table share one model.

## Additional accuracy, confidence and runtime metrics

| Configuration | GriTS content F1 | GriTS tables | Number recall tables | Native numeric coverage | Mean native numeric | Native range | Median recognition (s) | Timed outputs | Truncated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tesseract | N/A | 0 | 283 | 194 / 300 | 0.3330 | [0.0000, 0.7944] | 0.2530 | 300 | 0 |
| PP-OCRv5 | N/A | 0 | 283 | 300 / 300 | 0.9588 | [0.6698, 0.9984] | 9.7870 | 300 | 0 |
| MinerU (text) | N/A | 0 | 283 | 296 / 300 | 0.9798 | [0.5146, 1.0000] | 11.5280 | 300 | 11 |
| PaddleOCR-VL-1.6 | 0.9697 | 300 | 283 | 299 / 300 | 0.9964 | [0.9522, 1.0000] | 10.8065 | 300 | 0 |
| GLM-OCR | 0.9007 | 300 | 283 | 300 / 300 | 0.9889 | [0.8240, 1.0000] | 19.0240 | 300 | 1 |
| MonkeyOCR-pro-1.2B | 0.8418 | 300 | 283 | 300 / 300 | 0.9437 | [0.5992, 1.0000] | 35.2440 | 300 | 1 |
| MinerU (table) | 0.9319 | 300 | 283 | 300 / 300 | 0.9905 | [0.7717, 1.0000] | 12.6455 | 300 | 0 |

GriTS measures cell-content similarity and is averaged over its available saved scores. Its denominator can differ from financial fact F1. Native numeric coverage counts non-null native numeric confidence, including valid zero values; confidence is not correctness probability. Recognition times use saved per-output seconds within this prefix, including first-output setup, and exclude separate scoring/calibration. Sam’s pasted runtime medians instead pool all his cohorts.

## Financial F1 outcome counts

| Configuration | Eligible F1 tables | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 283 | 72 | 196 |
| GLM-OCR | 283 | 166 | 109 |
| MonkeyOCR-pro-1.2B | 283 | 231 | 45 |
| MinerU (table) | 283 | 105 | 170 |

Exact means F1 ≥ 1 − 1e−9 under the saved scorer; it does not certify the whole table.

## Native numeric confidence ranking — development

Within-model association between native numeric confidence and financial fact F1. These are descriptive development results, not held-out validation. Sam’s ranking definitions and 1,000 issuer-bootstrap resamples are reused. Only rows with both confidence and F1 enter this table; missing confidence is excluded here, while the accuracy table retains all eligible F1 rows. No confidence feature is selected here.

| Configuration | Rows | Issuers | Mean F1 | Mean native | Native range | Spearman | Spearman 95% issuer CI | Error AUC (F1 < 0.95) | F1 < 0.95 | Exact F1 tables |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 282 | 9 | 0.8878 | 0.9965 | [0.9522, 1.0000] | 0.3627 | [0.1400, 0.5107] | 0.6901 | 71 | 196 |
| GLM-OCR | 283 | 9 | 0.6316 | 0.9883 | [0.8240, 1.0000] | 0.5808 | [0.3788, 0.6795] | 0.8237 | 166 | 109 |
| MonkeyOCR-pro-1.2B | 283 | 9 | 0.4500 | 0.9410 | [0.5992, 0.9999] | 0.4860 | [0.2523, 0.6426] | 0.8800 | 231 | 45 |
| MinerU (table) | 283 | 9 | 0.7939 | 0.9899 | [0.7717, 1.0000] | 0.6055 | [0.3388, 0.6666] | 0.8568 | 105 | 170 |

Error AUC treats lower confidence as an error signal. N/A includes undefined correlation (constant data), one-class AUC, or insufficient issuer clusters for a confidence interval.

## Measurement flags and audit status

References are public benchmark annotations; independent human audit is pending. Flagged cases remain included. This report does not claim Sam’s audit passes for these new outputs.

| Table | Saved measurement flags |
| --- | --- |
| fintabnet_test_02146 | Sam flagged reference/header interpretation; retained, requires audit |

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
