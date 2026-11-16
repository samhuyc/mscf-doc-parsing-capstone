# Confidence follow-up — November 15

**Finding:** the blockers were both weak evaluation data and the limits of native certainty. More PDFs alone do not make a confidence average a correctness probability.

The new diagnostic checks whether confidence selects better pages and whether correlations depend on one issuer. It uses the existing 23-page weak-reference sample; it does not rerun OCR or fit calibration.

- Paddle's geometric-mean ranking selects 12/23 pages with 5.1% average error proxy, versus 8.6% across all pages.
- MinerU's most-confident half still includes its severe repetition failure.
- These are exploratory findings; reviewed, independent documents are the next priority.

[Measured results](results/REPORT.md) · [New-chat handoff and next experiment](HANDOFF.md)

Run `python3 diagnose.py`, then `python3 -m unittest -q test_diagnose` from this folder. Both use only Python's standard library. Existing native-confidence code and sponsor presentations remain unchanged.
