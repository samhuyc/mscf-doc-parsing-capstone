# Unified document parsing evaluation framework

This folder turns the strongest ideas from the team's FinTabNet, PubTabNet,
PubLayNet, TAT-QA, OmniDocBench/FinCriticalED, sponsor-document, and metadata
experiments into one dependency-free evaluation harness.

The framework answers several questions separately:

1. Did the parser run, and on the intended source bytes?
2. Did it preserve text, reading order, and financial number formatting?
3. Did it recover tables, spans, merged-cell structure, rows, and cell content?
4. Are financial values attached to the correct row and header path?
5. Did it retain downstream evidence such as answer spans and arithmetic operands?
6. Did it detect the right layout classes and bounding boxes?
7. Did a downstream metadata extractor resolve the right fields and abstain when appropriate?
8. How do quality and runtime vary by dataset, document, input type, and other attributes?

There is deliberately **no overall weighted score**. A high text score cannot
cancel a wrong sign or a value placed under the wrong year. Report the relevant
metric family and inspect its failures.

See [SOURCE_SYNTHESIS.md](SOURCE_SYNTHESIS.md) for the repository review and the
reason each component was included.

## Quick start

Python 3.10 or newer is sufficient; there are no third-party dependencies.

```bash
cd people/yujiezhu/evaluation_framework
python3 framework.py validate examples/manifest.jsonl examples/references.jsonl examples/predictions.jsonl
python3 framework.py score examples/manifest.jsonl examples/references.jsonl examples/predictions.jsonl \
  --output examples/results.json --summary-csv examples/summary.csv
python3 -m unittest discover -s tests -v
```

`validate` checks IDs, review states, run states, prediction/source hash
agreement, optional artifact hashes, and optional exact evidence spans. `score`
validates first and refuses to produce results from an invalid contract.

## Data flow

```text
source documents ── parser adapter ──────────────── predictions.jsonl
       │
       ├── frozen identities/hashes ─────────────── manifest.jsonl
       └── labels (kept from parser input) ──────── references.jsonl
                                                        │
                  validate → score → results.json + summary.csv
```

References must never be passed to the parser adapter. Raw parser output should
be retained beside the adapted record. Adapters may serialize only supported
capabilities; absent labels produce `N/A`, not a perfect score.

## Contract

Each file is JSON Lines: one JSON object per nonblank line.

### Manifest

Required fields:

```json
{
  "id": "sample-001",
  "document_id": "issuer-report-2025",
  "dataset": "fintabnet",
  "split": "test",
  "input_kind": "table_image",
  "source_sha256": "...",
  "attributes": {"language": "en", "scan_type": "digital"}
}
```

Use stable IDs. Split by document/issuer before selecting pages to avoid leakage.
Keep image, native-PDF, rendered-context, and OCR-assisted pathways distinct.

Optional `artifacts` make exact evidence auditable:

```json
"artifacts": {
  "pages": {"path": "exports/sample-001/pages.json", "sha256": "..."}
}
```

### References

Every manifest ID needs one reference. References are capability-based; omit a
field when no appropriate gold exists.

```json
{
  "id": "sample-001",
  "review_status": "human_verified",
  "text": "optional complete reference text",
  "tables": [{"html": "<table>...</table>"}],
  "table_facts": [
    {"row_label": "Operating profit", "header_path": ["2025"], "value": "(84.6)"}
  ],
  "critical_spans": ["Operating profit"],
  "arithmetic_operands": ["84.6", "12.0"],
  "layout": [{"class": "table", "bbox": [10, 20, 400, 500]}],
  "metadata": {
    "reference_period": {"value": {"year": 2025, "kind": "year", "number": null}, "status": "resolved"},
    "document_date": {"value": null, "status": "not_found"}
  }
}
```

Tables may instead use `{"grid": [["header", "2025"], ...]}`. HTML retains
`rowspan` and `colspan`; grids intentionally cannot invent them. `table_facts`
checks presence separately from row/header association and tolerates unrelated
blank spacer columns.

Review states are `draft`, `human_verified`, `adjudicated`, and `excluded`.
Normal scoring admits only verified/adjudicated labels. Use `--include-drafts`
only for clearly identified preliminary development results.

Optional evidence entries cite exact source spans:

```json
"evidence": [{
  "artifact": "pages", "pointer": "/pages/0/markdown",
  "start": 15, "end": 31, "quote": "Operating profit"
}]
```

The artifact must be inside `--artifact-root`; its declared hash and the JSON
pointer/offset/quote are verified. This validates provenance, not semantic truth.

### Predictions

```json
{
  "id": "sample-001",
  "parser": "mineru-3.4.5-pipeline",
  "status": "success",
  "source_sha256": "...same value as manifest...",
  "text": "untouched or deterministically adapted parser text",
  "tables": [{"html": "<table>...</table>"}],
  "layout": [{"class": "table", "bbox": [11, 19, 401, 501]}],
  "metadata": {},
  "runtime_seconds": 1.23
}
```

Run states are `success`, `partial`, `empty`, `failed`, and `timeout`. A missing
parser/sample row is synthesized as `missing`. All remain in applicable
denominators. `runtime_seconds` should measure parser work under a declared and
consistent scope; missing timing is preferable to mixing incompatible timings.

Adapters must not repair numbers, infer missing cells, or use reference values
to choose a table. Record parser/model versions, settings, prompt, OCR route,
hardware, and costs in a separate run manifest retained with predictions.

## Metric families

| Family | Metrics | What it reveals |
|---|---|---|
| Run | success rate, status counts, runtime | operational coverage and cost |
| Text | WER, text accuracy, character similarity, reading order | transcription fidelity and ordering |
| Numbers | lexical precision/recall/F1 | signs, grouping, decimals, currencies, and suffix retention |
| Tables | count, structure/content similarity, cell P/R/F1, row/shape/exact match, anchored numeric F1 | reconstruction quality from forgiving to strict |
| Financial association | selected-value presence, row/header association, exact formatting, negative-value accuracy | whether a retained value still means the right thing |
| Downstream evidence | critical-span and arithmetic-operand retention | whether later QA/extraction still has required evidence |
| Layout | class-aware IoU precision/recall/F1 and mean matched IoU | region detection independently of OCR text |
| Metadata | exact value/status, supported-value accuracy, coverage, explicit abstention, missing-prediction rate | downstream deterministic or model extraction behavior |

Every metric records its direction, numerator, denominator, and per-sample value.
The report includes:

- sample macro average;
- pooled micro value where count aggregation is meaningful;
- equal-document macro average so long documents do not dominate;
- dataset and input-kind strata by default; and
- arbitrary additional manifest attributes with repeated `--stratify-by FIELD`.

For confidence intervals on a larger benchmark, bootstrap documents—not pages or
cells—because pages from one filing are correlated. This implementation keeps
the necessary document IDs but does not manufacture intervals for tiny pilots.

## Interpretation rules

- Never compare these custom scores with an official leaderboard unless the
  dataset revision, split, preprocessing, input modality, and official metric
  implementation match.
- `null` means not applicable or not observed. It is not zero and not one.
- A valid output is not necessarily a correct output; read status and quality
  separately.
- Numeric presence does not establish correct row/year/unit association.
- Exact table match is intentionally strict. Read it beside cell recall and
  structure similarity.
- Metadata exact match including null must be paired with supported-value
  accuracy and coverage, or abstention can look artificially strong.
- OCR confidence is not a calibrated probability of document correctness.
- Freeze manifests, references, adapters, and scorer version before a final
  comparison. Reserve fresh issuer-disjoint documents for held-out evaluation.

## Extending the framework

Keep parser-specific code outside `framework.py`. An adapter should only map
native output into the contract and retain a pointer/hash to the original. New
metrics should be added only when the reference supports them, with adversarial
tests proving that missing output, swapped headers, lost signs, duplicates, and
malformed structures fail as intended.
