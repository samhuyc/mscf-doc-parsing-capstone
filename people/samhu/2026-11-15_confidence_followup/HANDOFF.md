# Confidence scoring — handoff for the week of November 15, 2026

## Objective and constraints

Build an evaluation/output framework that exposes each OCR model's native recognition confidence, aggregates it to page/document summaries, and tests whether it predicts independent correctness. Sam presented the prototype at the sponsor meeting and reports that it received approval. This week should establish where the signal is useful and improve its evaluation.

Use mechanical model evidence, not an LLM's stated confidence or cross-parser agreement as a substitute. Keep raw native scores separate from any fitted correctness probability. Do not promise that a large native score means a document is correct. Work directly on `main`, preserve teammates' files, and never force-push. Keep both existing presentations usable. Keep explanations short and concrete.

## Repository and status

Local checkout: `/Users/hu/Desktop/CMU MSCF/ML Capstone/mscf-doc-parsing-capstone`

Remote: `git@github.com:samhuyc/mscf-doc-parsing-capstone.git`

On November 15, fetch and fast-forward pull found no new main commits beyond `11ab0a0` (the November 11 merge of our native-confidence work). The current follow-up adds only `people/samhu/2026-11-15_confidence_followup/`. Fetch again when starting; inspect status before pulling or editing.

Three untracked files already existed under the native-confidence folder: `build_slides 2.py`, `slide_template 2.html`, `sponsor_slides 2.html`. They are byte-identical copies of the tracked originals as checked November 15. They were left untouched and excluded from the commit. Do not broadly stage unrelated files.

## What exists

`people/samhu/2026-11-10_native_confidence/` contains code, tests, compact results and presentations:

- PaddleOCR PP-OCRv5 mobile: retain CTC selected-path character probabilities before line averaging, with positions and alternatives. It is not an autoregressive LLM. These are not exact marginal probabilities that final characters are correct.
- Local MinerU2.5-Pro-2605-1.2B: retain token logits/alternatives, promote logits to FP32 before stable normalization. This fixed numerical exact-one scores. It did not remove genuine high certainty. The current run uses full-page generation, not MinerU's full layout-guided crop pipeline; check intended deployment before extending it.
- Tesseract baseline: word-certainty values. PyMuPDF renders/extracts PDF content; its native text extraction does not supply recognition probabilities.
- Mean, character-weighted mean, geometric mean, tenth percentile and fraction below 0.90 are raw summaries. Document-correctness probability stays null.
- `sponsor_slides.html` is the newer eight-slide deck; `sponsor_brief.html` is the older interactive brief. Preserve both and their generators.
- `TECHNICAL_NOTES.md` explains extraction, precision, references and resumable commands.

Original v1 processed 140 pages for all three engines. Instrumented v2 completed Paddle 80/140 and MinerU 74/140 before the presentation deadline. Tesseract remains 140/140. Do not merge old and new score versions to imply complete v2 coverage. Saved raw outputs and model weights are ignored local files; compact summaries/evidence are tracked.

## The actual blockers

1. **Ground truth and diversity:** six PDFs from five issuers; 13 assistant-authored, unverified snippets cover just 11 pages and 1,211 characters. These near-perfect snippets are insufficient for document evaluation. Embedded PDF text offers 89 weak-reference pages, but 51 scanned pages have no text layer. Only 23 pages are jointly available in the deadline v2 comparison, clustered in four PDFs from three issuers. They were deliberately selected, not randomly held out.
2. **Mismatch between confidence and the target:** confidence describes emitted text. It cannot by itself measure missing text, table association or completion. MinerU repeated “Underlying operating profit/(loss)” 557 times versus two in the source while averaging 99.873% token confidence. The page hit the 4,096-token limit. Full-page CER was about 697%. A good-looking excerpt concealed the failure.
3. **Incomplete reruns:** caused by the presentation deadline, not an established inability to process remaining pages.
4. **Environment restoration:** `/private/tmp/native-confidence-venv/bin/python` still exists, but its packages are no longer present (November 15: only pip, wheel, certifi; importing rapidfuzz failed). Do not assume the old environment works. Model directory `people/samhu/2026-11-10_native_confidence/work/mineru-model` and saved runs still exist. Restore a persistent environment and inspect the recorded lock/settings before inference; do not blindly upgrade source-guarded hooks.

## New diagnostic completed November 15

`people/samhu/2026-11-15_confidence_followup/diagnose.py` reuses saved v2 page metrics; no inference or calibration fitting. It checks omit-one-document/issuer sensitivity and confidence-based page selection. It retains tied cutoffs and uncapped micro CER. Six unit tests pass. Detailed results: `results/REPORT.md` and `results/diagnostics.json`, with the input SHA256.

On the same 23 weak-reference pages:

- Weighted-mean Spearman: Tesseract 0.535, Paddle 0.366, MinerU 0.205. Paddle geometric mean: 0.427.
- Paddle geometric-mean selection keeps 12/23 pages; mean page error proxy drops from 8.6% to 5.1%. This is promising descriptive evidence, not a validated threshold or reason to choose a winner after the fact.
- MinerU weighted-mean correlation varies from 0.036 to 0.443 when one issuer is omitted. Removing truncated pages changes pooled correlation from 0.205 to 0.377. This is sensitivity analysis, not training/testing or a confidence interval.
- MinerU's top-confidence half still contains the repetition failure. Its selected-page micro CER exceeds 100% under weighted-mean ranking even though clipped average page error looks better.

Reproduce using system Python, without external packages:

```sh
cd people/samhu/2026-11-15_confidence_followup
python3 diagnose.py
python3 -m unittest -q test_diagnose
```

## Recommended next experiment

Start with Paddle, whose character signal is available and whose current page ranking shows some utility. Restore its environment and complete the remaining v2 pages, writing new follow-up results without rebuilding the presentation artifacts. Freeze model/configuration and a primary aggregation before looking at new evaluation labels; retain arithmetic/geometric/tail summaries as declared secondary analyses.

Define the target explicitly: first transcription accuracy over a fixed source region or page, with omission/insertion errors included; separately report table structure and generation completeness. For a document statistic, pool error counts/reference lengths for actual correctness and compare declared confidence aggregations over all pages. Do not describe an average token probability as “probability the whole document is correct.”

Create an independently reviewed, source-anchored sample across more issuer/document families, including scanned pages, small numbers/signs and real errors. Keep a representative sample for headline results and targeted failures in a separate stress set. Reuse teammates' source crops and review infrastructure where useful, but their draft labels are not verified ground truth. Related issuer documents must stay together in fitting/evaluation splits.

Then evaluate ranking (Spearman and review/coverage tradeoffs) before fitting calibration. Report uncertainty at the document-family level and preserve failed/missing cases. If enough reviewed errors and families exist, fit a simple calibration map on development families and test on untouched families. A monotone remapping of an existing scalar cannot repair its ordering; weak ranking needs a better native summary or an explicitly separate quality/completeness signal. Do not secretly blend a heuristic flag into a “native probability.” Report truncation/repetition flags alongside raw confidence first, and test their incremental benefit on new data.

Success for the next iteration: complete score coverage with provenance; reviewed evaluation spanning independent families; a frozen primary statistic; an honest result on whether it ranks quality and routes review usefully. Calibrated probabilities remain a later claim unless held-out evidence supports them.

## Teammate context (brief review, not independently rerun)

- **Yujie:** confidence demo and separate logistic models for numeric transcription versus row/column association. Fifty draft cells; all five numeric errors belong to EDF, so holding EDF out leaves a one-class training set. Scored numeric folds miss all error cases; association struggles with Rolls-Royce headers. Human-review import and family split tooling are useful. This is a different feature-based correctness model, not our native-score baseline.
- **mc8:** Paddle PP-Structure comparison on the same sponsor PDFs; 46/140 pages with selected references. Distinguishes a number appearing on a page from being assigned to the correct cell. Useful reference table/crop assets; labels remain drafts.
- **Oli:** financial research agent integration, tool/evidence validation, memory, CLI and English demo. Potential downstream consumer of our confidence/review signals; does not validate OCR confidence.
- **Yuyang:** older PyMuPDF/PubTabNet work; latest path commits inspected were October 21. No newly fetched work changed our experiment.

## Suggested opening message for a new chat

“Continue the native OCR confidence project. Read `people/samhu/2026-11-15_confidence_followup/HANDOFF.md` and its results report first, inspect main/status, and focus on the next experiment described there. Work on main, preserve both sponsor presentations and teammates' work, and keep native confidence distinct from correctness/calibration. Start by restoring the environment, completing Paddle coverage into new results, and preparing source-anchored evaluation for independent review. Explain decisions briefly; do not replace the task with cross-model agreement.”
