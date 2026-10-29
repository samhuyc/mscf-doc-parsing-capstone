# FinTabNet evaluation results

## Current status

MinerU 3.4.5 was run in Google Colab with the `pipeline` backend on the 25-image pilot. The results below are a small pilot score, not an official FinTabNet leaderboard result.

| Check | Result |
|---|---:|
| Dataset | `docling-project/FinTabNet_OTSL` |
| Split | `test` |
| Samples downloaded | 25 |
| Images present | 25/25 |
| HTML references present | 25/25 |
| Total reference table rows | 368 |
| Total reference table columns | 105 |
| Parser | MinerU 3.4.5, `pipeline` |
| Parser runs completed | 25 |
| Scored successfully | 24/25 |
| Failed sample | `fintabnet-otsl-test-0002` (no predicted table) |
| Cell exact accuracy | 0.3185 |
| Row exact accuracy | 0.1645 |
| Numeric F1 | 0.9355 |

## What this means

The parser outputs are available under `content/fintabnet_pilot/mineru_output/`, and the detailed machine-readable scores are in `RESULTS.json`.

The previous command using `prepare_fintabnet_pilot.py /actual/path/to/FinTabNet` was not an evaluation run; it used a placeholder path for the original PDF/JSONL distribution. The current pilot uses the downloaded OTSL table-image format instead.

## Metrics to report after the parser run

- Exact or normalized cell-content accuracy.
- Table structure accuracy, including merged-cell handling.
- Row/column or topology similarity.
- Numeric-value exact match or numeric F1.
- Per-sample failures and malformed outputs.

Do not report an overall score until the parser name/version, output format, sample count, and scoring implementation are recorded.

## Planned result table

| Parser | Samples | Cell exact accuracy | Row exact accuracy | Numeric F1 | Failures |
|---|---:|---:|---:|---:|---:|
| MinerU 3.4.5 pipeline | 24/25 | 0.3185 | 0.1645 | 0.9355 | 1 |
