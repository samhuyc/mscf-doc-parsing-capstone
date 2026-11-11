# Extraction evidence — corrected sponsor demo

Open [CONFIDENCE_DEMO.pdf](CONFIDENCE_DEMO.pdf), [speaker notes](SPEAKER_NOTES.md),
or the [evidence report](REPORT.html).

## Implemented next step: separate learned models

[model_pipeline.py](model_pipeline.py) now fits individual-feature logistic models
for numeric transcription and row/column association separately. It includes
document-family validation, a separate sigmoid-calibration stage, label-free
inference, and human-review import. The full result is in
[MODEL_REPORT.md](model_results/MODEL_REPORT.md).

On the actual 50-cell pilot, the numeric model cannot be evaluated on EDF: holding
EDF out removes every numeric error from training. It scores only 40/50 cells,
including **zero of the five errors**. The association model does produce all
50 out-of-family diagnostic estimates, but struggles with the Rolls-Royce merged
headers. These failures are preserved in the report, not filled with in-sample
predictions. This is progress toward a probability model, not evidence that
probabilities are ready for use.

The [additional-data audit](model_results/additional_data_audit.json) found 133
sponsor reference cells (overlapping this pilot), all draft, and 25 local FinTabNet
tables from HAL. A conservative candidate alignment found five discrepancies;
three concern row association rather than established digit errors. No automatic
candidate matches were silently promoted to training labels.

To reproduce the model diagnostics and data audit:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv-score/bin/python model_pipeline.py
../.venv-score/bin/python audit_additional_data.py
../.venv-score/bin/python -m unittest -v test_demo test_model_pipeline
```

Use [review_queue.csv](model_results/review_queue.csv) to collect source-based human
reviews. Proposed labels are separate from blank human decision fields. The
importer requires explicit true/false decisions for numeric, row and column
correctness, a reviewer and date; it checks that the sample/value/context have
not changed and writes a new dataset. It does not certify the unit label.

```sh
# After a human has actually reviewed and filled the CSV:
../.venv-score/bin/python model_pipeline.py \
  --review-csv model_results/review_queue.csv --output reviewed_model_results

# With expanded independently reviewed data and explicit document-family splits:
../.venv-score/bin/python model_pipeline.py \
  --input reviewed_model_results/reviewed_input.json \
  --split path/to/split.json --output calibrated_model_results

# Apply fitted models to new label-free feature records:
../.venv-score/bin/python model_pipeline.py \
  --model calibrated_model_results/calibration_run.json \
  --input new_cells.json --output new_predictions
```

`split.json` has `train`, `calibration`, and `test` arrays of document-family IDs.
Every family must appear exactly once. The supplied split template demonstrates
the format and intentionally fails with the current inadequate data. Each
partition must have reviewed correct and incorrect examples for the target.
The base model and scaler see only training data; the calibrator sees calibration
data; test labels only evaluate. Output remains explicitly experimental even
when these minimum conditions pass. No automatic deployment approval is inferred.

## Correction on November 10

The previous 95.5% and 8.3% figures were add-one-smoothed development group rates:
21/22 from 20 observed successes and 1/12 from zero successes out of ten.
They were not validated probabilities that individual extracted numbers were
correct. Labeling them per-cell confidence overstated the evidence. Those scores,
the associated Brier comparison and the numerical acceptance-threshold example
have been removed from the current outputs. Every cell now has `confidence: null`
and `confidence_status: not_estimated_insufficient_validation`.

Two groups alone are not inherently invalid: a two-group probability model could
be calibrated with suitable evidence. The problem here is the small, selected,
correlated sample, known prior outcomes, and a target that combines numeric
correctness with strict structural usability. Smoothing does not establish
calibration; a larger range of output numbers would not establish it either.

## What the prototype actually does

It reads saved MinerU OCR and PyMuPDF4LLM outputs from the sponsor's documents,
checks for one well-formed value per cell, unmerged value/row cells, a unique
comparison row, and agreement on value and a bound column header. All checks
passing gives stronger evidence; other cases give weaker evidence. These are
observable features, not correctness probabilities. Unit correctness is reviewed
but is not independently predicted by the baseline.

The target reviewed so far is strict structured-cell usability: correct numeric
content/sign, row, column and unit context. It differs from numeric correctness
alone. In this sample 45/50 cells preserve numeric content; 30/50 meet the stricter
contract. A merged header fails that contract without making its numbers false.

| Group | Development sample | Retrospective replay |
|---|---|---|
| Stronger evidence | 20/20 pass, two documents | 10/10 pass |
| Weaker evidence | 0/10 pass, one document | 0/10 pass |

These are descriptive counts. They must not be assigned to new cells as confidence.

## Sample, review and limitations

The first ten nonempty value-position cells from the first table on each selected
page were sampled, excluding header and label/note/unit columns. Malformed cells
remain included. Page-specific configuration is in `protocol.json`.

| Partition | Document | Physical PDF page | Cells |
|---|---|---:|---:|
| Development | CVS | 6 | 10 |
| Development | EDF | 3 | 10 |
| Development | Hippodrome | 20 | 10 |
| Replay | Rolls-Royce presentation | 9 | 10 |
| Replay | Rolls-Royce release | 13 | 10 |

Both related Rolls-Royce documents stay together. Existing reports and outputs
were already inspected, so the replay is retrospective, not a blind validation.
Errors shared within tables mean 50 cells do not provide 50 independent trials.
The rules directly flag the types of structural failure used in the strict
label contract; this demonstration does not establish general error prediction.

EDF has five correct numeric strings with merged row/unit labels and five merged
numeric strings such as `3,037.10.0`. All ten sampled Rolls-Royce release numbers
are correct; their headers are merged in the primary export. A separate
Peterborough example has one collapsed table column and no bound cell to assess;
it returns review required and is outside the 50-cell denominator. Missing-value
recall and whole-document correctness are not estimated.

Labels in `review_labels.json` were visually checked by the assistant against
existing source-page PNG renders on November 9, not independently verified by a
human. Original sponsor PDFs are absent from this checkout. The renders are copied
unchanged from Sam's existing work. Recorded source URLs, PDF hashes, export and
image hashes are in `provenance.json`. Source labels, sample selection and parser
outputs were not changed by this correction.

These sponsor exports use the previously recorded MinerU 3.4.5 configuration,
not the separate 2.1.11 ExtractBench experiment. No parsers were rerun. Inference
features never read reference answers. Shared wrong values in both parsers remain
a known blind spot, demonstrated by a synthetic test excluded from sample counts.

## Toward a meaningful probability

1. Agree on the event. For the user's question, start with numeric transcription
   correctness (including sign and decimal); label association correctness separately.
   A future joint probability would need joint labels rather than multiplying scores
   under an unverified independence assumption.
2. Collect independent labels from representative documents, including true numeric
   errors, structural errors and cases where both parsers agree incorrectly. Keep
   calibration/evaluation sampling representative of actual deployment error rates.
3. Retain individual features, such as OCR evidence where available, parser
   agreement, source support, ambiguous matches and applicable consistency checks.
   Fit a simple correctness predictor; continuous output alone does not validate it.
4. Separate training, calibration and final testing by document and related document
   family. Test on genuinely new documents and check calibration by input type.
5. A score near 0.95 is meaningful if comparable unseen predictions assigned that
   score are correct approximately 95% of the time, within sampling uncertainty.
   Examine reliability plots, probabilistic losses and review-error tradeoffs.

[Scikit-learn's calibration documentation](https://scikit-learn.org/stable/modules/calibration.html)
explains this interpretation and why a Brier score alone does not isolate calibration.

## Files and reproduction

`predictions_without_labels.json` holds label-free evidence. `reviewed_cells.json`
and `.csv` add source annotations, evidence and null confidence. `summary.json`
contains descriptive counts. The PDF, HTML and notes no longer present the two
smoothed rates as probabilities. `PRESENTATION_BUNDLE.zip` contains the revised files.

From this folder:

```sh
../.venv-score/bin/python build_demo.py
../.venv-score/bin/python -m unittest -v test_demo
../.venv/bin/python make_slides.py
```

The first command reads sibling sponsor exports. BeautifulSoup is in the existing
score environment; ReportLab and Pillow are in the existing parser environment.
No new packages are needed. To share the HTML, include `assets/`.
