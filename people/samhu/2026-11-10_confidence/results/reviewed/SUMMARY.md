# Confidence pilot replay

Source commit: `0baababc2652757982ae5898500a1c72409c4848`. Labels: **reviewed_only**.

0 requested parser/field pairs; 0 documents; 0 issuer groups.

Probabilities are experimental held-out estimates. These are selected draft references, not production calibration.

| Parser | Scored/requested | Requested-field accuracy | Raw Brier | Base-rate Brier | Calibrated Brier | ECE | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|

Brier/ECE/AUROC use only the scored, resolved fields. Missing/ambiguous cells remain in requested-field accuracy and score coverage. Empty evaluations are unavailable, never perfect.

The raw score is a fixed parser-support diagnostic treated as a probability only for comparison. A separate sigmoid is fitted per parser using other issuer groups; both Rolls-Royce reports always stay together. The constant baseline uses the same training groups. No hyperparameters or review thresholds were selected on test folds.

See summary.json for reliability bins, risk/coverage curves (relative to scored fields), fold provenance, native Paddle diagnostics and document summaries. Multiply curve coverage by score coverage to obtain coverage of all requested fields.

This retrospective selection uses reference row/header names as the requested schema. It is not blind field discovery, full-document completeness, or an official benchmark submission. Cached MinerU VLM run metadata identifies MinerU 3.4.5 with MinerU2.5-Pro-2605-1.2B weights; no new inference or token-logprob collection was performed. Related parser pipelines can make the same mistake. Review labels and collect fresh issuer-disjoint examples before deployment.
