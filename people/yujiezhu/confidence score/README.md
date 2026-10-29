# MinerU benchmark pilot and confidence scoring

Research checked: October 28, 2026. The nine-document pilot is implemented and
downloaded (611 pages). See the [live run report](results/mineru_cpu_v2/SUMMARY.md)
for persisted completion states and scores; unfinished jobs are explicitly shown.

## Run this pilot

This machine is an Intel Mac with 8 GB RAM. It uses MinerU **2.1.11 pipeline CPU**,
not the newer Apple-silicon setup from the team's earlier experiment. OCR is
`ch_lite` (the default CPU multilingual mode); this release's English-specific
configuration requests retired model filenames and failed during setup.

No model API is configured, so `extract_rules.py` performs conservative local
schema mapping. This is an incomplete rule-based baseline, not a replacement for
a general schema-guided extraction model. Unsupported fields are omitted and
schema-validation failures are reported. Its code hash was frozen before scoring
in `adapter.lock.json`. Do not tune it against these pilot answers and then report
the same documents as held-out results.

From this directory, using the environments prepared here:

```sh
# Fetch the exact files/revisions in pilot_config.json; resume existing downloads.
.venv/bin/python prepare.py

# Resume successful documents; refuses to overwrite failed or unfinished records.
# Use a different --run name for a new configuration or retry.
.venv/bin/python run_parser.py --run mineru_cpu_v2 --timeout 1800

# Uses only Markdown + schema for prediction; references enter at scoring time.
.venv-score/bin/python evaluate.py --run mineru_cpu_v2
.venv/bin/python report.py --run mineru_cpu_v2

# Meaningful failure cases and official scorer positive/negative controls.
.venv-score/bin/python -m unittest -v test_pilot
```

To reproduce on another Intel Mac, create Python 3.11 and Python 3.12 environments
named `.venv` and `.venv-score`. Install `requirements-mineru.lock.txt` in the
first; run `prepare.py`; then install `requirements-scorer.lock.txt` in the
second. Scorer requirements refer to the upstream source directories downloaded
by `prepare.py`. The lock files capture the tested environment, not a portable
GPU setup. Network access is required for datasets, packages, and uncached model
weights. Existing successful artifacts are hash-checked before reuse.

Large PDFs, labels, environments, model caches, logs, and raw predictions stay
local in ignored directories. The manifest, scripts, small reports, and version
locks are shareable. PDF and output links in the report work on this machine;
another checkout must download/reproduce the ignored artifacts first.

The design notes below describe the original proposal. The implemented pilot
uses the explicit-label adapter because no model endpoint was available.

## What these benchmarks measure

Both sponsor links support evaluating a document extraction pipeline. Their
reference answers are schema-based structured data, so MinerU Markdown or layout
JSON cannot be sent directly to their scorers as a completed extraction.

| Benchmark | Public data | Evaluation target |
| --- | --- | --- |
| [ExtractBench](https://huggingface.co/datasets/llamaindex/ExtractBench) | 370 documents; short, medium, and long splits | Unified value F1; page/box grounding where verified evidence exists |
| [LongExtractionBench](https://www.micro1.ai/benchmark/long-extraction) | [50 public tasks](https://huggingface.co/datasets/micro1-inc/longextract-bench-50) from the reported 225-document corpus | Row precision, row recall, leaf accuracy, completion/failure reporting, and latency |

ExtractBench includes document PDFs, schemas, expected outputs, and field rules.
The public LongExtractionBench tasks each contain a PDF, schema, and ground truth.
The latter is particularly useful for missing rows and tables spanning pages.

Use the upstream [ExtractBench evaluator](https://github.com/run-llama/ExtractBench)
and [LongExtractionBench evaluator](https://github.com/micro1-research/longextract-bench)
for their respective official metrics. Keep reports separate: their metrics and
failure handling differ. ExtractBench's documented official time limit is 30
minutes, with failures/timeouts receiving zero. The public LongExtractionBench
harness reports accuracy over completed documents alongside failures and latency.
Its website additionally separates incompatibility; pin the code revision and
document the reporting rules actually used.

## Proposed first experiment

1. Start with six ExtractBench documents: two each from short, medium, and long.
   Within those buckets seek financial tables, scans, and repeated records.
   ExtractBench also provides a six-document smoke-test subset, but do not assume
   it has this proposed distribution without checking its manifest.
2. Select three public LongExtractionBench tasks covering increasing document
   length and table complexity. Record actual page counts before running.
3. Freeze document IDs, dataset revisions, PDF hashes, selection rationale, and
   scorer commits before inspecting parser predictions. Use full documents for
   official task scoring; cropped-page debugging runs are separate experiments.
4. Parse each PDF with a fixed MinerU backend/model. Save untouched Markdown,
   tables, available page/box information, logs, runtime, and completion status.
5. Apply one fixed schema extractor to MinerU output plus the task schema. It may
   use deterministic mappings where adequate, or a declared model with a frozen
   prompt and chunking policy. Keep reference answers and scoring-only rules out
   of inference inputs. Do not give this stage the original PDF/images if the
   experiment is intended to measure dependence on MinerU output.
6. Adapt predictions to each upstream evaluator's contract and run its scorer.
   Preserve provenance when mapping fields to pages/boxes; do not fabricate
   coordinates. Record missing grounding support explicitly and follow the
   official evaluator's treatment of missing evidence.
7. Review failures against source pages. Attribute errors to parsing, field
   mapping, chunking/aggregation, or operational failure where evidence permits;
   retain an unresolved category when attribution is uncertain.

The resulting benchmark scores describe **MinerU plus the chosen extractor**.
To compare parsers, hold the extractor, prompt, schema, chunking policy, and
document set fixed and change only the parser. This measures downstream effects
of parser choice; it does not fully isolate transcription and layout quality.

## Direct parsing checks

For a small independently reviewed selection of source regions, check text,
complete table rows, signs/decimals, and row/header/value associations against
MinerU output. Reuse the adjacent [evaluation framework](../evaluation_framework/README.md)
where its label contract applies. Schema ground truth is not a complete page
transcription or table-layout reference, so do not invent WER, TEDS, or layout
scores from extraction labels alone.

Existing MinerU setup and invocation examples are documented in the team's
[MinerU experiment](../../samhu/2026-09-09_minerU/README.md). Record the versions
actually used for this pilot rather than assuming its previous environment.

## Results and confidence

Report benchmark, document ID, page count, parser/extractor configuration,
completion status, official metrics, parser runtime, extraction runtime, and
observed error types. Keep every selected document in the run inventory,
including failures. Nine documents can establish feasibility and reveal errors;
they cannot establish a reliable overall ranking or calibrated confidence model.

A benchmark score measures observed correctness using reference answers. A
confidence score estimates correctness on a new document without those answers.
They are different quantities.

If confidence prediction becomes the next phase, first define its target (for
example, correctness of a returned financial field). Collect inference-time
signals such as source support, schema validity, missing-page indicators, or
parser disagreement. These are candidate predictors, not guarantees. Fit and
evaluate calibration on separate document-level sets; keep related documents
together. Use reliability plots/Brier score and review coverage versus error
rate on a sufficiently large held-out sample. Evaluate completeness separately:
high confidence in returned values does not establish that all rows were found.

Do not present an average benchmark score or raw OCR confidence as a probability
that an unseen document is correct. Label this initial work as a subset pilot,
and do not compare its aggregate directly to full-corpus leaderboard results.
