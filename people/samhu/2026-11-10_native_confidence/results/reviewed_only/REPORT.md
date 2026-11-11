# Native confidence versus transcription correctness

Raw model confidence only. No cross-model agreement and no fitted calibration.
Labels: **reviewed_only**; 0 available reference spans per engine.

| Engine | Document | Pages processed | Token-limit pages | Native weighted mean | Native p10 | Selected-span character accuracy |
|---|---|---:|---:|---:|---:|---:|
| tesseract | cvs_2025q2 | 12/12 | 0 | 0.9358 | 0.9300 | N/A |
| tesseract | edf_2024 | 6/6 | 0 | 0.9491 | 0.9252 | N/A |
| tesseract | hippodrome_2025 | 39/39 | 0 | 0.9535 | 0.9522 | N/A |
| tesseract | peterborough_2025 | 12/12 | 0 | 0.9574 | 0.9537 | N/A |
| tesseract | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9034 | 0.6779 | N/A |
| tesseract | rolls_royce_2026h1_release | 52/52 | 0 | 0.9550 | 0.9322 | N/A |
| paddle | cvs_2025q2 | 12/12 | 0 | 0.9822 | 0.9422 | N/A |
| paddle | edf_2024 | 6/6 | 0 | 0.9807 | 0.9198 | N/A |
| paddle | hippodrome_2025 | 39/39 | 0 | 0.9790 | 0.9622 | N/A |
| paddle | peterborough_2025 | 12/12 | 0 | 0.9773 | 0.9484 | N/A |
| paddle | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9768 | 0.9293 | N/A |
| paddle | rolls_royce_2026h1_release | 52/52 | 0 | 0.9780 | 0.8877 | N/A |
| mineru | cvs_2025q2 | 12/12 | 0 | 0.9903 | 0.9929 | N/A |
| mineru | edf_2024 | 6/6 | 0 | 0.9965 | 0.9998 | N/A |
| mineru | hippodrome_2025 | 39/39 | 1 | 0.9972 | 0.9996 | N/A |
| mineru | peterborough_2025 | 12/12 | 0 | 0.9957 | 0.9994 | N/A |
| mineru | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9848 | 0.9880 | N/A |
| mineru | rolls_royce_2026h1_release | 52/52 | 7 | 0.9970 | 0.9987 | N/A |

**Generation limits:** processed-page coverage includes pages that hit the token limit. Their emitted-token scores remain visible, but they are not complete generations. Repetition can have very high native confidence.
- mineru, hippodrome_2025: token-limit pages [36].
- mineru, rolls_royce_2026h1_release: token-limit pages [25, 27, 28, 32, 33, 39, 41].

| Engine | Summary | Spearman rank correlation | Pearson correlation | n documents |
|---|---|---:|---:|---:|
| tesseract | character_weighted_mean | N/A | N/A | 0 |
| tesseract | mean | N/A | N/A | 0 |
| tesseract | geometric_mean | N/A | N/A | 0 |
| tesseract | p10 | N/A | N/A | 0 |
| tesseract | fraction_below_0_90 | N/A | N/A | 0 |
| paddle | character_weighted_mean | N/A | N/A | 0 |
| paddle | mean | N/A | N/A | 0 |
| paddle | geometric_mean | N/A | N/A | 0 |
| paddle | p10 | N/A | N/A | 0 |
| paddle | fraction_below_0_90 | N/A | N/A | 0 |
| mineru | character_weighted_mean | N/A | N/A | 0 |
| mineru | mean | N/A | N/A | 0 |
| mineru | geometric_mean | N/A | N/A | 0 |
| mineru | p10 | N/A | N/A | 0 |
| mineru | fraction_below_0_90 | N/A | N/A | 0 |

Higher is better for all summaries except fraction_below_0_90 (where a negative correlation is desirable).
Constant correctness or confidence produces N/A, not zero correlation. Different engines have different native score scales.


- Six documents, five issuers: the two Rolls-Royce documents are related.
- Labels are selected spans with no exact boxes; best-window matching can credit repeated text.
- Reference labels are assistant-authored drafts unless independently reviewed.
- Native scores and their averages are not calibrated document correctness probabilities.
- Missing text can coexist with high confidence on returned text.
- Repetitive generated text can have high token confidence and dominate an output-length-weighted average; token-limit flags must be read separately.
- Permutation p-values assume exchangeable documents, weakened by shared issuer; exploratory only.
- Several aggregations are reported without selecting a winner; correlations are not proof of generalization.
