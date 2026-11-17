# Native-confidence prototype

Shared table crops → unchanged recognizer logits → native output probabilities → optional, separately fitted expected-quality score. No LLM self-rating, cross-model voting or weight training.

## Data and references

- **Sponsor development:** 16 complete original crops plus five repaired crops, replacing three incomplete regions. All six recognizers receive identical pixels. MinerU table mode adds the same 21 inputs.
- **Public development:** 60 FinTabNet_OTSL test images from 57 reports / 34 issuers; max two tables per issuer. Selection was frozen before inference. Four legal exhibit lists have no eligible financial facts and are excluded from financial statistics, not from run coverage. Original benchmark images are often small; model pretraining overlap is unknown.
- **Fresh test:** 17 tables from four new issuers, including seven real scans. References were transcribed directly from source images before inspecting predictions. These are assistant checks, not human approvals. A separate reference snapshot records hashes.
- Fresh pages used the same PP-DocLayout_plus-L detector at 200 DPI. One missed cash-flow table was recovered manually, and two boundaries repaired before recognition. This is a targeted layout audit, not a layout-recall benchmark.

Human reviews remain unchanged. Derived source corrections are explicit in `reference_annotations.py`; `metric_audit.json` records scoring repairs. Raw PDFs, images, weights and predictions remain local under ignored directories.

## What the scores mean

Primary native signal: geometric mean of probabilities for emitted tokens overlapping numbers, excluding HTML/OTSL tags. Secondary signals: all-token, numeric-tail, per-number-tail, structural-token and non-tag-content summaries. Selection uses no reference text. Tokens spanning both content and markup retain their original probability; no conditional probability is invented for a substring.

Paddle reports CTC selected-path character probabilities, not exact marginal correctness probabilities. VLMs report emitted-token probabilities from original logits normalized in FP32. Tesseract reports word certainty / 100, a score control rather than a neural probability. Native scales are not comparable across models. The model files remain below 4 GB; runtime memory can exceed this.

Saved tokens are aligned to the emitted text, including split Unicode pieces. Every native unit is retained. Missing numbers yield missing numeric confidence; they are not assigned zero or discarded from accuracy/prediction evaluation. Omissions have no emitted-token score.

The evaluated adapters use shared crops and greedy decoding, not complete publisher pipelines. Original `METHODS.md` records backend and processor adaptations. The additional MinerU variant uses the publisher's `Table Recognition:` task prompt with the same checkpoint and unchanged logits; it is not a seventh model.

## Accuracy

**Associated financial-value F1:** match `(section, row label, repeated-row occurrence, column-header path, value)` one-to-one; `2 × matches / (reference facts + predicted facts)`. Swapped periods, swapped rows, wrong values, missing facts and extra facts lose credit. Values preserve signs, percentages and guidance qualifiers. Merged headers expand to their column paths. Empty margins, explicit footnotes, equivalent line breaks and global-caption placement are normalized. Global scale/period captions remain part of the association.

This deterministic interpretation is imperfect: ambiguous bare footnotes can count as label errors; complete unit reasoning and arbitrary multi-stub tables are not implemented. Reference notes are not financial values. The same interpretation runs on predicted structure without looking at the reference. No grid is invented for plaintext.

**GriTS_Con:** official Microsoft implementation, pinned with license and source hash under `vendor/`. It scores cell-content similarity with partial text credit. It can score a materially wrong number or period highly; inspect it alongside financial facts.

**Financial-number recall:** separate text-only control across all six models. It ignores extra numbers and association errors. It must not be presented as table accuracy. Malformed/missing table output from a table task receives zero structure accuracy rather than disappearing from the comparison.

## Validation

Each model is evaluated separately. Leave one whole issuer out; fit a monotone isotonic map on the remaining issuers. The primary map uses numeric confidence. Secondary score selection uses another issuer-held-out loop inside training only. Compare prediction MSE/MAE against the training-mean baseline. Missing selected scores use that baseline explicitly and are flagged for review.

Report benchmark-only, sponsor-only and combined development diagnostics. These are retrospective development results: scoring repairs used source inspection and development outputs. Approximate intervals bootstrap issuers over held-out predictions; they do not capture every source of selection or reference uncertainty.

Two calibration families—benchmark-only and combined development—were frozen before fresh-output inspection. Fresh scores never select a feature, threshold or model. Four fresh issuers are too few for a broad reliability claim. Digital and scanned results are also shown separately. Review prioritization uses the bottom-20% training confidence cutoff; held-out coverage varies, and ties stay together. No automatic approval is issued.

## Use and reproduce

From this experiment directory:

```sh
# Inspect saved results
work/extra-env/bin/python prototype/panel.py
# Open http://127.0.0.1:8768

# Predict a new crop, without reference labels
work/extra-env/bin/python prototype/predict_crop.py --image /absolute/path/crop.png --engine glm

# Score an existing instrumented output without rerunning its model
work/extra-env/bin/python prototype/score_round2.py --engine glm --record /absolute/path/output.json

# Recompute evidence/evaluation after all inference completes
work/extra-env/bin/python prototype/extract_evidence.py --selected-only
work/extra-env/bin/python prototype/extract_evidence.py --root runs/native_prototype/benchmark
work/extra-env/bin/python prototype/extract_evidence.py --root runs/native_prototype/repairs
work/extra-env/bin/python prototype/extract_evidence.py --root runs/native_prototype/sponsor_table_mode
work/extra-env/bin/python prototype/extract_evidence.py --root runs/native_prototype/fresh_public
work/extra-env/bin/python prototype/evaluate.py
work/extra-env/bin/python prototype/analyze.py
work/extra-env/bin/python prototype/analyze.py --fresh
work/extra-env/bin/python prototype/build_report.py
work/extra-env/bin/python prototype/audit.py
work/extra-env/bin/python -m unittest discover -s prototype -p 'test_*.py'
```

Use the three pinned environments already recorded in the parent directory. `run_batch.py --root …` resumes matching records and allows only one heavy recognizer at a time. Preparation scripts record input/source hashes. Do not rerun preparation over completed inputs; create a new run for changed crops. Never refit `calibrators_frozen.json` after inspecting its test outputs.

## Incremental revisions and final test

**Round one remains preserved.** After its 17 fresh outputs were inspected, source review found false errors in the deterministic scorer: year/currency/scale headers treated as body values, `unaudited` rows treated as data, and explicit LaTeX letter footnotes. `table_structure_v2.py` corrects these formatting cases while retaining penalties for swapped years, wrong periods and misplaced values. `metric_sensitivity.py` applies the same rules to both sides, records every changed score, and leaves the original metric/calibrators/results intact. Its 17-table results are post-inspection sensitivity analysis, not untouched validation.

**Round two:** all 94 eligible earlier tables become development. Add four native-only summaries: header geometric mean/p10 and row-label geometric mean/p10, located from the model's own emitted structure. No reference selects tokens. Nested issuer validation compares numeric confidence, selection among the original eight summaries, and selection among all twelve. Features with less than 80% training coverage cannot be selected; missing test scores use the training mean and trigger review. No recognizer weights, logits or decoding settings change.

The final maps were frozen at `2026-11-16T19:16:17Z`, before final-test inference. A separate seal records scorer/evaluator hashes and exact inputs. The requested 40-company cohort yielded **11 new companies** because public row retrieval returned 429/502 errors. These are deterministically selected available FinTabNet test samples, one per issuer, excluding every prior issuer. This availability-limited sample is not representative of all financial reports; foundation-model pretraining overlap is unknown. All seven configurations receive the identical 11 images. The original 17 fresh tables are not counted as round-two held-out evidence.

`score_round2.py` consumes a saved instrumented output and the sealed development map. `predict_crop.py` runs one model first. Both return raw native summaries separately from an expected financial-association F1 and review flags. They never read the crop's reference labels and never auto-approve it. Missing numeric confidence stays missing; the expected-score fallback is explicitly labeled.

Round-two reproduction:

```sh
# Existing preserved outputs -> corrected sensitivity -> development freeze.
work/extra-env/bin/python prototype/metric_sensitivity.py
# train_round2.py refuses to overwrite its existing freeze.
# download_confirmatory.py refuses to overwrite its existing manifest.
work/extra-env/bin/python prototype/run_confirmatory.py
work/extra-env/bin/python prototype/package_results.py
```

Preserve the original `calibrators_frozen.json`, `round2/calibrators_frozen.json`, input seals and reference snapshots. Changed models, scoring rules or new calibration data require a new version and a new test cohort. `input_manifest.json` distinguishes source-report identifiers from full PDFs; most public benchmark inputs are table images rather than full documents. Numerical arrays in the scientific plots use the same saved measurements; near-one confidence is expanded only for display.

## Final measurement audit

The sealed eleven-table test exposed two further limitations: `fintabnet_test_02146` omits a unit caption in the public reference and triggers a frozen header-classification error; `fintabnet_test_09879` has a title/year row classified as data. Both are visibly flagged in the panel. Neither references, metric, frozen forecasts nor thresholds were changed after test inspection. `round2/measurement_audit.json` additionally excludes both cases across every model as a **post-inspection sensitivity**, not a replacement untouched test. Neither the original eleven-case results nor that nine-case sensitivity establish reliable improvement over the mean-only baseline. The next substantive step is human auditing of financial-fact annotations and header interpretation, before treating forecast accuracy as validated.
