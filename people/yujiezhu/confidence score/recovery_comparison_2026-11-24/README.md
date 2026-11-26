# Small recovery comparison — 24 November 2026

Open [UPDATE_SLIDES.pdf](UPDATE_SLIDES.pdf) for the two update slides and [REPORT.html](REPORT.html) for the eight-case comparison, actual parser snippets, source-page images, and runtime provenance. [SPEAKER_NOTES.md](SPEAKER_NOTES.md) provides the presentation script.

One alternative method: saved PyMuPDF4LLM output compared with original MinerU OCR output. This is a retrospective recovery replay with manual source review, not a new inference run. No model or scoring algorithm was built or changed. The previous demo remains unchanged.

## Findings

- Strict correctness improves from **2/8 to 5/8** extraction records: **3 of 6 original errors fully corrected**.
- **0 new errors among 2 originally correct controls**.
- Three remaining EDF records have readable, separated numeric text but still combine multiple source rows in one HTML cell. These are partial recoveries, not fully corrected financial cells.
- Both selected Rolls-Royce errors have an existing association diagnostic output of **0.8837**. Their digits were already correct; the year bindings were not.
- There is **no low-score fully-correct record** in the existing 50-record pool. Two high-score correct controls replace that requested category. Some low-association-score EDF records have correct numbers, but they are not correct structured cells.

## What “score” and “correct” mean

Selection uses the existing out-of-document-family **association** diagnostic outputs, with descriptive low/high bands below/at-or-above 0.5. These outputs are **uncalibrated and are not validated correctness probabilities**. The numeric scores are kept separate. EDF numeric scores remain missing because their training fold had only one class; no in-sample replacements are used.

The primary contract follows the prior demo: correct numeric content, separate row and column bindings, and usable unit context. EDF's bundled `number<br/>0.0` cells do not pass that contract. Splitting them manually could be a later repair, but is outside this comparison. The secondary numeric-content check asks only whether the actual saved output preserves the reference number(s), including explicit line breaks. Do not present that check as successful extraction of separate financial records.

There are eight selected extraction records covering eleven source numeric values: three records each originally combined two rows. The cases come from four documents, and several share the same table-level failure. Counts are descriptive, not independent statistical trials.

## Review and provenance

The assistant inspected the existing source-page renders for EDF p3, Rolls-Royce release p13, CVS p6, and Hippodrome physical p20 (printed p18). Existing reference labels were checked against those images. Both original labels and this review lack independent human verification. Original PDFs were not downloaded again.

The alternative parser also supplied agreement features for the existing confidence experiment. Its output is not independent evidence for validating confidence. Cases were selected using known original outcomes; this is not blind evaluation or a random sample.

`manual_review.json` records manual retry judgments, reasons and zero-based span-expanded table coordinates. `build_comparison.py` verifies coordinates, source hashes, source numeric content and successful header bindings; it does not infer correctness labels or train models. `comparison.json` and `comparison.csv` preserve all decisions. `assets/` contains unchanged source-page images, parser page exports and historical parser run records. `provenance.json` hashes the input files.

Historical PyMuPDF4LLM full-document runtimes: EDF **3.989 s / 6 pages**, Rolls-Royce release **30.591 s / 52 pages**, CVS **8.071 s / 12 pages**, Hippodrome **75.985 s / 39 pages**. These are Sam's saved September 30 measurements, not per-cell latency or measurements from this replay. No fresh parser inference was run.

## Reproduce locally

From this folder, using the existing environments:

```sh
../.venv-score/bin/python build_comparison.py
../.venv/bin/python make_slides.py
```

This rebuilds the evidence table and two-slide PDF without network access. The first command requires BeautifulSoup and imports the existing demo's table reader; the second uses ReportLab and Pillow.
