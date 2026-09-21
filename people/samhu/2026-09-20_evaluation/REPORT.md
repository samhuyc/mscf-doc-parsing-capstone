# Preliminary evaluation report — 2026-09-20

The framework now runs existing benchmark pages through a parser, saves Markdown with HTML tables, and evaluates the result against published labels. The local MinerU vision-language backend performed better on this small pilot. The more useful outcome is an auditable evaluation path that exposes numeric and table failures separately.

## Delivered

1. **Design and resource review:** [README](README.md) specifies the common output, input/label separation, metrics and commands; [RESOURCES](RESOURCES.md) records the datasets, evaluation inspirations and every parser named in the two starter documents.
2. **Working pilot:** 8 OmniDocBench pages and 8 FinCriticalED pages, each processed by MinerU's OCR pipeline and vision-language backend: 32 page-level model runs. Nine unit tests, an eight-page external-output import check, direct-image and native-PDF smoke tests, and an image-PDF negative control validate the harness.

## Results

These are custom diagnostics, not published benchmark scores. Values are page-macro averages on the same eight inputs per dataset; empty outputs count as failures. A dash means suitable labels are unavailable.

| Dataset | Backend | Nonempty pages | Text | Numeric F1 | Table structure | Numeric cell F1 | Critical span recall | Exact context recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| OmniDocBench | OCR pipeline | 8/8 | 0.904 | 0.914 | 0.857 | 0.603 | — | — |
| OmniDocBench | Local VLM | 8/8 | 0.936 | 0.936 | 0.978 | 0.873 | — | — |
| FinCriticalED | OCR pipeline | 7/8 | 0.779 | 0.720 | — | — | 0.611 | 0.157 |
| FinCriticalED | Local VLM | 7/8 | 0.826 | 0.849 | — | — | 0.648 | 0.427 |

Raw machine-readable results: [Omni OCR](results/omni_pipeline.json), [Omni VLM](results/omni_vlm.json), [FinCriticalED OCR](results/fin_pipeline.json), [FinCriticalED VLM](results/fin_vlm.json). These include per-page scores, model settings, timestamps, source/output checksums and diagnostic examples. Original predictions, images, labels and logs are local in the ignored `outputs/` and `data/` folders.

The two backends both produced 14 HTML tables on the OmniDocBench sample; matching table counts did not guarantee matching cells. The VLM's higher structural and numeric-cell scores expose an improvement that a text-only score understates. In FinCriticalED, the OCR pipeline returned empty output for `fin_348`, a readable Berkshire Hathaway balance sheet; the VLM recovered text and table output. The VLM returned empty output for `fin_367`; visual inspection found literal CSS and compressed numbers in that published input image, rather than a correctly rendered financial page. Retain both cases for review, distinguishing parser failure from dataset quality. The reported sample remains unchanged after this inspection.

Wall time including per-page process startup: omni_pipeline: 156.6s; omni_vlm: 447.5s; fin_pipeline: 127.0s; fin_vlm: 330.6s. These are local observations with cached weights and different inference runtimes, not standardized throughput measurements.

## What ran, and where the LLM was used

MinerU **3.4.5** ran on an Apple M1 Pro with 16 GB memory. The conventional pipeline used CPU. `vlm-engine` selected **MLX** and used the locally cached **MinerU2.5-Pro-2605-1.2B** model. Hugging Face supplied model files and datasets; inference ran on this computer. No Hugging Face hosted inference, OpenAI/Anthropic inference, or LLM judging service was used. Cache revision hashes are recorded in [model_cache_revisions.json](results/model_cache_revisions.json).

OpenAI/Anthropic and most starter models can plausibly feed this output contract through prompting or native exports. That is a documented compatibility assessment, not a measured model comparison. Small models should keep their supported recognition prompts and use deterministic adapters. Nemotron Parse's default LaTeX tables remain an explicit unsupported adapter case.

## Dataset and metric limits

- **OmniDocBench:** 8 coverage-selected pages with 14 annotated tables: 6 simplified-Chinese, 1 traditional-Chinese and 1 English page. The English item tagged `research_report` is actually an electronics datasheet. It remains in the preselected sample as a general table stress test, and is not evidence about English financial filings. Selection and hashes: [pilot_selection.json](pilot_selection.json).
- **FinCriticalED:** the approved download is in the repository's `data/raw/FinCriticalED/`. The current CSV has 848 inputs, each with a matching annotation file. The pilot selects 8 of 65 available pages with at least 5 existing number annotations, using deterministic hash ordering. Those pages contain 330 annotated fields, including 226 numbers. The malformed `fin_367` image shows that expert annotations do not guarantee a usable rendered input. This is a diagnostic selection, not a representative sample or an issuer-disjoint test split. Selection and hashes: [fin_selection.json](fin_selection.json).
- **Inputs:** accuracy evaluation uses published page images wrapped in PDFs without a text layer. This does not measure true native-PDF extraction, scanner degradation or long-document behavior. Plain PyMuPDF correctly produced empty text on all eight image-PDF controls; native text extraction separately succeeded on a one-page Apple filing smoke test. The mentors' exact PyMuPDF/OCR configuration still needs confirmation.
- **Labels and scoring:** OmniDocBench supplies explicit table gold. FinCriticalED's HTML includes layout tables, so only text/numeric and annotated-field diagnostics are scored there. Exact context recall is sensitive to punctuation, markup-induced whitespace and source encoding artifacts; it is a preservation diagnostic, not semantic financial-fact accuracy. Unit tests show that swapping values between columns reduces numeric-cell F1 even when page-level numeric F1 stays perfect.
- **Scope:** MultiFinBen-EnglishOCR was reviewed, not run. No benchmark labels were manually created. This prototype does not yet evaluate document hierarchy, chunk retrieval, cross-page tables or financial-template filling.

## Next increment

Define an input-quality screen before drawing a new sample, validate one additional parser through the same import contract, confirm the production baseline, and add a labeled native-PDF subset with issuer/document-level splits. Expand coverage before ranking models. Keep chunking and financial-template extraction as separate downstream evaluations with source-page references and existing task labels.
