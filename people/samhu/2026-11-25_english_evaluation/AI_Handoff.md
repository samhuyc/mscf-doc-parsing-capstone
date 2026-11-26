# English financial statement parsing | Technical handoff

**For Eunice (Yuyang) and anyone helping her prepare the evaluation section.** Sam Hu assembled this preliminary release on **25 November 2026 at 9:56 PM ET**. The folder contains a five-page presenter guide and a one-page exhibit. Page 4 of the guide is the same exhibit. This Markdown carries the underlying numbers and definitions, so it can be uploaded on its own.

## 1. What changed and who supplied what

The earlier work answered two questions separately. Eunice compared table trees using TEDS. Sam showed how an engine’s output probabilities can signal an unreliable extraction. This release compares predicted outputs directly to their references. It uses the same English inputs across eligible parsers and gives each type of error its own score. Model confidence belongs in the confidence section of the presentation.

| Contributor | What you can credit | What this release used |
|---|---|---|
| Eunice / Yuyang So | PubTabNet evaluation, full TEDS and structure-only TEDS using APTED tree edit distance | Her two scoring functions, applied to common normalized table markup. Her original PubTabNet runner and its parser configuration are separate from the English benchmark runs. |
| Sam Hu | Earlier native-confidence presentation, whole-page evaluation harness and table-fact matching | Saved crop predictions, numeric-cell F1, exact text checks, new end-to-end parsing and scoring, filing-level checks and the matched comparison. |
| Yujie Zhu | Manifest, reference and prediction interface, checksums, metric applicability and FinTabNet/OTSL experiments | Stable item IDs, model/output fingerprints and separate result families. Her source-reviewed parser-recovery work addresses a different outcome. |
| Michael | Larger CPU crop run with per-table output scores | Reused the 300-table archive for a separate sample-size check. Its 283 eligible financial tables contribute one vote each to financial fact F1. |
| Oli | Layout and metadata evaluation | Background for a separate outcome family. Layout box accuracy needs box labels, and metadata accuracy needs field labels. Neither is inferred from this table. |

## 2. Fixed results for this release

**Five-parser comparison.** Every entry below uses the same **16 English FinTabNet development crops from 16 issuers**. The common set contains every eligible crop with an outcome from every configuration at the snapshot. The 2 MinerU crop timeouts in this set were included at zero. Each number is the unweighted mean of individual crop scores. Higher is better in all five columns.

| Parser | Structure TEDS | Full TEDS | GriTS content | Numeric-cell F1 | Financial fact F1 |
| --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 0.950 | 0.946 | 0.964 | 0.881 | 0.908 |
| GLM-OCR | 0.875 | 0.852 | 0.872 | 0.837 | 0.714 |
| MonkeyOCR-pro-1.2B | 0.888 | 0.771 | 0.820 | 0.409 | 0.343 |
| MinerU 2.5 Pro | 0.656 | 0.650 | 0.714 | 0.311 | 0.308 |
| PyMuPDF4LLM + Tesseract | 0.111 | 0.085 | 0.086 | 0.006 | 0.000 |

**Larger samples.** The 56 development crops, the 11 different-issuer crops and the seven UK crops have complete coverage for the three recognizers and PyMuPDF. The five-model overlap at this snapshot is 16/56, 8/11 and 7/7. Each cell below is GriTS content / financial fact F1 on **all** items in its column. The 11 validation issuers are absent from the 56 development crops. The UK seven are Dyson and Harrods scanned table crops with source-checked grid transcriptions.

| Parser | FinTabNet development (56) | FinTabNet new issuers (11) | UK scan crops (7) |
| --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 0.961 / 0.907 | 0.939 / 0.822 | 0.899 / 0.728 |
| GLM-OCR | 0.880 / 0.682 | 0.915 / 0.722 | 0.971 / 0.954 |
| MonkeyOCR-pro-1.2B | 0.835 / 0.355 | 0.891 / 0.442 | 0.751 / 0.143 |
| PyMuPDF4LLM + Tesseract | 0.111 / 0.002 | 0.065 / 0.000 | 0.378 / 0.000 |

**Five-model checks on the other two cohorts.** These columns use the common IDs for each cohort. GriTS / financial fact F1 are shown for every model.

| Parser | Different-issuer FinTabNet (8) | UK scan crops (7) |
| --- | --- | --- |
| PaddleOCR-VL-1.6 | 0.982 / 0.982 | 0.899 / 0.728 |
| GLM-OCR | 0.912 / 0.747 | 0.971 / 0.954 |
| MonkeyOCR-pro-1.2B | 0.909 / 0.519 | 0.751 / 0.143 |
| MinerU 2.5 Pro | 0.557 / 0.125 | 0.857 / 0.571 |
| PyMuPDF4LLM + Tesseract | 0.000 / 0.000 | 0.378 / 0.000 |

**Michael’s separate FinTabNet CPU run.** 300 crops from 55 reports and nine issuers. GriTS uses all 300. Financial fact F1 and the number-anywhere recall use the 283 crops with eligible financial facts. This archive contains 2,100 model–table rows across seven configurations. The three compatible recognizers below provide the larger comparison.

| Crop recognizer | GriTS content (300) | Financial fact F1 (283) | Number-anywhere recall (283) |
| --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | 0.970 | 0.888 | 0.992 |
| GLM-OCR | 0.901 | 0.632 | 0.916 |
| MonkeyOCR-pro-1.2B | 0.842 | 0.450 | 0.827 |

Eleven of the 56 development table IDs and three of the 11 validation IDs also occur in Michael’s archive. The overlapping validation IDs are `fintabnet_test_00334`, `fintabnet_test_01739` and `fintabnet_test_02146`. Across the three FinTabNet lists there are 353 distinct table IDs. The incremental eight validation issuers are also absent from Michael’s archive. Keep the runs separate when discussing generalization.

**FinCriticalED.** The two page parsers processed the same 12 Berkshire Hathaway Q3 2025 Form 10-Q excerpts, IDs 347–358. There are 690 annotated occurrences. All five figures below are computed per excerpt and averaged across the 12 excerpts.

| End-to-end parser | Critical span recall ↑ | Exact context recall ↑ | Published normalized edit distance ↓ | Project text similarity ↑ | Page numeric F1 ↑ |
| --- | --- | --- | --- | --- | --- |
| MinerU 2.5 Pro | 0.7137 | 0.5703 | 0.0261 | 0.9747 | 0.9533 |
| PyMuPDF4LLM + Tesseract | 0.8234 | 0.5025 | 0.0285 | 0.9720 | 0.9054 |

**Original filed PDFs.** A value matches when the named row is uniquely located and the correct signed value appears in the expected place among that row’s checked values. The table shows total matching values and wholly correct rows. Each denominator counts checked items, irrespective of whether the parser found them.

| Source | Pages | MinerU values | MinerU rows | PyMuPDF values | PyMuPDF rows |
| --- | --- | --- | --- | --- | --- |
| Apple FY2024 10-K | 5 | 56/56 | 20/20 | 56/56 | 20/20 |
| Apple FY2026 Q3 10-Q | 4 | 63/63 | 16/16 | 63/63 | 16/16 |
| UK scans combined | 10 | 100/100 | 38/38 | 76/100 | 24/38 |
| ↳ Lamray | 4 | 51/51 | 15/15 | 50/51 | 14/15 |
| ↳ Dyson | 3 | 25/25 | 11/11 | 23/25 | 10/11 |
| ↳ Harrods | 3 | 24/24 | 12/12 | 3/24 | 0/12 |

The UK total comprises Lamray, Dyson and Harrods. Harrods accounts for 21 of the baseline’s 24 missed UK values. On its balance sheet, the cash row shows £76.6m for 1 February 2025 and £50.8m for 3 February 2024. MinerU returned `76.6 | 50.8`. PyMuPDF4LLM with Tesseract returned `76.6 | 508`. The baseline earned one of two values and zero of one entire row. The guide reproduces the actual source line. [Original Harrods accounts, PDF page 24, printed page 22](https://find-and-update.company-information.service.gov.uk/company/00030209/filing-history/MzQ4Mzc5NDM2N2FkaXF6a2N4/document?download=0&format=pdf)

## 3. What each score actually measures

*Financial fact matching.* Index the reference and extracted facts by section path, normalized row label and repeat occurrence, column-header path, and normalized numeric value. The repeat occurrence distinguishes two equally named rows. Numeric normalization recognizes sign, accounting parentheses, percentages and supported units. A lost minus sign or a decimal moving from 50.8 to 508 changes the value. With \(M\) matched facts counted with multiplicity, \(G\) reference facts and \(P\) predicted facts, the Sørensen–Dice F1 is \(2M/(G+P)\). Extra facts increase \(P\), missed facts reduce \(M\). The calculation is made once per table.

| Question | Measure and interpretation |
|---|---|
| Were rows, cells and merged headings rebuilt? | **Structure-only TEDS ↑.** PubTabNet Tree-Edit-Distance-based Similarity compares ordered trees. The normalized distance uses the larger node count. Text is removed, while row/column spans are retained. |
| Did the table structure and its cell text survive? | **Full TEDS ↑.** Same tree and normalization. Cell renaming also considers normalized edit distance between tokenized contents. A single changed digit can have a small effect on a large table. |
| How much of the grid can be aligned? | **GriTS content ↑.** The Microsoft GriTS content scorer aligns ordered rows and columns and gives partial credit for similar cell strings. Long, mostly correct tables can score highly despite a material error. |
| Are the values attached to the right financial facts? | **Financial fact F1 ↑.** Uses the multiset and formula above. Report it next to full TEDS. |
| Is a number anchored in its original cell? | **Numeric-cell F1 ↑.** Exact multiset matching on logical row, column, row span, column span and numeric token. The cell metric uses the project’s numeric tokenizer. Formatting rules can therefore differ from financial fact normalization. |
| Did a critical item survive anywhere in the excerpt? | **Critical span recall ↑.** Compare annotated strings against the canonical output with token boundaries and cap credit at the annotated multiplicity. Position within a row is not required. |
| Did the item’s wording survive in context? | **Exact context recall ↑.** For each annotated table row, paragraph or fallback container, require its full normalized text. A matching context earns credit for the annotated items in that occurrence. This is a deterministic project metric. |
| How much did the page change overall? | **FinCriticalED normalized edit distance ↓.** Traditional Levenshtein distance between the dataset-matched HTML text and raw parser output after the upstream cleanup, divided by the larger character count. Lower is better. **Canonical text similarity ↑** uses the project’s Markdown/HTML normalization and annotated reference. The different text preparation explains why these reported columns need not sum to one. |
| Did printed numbers survive anywhere on the page? | **Page numeric F1 ↑.** Multiset F1 on numeric tokens, ignoring their location. An intact number under the wrong header can still count. |
| Can a selected filing value be used with its row? | **Ordered-value recovery ↑** and **whole-row recovery ↑.** Normalize the row name and require a unique match. Strip currency formatting, spaces and grouping commas from values, preserve sign and decimal meaning, and compare the rightmost expected sequence in its original order. An ambiguous or missing row earns no values. An entire row passes only if every selected value matches. |

**Worked example.** Suppose the reference says Revenue = 100 for 2024 and 120 for 2025. The prediction prints 120 under 2024 and 100 under 2025. With all headers and spans unchanged, structure-only TEDS is 1.00. Both amount tokens are present, so number-anywhere recall for those two tokens is 1.00. Both financial facts are assigned to a wrong year. \(M=0,\ G=P=2\), so financial fact F1 is 0.00. Full TEDS lies below 1 because the cell contents differ. These are illustrative values.

**Multi-table output and applicability.** Each FinTabNet crop contains one reference table. The adapter canonicalizes equivalent native HTML/OTSL/Markdown to a common grid, preserves spans and applies Eunice’s scorer to every predicted table. It takes the pair with highest full TEDS and divides its full and structure scores by the number of predicted tables to penalize extras. A missing structured prediction earns zero. The UK crop references are transcribed grids without verified merged-cell spans. Only GriTS content and financial fact F1 are reported for them. FinCriticalED exact recalls are separate from the authors’ GPT-4o-based Financial Fact Accuracy (FFA), which was not run.

## 4. Input, parser and scoring pipeline

1. **Freeze the English inputs and their references.** There are 105 distinct manifest items, comprising 74 cropped tables and 31 whole pages or excerpts. The FinTabNet development set has 56 eligible crops from 33 issuers. They come from the public FinTabNet/OTSL test split and serve as development data for this project. The earlier 60-crop selection also contained four legal exhibit lists without eligible financial facts. A separate 11-crop set uses 11 different issuers. Seven UK crops come from two scanned issuers. Some UK crops originate on pages also used for whole-page checks.
2. **Use the appropriate input for each parser.** Three recognizers receive exactly the same crop pixels and a table prompt. The two page parsers receive those images embedded one per PDF. This comparison includes the cost of finding the table in the one-page wrapper for the page parsers. Only MinerU and PyMuPDF have end-to-end outcomes on the 31 full pages/excerpts here.
3. **Keep native outputs and provenance.** Record sample ID, engine, input and output SHA-256, runtime scope and state per observation. Reuse completed predictions when their IDs and input hashes match. Table-specific score conversion happens after inference. A completed empty result or a bounded timeout contributes a measured zero to applicable metrics. Unattempted model–input pairs are absent from the matched cohort.
4. **Score against the right reference.** FinTabNet uses published cell text and restored table structure. FinCriticalED uses dataset annotations and matched text. The Apple 10-K uses issuer filing HTML. The Apple 10-Q and UK use selected source-image transcriptions. The seven UK crop grids were source-checked before inspection of fresh predictions. Independent human adjudication of those source transcriptions is outstanding.
5. **Aggregate at the unit named in each column.** Table scores are macro means by crop. Berkshire scores are macro means by excerpt. Original filing counts pool checked values/rows with explicit integer denominators. Fair head-to-head comparisons use the identical IDs. The release has 389 scored input–parser observations and 357 distributable prediction texts. Timeouts can have a saved empty string.

| Configuration | Run scope and provenance |
|---|---|
| PaddleOCR-VL-1.6 | `PaddlePaddle/PaddleOCR-VL-1.6@132c45f5`. Reused MLX table-prompt predictions. |
| GLM-OCR | `zai-org/GLM-OCR@2e85a628`. Reused MLX table-prompt predictions. |
| MonkeyOCR-pro-1.2B | `echo840/MonkeyOCR-pro-1.2B@2fb37263`. Reused MLX HTML table-prompt predictions. |
| MinerU 2.5 Pro | One checkpoint, `opendatalab/MinerU2.5-Pro-2605-1.2B@bff20d4ae2bf202df9f45284b4d43681555a97ed`. The Python package version is `mineru 3.4.5`. New runs used the end-to-end VLM, Transformers CPU FP32, batch size one, tables on. The archive contributes same-checkpoint MLX runs for three Berkshire excerpts, the four Apple 10-Q pages and the four Lamray pages. |
| PyMuPDF4LLM + Tesseract | `PyMuPDF4LLM 2.1` with layout, English automatic OCR at 300 dpi when needed, and HTML table output. Runs end to end on PDFs. |

Michael’s historical MinerU table-prompt run is a different configuration. His three reused recognizers were benchmarked on CPU for the archive. Times from a crop prompt, a warm page parser, a whole-document batch and a cold replay have different scopes. Use the recorded timing scope before answering a latency question.

## 5. Expected presentation questions

**Can I say Paddle was the most accurate parser?** On the matched English FinTabNet crops in this snapshot it had the highest financial fact F1. It also led the three recognizers on financial fact F1 in Michael’s 283 eligible-table run. GLM led the three recognizers on the seven UK scan crops, and only two configurations were evaluated on whole pages. Name the task, sample and metric when describing a leader.

**Why can PyMuPDF find more Berkshire spans while MinerU recovers more exact contexts?** A span can be found elsewhere in the same excerpt. Exact context also requires the surrounding row or paragraph. Both rankings are observed. The aggregate scores alone do not identify the mechanism of every error.

**Does 119/119 mean perfect Apple parsing?** The two end-to-end parsers recovered the selected 56 annual and 63 quarterly values. Across 19 original pages there are 74 selected rows and 219 checked values. Apple 10-Q page 24 and Lamray page 4 have no selected rows. They count as processed pages and contribute zero items to the field denominator. Other values, prose and layout on these pages are outside the field check.

**Does OmniDocBench have ground truth?** Yes. The pinned release provides structured region annotations, text and reading order, plus table markup where available. The earlier eight-page pilot contained seven Chinese pages. Its sole English page was an electrical varistor specification. At the pinned version the inspected `research_report` category contains 132 pages and one English page, that same specification. The broader benchmark contains other English material. This finance-specific exhibit uses English company filings and financial tables. [Pinned OmniDocBench annotations](https://huggingface.co/datasets/opendatalab/OmniDocBench/blob/aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec/OmniDocBench.json)

**Does this establish significance, overall parser quality, or results on every domain?** These are descriptive point estimates from a partly completed paired development run, selected filings, and one Berkshire issuer. If expanding the benchmark, freeze new issuer-disjoint PDFs, preserve the overlap list, obtain independent review of transcribed rows and update all slide numbers from the same snapshot. A formal uncertainty analysis would need to account for tables/pages from the same issuer.

## 6. Where to look and how to reproduce a number

All relative `evidence/` paths below live next to this document. From a fresh repository checkout use the folder `people/samhu/2026-11-25_english_evaluation/`. The prior-source revision used for the handoff was `11f2a5a8b4cabb1f88a54c788d92941dd329e375`. [Release folder](https://github.com/samhuyc/mscf-doc-parsing-capstone/tree/main/people/samhu/2026-11-25_english_evaluation)

| Question / file | Where the answer lives |
|---|---|
| Which inputs and sources? | `evidence/inputs.csv` contains sample IDs, cohort, issuer, source locator, English language, document page, reference type and hashes. The source material includes [FinTabNet/OTSL](https://huggingface.co/datasets/docling-project/FinTabNet_OTSL), [FinCriticalED](https://huggingface.co/datasets/TheFinAI/FinCriticalED) and the original filing PDF URLs in the manifest. |
| What value went into the plot? | `evidence/observations.csv` has one row per measured sample/engine. `evidence/metric_outcomes.csv` contains aggregate numerator scope, sample counts, units, timing scopes and statuses. `reproduce.py` verifies and prints the paired results. |
| Can I inspect the source of a filing miss? | `evidence/filing_checks.csv` contains expected label, ordered values, observed values per end-to-end parser, matched counts and reference provenance. `evidence/harrods_cash_line.png` is the source strip shown in the guide. |
| Can I see the prediction? | `evidence/predictions.jsonl.gz` holds native outputs, model IDs and hashes. The Berkshire FinCriticalED subset uses approved data access, so the bundle carries scores and digests for it. The eight archived MinerU Apple/Lamray page outcomes point to checked filing rows and output hashes. `evidence/uk_table_references.json` includes the seven transcribed grids. |
| Where are the actual scorer and source methods? | `score_prediction.py` imports Eunice’s scoring definitions. See `people/yuyangso/miner_u2.5/minerU2.5.py` around `teds_score`, and `people/samhu/2026-11-15_table_confidence/prototype/table_structure_v2.py` at `fact_key` and `fact_score`. Microsoft’s GriTS is called by `prototype/standard_metric.py` in the same folder. |
| Where are the text rules and exact archived scores? | `people/samhu/2026-09-20_evaluation/formats.py` at `fact_groups`, and `score.py` at `span_count`, `score_page` and `numeric_cells`. The traditional edit distance follows the [FinCriticalED authors’ scoring code](https://github.com/The-FinAI/FinCriticalED/blob/main/model_eval/evaluation.py). `evidence/michael_overlap.json` lists duplicate IDs. |
| How do I check attribution? | `people/yujiezhu/evaluation_framework/{README.md,framework.py,SOURCE_SYNTHESIS.md}`, `people/samhu/2026-11-10_native_confidence/sponsor_slides.html`, `people/mc8/2026-11-17_confidence_cpu/results/300_tables/{summary.md,scores.csv}`, and `people/oli2/2026-09-29_metadata_extraction/README.md`. |

**Check the entire report without any models or data downloads.** From the release folder, `python3 reproduce.py` verifies the score table against the row-level observations, reports the main comparison and validates every archived prediction digest. Use `python3 reproduce.py --json` for the matched IDs, other cohorts, field totals and unrounded summaries.

**Re-score an actual saved output.** In a Python environment with `python3 -m pip install -r scoring_requirements.txt`, run the examples below. The first two read the bundled evidence offline. The third retrieves one public FinTabNet annotation and verifies its SHA-256. An existing cached annotation can be supplied via `--annotation-json`.

~~~sh
python3 replay_saved.py harrods_fy2025_accounts_p24 pymupdf
python3 replay_saved.py harrods_fy2025_accounts_p022_t01 glm
python3 replay_saved.py fintabnet_test_10212 paddle_vl
~~~

**Score a new prediction.** For a raw native crop result use `score_prediction.py table --reference one_reference.json --prediction raw.txt`. For end-to-end Markdown add `--format markdown`. For an original page use `score_prediction.py filing --id harrods_fy2025_accounts_p24 --prediction output.md`. For an approved FinCriticalED case use `score_prediction.py page --annotated-html gold.txt --matched-html matched.html --prediction output.md`. The finance page requires the exact paired reference HTML as well as the annotated file.

**Run a page parser.** Use a separate engine environment with the pinned weights/packages, Tesseract English language data for the baseline, and an input PDF. `run_pdf.py pymupdf input.pdf output.json` or `run_pdf.py mineru input.pdf output.json --weights /path/to/checkpoint --mineru-config /path/to/config.json` saves the text, model package, input/output hashes and elapsed time. Extract the `text` key as a UTF-8 file before using `--prediction`. This single-item replay includes startup overhead. To regenerate the PDFs from frozen scores, install `reportlab` and `pypdf` and run `python3 build_handoff.py`.

**For an assistant reading only this file.** Cite the cohort, unit, metric direction and denominator when answering. Use the exact counts above for presentation wording. For a new question about a particular cell or failure, request the item’s `observations.csv` row, `filing_checks.csv` row or saved prediction identified here. If a needed file is unavailable, identify it and say what the supplied evidence establishes. Useful prompts include “Explain why the swapped-year example earns 1.00 on structure and 0.00 on facts” and “Show how the 24 missed UK values split across the three issuers.”
