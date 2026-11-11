# Native confidence versus transcription correctness

Raw model confidence only. No cross-model agreement and no fitted calibration.
Labels: **draft_exploratory**; 13 available reference spans per engine.

| Engine | Document | Pages processed | Token-limit pages | Native weighted mean | Native p10 | Selected-span character accuracy |
|---|---|---:|---:|---:|---:|---:|
| tesseract | cvs_2025q2 | 12/12 | 0 | 0.9358 | 0.9300 | 0.9949 |
| tesseract | edf_2024 | 6/6 | 0 | 0.9491 | 0.9252 | 0.9911 |
| tesseract | hippodrome_2025 | 39/39 | 0 | 0.9535 | 0.9522 | 1.0000 |
| tesseract | peterborough_2025 | 12/12 | 0 | 0.9574 | 0.9537 | 1.0000 |
| tesseract | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9034 | 0.6779 | 0.9036 |
| tesseract | rolls_royce_2026h1_release | 52/52 | 0 | 0.9550 | 0.9322 | 1.0000 |
| paddle | cvs_2025q2 | 12/12 | 0 | 0.9822 | 0.9422 | 0.9898 |
| paddle | edf_2024 | 6/6 | 0 | 0.9807 | 0.9198 | 1.0000 |
| paddle | hippodrome_2025 | 39/39 | 0 | 0.9790 | 0.9622 | 1.0000 |
| paddle | peterborough_2025 | 12/12 | 0 | 0.9773 | 0.9484 | 0.9980 |
| paddle | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9768 | 0.9293 | 1.0000 |
| paddle | rolls_royce_2026h1_release | 52/52 | 0 | 0.9780 | 0.8877 | 0.9832 |
| mineru | cvs_2025q2 | 12/12 | 0 | 0.9903 | 0.9929 | 1.0000 |
| mineru | edf_2024 | 6/6 | 0 | 0.9965 | 0.9998 | 1.0000 |
| mineru | hippodrome_2025 | 39/39 | 1 | 0.9972 | 0.9996 | 1.0000 |
| mineru | peterborough_2025 | 12/12 | 0 | 0.9957 | 0.9994 | 1.0000 |
| mineru | rolls_royce_2026h1_presentation | 19/19 | 0 | 0.9848 | 0.9880 | 1.0000 |
| mineru | rolls_royce_2026h1_release | 52/52 | 7 | 0.9970 | 0.9987 | 1.0000 |

**Generation limits:** processed-page coverage includes pages that hit the token limit. Their emitted-token scores remain visible, but they are not complete generations. Repetition can have very high native confidence.
- mineru, hippodrome_2025: token-limit pages [36].
- mineru, rolls_royce_2026h1_release: token-limit pages [25, 27, 28, 32, 33, 39, 41].

| Engine | Summary | Spearman rank correlation | Pearson correlation | n documents |
|---|---|---:|---:|---:|
| tesseract | character_weighted_mean | 0.8804 | 0.9449 | 6 |
| tesseract | mean | 0.8804 | 0.9611 | 6 |
| tesseract | geometric_mean | 0.1078 | 0.2826 | 6 |
| tesseract | p10 | 0.9411 | 0.9973 | 6 |
| tesseract | fraction_below_0_90 | -0.8804 | -0.9717 | 6 |
| paddle | character_weighted_mean | -0.1518 | -0.1721 | 6 |
| paddle | mean | 0.5161 | 0.7469 | 6 |
| paddle | geometric_mean | 0.6983 | 0.6840 | 6 |
| paddle | p10 | 0.3339 | 0.6449 | 6 |
| paddle | fraction_below_0_90 | -0.3339 | -0.5221 | 6 |
| mineru | character_weighted_mean | N/A | N/A | 6 |
| mineru | mean | N/A | N/A | 6 |
| mineru | geometric_mean | N/A | N/A | 6 |
| mineru | p10 | N/A | N/A | 6 |
| mineru | fraction_below_0_90 | N/A | N/A | 6 |

Higher is better for all summaries except fraction_below_0_90 (where a negative correlation is desirable).
Constant correctness or confidence produces N/A, not zero correlation. Different engines have different native score scales.

## tesseract: exploratory word-confidence reliability

190 aligned output words; Brier 0.0192; 10-bin ECE 0.0462.
These use normalized native scores as probability proxies and draft, best-window word alignment. They do not establish calibrated probabilities.

| Native score bin | Words | Mean confidence | Observed exact-word accuracy |
|---|---:|---:|---:|
| 0.2–0.3 | 1 | 0.2973 | 1.0000 |
| 0.4–0.5 | 1 | 0.4644 | 0.0000 |
| 0.5–0.6 | 1 | 0.5367 | 0.0000 |
| 0.7–0.8 | 2 | 0.7920 | 0.5000 |
| 0.8–0.9 | 4 | 0.8806 | 0.7500 |
| 0.9–1.0 | 181 | 0.9615 | 0.9945 |

- Six documents, five issuers: the two Rolls-Royce documents are related.
- Labels are selected spans with no exact boxes; best-window matching can credit repeated text.
- Reference labels are assistant-authored drafts unless independently reviewed.
- Native scores and their averages are not calibrated document correctness probabilities.
- Missing text can coexist with high confidence on returned text.
- Repetitive generated text can have high token confidence and dominate an output-length-weighted average; token-limit flags must be read separately.
- Permutation p-values assume exchangeable documents, weakened by shared issuer; exploratory only.
- Several aggregations are reported without selecting a winner; correlations are not proof of generalization.
