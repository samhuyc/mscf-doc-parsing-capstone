# Synthesis of the team's evaluation work

This review covers all evaluation-related work currently under `people/` as of
October 6, 2026. It distinguishes ideas incorporated into the unified framework
from experiment-specific behavior that should remain local.

## What each contribution added

| Contributor / experiment | Strongest contribution retained | Boundary carried forward |
|---|---|---|
| Yujie — pdfplumber/Marker findings | Page-level words, coordinates, dimensions, table boxes, transparent JSON, reading-order review, OCR capability declaration, and honest separation of package failure from model quality | Marker produced no output because of a dependency mismatch, so it cannot receive an accuracy score. The combined run states retain environment failures and missing output instead of silently dropping them. Separated currency cells and extra blank columns motivate both strict structure metrics and tolerant financial association checks. |
| Yujie — FinTabNet/FinTabNet OTSL | Official split/revision awareness; fixed sample manifests and hashes; table-image versus native-PDF distinction; cell, row, structure, and numeric checks; failed tables visible | The 25-image pilot is not an official leaderboard run. First-table-only zip alignment is replaced by multi-table pairing and explicit missing/extra penalties. |
| Yuyang — PubTabNet | Reproducible table-image conversion, timeout isolation, native-output capture, and a quick structural diagnostic | Cell-node-count similarity is useful only as a smoke signal: the right number of cells can still have entirely wrong content or topology. The combined scorer adds content, spans, order, shapes, exactness, and anchored values. |
| Oli — PubLayNet notebooks | Class-aware layout detection with IoU matching, per-class precision/recall/F1, matched IoU, and a clean split between native-PDF and OCR-assisted pathways | OCR word counts/confidence are not layout accuracy. The framework preserves input-path strata and scores layout separately from text. |
| Michael — TAT-QA | Micro WER, explicit text-accuracy complement, order-preserving token accuracy, table cell/shape/exact metrics, answer-span retention, arithmetic-operand retention, and parser-only runtime | Deterministically rendered TAT-QA contexts test clean extraction, not original visual pages or official QA accuracy. The unified report keeps task-evidence retention separate from answering. |
| Sam — OmniDocBench/FinCriticalED | Input/reference separation; common Markdown + HTML-table adapter; tree-like structure/content diagnostics; strict financial number tokenization; numeric-cell anchors; one-to-one table matching; failures in denominators; `null` for unavailable labels; raw output/provenance retention | The custom metrics are diagnostics rather than official TEDS/OmniDocBench/FFA. The dependency-free implementation uses ordered structure similarity rather than claiming official tree-edit distance. |
| Sam — sponsor samples | Full-document source provenance; physical page mapping; digital versus scanned strata; OCR routing; exact financial-row checks; runtime and coverage; visible comparison artifacts; warning against calibrated confidence claims | Selected checks are not document-wide gold. The combined contract names review status and does not turn selected precision into a hallucination score. |
| Sam — October pilot benchmark | Row/header-path/value association; blank-spacer tolerance; complete-matrix precision; adversarial tests; draft/verified/adjudicated label lifecycle; optional review import; report/scorer/label hashes; pooled and equal-document views; no composite score | Preliminary assistant labels remain opt-in. Unscored semantic relationships remain unscored rather than being inferred from proximity. |
| Oli — metadata extraction | Fixed canonical inputs, schema-oriented outputs, evidence spans, exact abstention semantics, supported-value accuracy, coverage, status accuracy, frozen rule versions, leakage controls, and changed-decision comparison | Parser routing was selected outside that experiment, and its six documents are a development set. The combined framework evaluates supplied metadata but does not silently select a parser or extract fields. |

## Design decisions

### One contract, multiple capabilities

A single mandatory Markdown representation would unfairly erase geometry from a
layout parser or force a plain-text parser to invent tables. The unified contract
therefore has optional capability blocks (`text`, `tables`, `table_facts`,
`layout`, `critical_spans`, `arithmetic_operands`, and `metadata`). A metric is
applicable only when its reference block exists.

### Gold-blind adapters

All mature team experiments converged on separating parser input/output from the
reference. The combined validator requires source-hash agreement and never uses
expected cells or values to repair or select predictions. Optional exact evidence
citations borrow the metadata experiment's quotation/offset verification.

### A metric ladder instead of one verdict

The table experiments show why one score is unsafe:

```text
value appears on page
  → value appears in a table cell
    → correct row and hierarchical header
      → correct sign/unit/format
        → exact complete table
```

Each step is reported independently. Similarly, layout IoU, transcription,
metadata decisions, downstream evidence retention, and runtime remain different
families. No weights are supplied because choosing them is a product decision,
not a property of the parser.

### Strict denominator and `N/A` rules

Missing, failed, empty, and timed-out predictions are converted to empty
predictions and stay in every applicable denominator. In contrast, a page with
no table label or no metadata label has an unavailable metric (`null`). This
combines the strongest denominator behavior from the OmniDocBench, TAT-QA, and
sponsor pilots while avoiding the false “perfect on no targets” case.

### Aggregation that matches deployment questions

The report exposes sample macro, pooled micro, and equal-document macro results.
It also stratifies dataset and input type by default. These answer different
questions: pooled counts describe total retained items, sample macro treats pages
equally, and document macro prevents a long filing from dominating. Future
uncertainty estimates should resample whole documents.

### Review and version discipline

Only `human_verified` and `adjudicated` references enter normal results. Drafts
require an explicit flag. The output hashes manifest, references, predictions,
and scorer so a report can be tied to exact inputs. This incorporates the pilot
review gate and metadata ruleset/version lessons without copying their UI or
domain-specific extraction rules.

## Recommended combination

The strongest overall approach is a layered evaluation suite coordinated by
this framework, rather than a single benchmark or weighted composite score.

| Layer | Recommended tool or dataset | Primary purpose |
|---|---|---|
| Financial tables | FinTabNet.c with official GriTS topology, content, and location metrics | Table structure, merged cells, cell content, and geometry |
| Whole-page parsing | OmniDocBench and its applicable official metrics | Text accuracy, reading order, tables, and general document structure |
| Layout geometry | PubLayNet class-aware IoU | Text, title, list, table, and figure region detection |
| Financial fidelity | FinCriticalED plus strict financial-number metrics | Critical numbers, dates, units, entities, and surrounding context |
| Downstream usefulness | TAT-QA evidence-retention metrics | Whether answer spans and arithmetic operands survive parsing |
| Real-world validation | Independently reviewed sponsor-document labels | Correct row, hierarchical-header, value, sign, and unit associations on realistic reports |
| Metadata | Evidence-backed metadata evaluation | Document type, reporting period/date, explicit abstention, and evidence validity |
| Coordination and reporting | This unified framework | Contract validation, provenance, review gates, failures, stratification, and aggregation |

### Recommended core suite

For the first production-quality version, use **FinTabNet.c + OmniDocBench +
TAT-QA + an independently verified sponsor-table set**. Together they cover
financial table structure, whole-page fidelity, downstream evidence retention,
and realistic financial associations. Add PubLayNet when bounding-box quality is
important, FinCriticalED when critical-field preservation is in scope, and the
metadata evaluation when downstream document classification and dates are part
of the product.

Each component should retain its own official or fit-for-purpose metrics. Results
should be passed through the unified framework for consistent source hashes,
denominators, review status, per-sample diagnostics, and dataset/input-type
strata. Scores from different datasets should be presented as a suite and never
pooled into one number.

### Acceptance gates

Parser acceptance should use separate minimum requirements for:

- run completion and nonempty-output coverage;
- text accuracy and reading order;
- GriTS or another pinned table-structure metric;
- numeric precision/recall, with signs and units preserved;
- row/header/value association accuracy;
- critical-span and arithmetic-operand retention;
- metadata supported-value accuracy, coverage, and valid abstention; and
- runtime and failure rate, stratified by digital, scanned, and image-only input.

This prevents a strong text result from compensating for a wrong financial sign,
period, unit, or column association.

### Metrics that should remain secondary

- PubTabNet cell-node-count similarity is a useful smoke diagnostic, but a table
  can have the correct cell count and incorrect topology or content.
- Page-level numeric recall cannot establish that values belong to the correct
  row, header, period, or unit.
- Exact table match is too strict to describe partially useful extraction and
  must be read alongside cell recall and structure similarity.
- OCR confidence is not calibrated document correctness and is not comparable
  across engines without held-out calibration.
- A weighted overall score can hide critical failures and is therefore not
  recommended.

### Parser deployment implication

Evaluation tools and parsers should remain conceptually separate. If a parser
deployment combination is also needed, the current team evidence favors
PyMuPDF/PyMuPDF4LLM for fast native-PDF extraction with selective OCR, plus a
MinerU VLM fallback for difficult scans and complex tables. This is a routing
hypothesis to validate with the suite above, not a conclusion that should be
derived from one pilot or one aggregate score.

## Known gaps and next increments

The first release is intentionally an evaluation core, not a parser runner or
annotation UI. The next useful additions are:

1. thin adapters for the team's existing MinerU, PyMuPDF4LLM, Marker, and plain
   PyMuPDF exports;
2. an issuer-disjoint, independently reviewed benchmark spanning native digital,
   scanned, image-only, and mixed PDFs;
3. reference coverage for cross-page tables, footnote attachment, units/basis,
   charts, hierarchy, and reading order beyond selected pairs;
4. a separate retrieval/chunking benchmark that preserves source-page identity
   and keeps tables intact;
5. official metric adapters (for example GriTS/TEDS) only when their exact
   upstream implementation and preprocessing can be pinned; and
6. document-bootstrap confidence intervals once the sample is large enough.

FinTabNet remains the best financial table-structure component, PubLayNet covers
layout regions, OmniDocBench broadens document structure, FinCriticalED focuses
critical financial fields, TAT-QA tests downstream evidence preservation, and
fresh sponsor documents test deployment realism. They should be reported as a
suite, not pooled into a single number.
