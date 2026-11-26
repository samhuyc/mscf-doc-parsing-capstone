# Two-slide update script

## Slide 1 — Can an alternative parser recover errors?

“I revisited our 50 extracted records and selected eight examples for a small recovery comparison. I compared the saved MinerU OCR outputs with the saved PyMuPDF4LLM outputs and checked the original page images. I did not train another model or rerun inference.

“The set includes four low-score errors, two high-score errors and two correct controls. There were no low-score fully-correct records in the existing dataset, so I used high-score correct controls and disclosed that missing category.

“Three of the six original errors became fully correct. The two correct controls stayed correct, so we observed no new errors in those two controls. The other three errors improved, but did not meet our full extraction contract. Overall, fully correct records increased from two to five out of eight.

“These are deliberately selected examples, not a measured general recovery rate. The scores shown are experimental association-model outputs, not calibrated probabilities.”

## Slide 2 — What improved, and what still failed?

“Rolls-Royce is the important high-score failure. Revenue of 11,448 and cost of sales of negative 8,021 were numerically correct, but the original extraction combined both year headers. The association model nevertheless produced 0.8837. PyMuPDF4LLM restored the separate 2026 column, so these two cases were fully recovered.

“EDF shows why a different output is not automatically a complete repair. For example, the original text was 3,037.10.0. PyMuPDF4LLM separated that into 3,037.1 and 0.0 with an HTML line break. However, the revenue and other-revenue rows still occupied one cell. I counted that as partial recovery, not a correct structured extraction. Three selected EDF records have this problem. A separate EDF total-revenue record was fully recovered.

“The preliminary conclusion is that another parser can recover some errors, but its result still needs checking. Retrying only low-score outputs would miss the high-score association errors demonstrated here. The next small experiment should evaluate an explicit row-splitting repair on the remaining EDF cases, then test both recovery and regression on additional document families.”

## Questions you may receive

- **Does 0.8837 mean 88.37% confident?** No. It is an existing uncalibrated, out-of-family association diagnostic output. Calibration has not been established.
- **Did incorrect numbers receive high scores?** The selected high-score errors are incorrect associations, with correct numbers. The five numeric errors in the original dataset have no out-of-family numeric score because that fold could not train. We cannot claim a high-score wrong-number finding from these data.
- **Why no low-score correct example?** At the association threshold of 0.5, there are zero fully-correct low-score records in the 50-record pool. Correct digits with wrong context do not qualify.
- **How long does recovery take?** We did not measure fresh inference. Saved full-document PyMuPDF4LLM runs took about 4 seconds for EDF and 31 seconds for the Rolls-Royce release; they are not per-cell retry timings.
- **Was this independently reviewed?** No. These are assistant-reviewed examples checked against source-page images. Independent human verification remains needed.
- **Are eight examples eight independent cells?** No. Several share a table-level problem, and three EDF records bundle two source values each. The eight records cover eleven source numeric values.
- **Could a human interpret EDF's line breaks?** Yes, but our unchanged contract requires separate row bindings. Adding manual interpretation would change the recovery method and must be reported separately.
