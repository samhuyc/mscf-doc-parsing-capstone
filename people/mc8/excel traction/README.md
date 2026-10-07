# Canonical Excel extraction v1

This experiment converts `.xlsx` and `.xlsm` workbooks into auditable JSON for
the document-parsing benchmark. It preserves workbook structure before any
financial-statement normalization: sheets, cells, formulas, cached results,
number formats, merged-cell roles, hidden flags, detected tables, and original
cell coordinates.

The implementation intentionally uses `openpyxl` only in the parsing path. It
does not use pandas, evaluate formulas, define a financial ontology, or silently
invent missing values.

## Contents

- `schema/workbook.schema.json`: canonical JSON Schema (version 1.0.0).
- `excel_parser/parser.py`: two-pass workbook parser and rule-based table
  detector.
- `scripts/extract_workbook.py`: command-line extractor.
- `scripts/generate_fixtures.py`: edge-case and gold-workbook generator.
- `scripts/evaluate.py`: Level 1 reconstruction and Level 2 line-item survival
  evaluation.
- `REPORT.md`: measured fixture results and their limits.
- `benchmark_cases/`: 11 sponsor-pilot and 278 TAT-QA tables converted into
  committed Excel workbooks with machine-readable gold data.
- `scripts/evaluate_benchmark_cases.py`: broader financial-table evaluation.
- `fixtures/`: generated edge-case workbook, hand-labeled financial workbook,
  and gold annotations.
- `tests/`: regression tests for formulas, caches, merges, hidden cells,
  errors, multiple tables, and both evaluation levels.
- `docs/`: formula policy, PDF JSON mapping, and sponsor questions/defaults.

## Reproduce

Use Python 3.10 or newer from this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python scripts/generate_fixtures.py
python -m unittest discover -s tests -v
python scripts/evaluate.py
python scripts/evaluate_benchmark_cases.py
python scripts/extract_workbook.py fixtures/gold_financial_statement.xlsx
```

The extractor writes JSON to `outputs/` by default. Generated outputs are not
committed because they contain machine-specific absolute source paths; the
evaluation summary in `results/evaluation.json` is committed.

## Canonical cell semantics

Every cell in a sheet's used rectangle has:

- `coordinate`, `value`, and stable `value_type`;
- `formula`, `cached_value`, and an explicit cache status;
- the original Excel `number_format` (not rendered text);
- merged-cell role, range, and anchor; and
- row and column hidden flags.

Blank merged children and blank cells inside the used rectangle are retained so
tables can be reconstructed without losing shape. Each detected table includes
its range, cell coordinates, optional title, and title/header/body/footnote row
numbers. See `docs/FORMULA_POLICY.md` for the exact formula contract.

## Rule-based table detection

The v1 detector is tuned for classic financial-statement layouts:

1. Rows with at least two non-empty cells are table-core candidates.
2. Candidate rows separated by no more than one intervening row form a table.
3. The first core row is the header; remaining core rows (including an internal
   spacer) are body rows.
4. Nearby one-cell or spanning merged rows are titles.
5. Nearby rows beginning with `Note`, `Source`, or `*` are footnotes.

This deliberately transparent rule set can miss side-by-side tables, tables
whose data rows contain only one populated cell, layouts separated by multiple
blank spacer rows, and titles or notes farther than three rows from the table.
It can also join adjacent tables separated by only one blank row. Those cases
should become labeled test cases before making the detector more complex.

## Evaluation

Level 1 reconstructs every detected table from canonical JSON and compares raw
values—and formula caches where applicable—with an independent direct
`openpyxl` read. The target is 100%; any mismatch fails the command.

Level 2 uses a small hand-labeled balance-sheet/P&L workbook. It checks that
selected line-item labels survive, remain at the expected coordinates, and
retain the expected numeric or cached values. This is a provenance and survival
test, not a financial ontology or downstream RAG score.

The generated fixtures are synthetic and contain no restricted source data.
The converted benchmark cases extend the test to 289 published financial
tables. See `benchmark_cases/README.md` for provenance, licensing, conversion
details, and the important native-Excel limitation.
