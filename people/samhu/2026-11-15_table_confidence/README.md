# Native confidence on financial tables

**Finding:** native confidence has not yet demonstrated reliable error detection on this small sample.

Six models processed the same 103 table crops from six sponsor PDFs (618 outputs). Accuracy was checked on **19 identical crops per model**, across five issuers. References are assistant-reviewed, pending human verification.

| Model | Numeric F1 | Confidence–accuracy correlation¹ |
|---|---:|---:|
| PP-OCRv5 | 99.25% | +0.27 |
| Tesseract | 96.27% | −0.03 |
| PaddleOCR-VL | 100.00% | Not estimable: no accuracy variation |
| GLM-OCR | 98.98% | +0.17 |
| MonkeyOCR | 99.61% | +0.14 |
| MinerU recognition | 99.57% | −0.07 |

¹ Spearman correlation; all estimable 95% intervals include zero. Confidence scales differ by model.

**What accuracy means:** match numeric occurrences, including duplicates; F1 = `2 × matches / (reference count + output count)`, averaged equally across crops. Missing/extra numbers and wrong signs count as errors. **Swapped columns, incorrect units and missed tables can go undetected.**

**Pipeline:** shared PP-DocLayout_plus-L detector → identical crops → each recognizer → geometric mean of native probabilities. No training or calibration. Publisher pipelines are adapted; this is not an end-to-end product benchmark.

**Before adding documents:** human-verify financial facts (label, period, value, unit); check missed/cut-off tables; then test whether confidence identifies consequential errors. Expand toward 60 documents after these checks, holding out issuers.

Two MinerU outputs hit the token limit, both outside the 19-crop comparison.

[Plot](results/sponsor_all/accuracy/confidence_vs_numeric_accuracy.png) · [Per-table results](results/sponsor_all/accuracy/pairs.csv) · [Statistics](results/sponsor_all/accuracy/tracking.json) · [Methods and commands](METHODS.md)

Local interactive summary: `runs/sponsor_all/accuracy/report.html`.

Manual review: run `python3 review_panel.py`, then open http://127.0.0.1:8766. Compare each source with its editable grid; correct row/column assignments before confirming. Reviews save locally, separately from the earlier numeric references.
