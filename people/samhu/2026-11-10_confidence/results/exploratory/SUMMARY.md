# Confidence pilot replay

Source commit: `0baababc2652757982ae5898500a1c72409c4848`. Labels: **draft_exploratory**.

665 requested parser/field pairs; 6 documents; 5 issuer groups.

Probabilities are experimental held-out estimates. These are selected draft references, not production calibration.

| Parser | Scored/requested | Requested-field accuracy | Raw Brier | Base-rate Brier | Calibrated Brier | ECE | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|
| mineru_ocr | 57/133 | 40.6% | 0.0274 | 0.0506 | 0.0435 | 0.0227 | 0.9877 |
| mineru_vlm | 95/133 | 71.4% | 0.0901 | 0.0002 | 0.0002 | 0.0144 | N/A |
| paddleocr_ppstructurev3 | 86/133 | 53.4% | 0.0628 | 0.1491 | 0.0866 | 0.1444 | 0.9413 |
| pymupdf4llm | 119/133 | 86.5% | 0.1126 | 0.0360 | 0.0353 | 0.0104 | 0.0348 |
| pymupdf4llm_vlm | 113/133 | 82.0% | 0.0896 | 0.0381 | 0.0375 | 0.0122 | 0.0367 |

Brier/ECE/AUROC use only the scored, resolved fields. Missing/ambiguous cells remain in requested-field accuracy and score coverage. Empty evaluations are unavailable, never perfect.

The raw score is a fixed parser-support diagnostic treated as a probability only for comparison. A separate sigmoid is fitted per parser using other issuer groups; both Rolls-Royce reports always stay together. The constant baseline uses the same training groups. No hyperparameters or review thresholds were selected on test folds.

See summary.json for reliability bins, risk/coverage curves (relative to scored fields), fold provenance, native Paddle diagnostics and document summaries. Multiply curve coverage by score coverage to obtain coverage of all requested fields.

This retrospective selection uses reference row/header names as the requested schema. It is not blind field discovery, full-document completeness, or an official benchmark submission. Cached MinerU VLM run metadata identifies MinerU 3.4.5 with MinerU2.5-Pro-2605-1.2B weights; no new inference or token-logprob collection was performed. Related parser pipelines can make the same mistake. Review labels and collect fresh issuer-disjoint examples before deployment.
