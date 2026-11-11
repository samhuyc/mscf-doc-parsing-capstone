# Native OCR confidence prototype

[Open the presentation](sponsor_brief.html) · [All 13 reference snippets and matched outputs](results/v2/snippet_examples.json)

**Question:** Do probabilities from recognition help rank transcription quality?

- **PaddleOCR:** retain each decoded character’s CTC probability, including spaces, before line averaging. On CVS page 6, the line score is **97.09%**, but its correctly recognized `$` scores **59.63%**.
- **MinerU:** promote original logits before FP32 normalization. Save logits, competing tokens and probabilities. Across 41,181 tokens, the revised calculation removes 1,295 exact-one scores left by the previous correction. High confidence remains.
- **Tesseract:** retain the existing word-certainty baseline.

Document summaries use a character-weighted mean or geometric mean. They describe model certainty, not a calibrated probability that a document is correct.

## Current evidence

The deadline rerun completed **80/140 Paddle pages** and **74/140 MinerU pages**, with unchanged output text on every completed page. It also includes a one-page FP32 model check.

On **23 shared pages** with unreviewed embedded PDF text, Spearman rank correlations are:

| Model | Weighted mean | Geometric mean |
|---|---:|---:|
| Tesseract | 0.535 | 0.275 |
| PaddleOCR | 0.366 | 0.427 |
| MinerU | 0.205 | 0.155 |

This is a selected diagnostic sample. Full-page text agreement penalizes repetition, but also reading-order and markup differences. The original **13 draft snippets cover only 11 pages and 1,211 characters**; none is human-verified. They cannot validate document reliability.

**Next:** finish the resumable reruns and review broader ground truth, particularly the 51 scanned pages without text layers. Calibration requires separate fitting and evaluation documents.

[Methods, limitations and reproduction](TECHNICAL_NOTES.md) · [Measured page results](results/v2/page_evaluation.json)
