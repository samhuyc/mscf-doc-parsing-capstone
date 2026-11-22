# mc8: findings from 300 financial tables

Completed November 18, 2026; published November 22, 2026. **300 cropped FinTabNet development tables, 55 source reports, nine issuers, six recognizers and seven configurations produced 2,100 successful scored outputs.** Financial-association F1 is available on 283 tables; 17 have no eligible financial reference facts. This is the completed prefix of a prepared 2,000-table experiment. The 400-table final test has not been evaluated.

## Findings

PaddleOCR-VL has the highest mean financial-association F1 in this development prefix (0.8877), followed by MinerU table mode (0.7939). High native numeric confidence coexists with imperfect financial associations: GLM averages 0.9889 native confidence over 300 outputs but only 0.6316 financial F1 over 283 eligible tables. Native confidence scales differ across models and do not measure the probability that a whole table is correct.

| Configuration | Financial F1 | Number recall | Native numeric confidence | Median recognition (s) |
| --- | ---: | ---: | ---: | ---: |
| Tesseract | N/A | 3.59% | 0.3330 | 0.2530 |
| PP-OCRv5 | N/A | 83.81% | 0.9588 | 9.7870 |
| MinerU text | N/A | 84.40% | 0.9798 | 11.5280 |
| PaddleOCR-VL-1.6 | 0.8877 | 99.18% | 0.9964 | 10.8065 |
| GLM-OCR | 0.6316 | 91.60% | 0.9889 | 19.0240 |
| MonkeyOCR-pro-1.2B | 0.4500 | 82.72% | 0.9437 | 35.2440 |
| MinerU table | 0.7939 | 97.63% | 0.9905 | 12.6455 |

Financial F1 measures associated financial facts, including row/column interpretation. Number recall is a separate content metric over 283 reference-eligible tables. Text-only configurations have no financial F1. Native numeric confidence is averaged over available evidence: 194 Tesseract, 296 MinerU text, 299 PaddleOCR-VL and 300 outputs for each remaining configuration. Recognition medians cover 300 outputs each and exclude separate scoring/calibration. Tesseract's very low saved number recall warrants investigation; this prefix does not establish a general ranking of OCR engines.

Within-model confidence has a positive descriptive association with financial F1: Spearman is 0.3627 for PaddleOCR-VL, 0.6055 for MinerU table, 0.5808 for GLM and 0.4860 for MonkeyOCR. Error-detection AUC is 0.6901, 0.8568, 0.8237 and 0.8800 respectively, using F1 < 0.95 as an error and lower confidence as the signal. See the [full milestone report](summary.md) for confidence intervals, denominators, truncations, GriTS and the retained measurement flag.

## Exploratory forecast analysis

A separate report uses nested leave-one-issuer-out development cross-validation: confidence-feature selection occurs inside each outer training fold, followed by isotonic regression. The baseline is that fold's training-issuer mean F1. Missing selected confidence uses the training mean and the table remains included.

| Structured configuration | Forecast MAE (percentage points) | Forecast MSE | Baseline MSE | MSE gain | Gain 95% issuer interval |
| --- | ---: | ---: | ---: | ---: | --- |
| PaddleOCR-VL | 13.79 | 0.0535 | 0.0604 | 0.0068 | [0.0028, 0.0101] |
| MinerU table | 21.51 | 0.1002 | 0.1227 | 0.0225 | [-0.0077, 0.0547] |
| GLM-OCR | 25.46 | 0.1102 | 0.1817 | 0.0715 | [0.0347, 0.1090] |
| MonkeyOCR | 28.59 | 0.1228 | 0.1704 | 0.0476 | [0.0081, 0.0755] |

Positive gain favors the forecast. Three intervals exclude zero in this exploratory development analysis; MinerU's does not. These intervals resample nine issuer clusters from fixed out-of-issuer predictions and do not repeat feature selection. They do not establish final-test performance. The production calibration is still pending; the original cumulative summaries therefore correctly leave held-out forecast fields pending. No recognizer weights were trained.

## Files and reproduction

- [Full accuracy and native-confidence report](summary.md), [original summary JSON](summary.json), and [full-precision additional metrics](summary-metrics.json).
- [All 2,100 scores as CSV](scores.csv) and [complete per-table native features and provenance](development/pairs.json).
- [Presentation PDF](presentation/confidence_results_summary_2026-11-18.pdf), [forecast comparison](presentation/forecast_and_confidence_summary.md), and [per-fold forecasts and validation details](presentation/exploratory_development_forecasts.json). Sam's earlier development CV and final test are labeled separately in the comparison; they are not additional mc8 test results.
- [100-, 200-, and 300-table milestone reports](batch-results/), [batch ledger](batch-progress.json), and [sealed 2,000-table selection manifest](data_snapshot/tables.json). The manifest includes unrun selections; it does not imply 2,000 completed evaluations. Image paths refer to local assets omitted from Git.
- [Pipeline source and setup](../../README.md), [methods](../../METHODS.md), [model/runtime configuration](../../config.json), [source-code hashes](../../sam-code-lock.json), and [export provenance](export-provenance.json).

From the repository root, validate the published scores using only Python's standard library:

```sh
python3 people/mc8/2026-11-17_confidence_cpu/results/300_tables/validate_export.py
```

The exported analysis scripts use paths relative to this repository. In the configured CPU environment, `python presentation/compute_development_forecasts.py` recomputes exploratory development forecasts from this snapshot, and `python presentation/build_summary.py` rebuilds the PDF. Run those commands from this directory. These scripts replace the report files they generate; use a separate checkout to preserve the published snapshot. Original local scripts and published JSON/PDF were preserved at export; the two copied scripts were adapted only for exported file locations. Historical provenance files retain their original local paths and hashes.

## Limits

Public benchmark labels have not received an independent human audit. The flagged reference/header case `fintabnet_test_02146` remains included. Successful execution does not guarantee complete generation: MinerU text has 11 truncated outputs; GLM and MonkeyOCR have one each. Nine issuers provide limited independent evidence, and the ordered prefix can differ from the full cohort. This crop experiment does not measure full-PDF table detection. CPU runtime adaptations differ from Sam's MLX setup; methods document those differences.

Large model weights, environments, source images/annotations, raw token/logit records and unfinished later outputs remain local. The exported scores support recomputing aggregate metrics and exploratory forecasts; rerunning recognition requires restoring the pinned local inputs and model assets through the setup pipeline. Original readiness files and the copied setup seal describe pre-execution setup checks; completed execution is established by the scored pairs and milestone reports.
