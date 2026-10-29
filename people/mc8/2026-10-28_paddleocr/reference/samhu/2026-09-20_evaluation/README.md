# Financial PDF parsing evaluation prototype — 2026-09-20

A small evaluation harness for **preserving financial values and table structure**, using existing benchmark labels. Start with [REPORT.md](REPORT.md) for results and [RESOURCES.md](RESOURCES.md) for dataset choices and model compatibility.

## Scope and design

The first two deliverables are an output/metric specification and a reproducible page-level pilot. This implements both on OmniDocBench and FinCriticalED. MultiFinBen-EnglishOCR is surveyed as an expansion source. No new benchmark labels are authored; synthetic fixtures are used only for unit tests.

```text
Published images + existing annotations
  ├─ prepare.py → inputs.jsonl → run.py → raw output + document.md + run metadata
  └─ prepare.py → references.jsonl ──────→ score.py → per-page and aggregate JSON
```

Models receive only the input manifest and source image/PDF. References are loaded separately by the scorer. One sample is one page; stable IDs, source IDs, input hashes, dataset revision and language/layout attributes connect inputs, labels and outputs. Failures and empty outputs remain in the denominator. Different input kinds must be evaluated separately.

### Output contract

Each page produces `document.md`: Markdown prose/headings, with tables represented as HTML `<table>`, `<tr>`, `<td>`/`<th>`, preserving `rowspan` and `colspan` where available. The runner keeps untouched parser text in `raw.txt`, MinerU's native artifacts, logs, elapsed time and parser settings. It converts ordinary Markdown pipe tables mechanically. It does **not** infer missing cells, repair numbers, summarize text, or ask an LLM to improve predictions before scoring.

This is an **adapter contract**, not a requirement that every smaller model obey a custom prompt. Native Markdown/HTML and cell-array exports can meet it. Plain-text parsers can enter the same harness but earn no table credit if structure is absent. LaTeX tables require an additional adapter; the current scorer flags them as unsupported.

For a generalist vision model, use one page per request and save its response for import:

> Transcribe this page in reading order. Use Markdown for prose and headings, and HTML tables with rowspan/colspan where necessary. Preserve all numbers, signs, decimals, currencies, units and dates exactly. Do not summarize, calculate, complete missing values, or add commentary. Return only the transcription.

Prompt feasibility is documented; no OpenAI/Anthropic API inference was run. Their model/version, prompt, image resolution, token limits and cost should accompany any imported outputs. Import timing measures no inference and is recorded as unavailable.

### Metrics

All scores are 0–1, higher is better. These are **prototype diagnostics**, not the official OmniDocBench or FinCriticalED leaderboard metrics. Do not compare these numbers to published leaderboards.

| Metric | Calculation and purpose | Limitation |
|---|---|---|
| Text similarity | 1 − character edit distance / longer normalized text length | Page-level; reading order, headers and whitespace conventions affect it |
| Numeric precision / recall / F1 | Multiset intersection of lexical numeric tokens; duplicates counted | Location-independent; preserves grouping, decimals, signs and percent/currency marks, but is not a locale-aware financial interpreter |
| Table structure | Ordered tree edit similarity over table/row/cell nodes and spans | Custom TEDS-style diagnostic, not official TEDS; ignores CSS and treats th/td alike |
| Table content | Same tree score, with character edit cost inside corresponding cells | Can remain high when a small but important value is wrong |
| Table numeric cell F1 | Numeric tokens must match logical row/column anchors and spans within matched tables | Strict: an extra header row shifts positions; reports alignment problems, not their cause |
| Critical span recall | Exact occurrences of FinCriticalED's existing number/date/unit/entity/concept tags | Can miss semantically equivalent formatting and cannot establish correct association alone |
| Critical context recall | Annotated fields count only when their complete containing row/paragraph is preserved | Deliberately strict; not semantic FFA, not fact precision, and not sufficient for cross-row header association |

Table pairs are matched one-to-one by maximum content similarity; structure/content sums are divided by the larger table count, so missing and extra tables cost credit. Table numeric F1 includes unmatched values. Malformed/unclosed or nested predicted tables receive zero structural credit; unsupported reference tables fail explicitly. No-table/no-number cases are `null`, not perfect scores. FinCriticalED's source HTML contains layout tables, so its table metrics are unavailable; OmniDocBench supplies explicit table annotations. Financial-field metrics are unavailable for OmniDocBench.

Keep metrics separate rather than hiding a critical error inside a weighted overall score. Review numeric cell/context failures before accepting a parser. Per-page records preserve flags, unmatched-number examples and table matches for inspection.

## Run

Use Python 3.12 from this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v
python prepare.py omni --count 8
python prepare.py fin --folder ../../../data/raw/FinCriticalED --count 8
```

FinCriticalED requires an approved Hugging Face account. The user's approved download is stored in the repo's ignored `data/raw/FinCriticalED/`, containing `raw_input.csv` and `gold_annotation_html/`. No credentials belong in this project. The adapter reads only the current CSV and annotations, not `Archived/`. Download revision metadata is used when available; otherwise input/annotation hashes identify the local copy.

MinerU is an optional, separate installation. The pilot used the existing MinerU 3.4.5 environment; `--mineru` accepts its executable path. Use a new run name each time; existing runs are never silently overwritten.

```bash
python run.py data/omni/inputs.jsonl --parser mineru --backend pipeline \
  --device cpu --mineru /path/to/mineru --name omni_pipeline
python run.py data/omni/inputs.jsonl --parser mineru --backend vlm-engine \
  --mineru /path/to/mineru --name omni_vlm
python score.py data/omni/inputs.jsonl data/omni/references.jsonl \
  outputs/omni_vlm/predictions.jsonl --output results/omni_vlm.json
```

Replace `omni` with `fin` for the financial-field pilot. `HF_HOME` can point to an existing local model cache. The VLM backend auto-selects its runtime; the recorded pilot used local MLX on Apple Silicon. Model weights were downloaded from Hugging Face and executed locally, with no hosted inference API or external LLM judge.

To import another parser's outputs, place `<sample-id>.md` (or `.html`/`.txt`) in a directory:

```bash
python run.py data/omni/inputs.jsonl --parser import --format markdown \
  --predictions /path/to/predictions --name other_model
python score.py data/omni/inputs.jsonl data/omni/references.jsonl \
  outputs/other_model/predictions.jsonl --output results/other_model.json
```

`--input-kind image` uses the original image. The default `image_pdf` wraps that image in a PDF with **no text layer**. This tests OCR input handling, not native PDF extraction or realistic scan degradation. A native-PDF manifest instead supplies `native_pdf` and `native_pdf_sha256`; use `--input-kind native_pdf`. Native PDF extraction has a smoke test, but this pilot has no paired native-PDF gold evaluation.

```bash
python run.py data/omni/inputs.jsonl --parser pymupdf --name native_text_control
```

That PyMuPDF baseline extracts embedded text only. Empty results on image PDFs are an expected negative control, not a comparison against PyMuPDF with OCR or PyMuPDF4LLM.

## Next increment

Add a native-PDF benchmark with existing page-aligned labels and document-level splits; broaden issuer/language/layout coverage and confirm the mentors' exact PyMuPDF configuration. Then import one additional parser or generalist model through the same contract. Chunking, cross-page hierarchy, retrieval and filling a financial-metric template should be evaluated separately after page fidelity is established. Retain page IDs and native parser metadata now; do not invent hierarchy labels or infer financial facts for this pilot.
