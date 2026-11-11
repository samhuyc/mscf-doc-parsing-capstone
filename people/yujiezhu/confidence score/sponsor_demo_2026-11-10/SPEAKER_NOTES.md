# Corrected five-minute presentation script

## 1 — What is ready

“We have a working extraction-evidence prototype and separate learned numeric and association models. It detects agreement and
structural problems in saved parser outputs. We have not yet established a
probability that each extracted number is correct, so we do not display one.”

## 2 — Two questions

“Numeric transcription and financial association are different. A number may be
right but have no clear year attached. In 50 reviewed cells, 45 preserve numeric
content and 30 satisfy a strict structured-cell contract. These are sample counts,
not per-cell probabilities. The source renders were reviewed by the assistant;
independent human verification remains to be done.”

## 3 — What the evidence checks do

“We check whether there is one numeric value, a distinct row, and a unique matching
row/value/header in a second parser. These checks assign an evidence category.
They do not establish a percentage probability. Two parsers can agree incorrectly.”

## 4 — CVS example

“CVS revenue of $98.9 billion for 2Q 2025 is retained by both parsers with matching
context. It has stronger evidence, and source review confirms it. The probability
for a new case with similar features is still unknown.”

## 5 — EDF example

“EDF has merged row labels and strings like 3,037.10.0. The prototype flags weaker
evidence and exposes the specific problems. A correct string such as 3,037.1 can
still lack an unambiguous financial row. This does not imply that its digits are
probably wrong.”

## 6 — Retrospective check

“Across the development pages, 20/20 stronger-evidence cells passed the strict
contract and 0/10 weaker-evidence cells passed. Separate Rolls-Royce documents
have 10/10 and 0/10 respectively. Those release failures are merged headers:
all ten sampled numbers are right. Earlier reports were known, the sample is
small, and cells share errors. This does not establish calibration.”

## 7 — Why the earlier percentages were removed

“The earlier version converted those development counts to 95.5% and 8.3% through
add-one smoothing. That arithmetic did not establish the probability of correctness
for individual values. We removed those scores. More varied percentages would
not solve the validation problem.”

## 8 — What the learned models found, and the next step

“We have implemented logistic models using the individual signals, rather than
the two-group switch. We test on separate document families. The numeric model
cannot score the EDF holdout because training then contains no numeric failures.
The association model struggles with the unseen merged-header pattern in the
Rolls-Royce release. We report those failures explicitly. Calibration and new-cell
inference are implemented, but the dataset does not yet qualify for calibrated
scores.”

See `model_results/MODEL_REPORT.md` for fold results. The numeric validation covers
40/50 cells, including zero of five errors; do not quote its low loss as evidence
of error detection. Proposed labels and human decisions are separated in the
review queue. Additional representative errors and independent review are the
next inputs required.

## Sponsor question

“Should the probability refer to correct numeric transcription, correct financial
association, or both? We propose labeling them separately, collecting independent
examples across representative documents, fitting a simple model and testing its
probabilities on new documents. A score near 95% should correspond to about 95%
correct outcomes among comparable new cases receiving that score.”

## Questions

**Do you have the sponsor's requested probability score today?** No. We have the
feature extraction, evidence checks and a small reviewed sample needed to begin
building it. We should not present a heuristic category as a validated probability.

**Is having two probability values inherently wrong?** No. Two groups can have
meaningful rates if validated appropriately. Here their applicability to future
cases was not established, and the target was different from numeric correctness.

**Why not give each passed check some points?** That could give a diagnostic score,
but an 85/100 checklist score does not mean an 85% chance of correctness.

**How could a future model improve this?** Use individual evidence features rather
than a single all-checks-pass switch; learn their relationship with independently
reviewed correctness, then check/calibrate the probabilities on separate documents.

**What did the tests prove?** The code handles certain feature changes and failure
cases, and does not emit unvalidated probabilities. Tests are not proof of real-world
predictive accuracy. A synthetic shared-wrong-value case still has stronger evidence.

**What happens to Peterborough?** Its collapsed one-column table produces review
required with no bound cell. It is outside the 50-cell counts. No probabilities are
emitted for the other cells either, because probability validation is unfinished.
