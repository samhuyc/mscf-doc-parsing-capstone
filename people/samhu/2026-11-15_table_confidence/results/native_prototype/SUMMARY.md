# Results: native confidence prototype

**Finding: native confidence does not yet reliably predict table accuracy on unseen companies.** No final-test MSE improvement interval excludes zero; the post-inspection nine-table sensitivity also shows no established improvement.

**763 outputs · 109 shared crops · six models.** Final test: 11 tables from 11 unseen companies, scored with frozen calibration.

| Table model | Association F1 | Prediction MAE (pp) ↓ | Mean-only MAE (pp) ↓ | Native feature |
|---|---:|---:|---:|---|
| PaddleOCR-VL | 82.2% | 21.9 | 19.9 | number_p10 |
| GLM-OCR | 72.2% | 27.5 | 28.4 | all |
| MonkeyOCR | 44.2% | 26.3 | 30.9 | all |
| MinerU table | 84.3% | 20.8 | 20.7 | label_p10 |

Two final-test tables have documented annotation/header-scoring defects. The table above preserves the original 11-case scores; see [measurement audit and nine-case sensitivity](round2/measurement_audit.json).

F1 requires the correct value **and** row/column association. Prediction MAE measures error in estimated F1 in percentage points; the baseline always predicts the development mean. These are per-table averages.

PP-OCR, Tesseract and MinerU text have number-recall controls, not invented table-association scores. MinerU table uses the same checkpoint with its table task.

**Limits:** small final test; benchmark pretraining overlap unknown; reference and header-interpretation uncertainty. Confident structural errors remain. Native probability is not whole-table correctness probability.

[Open local panel](http://127.0.0.1:8768) · [Full measurements](findings.json) · [Methods](../../prototype/METHODS.md)
