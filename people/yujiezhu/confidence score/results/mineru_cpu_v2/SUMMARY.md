# MinerU CPU subset pilot

Status: in progress. MinerU parsed 3/9 complete documents.

This experiment evaluates **MinerU 2.1.11 pipeline CPU + explicit-labels-tables-v1**, using the official metric functions on a selected subset. It is not a full benchmark submission, a score for MinerU alone, or a calibrated confidence model.

The local extractor uses only explicit labels and HTML table headers. It omits unsupported or ambiguous fields, does not infer missing values, and supplies no page/box citations. Its incomplete schema coverage is a material limitation.

## Documents and scores

| ID | Pages | Parser | Extractor | Value F1 | Row precision | Row recall | Leaf accuracy | Parser seconds |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 01_extractbench | 1 | success | completed | 24.00% | — | — | — | 52.436 |
| 02_extractbench | 2 | success | completed | 59.09% | — | — | — | 85.309 |
| 03_extractbench | 12 | success | completed | 13.69% | — | — | — | 611.391 |
| 04_extractbench | 25 | running | not_run_parser_running | — | — | — | — | — |
| 05_extractbench | 59 | not_run | not_run | — | — | — | — | — |
| 06_extractbench | 56 | not_run | not_run | — | — | — | — | — |
| 07_longextract | 40 | not_run | not_run | — | — | — | — | — |
| 08_longextract | 204 | not_run | not_run | — | — | — | — | — |
| 09_longextract | 212 | not_run | not_run | — | — | — | — | — |

ExtractBench reports value F1; LongExtractionBench reports row precision/recall and leaf accuracy. Dashes indicate unavailable/inapplicable metrics.

## Aggregate interpretation

- **extractbench:** 3/6 scored; value F1 32.26%. Schema-valid outputs: 0/6. Attempted terminal failures score zero; unfinished jobs excluded and disclosed.
- **longextract:** 0/3 scored; row precision —, row recall —, leaf accuracy —. Schema-valid outputs: 0/3. Completed nonempty extractions only; failures excluded and disclosed.

A low extraction score can reflect an unsupported schema mapping even when the text is present in MinerU output. Inspect raw outputs before attributing errors to MinerU. Grounding scores are zero where applicable because this adapter supplies no citations.

## Inspect the artifacts

| ID and source task | Original PDF | MinerU Markdown | Predicted JSON |
| --- | --- | --- | --- |
| 01_extractbench: `short/aclu_cdwg_invoice` | [PDF](../../data/01_extractbench/document.pdf) | [Markdown](../../runs/mineru_cpu_v2/01_extractbench/parsed/document/auto/document.md) | [JSON](../../runs/mineru_cpu_v2/01_extractbench/prediction.json) |
| 02_extractbench: `short/13f__audent_global_2025q4` | [PDF](../../data/02_extractbench/document.pdf) | [Markdown](../../runs/mineru_cpu_v2/02_extractbench/parsed/document/auto/document.md) | [JSON](../../runs/mineru_cpu_v2/02_extractbench/prediction.json) |
| 03_extractbench: `medium/13f__nalls_sherbakoff_2025q4` | [PDF](../../data/03_extractbench/document.pdf) | [Markdown](../../runs/mineru_cpu_v2/03_extractbench/parsed/document/auto/document.md) | [JSON](../../runs/mineru_cpu_v2/03_extractbench/prediction.json) |
| 04_extractbench: `medium/baker_hughes_earnings_deck_q4fy25` | [PDF](../../data/04_extractbench/document.pdf) | — | — |
| 05_extractbench: `long/real_credit_strategies_full` | [PDF](../../data/05_extractbench/document.pdf) | — | — |
| 06_extractbench: `long/dd1155_schedule_continuation_0011` | [PDF](../../data/06_extractbench/document.pdf) | — | — |
| 07_longextract: `06_10_26_Budget_vs_actuals_report_cbd029d1_2024_09_SEP_Period_3_MFR_1` | [PDF](../../data/07_longextract/document.pdf) | — | — |
| 08_longextract: `m1__Calibration__Quarterly_Report__10-Q__-_JPMorgan` | [PDF](../../data/08_longextract/document.pdf) | — | — |
| 09_longextract: `06_10_26_Federal_Reserve_Z_1_Financial_Accounts_of_the_United_States_e` | [PDF](../../data/09_longextract/document.pdf) | — | — |

## Reproducibility and limitations

- PDFs, schemas, and reference files are hashed in `manifest.json`; revisions are pinned in `pilot_config.json`.
- Run metadata, logs, raw artifacts, predictions, and extraction evidence are retained in `runs/` locally.
- Model/package versions and adapter source hash are recorded; the adapter was frozen before official scoring.
- Hardware: Intel Core i5-8257U, 8 GB RAM. MinerU uses CPU, four threads, batches of four pages, tables enabled, formula recognition disabled, and `ch_lite` OCR.
- The English-specific OCR configuration could not load its retired model files. `mineru_cpu_v1` is an unsuccessful setup attempt; this report uses the separately recorded rerun.
- A 30-minute parser limit applies per document. Timing includes CLI startup; the smoke run warmed the model cache.
- No model API or LLM was used. Nested arrays, contextual field interpretation, and implicit unit scaling are unsupported by the schema adapter.
- Sampling was purposive and small. Scores do not establish a population ranking or a confidence probability.
- LongExtractionBench leaf accuracy is conditional on matched rows and must be read with row recall and completion.

[Detailed results](results.json) · [CSV](summary.csv) · [Parser inventory](parser_inventory.json) · [Source-page spot checks](../../spot_checks.md)
