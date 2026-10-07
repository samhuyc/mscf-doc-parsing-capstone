# Converted financial-table benchmark cases

These files let the Excel parser run against financial tables already used by
the capstone's evaluation work.

| File | Contents |
| --- | --- |
| `sponsor_pilot_tables.xlsx` | 11 reference tables from the October 5 sponsor pilot, one worksheet per table |
| `sponsor_pilot_tables_gold.json` | Exact cells, merged ranges, titles, and expected header rows for those 11 tables |
| `tatqa_dev_tables.xlsx` | All 278 tables from the official English TAT-QA development split |
| `tatqa_dev_tables_gold.json` | Exact source matrices, context IDs, dimensions, and expected header rows |

Each worksheet has a merged source-title row, a blank spacer row, and the
benchmark table beginning at `A3`. HTML row/column spans in the sponsor
references become Excel merged ranges. Values remain strings so punctuation
such as parentheses, percent signs, currency symbols, commas, dashes, and
decimal precision can be compared exactly.

## Run the evaluation

From the parent `excel traction` directory:

```bash
python scripts/evaluate_benchmark_cases.py
```

This writes `results/benchmark_cases.json`. It evaluates cell values, source
coordinates, merged-cell metadata, table count, exact table boundaries, title
association, and header-row classification.

## Regenerate the cases

The sponsor reference HTML files are already in the repository. Regeneration
also requires the pinned TAT-QA development JSON:

```bash
python scripts/build_benchmark_cases.py \
  --tatqa-source /path/to/tatqa_dataset_dev.json
```

The builder requires SHA-256
`8da095a819af6db3c14877c6df2d4d29960e41d1a63dd1fa853507bd2a616af5`
from upstream commit `644770eb2a66dddc24b92303bd2acbad84cd2b9f`.
Generated workbooks have deterministic metadata and ZIP timestamps.

## Provenance and limits

- The sponsor cases come from `people/samhu/2026-10-05_pilot_benchmark/reference_tables`.
  Those references are assistant-authored preliminary labels and have not been
  independently human verified.
- TAT-QA is attributed to its official upstream project. The dataset is CC BY
  4.0, as recorded in the existing TAT-QA benchmark documentation.
- Both sources were converted into controlled `.xlsx` containers. This tests
  realistic financial-table content and known layouts, but it does not measure
  the quirks of native sponsor-authored Excel files.
- An explicit source empty string is normalized to an Excel blank and returned
  by `openpyxl` as `null`. Results report this separately from nonblank value
  accuracy.
