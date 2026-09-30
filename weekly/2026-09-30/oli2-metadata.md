# O6: Document metadata extraction

Implemented a deterministic metadata prototype for the six sponsor documents,
using existing parsed outputs. It extracts document type, reporting period,
reference date and document date with source-page evidence and explicit abstention.

The 1.0.0 baseline exposed an ambiguity between a current-period title and
comparative table headers. A general rule, heading/title > narrative > table,
resolved it in 1.1.0: two decisions changed and the other 22 stayed unchanged.
Adversarial tests include a future-year table entry to verify that the rule does
not simply choose the latest year.

On this six-document prototype set, 1.1.0 matches all provisional reference labels:
18/24 fields have resolved values and six have expected abstentions. All 473
evidence spans validate; extraction took about 0.26 seconds. These labels are
development-set annotations, not held-out gold. All 34 tests pass.

Next: expand to a larger independently labeled corpus and test generalization
before considering an LLM fallback.

- [Experiment, reproduction instructions and baseline analysis](../../people/oli2/2026-09-29_metadata_extraction/README.md)
- [1.1.0 evaluation](../../people/oli2/2026-09-29_metadata_extraction/results/1.1.0/evaluation.json)
- [Changed decisions](../../people/oli2/2026-09-29_metadata_extraction/results/1.1.0/comparison.json)
