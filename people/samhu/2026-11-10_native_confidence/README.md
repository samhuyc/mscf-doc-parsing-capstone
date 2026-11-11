# Native confidence: research prototype

**Question:** Can a parser’s own confidence indicate how accurate its output will be?

[Open the sponsor presentation](sponsor_brief.html) · [Detailed results](results/REPORT.md)

## Where the scores come from

| Model | Native score |
|---|---|
| Tesseract | Internal recognition certainty converted to a word confidence, then scaled from 0–100 to 0–1. |
| PaddleOCR | Average selected-character probability within each recognized line, after removing decoder blanks and duplicates. |
| MinerU recognition | Softmax probability of each emitted subword token, given the image and preceding output. |

These are mechanical signals. No model is prompted to assess its own confidence.

## Why combine them?

A document needs one summary. We tested a **character-weighted mean**, which gives longer text more influence, and a **geometric mean**, which penalizes low-confidence units more strongly. Neither automatically represents the probability that the document is correct.

## What we learned

All three processed six PDFs / 140 pages each. Rank correlations with accuracy on **13 draft reference snippets** were:

| Model | Weighted mean | Geometric mean |
|---|---:|---:|
| Tesseract | 0.88 | 0.11 |
| PaddleOCR | −0.15 | 0.70 |
| MinerU recognition | Not measurable | Not measurable |

PaddleOCR’s result depends on aggregation; this does not imply poor OCR accuracy. MinerU matched every reference snippet, so accuracy was constant and could not be ranked. Yet eight pages hit its token limit, including confident repetition that the snippets missed.

**Next:** review broader ground truth, freeze an aggregation rule, and test both ranking and calibration on separate documents. Current scores are exploratory confidence indicators, not validated correctness probabilities.

[Technical details and reproduction](TECHNICAL_NOTES.md)
