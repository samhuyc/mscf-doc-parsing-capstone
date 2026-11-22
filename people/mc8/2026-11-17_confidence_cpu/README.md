# Six-model confidence pipeline on an Intel Mac

Prepared and run on the 2 GHz Intel i5 / 16 GB MacBook. **300 development tables are complete: 2,100 scored outputs across seven configurations.** The 2,000-table cohort is the planned full experiment; the 400-table final test has not been evaluated.

**[300-table findings and published results](results/300_tables/README.md)** · [Detailed confidence report](results/300_tables/summary.md) · [Presentation PDF](results/300_tables/presentation/confidence_results_summary_2026-11-18.pdf) · [Per-table scores (CSV)](results/300_tables/scores.csv) · [Exploratory development forecasts](results/300_tables/presentation/forecast_and_confidence_summary.md)

The published snapshot preserves the completed November 18 milestone. Native confidence is not a correctness probability. Exploratory issuer-held-out development forecasts are saved separately from the production calibration, which remains pending. Setup/readiness JSON files below describe the earlier installation checks; their `inference_run: false` fields are historical, not the current execution status. Large raw inference records, weights and datasets remain local; compact scores, manifests, methods and source are published here under **mc8**.

- Sam's six recognizers: Tesseract, PP-OCRv5, MinerU, PaddleOCR-VL-1.6, GLM-OCR and MonkeyOCR-pro-1.2B.
- Seven configurations: MinerU text and table modes share a checkpoint. **14,000 planned outputs.**
- **2,000 FinTabNet tables:** all **71** Sam inputs, plus **1,929** additional tables. Original image and annotation hashes match exactly.
- **1,600 development / 400 test** tables. Test issuers: ADS, AKAM, DLR, HOG, NFLX. Sam had already used the other 45 issuers in this test split.
- CPU-only, one resident recognizer at a time, resumable outputs and retained failures. Converted language weights and image projectors use F16, with no low-bit quantization.

From this directory:

```sh
source activate.sh
python preflight.py                 # installation/data checks only
python pipeline.py                  # prints the plan only
```

**Run continuously, saving results after each batch of 100 tables:**

```sh
cd /Users/cbc/Desktop/MSCF/capstone/github_repo/people/mc8/2026-11-17_confidence_cpu
source activate.sh
caffeinate -i python -u pipeline.py --execute
```

The launcher runs **all remaining batches automatically**. After each batch of 100 tables across all seven configurations, it saves cumulative results in **Markdown and JSON**, checkpoints progress, and starts the next batch: **100 → 200 → 300 → … → 2,000** tables. There are **20 batches**: 16 development batches followed by 4 held-out test batches. Calibration freezes after all 1,600 development tables, before test inference starts. Earlier development results contain native confidence and descriptive accuracy, without held-out calibration claims. If batch 1 is already complete, the command starts at batch 2.

Existing compatible outputs are reused, including work already saved by the old full launcher. An interrupted batch resumes its missing outputs on the next invocation; it does not advance until inference and scoring finish. Completed attempts remain cached. Scoring also caches unchanged rows, so later runs update cumulative aggregates without repeating expensive per-table scoring. Batching provides earlier results; it does not reduce the recognizers' processing time per table.

`caffeinate` prevents idle sleep while the command runs; keep the lid open. Nothing starts automatically at installation or activation. These terminal commands do not consume assistant tokens.

After each completed batch:

- **`runs/cpu_v1/summary.md`** is the readable cumulative report, with progress counts and per-configuration accuracy tables. **`summary.json`** contains the same results with full numeric precision and all forecast details. Separate development/test summaries are included. Unrun tables are excluded from these averages.
- **`runs/cpu_v1/batch-results/batch-01.md`** and **`batch-01.json`**, `batch-02.md` and `batch-02.json`, etc. preserve each cumulative milestone in both formats.
- `runs/cpu_v1/development/summary.md` and, later, `test/summary.md` provide readable split summaries alongside their JSON files.
- `runs/cpu_v1/development/pairs.json` and, later, `test/pairs.json` contain cumulative per-table accuracy and native confidence features for each split.
- `runs/cpu_v1/batch-progress.json` records the fixed subsets and which ones are finished.

`python pipeline.py` previews the next batch and continuous-run setting without starting work. To stop after just one batch, use `python pipeline.py --execute --one-batch`. The original launcher without intermediate batch results is available as `python pipeline.py --execute --full` for a full-run directory; use the default batch command consistently for this incremental run.

To regenerate Markdown from saved results without inference or scoring, run `python markdown_report.py`. This also converts existing milestone and split summaries while leaving their JSON files untouched.

Reports also include Sam's available metric families: cohort/issuer counts, GriTS content F1, native numeric confidence coverage/mean/range, median saved recognition time, truncations, exact-F1 and below-0.95 counts, and within-model confidence ranking (Spearman with a 95% issuer-bootstrap interval and error-detection AUC). Development rankings are descriptive; test rankings stay separate. Each historical milestone uses its own table prefix even when newer scores exist. Number recall, GriTS, fact F1 and confidence can have different denominators, which are shown. Runtime medians cover the report prefix, whereas Sam's pasted findings pool his cohorts for runtime.

Forecast MAE/MSE, baseline errors, MSE gain and its interval, selected feature, and review/retention metrics show **Pending** until frozen calibration and held-out forecasts exist. No provisional calibrator is fitted to fill the report. Text-only fact F1 stays **N/A**. Additional full-precision values and source-score hashes are saved beside each report as `summary-metrics.json` or `batch-03-metrics.json`, etc.; original summary JSON, inference records and score caches are preserved. The updated report writer is used on the next launcher invocation; `python markdown_report.py` updates existing reports immediately.

**Watch progress in a second Terminal tab/window:**

```sh
cd /Users/cbc/Desktop/MSCF/capstone/github_repo/people/mc8/2026-11-17_confidence_cpu
source activate.sh
python progress.py --watch
```

Shows the current batch and completed batch count, inference % out of **14,000**, each configuration's counts, successes/failures, active table and elapsed time, pipeline stage, scoring progress and calibration status. Inference counters include compatible outputs saved by earlier full runs, even when those tables have not yet entered a completed batch summary. **Total running time** includes inference, scoring and calibration; each configuration has **Runtime** and **Left (est.)** columns. Timers include model loading/processing and carry across resumed runs, excluding pauses. Older saved timings are reconstructed from existing timestamps and output durations and may be approximate. MinerU text/table modes have separate rows. Inference % counts completed attempts, including failures; scoring/calibration are tracked separately. Per-configuration estimates appear after successful timing samples; the combined remaining/total inference estimate appears after every remaining configuration has samples. Estimates exclude future scoring/calibration time. Ctrl+C in the tracker leaves the experiment running. `python progress.py` prints one snapshot; `--json` produces machine-readable status. The tracker never loads models.

To pause execution, press Ctrl+C in the **experiment** terminal. Run the same command to resume. To retry retained failures, use:

```sh
caffeinate -i python -u pipeline.py --execute --retry-failed
```

This retries failures within the current cumulative prefix, resumes that same unfinished batch, and continues through the remaining batches. A failure stops the launcher so it can be fixed; completed batch summaries remain available if a later batch fails or is interrupted. After calibration freezes, development inference is locked. Changed recognizer settings/weights/data require a new `--run-dir runs/cpu_v2` on **both** the experiment and tracker commands. The continuous-run and reporting updates preserve inference and scoring hashes, so existing records and score caches remain compatible.

For a one-table development pilot later:

```sh
python run.py --execute --split development --limit 1 --run-dir runs/pilot
```

Held-out test scores appear in `runs/cpu_v1/test/summary.md` and `summary.json` once test batches start; the latest overall cumulative results are `runs/cpu_v1/summary.md` and `summary.json` after each batch finishes, even while the next batch runs. Raw native evidence stays in per-engine JSON records. No fitted quality estimate is supplied for the text-only OCR controls. Expected table F1 is distinct from probability that the table is correct.

[Methods and adaptations](METHODS.md) · [Cohort counts](cohort-summary.json) · [Sam's included tables](sam-included-71.json) · [Readiness checks](readiness.json) · [Settings](config.json)

Validation without running models: `python preflight.py --full-hashes`, `python -m pip check`, and `python -m unittest -v test_contracts test_progress test_batches`. Progress/launcher tests use temporary synthetic records and fake subprocesses. Batch checks cover all 20 disjoint subsets, cumulative averages, cache reuse/invalidation, interruption recovery, freeze boundaries and completion without starting extra work. Actual inference, peak memory and throughput require your manual run.

Large weights, environments and input data are local/ignored under `.local/`, `.venv` and `data/`. The installed `.venv` links to the shared capstone CPU environment. Sam's original source/results are preserved and scientific source hashes are checked. To reproduce installation elsewhere, run `python setup.py --stage all`; setup never invokes inference.
