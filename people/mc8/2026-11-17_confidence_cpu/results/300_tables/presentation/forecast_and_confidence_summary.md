# Confidence and exploratory forecast summary

Our 300 completed tables contain 283 financial-F1-eligible tables from 9 issuers. Our MAE/MSE use nested leave-one-issuer-out development cross-validation, with feature selection inside the training folds. Sam’s saved development CV uses 94 tables from 42 issuers. These are development validation comparisons; our final held-out test is not evaluated.

## Forecast validation

| Model | Our MAE (pp) | Sam CV MAE (pp) | Our MSE | Sam CV MSE | Our baseline MAE (pp) | Our baseline MSE | Our MSE gain | Our gain 95% issuer CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| PaddleOCR-VL | 13.79 | 11.70 | 0.0535 | 0.0446 | 16.89 | 0.0604 | 0.0068 | [0.0028, 0.0101] |
| MinerU table | 21.51 | 14.92 | 0.1002 | 0.0584 | 27.85 | 0.1227 | 0.0225 | [-0.0077, 0.0547] |
| GLM-OCR | 25.46 | 17.21 | 0.1102 | 0.0743 | 39.01 | 0.1817 | 0.0715 | [0.0347, 0.1090] |
| MonkeyOCR | 28.59 | 29.74 | 0.1228 | 0.1406 | 37.39 | 0.1704 | 0.0476 | [0.0081, 0.0755] |

MAE is in percentage points of expected F1; MSE uses F1 on the 0–1 scale. Each baseline is the mean F1 of the outer training issuers. All eligible outputs are retained; missing selected confidence uses the training mean. Positive MSE gain favors the forecast. Intervals resample issuer clusters from fixed out-of-issuer predictions; they do not rerun feature selection. With only 9 issuer clusters and public references, these remain exploratory.

## Native numeric confidence versus financial F1

Sam below uses his 11-case final test; our columns use 282–283 eligible development rows with available native numeric confidence. Pearson is additionally computed from saved pairs for both runs.

| Model | Sam Spearman | Our Spearman | Sam Pearson | Our Pearson | Sam error AUC | Our error AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PaddleOCR-VL | 0.1895 | 0.3627 | 0.3513 | 0.3414 | 0.5714 | 0.6901 |
| MinerU table | 0.6186 | 0.6055 | 0.6225 | 0.4023 | 0.8750 | 0.8568 |
| GLM-OCR | 0.5583 | 0.5808 | 0.1626 | 0.4739 | 0.7667 | 0.8237 |
| MonkeyOCR | 0.3264 | 0.4860 | 0.3802 | 0.4321 | 0.9000 | 0.8800 |

Spearman measures rank association and Pearson linear association. Error AUC uses low confidence to identify F1 < 0.95 (0.5 = chance, 1 = perfect ranking). Native confidence is not a whole-table correctness probability.

## Sam’s separate final test

| Model | MAE (pp) | Baseline MAE (pp) | MSE | Baseline MSE |
| --- | ---: | ---: | ---: | ---: |
| PaddleOCR-VL | 21.87 | 19.91 | 0.1218 | 0.1055 |
| MinerU table | 20.80 | 20.73 | 0.0913 | 0.1012 |
| GLM-OCR | 27.48 | 28.44 | 0.1305 | 0.1251 |
| MonkeyOCR | 26.30 | 30.94 | 0.1066 | 0.1352 |

Final-test results use 11 unseen issuers and the frozen header-selected calibration. They are distinct from the 94-table development CV above. Sam’s original two flagged cases remain included.

No OCR or recognition-weight training was run. This report-only analysis does not create or alter the production calibration freeze, raw records, public references or saved scoring summaries. Full predictions, training issuer lists, selected features, and source hashes are in [exploratory_development_forecasts.json](exploratory_development_forecasts.json).
