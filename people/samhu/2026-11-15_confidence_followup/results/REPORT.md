# Does native confidence help select better pages?

Retrospective diagnostic on the same 23 selected pages, four PDFs, three issuers. No new inference, verified labels, fitted calibration or held-out validation.

Spearman compares higher confidence with better full-page text agreement. Leave-one-family-out below means deleting a family and recomputing the statistic; no model is trained.

| Engine | Summary | All pages | Without truncated pages | Omit-one-family range |
|---|---|---:|---:|---:|
| mineru | character_weighted_mean | 0.205 | 0.377 | 0.036 to 0.443 |
| mineru | geometric_mean | 0.155 | 0.320 | -0.088 to 0.315 |
| mineru | p10 | 0.121 | 0.281 | -0.245 to 0.309 |
| mineru | fraction_below_0_90 | 0.151 | 0.316 | -0.173 to 0.337 |
| paddle | character_weighted_mean | 0.366 | 0.366 | 0.259 to 0.809 |
| paddle | geometric_mean | 0.427 | 0.427 | 0.309 to 0.809 |
| paddle | p10 | 0.161 | 0.161 | -0.013 to 0.636 |
| paddle | fraction_below_0_90 | 0.306 | 0.306 | 0.127 to 0.800 |
| tesseract | character_weighted_mean | 0.535 | 0.535 | 0.402 to 0.536 |
| tesseract | geometric_mean | 0.275 | 0.275 | 0.005 to 0.688 |
| tesseract | p10 | 0.121 | 0.121 | -0.056 to 0.500 |
| tesseract | fraction_below_0_90 | 0.248 | 0.248 | -0.059 to 0.527 |

## Selecting the most confident half

Lower error is better. The baseline is keeping all pages (also the expected mean error of a uniformly random subset). Error is 1 − clipped text agreement, averaged per page. Micro CER in the JSON remains uncapped so repetition is visible. All ties at the threshold are included. The 50% target is rounded up; missing scores are excluded, never set to zero.

| Engine | Summary | Pages retained | Selected mean error | All-page mean error | Selected micro CER |
|---|---|---:|---:|---:|---:|
| mineru | character_weighted_mean | 12 | 0.213 | 0.263 | 1.014 |
| mineru | geometric_mean | 12 | 0.217 | 0.263 | 0.960 |
| mineru | p10 | 12 | 0.164 | 0.263 | 0.961 |
| mineru | fraction_below_0_90 | 12 | 0.204 | 0.263 | 0.953 |
| paddle | character_weighted_mean | 12 | 0.058 | 0.086 | 0.049 |
| paddle | geometric_mean | 12 | 0.051 | 0.086 | 0.043 |
| paddle | p10 | 12 | 0.062 | 0.086 | 0.055 |
| paddle | fraction_below_0_90 | 12 | 0.064 | 0.086 | 0.046 |
| tesseract | character_weighted_mean | 12 | 0.192 | 0.204 | 0.132 |
| tesseract | geometric_mean | 12 | 0.230 | 0.204 | 0.143 |
| tesseract | p10 | 12 | 0.266 | 0.204 | 0.241 |
| tesseract | fraction_below_0_90 | 12 | 0.262 | 0.204 | 0.208 |

## Interpretation limits

- Embedded PDF text is unreviewed and reading order/markup can affect error.
- Only three issuer families are represented; these sensitivity ranges are not confidence intervals.
- Selection and truncation removal are diagnostics on already inspected data, not new test results.
- The fraction-below-0.90 score is sign-reversed for ranking: fewer low-confidence units ranks higher.
- No aggregation is selected as a winner here. A future evaluation must freeze its primary metric before inspecting new labels.
- Native token certainty does not cover omitted text or validate page structure. A calibrated page score needs an explicit correctness target and separate families for fitting and testing.
