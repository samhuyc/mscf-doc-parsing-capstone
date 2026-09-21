# TAT-QA parser benchmark

This project compares **PyMuPDF4LLM 0.2.9** and **PyMuPDF 1.28.2** on the
official English TAT-QA development split. The complete run covers 278 hybrid
table/text contexts, 298 PDF pages, and 1,668 questions.

See [REPORT.md](REPORT.md) for the measured
results, metric definitions, and interpretation.

## What is being measured

TAT-QA publishes structured JSON contexts rather than the source financial
report PDFs. `scripts/prepare_tatqa.py` therefore renders every official dev
context into a deterministic PDF without adding content. Both parsers process
the exact same PDFs.

The evaluator reports:

- word error rate and its explicit complement, text accuracy;
- order-preserving token accuracy;
- table cell precision, recall, and F1;
- table shape accuracy and exact table match;
- retention of gold spans for TAT-QA extractive questions;
- retention of operands used by TAT-QA arithmetic derivations; and
- mean and median wall-clock runtime per context.

These are parser-fidelity metrics, not TAT-QA's official QA exact-match/F1
scores. PyMuPDF and PyMuPDF4LLM extract document content but do not answer
questions.

## Data provenance

- Dataset: official TAT-QA `dataset_raw/tatqa_dataset_dev.json`
- Upstream commit: `644770eb2a66dddc24b92303bd2acbad84cd2b9f`
- Local SHA-256: `8da095a819af6db3c14877c6df2d4d29960e41d1a63dd1fa853507bd2a616af5`
- Language: English (TAT-QA is an English financial QA benchmark)
- Local copy: `data/tatqa/raw/tatqa_dataset_dev.json`
- Dataset license: CC BY 4.0, as stated by the official TAT-QA repository

## Reproduce

Use Python 3.10 or newer and run commands from this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python scripts/download_tatqa.py
python scripts/prepare_tatqa.py
python scripts/run_parsers.py --force
python scripts/evaluate_tatqa.py
```

To run only one parser:

```bash
python scripts/run_parsers.py pymupdf4llm --force
python scripts/run_parsers.py pymupdf --force
```

Important outputs:

- `data/tatqa/dev/manifest.csv`: auditable context/PDF manifest
- `outputs/<parser>/*.json`: extracted text and tables
- `outputs/<parser>/runtime.csv`: per-context timings and status
- `results/metrics_by_parser.csv`: aggregate comparison
- `results/metrics_by_context.csv`: context-level metrics
- `results/manifest.csv`: manifest snapshot from the reported run

The renderer accepts `--limit N` for smoke tests. Parser outputs are reused
unless `--force` is supplied.

## Method limits

This is a controlled extraction test over PDFs rendered from TAT-QA's official
content. It measures how well each parser preserves that content and structure;
it does not measure OCR, scanned-document quality, or performance on the
unreleased original report pages. Use a document-image benchmark such as
TAT-DQA if original visual pages are required.
