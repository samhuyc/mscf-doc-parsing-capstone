# Sam versus your 300-table results

**Different evaluation sets:** Sam’s accuracy, confidence and ranking results below use 11 held-out tables from 11 issuers. Yours use the first 300 development tables from 9 issuers; 283 have eligible financial facts. These averages do not establish a better implementation. Both use the same financial-association metric, with different inference runtimes.

## Extraction accuracy

| Configuration | Sam F1 | Your F1 | Sam GriTS | Your GriTS | Sam number recall | Your number recall |
| --- | --- | --- | --- | --- | --- | --- |
| Tesseract | N/A | N/A | N/A | N/A | 3.86% | 3.59% |
| PP-OCRv5 | N/A | N/A | N/A | N/A | 84.71% | 83.81% |
| MinerU text | N/A | N/A | N/A | N/A | 97.56% | 84.40% |
| PaddleOCR-VL | 82.22% | 88.77% | 93.89% | 96.97% | 100.00% | 99.18% |
| GLM-OCR | 72.15% | 63.16% | 91.46% | 90.07% | 97.69% | 91.60% |
| MonkeyOCR | 44.16% | 45.00% | 89.10% | 84.18% | 89.02% | 82.72% |
| MinerU table | 84.31% | 79.39% | 94.83% | 93.19% | 99.78% | 97.63% |

F1 requires correct financial values and row/column associations. GriTS measures cell-content similarity. N/A is inapplicable, not zero. Your F1 and number recall average 283 reference-eligible tables; your structured GriTS averages all 300 tables. Sam’s corresponding averages use all 11 final-test cases, including two flagged cases.

## Native numeric confidence

| Configuration | Sam coverage | Your coverage | Sam mean | Your mean | Sam range | Your range |
| --- | --- | --- | --- | --- | --- | --- |
| Tesseract | 7 / 11 | 194 / 300 | 0.2315 | 0.3330 | Not in pasted summary | [0.0000, 0.7944] |
| PP-OCRv5 | 11 / 11 | 300 / 300 | 0.9704 | 0.9588 | Not in pasted summary | [0.6698, 0.9984] |
| MinerU text | 11 / 11 | 296 / 300 | 0.9928 | 0.9798 | Not in pasted summary | [0.5146, 1.0000] |
| PaddleOCR-VL | 11 / 11 | 299 / 300 | 0.9900 | 0.9964 | [0.9145, 1.0000] | [0.9522, 1.0000] |
| GLM-OCR | 11 / 11 | 300 / 300 | 0.9962 | 0.9889 | [0.9754, 1.0000] | [0.8240, 1.0000] |
| MonkeyOCR | 11 / 11 | 300 / 300 | 0.9420 | 0.9437 | [0.6474, 0.9955] | [0.5992, 1.0000] |
| MinerU table | 11 / 11 | 300 / 300 | 0.9989 | 0.9905 | [0.9940, 1.0000] | [0.7717, 1.0000] |

Coverage counts non-null native numeric confidence, including valid zeros. Means/ranges use available confidence. Native confidence is not correctness probability and is not directly comparable across models. Sam’s text-only ranges were not supplied in his pasted summary.

## Recognition time

| Configuration | Sam median (seconds) | Your median (seconds) |
| --- | --- | --- |
| Tesseract | 0.298 | 0.253 |
| PP-OCRv5 | 5.253 | 9.787 |
| MinerU text | 3.887 | 11.528 |
| PaddleOCR-VL | 4.196 | 10.806 |
| GLM-OCR | 6.820 | 19.024 |
| MonkeyOCR | 10.022 | 35.244 |
| MinerU table | 4.832 | 12.646 |

**Different timing scopes:** Sam’s published medians pool his evaluated cohorts, rather than only the 11 final-test tables. Yours use saved per-output times for these 300 tables and include setup charged to the first output. Hardware/runtime differences also prevent treating these ratios as a controlled speed benchmark.

## Confidence ranking against financial F1

| Configuration | Sam ranking rows | Your ranking rows | Sam Spearman | Your Spearman | Sam 95% issuer CI | Your 95% issuer CI | Sam error AUC | Your error AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL | 11 | 282 | 0.1895 | 0.3627 | [-0.5303, 0.7053] | [0.1400, 0.5107] | 0.5714 | 0.6901 |
| GLM-OCR | 11 | 283 | 0.5583 | 0.5808 | [-0.0294, 0.8212] | [0.3788, 0.6795] | 0.7667 | 0.8237 |
| MonkeyOCR | 11 | 283 | 0.3264 | 0.4860 | [-0.4105, 0.8096] | [0.2523, 0.6426] | 0.9000 | 0.8800 |
| MinerU table | 11 | 283 | 0.6186 | 0.6055 | [0.0756, 0.8347] | [0.3388, 0.6666] | 0.8750 | 0.8568 |

Ranking includes only rows with both confidence and F1. Your PaddleOCR-VL ranking excludes one row with missing native confidence, leaving 282. Sam’s ranking uses 11 issuer clusters; yours uses 9. Both use native numeric confidence, with lower confidence predicting an error (F1 < 0.95). Your ranking is descriptive development analysis, not held-out validation.

| Configuration | Sam F1 < 0.95 (ranking) | Your F1 < 0.95 (ranking) | Sam exact F1 (ranking) | Your exact F1 (ranking) | Your F1 < 0.95 (all eligible) |
| --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL | 4 | 71 | 7 | 196 | 72 |
| GLM-OCR | 6 | 166 | 4 | 109 | 166 |
| MonkeyOCR | 10 | 231 | 1 | 45 | 231 |
| MinerU table | 3 | 105 | 8 | 170 | 105 |

Exact means F1 ≥ 1 − 1e−9 under the saved scorer; it does not certify a whole table. Compare rates with their denominators, rather than raw counts.

## Forecast errors — Sam’s held-out test

| Configuration | Sam MAE (pp) | Baseline MAE (pp) | Sam MSE | Baseline MSE | MSE gain | MSE gain 95% issuer CI | Your forecast results |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL | 21.87 | 19.91 | 0.1218 | 0.1055 | -0.0164 | [-0.0461, 0.0061] | Pending |
| GLM-OCR | 27.48 | 28.44 | 0.1305 | 0.1251 | -0.0054 | [-0.0800, 0.0769] | Pending |
| MonkeyOCR | 26.30 | 30.94 | 0.1066 | 0.1352 | 0.0286 | [-0.0770, 0.1332] | Pending |
| MinerU table | 20.80 | 20.73 | 0.0913 | 0.1012 | 0.0099 | [-0.0256, 0.0620] | Pending |

MAE is shown in percentage points (pp); MSE uses F1 on the 0–1 scale. Positive MSE gain favors the fitted forecast over the development-mean baseline. Every Sam interval above includes zero. Your calibration freezes after all 1,600 development tables, followed by 400 test tables; no provisional model was fitted for this comparison.

| Configuration | Sam selected feature | Sam selection count | Your selected feature |
| --- | --- | --- | --- |
| PaddleOCR-VL | native_number_p10 | native_number_p10: 11 | Pending |
| GLM-OCR | native_all | native_all: 11 | Pending |
| MonkeyOCR | native_all | native_all: 11 | Pending |
| MinerU table | native_label_p10 | native_label_p10: 11 | Pending |

## Review and retention — Sam’s frozen development cutoff

| Configuration | Reviewed / total | Errors | Caught | Error capture | Kept | Kept coverage | Kept mean F1 | All mean F1 | Your review results |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL | 3 / 11 | 4 | 1 | 25.00% | 8 | 72.73% | 82.59% | 82.22% | Pending |
| GLM-OCR | 2 / 11 | 6 | 2 | 33.33% | 9 | 81.82% | 79.30% | 72.15% | Pending |
| MonkeyOCR | 1 / 11 | 10 | 1 | 10.00% | 10 | 90.91% | 48.58% | 44.16% | Pending |
| MinerU table | 4 / 11 | 3 | 2 | 66.67% | 7 | 63.64% | 91.67% | 84.31% | Pending |

Errors mean F1 < 0.95. Kept mean F1 is extraction accuracy among retained tables, not a correctness probability. Your held-out review policy has not been evaluated.

## Experiment counts

Sam’s counts in this table describe all 109 crops across development and test. Your counts describe the completed 300-table prefix.

| Metric | Sam (all evaluated cohorts) | Yours (completed prefix) |
| --- | --- | --- |
| Unique crops | 109 | 300 |
| Outputs | 763 | 2100 |
| Crops with financial facts | 105 | 283 |
| Source reports | 78 | 55 |
| Issuers with financial facts | 53 | 9 |
| Held-out test crops | 11 | 0 |
| Held-out test issuers | 11 | 0 |
| Configurations | 7 | 7 |
| Models | 6 | 6 |

## Measurement limitations

Sam retains two flagged final-test cases: `fintabnet_test_02146` and `fintabnet_test_09879`. His 9-case exclusion sensitivity is a separate post-inspection analysis. Your current prefix includes the first flagged case and retains it in scoring; independent human reference audit remains pending. Sam’s audit passes do not establish audit passes for your new outputs.

Sources: [Sam’s findings](../../../../../samhu/2026-11-15_table_confidence/results/native_prototype/findings.json) · [Your Batch 3 metrics](batch-03-metrics.json) · [Your full Batch 3 report](batch-03.md)
